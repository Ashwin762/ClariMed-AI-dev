// frontend/src/i18n/LanguageContext.tsx
import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { fetchLanguages, translateUIStrings, type SupportedLanguage } from '../api';
import { UI_STRINGS, type UIStringKey } from './strings';

const STORAGE_KEY_LANG = 'clarimed_language';
const STORAGE_KEY_CACHE_PREFIX = 'clarimed_ui_strings_';

interface LanguageContextValue {
  language: string;
  setLanguage: (code: string) => void;
  languages: Record<string, SupportedLanguage>;
  locale: string; // BCP-47 code for the current language, for STT/TTS
  t: (key: UIStringKey) => string;
  translating: boolean;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [languages, setLanguages] = useState<Record<string, SupportedLanguage>>({});
  const [language, setLanguageState] = useState<string>(
    () => (typeof window !== 'undefined' && localStorage.getItem(STORAGE_KEY_LANG)) || 'en'
  );
  const [translated, setTranslated] = useState<Record<string, string>>({});
  const [translating, setTranslating] = useState(false);

  useEffect(() => {
    fetchLanguages().then(setLanguages).catch(() => {});
  }, []);

  const loadTranslations = useCallback(async (code: string) => {
    if (code === 'en') {
      setTranslated({});
      return;
    }
    // Cached from a previous visit/session -- avoid re-translating the
    // whole dictionary every time someone picks the same language again.
    const cached = typeof window !== 'undefined' ? localStorage.getItem(STORAGE_KEY_CACHE_PREFIX + code) : null;
    if (cached) {
      try {
        setTranslated(JSON.parse(cached));
        return;
      } catch {
        // fall through to a fresh fetch if the cached JSON is somehow corrupt
      }
    }
    setTranslating(true);
    try {
      const result = await translateUIStrings(UI_STRINGS as Record<string, string>, code);
      setTranslated(result);
      if (typeof window !== 'undefined') {
        localStorage.setItem(STORAGE_KEY_CACHE_PREFIX + code, JSON.stringify(result));
      }
    } catch {
      // Graceful degradation: keep whatever was there before (likely
      // English fallback via t()) rather than showing a broken UI.
    } finally {
      setTranslating(false);
    }
  }, []);

  useEffect(() => {
    loadTranslations(language);
  }, [language, loadTranslations]);

  const setLanguage = (code: string) => {
    setLanguageState(code);
    if (typeof window !== 'undefined') localStorage.setItem(STORAGE_KEY_LANG, code);
  };

  const t = (key: UIStringKey): string => translated[key] || UI_STRINGS[key];

  const locale = languages[language]?.locale || 'en-IN';

  return (
    <LanguageContext.Provider value={{ language, setLanguage, languages, locale, t, translating }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error('useLanguage() must be used inside a <LanguageProvider>');
  return ctx;
}