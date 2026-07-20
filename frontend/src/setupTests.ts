// frontend/src/setupTests.ts
import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
  cleanup();
});

Object.defineProperty(window, 'speechSynthesis', {
  writable: true,
  value: {
    getVoices: vi.fn(() => []),
    speak: vi.fn(),
    cancel: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  },
});

class MockSpeechRecognition {
  lang = '';
  onresult: ((event: any) => void) | null = null;
  onerror: ((event: any) => void) | null = null;
  onend: (() => void) | null = null;
  start = vi.fn();
  stop = vi.fn();
}
// @ts-ignore
window.SpeechRecognition = MockSpeechRecognition;
// @ts-ignore
window.webkitSpeechRecognition = MockSpeechRecognition;

class MockSpeechSynthesisUtterance {
  text: string;
  lang = '';
  rate = 1;
  constructor(text: string) {
    this.text = text;
  }
}
// @ts-ignore
window.SpeechSynthesisUtterance = MockSpeechSynthesisUtterance;

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// REAL BUG FOUND IN TESTING: jsdom doesn't implement a real
// requestAnimationFrame with real frame timing -- components that animate
// a value across multiple rAF calls (like ReasoningPanel's AnimatedNumber,
// which computes progress as (now - start) / duration) got garbage,
// even-negative intermediate values because jsdom's rAF timing doesn't
// behave like a real browser's. This mock resolves any rAF-driven
// animation to its end state on the FIRST call instead of trying to
// simulate real frame-by-frame timing, which isn't something a unit test
// environment can do reliably anyway -- what matters for a test is the
// settled final value, not real animation frames.
window.requestAnimationFrame = ((cb: FrameRequestCallback) => {
  return setTimeout(() => cb(performance.now() + 10000), 0) as unknown as number;
}) as typeof requestAnimationFrame;
window.cancelAnimationFrame = ((id: number) => clearTimeout(id)) as typeof cancelAnimationFrame;