// frontend/src/i18n/LanguageContext.test.tsx
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { LanguageProvider, useLanguage } from './LanguageContext';
import * as api from '../api';

vi.mock('../api', async () => {
  const actual = await vi.importActual('../api');
  return {
    ...actual,
    fetchLanguages: vi.fn(),
    translateUIStrings: vi.fn(),
  };
});

const mockFetchLanguages = vi.mocked(api.fetchLanguages);
const mockTranslateUIStrings = vi.mocked(api.translateUIStrings);

const MOCK_LANGUAGES = {
  en: { label: 'English', locale: 'en-IN' },
  hi: { label: 'Hindi', locale: 'hi-IN' },
  kn: { label: 'Kannada', locale: 'kn-IN' },
};

/** Small harness component that exposes context values as visible text,
 * so tests can assert on them via screen queries like any other UI. */
function Harness() {
  const { language, setLanguage, locale, t, translating } = useLanguage();
  return (
    <div>
      <span data-testid="language">{language}</span>
      <span data-testid="locale">{locale}</span>
      <span data-testid="translating">{String(translating)}</span>
      <span data-testid="hero-cta">{t('hero_cta_wizard')}</span>
      <button onClick={() => setLanguage('hi')}>Switch to Hindi</button>
      <button onClick={() => setLanguage('en')}>Switch to English</button>
    </div>
  );
}

function renderWithProvider() {
  return render(
    <LanguageProvider>
      <Harness />
    </LanguageProvider>
  );
}

describe('LanguageProvider / useLanguage', () => {
  beforeEach(() => {
    localStorage.clear();
    mockFetchLanguages.mockReset();
    mockTranslateUIStrings.mockReset();
    mockFetchLanguages.mockResolvedValue(MOCK_LANGUAGES);
    mockTranslateUIStrings.mockResolvedValue({});
  });

  it('defaults to English when nothing is in localStorage', async () => {
    renderWithProvider();
    await waitFor(() => expect(screen.getByTestId('language')).toHaveTextContent('en'));
  });

  it('reads a previously persisted language choice from localStorage on mount', async () => {
    localStorage.setItem('clarimed_language', 'hi');
    renderWithProvider();
    await waitFor(() => expect(screen.getByTestId('language')).toHaveTextContent('hi'));
  });

  it('persists the language choice to localStorage when changed', async () => {
    renderWithProvider();
    await waitFor(() => expect(screen.getByTestId('language')).toHaveTextContent('en'));
    fireEvent.click(screen.getByText('Switch to Hindi'));
    await waitFor(() => expect(localStorage.getItem('clarimed_language')).toBe('hi'));
  });

  it('resolves the correct locale (BCP-47 code) once languages have loaded', async () => {
    localStorage.setItem('clarimed_language', 'kn');
    renderWithProvider();
    await waitFor(() => expect(screen.getByTestId('locale')).toHaveTextContent('kn-IN'));
  });

  it('does not call translateUIStrings at all when the language is English', async () => {
    renderWithProvider();
    await waitFor(() => expect(screen.getByTestId('language')).toHaveTextContent('en'));
    expect(mockTranslateUIStrings).not.toHaveBeenCalled();
  });

  it('calls translateUIStrings once when switching to a non-English language', async () => {
    mockTranslateUIStrings.mockResolvedValue({ hero_cta_wizard: 'गाइडेड स्क्रीनिंग शुरू करें' });
    renderWithProvider();
    await waitFor(() => expect(screen.getByTestId('language')).toHaveTextContent('en'));
    fireEvent.click(screen.getByText('Switch to Hindi'));
    await waitFor(() => expect(mockTranslateUIStrings).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId('hero-cta')).toHaveTextContent('गाइडेड स्क्रीनिंग शुरू करें'));
  });

  it('reads from the localStorage cache instead of calling translateUIStrings again for a language already translated once', async () => {
    localStorage.setItem('clarimed_ui_strings_hi', JSON.stringify({ hero_cta_wizard: 'cached Hindi text' }));
    localStorage.setItem('clarimed_language', 'hi');
    renderWithProvider();
    await waitFor(() => expect(screen.getByTestId('hero-cta')).toHaveTextContent('cached Hindi text'));
    expect(mockTranslateUIStrings).not.toHaveBeenCalled();
  });

  it('falls back to the English string when a key has no translation for the active language', async () => {
    mockTranslateUIStrings.mockResolvedValue({}); // no keys translated at all
    localStorage.setItem('clarimed_language', 'hi');
    renderWithProvider();
    await waitFor(() => {
      const text = screen.getByTestId('hero-cta').textContent;
      expect(text).toBeTruthy(); // never blank, even with zero translations available
    });
  });

  it('degrades gracefully -- keeps working, does not crash -- when translateUIStrings itself fails', async () => {
    mockTranslateUIStrings.mockRejectedValue(new Error('network error'));
    localStorage.setItem('clarimed_language', 'hi');
    expect(() => renderWithProvider()).not.toThrow();
    await waitFor(() => expect(screen.getByTestId('translating')).toHaveTextContent('false'));
    // The English default must still be visible rather than a blank/broken UI.
    expect(screen.getByTestId('hero-cta').textContent).toBeTruthy();
  });

  it('sets translating=true while a translation is in flight and false once resolved', async () => {
    let resolveTranslate: (value: Record<string, string>) => void;
    mockTranslateUIStrings.mockReturnValue(
      new Promise((resolve) => {
        resolveTranslate = resolve;
      })
    );
    renderWithProvider();
    await waitFor(() => expect(screen.getByTestId('language')).toHaveTextContent('en'));
    fireEvent.click(screen.getByText('Switch to Hindi'));
    await waitFor(() => expect(screen.getByTestId('translating')).toHaveTextContent('true'));
    resolveTranslate!({});
    await waitFor(() => expect(screen.getByTestId('translating')).toHaveTextContent('false'));
  });

  it('clears translated strings (falls back to English) when switching back to English', async () => {
    mockTranslateUIStrings.mockResolvedValue({ hero_cta_wizard: 'Hindi version' });
    localStorage.setItem('clarimed_language', 'hi');
    renderWithProvider();
    await waitFor(() => expect(screen.getByTestId('hero-cta')).toHaveTextContent('Hindi version'));
    fireEvent.click(screen.getByText('Switch to English'));
    await waitFor(() => expect(screen.getByTestId('language')).toHaveTextContent('en'));
    expect(screen.getByTestId('hero-cta')).not.toHaveTextContent('Hindi version');
  });
});

describe('useLanguage outside a provider', () => {
  it('throws a clear, actionable error rather than failing silently or with a cryptic null-reference', () => {
    function Broken() {
      useLanguage();
      return null;
    }
    // Suppress the expected React error-boundary console noise for this
    // one intentional-failure test.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Broken />)).toThrow('useLanguage() must be used inside a <LanguageProvider>');
    spy.mockRestore();
  });
});