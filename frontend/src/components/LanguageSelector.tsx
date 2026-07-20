// frontend/src/components/LanguageSelector.tsx
import React from 'react';
import { Globe } from 'lucide-react';
import { useLanguage } from '../i18n/LanguageContext';

/**
 * A small, persistent language switcher meant to sit in a consistent spot
 * across the whole app (landing page, wizard, chat) -- not locked inside
 * any one flow's consent screen. Changing it here updates the shared
 * LanguageContext, which every connected component reads from.
 */
export default function LanguageSelector({ className = '' }: { className?: string }) {
  const { language, setLanguage, languages, translating } = useLanguage();

  if (Object.keys(languages).length === 0) return null;

  return (
    <div className={`flex items-center gap-1.5 ${className}`}>
      <Globe size={13} className={translating ? 'text-emerald-400 animate-pulse' : 'text-slate-500'} />
      <select
        value={language}
        onChange={(e) => setLanguage(e.target.value)}
        aria-label="Select language"
        className="bg-slate-900/80 border border-slate-800 rounded-lg text-xs px-2 py-1 text-slate-300 focus:outline-none focus:border-emerald-600 cursor-pointer"
      >
        {(Object.entries(languages) as [string, { label: string; locale: string }][]).map(([code, meta]) => (
          <option key={code} value={code}>{meta.label}</option>
        ))}
      </select>
    </div>
  );
}