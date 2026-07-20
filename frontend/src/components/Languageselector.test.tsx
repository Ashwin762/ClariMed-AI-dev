// frontend/src/components/LanguageSelector.test.tsx
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import LanguageSelector from './LanguageSelector';
import * as LanguageContextModule from '../i18n/LanguageContext';

vi.mock('../i18n/LanguageContext', () => ({
  useLanguage: vi.fn(),
}));

const mockUseLanguage = vi.mocked(LanguageContextModule.useLanguage);

describe('LanguageSelector', () => {
  beforeEach(() => {
    mockUseLanguage.mockReset();
  });

  it('renders nothing while the language list is still empty (e.g. before the API call resolves)', () => {
    mockUseLanguage.mockReturnValue({
      language: 'en', setLanguage: vi.fn(), languages: {}, translating: false,
    } as any);
    const { container } = render(<LanguageSelector />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders an option for every supported language once loaded', () => {
    mockUseLanguage.mockReturnValue({
      language: 'en',
      setLanguage: vi.fn(),
      languages: {
        en: { label: 'English', locale: 'en-IN' },
        hi: { label: 'Hindi', locale: 'hi-IN' },
        kn: { label: 'Kannada', locale: 'kn-IN' },
      },
      translating: false,
    } as any);
    render(<LanguageSelector />);
    expect(screen.getByRole('option', { name: 'English' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Hindi' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Kannada' })).toBeInTheDocument();
  });

  it('shows the currently selected language as the select value', () => {
    mockUseLanguage.mockReturnValue({
      language: 'hi',
      setLanguage: vi.fn(),
      languages: {
        en: { label: 'English', locale: 'en-IN' },
        hi: { label: 'Hindi', locale: 'hi-IN' },
      },
      translating: false,
    } as any);
    render(<LanguageSelector />);
    expect(screen.getByRole('combobox')).toHaveValue('hi');
  });

  it('calls setLanguage with the new code when a different language is picked', () => {
    const setLanguage = vi.fn();
    mockUseLanguage.mockReturnValue({
      language: 'en',
      setLanguage,
      languages: {
        en: { label: 'English', locale: 'en-IN' },
        kn: { label: 'Kannada', locale: 'kn-IN' },
      },
      translating: false,
    } as any);
    render(<LanguageSelector />);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'kn' } });
    expect(setLanguage).toHaveBeenCalledWith('kn');
  });

  it('never crashes regardless of the translating flag', () => {
    mockUseLanguage.mockReturnValue({
      language: 'en',
      setLanguage: vi.fn(),
      languages: { en: { label: 'English', locale: 'en-IN' } },
      translating: true,
    } as any);
    expect(() => render(<LanguageSelector />)).not.toThrow();
  });
});