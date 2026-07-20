// frontend/src/speech.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  isSpeechRecognitionSupported, isSpeechSynthesisSupported,
  startListening, hasVoiceFor, speak, stopSpeaking,
} from './speech';

function mockVoice(lang: string): SpeechSynthesisVoice {
  return { lang, name: lang, default: false, localService: true, voiceURI: lang } as SpeechSynthesisVoice;
}

describe('isSpeechRecognitionSupported / isSpeechSynthesisSupported', () => {
  it('reports supported when the setup mocks are in place', () => {
    expect(isSpeechRecognitionSupported()).toBe(true);
    expect(isSpeechSynthesisSupported()).toBe(true);
  });
});

describe('startListening', () => {
  it('calls onResult with the recognized text and then onEnd, simulating a real recognition result', () => {
    let capturedInstance: any = null;
    class SpyRecognition {
      lang = '';
      onresult: any = null;
      onerror: any = null;
      onend: any = null;
      start = vi.fn();
      constructor() {
        capturedInstance = this;
      }
    }
    const original = (window as any).SpeechRecognition;
    (window as any).SpeechRecognition = SpyRecognition;

    const onResult = vi.fn();
    const onEnd = vi.fn();
    startListening('hi-IN', onResult, onEnd);

    // Simulate the browser firing a real result event, matching the actual
    // SpeechRecognitionEvent shape (results[0][0].transcript).
    capturedInstance.onresult({ results: [[{ transcript: 'मुझे बुखार है' }]] });
    expect(onResult).toHaveBeenCalledWith('मुझे बुखार है');

    capturedInstance.onend();
    expect(onEnd).toHaveBeenCalled();

    (window as any).SpeechRecognition = original;
  });

  it('reports an honest unsupported message and still calls onEnd when no recognition API exists', () => {
    const original = (window as any).SpeechRecognition;
    const originalWebkit = (window as any).webkitSpeechRecognition;
    // @ts-ignore
    delete window.SpeechRecognition;
    // @ts-ignore
    delete window.webkitSpeechRecognition;

    const onResult = vi.fn();
    const onEnd = vi.fn();
    const onError = vi.fn();
    startListening('hi-IN', onResult, onEnd, onError);

    expect(onError).toHaveBeenCalledWith(expect.stringContaining('not supported'));
    expect(onEnd).toHaveBeenCalled();
    expect(onResult).not.toHaveBeenCalled();

    (window as any).SpeechRecognition = original;
    (window as any).webkitSpeechRecognition = originalWebkit;
  });

  it('sets the recognition language to the requested locale', () => {
    let capturedInstance: any = null;
    class SpyRecognition {
      lang = '';
      onresult: any = null;
      onerror: any = null;
      onend: any = null;
      constructor() {
        capturedInstance = this;
      }
      start = vi.fn();
    }
    const original = (window as any).SpeechRecognition;
    (window as any).SpeechRecognition = SpyRecognition;

    startListening('ta-IN', vi.fn(), vi.fn());
    expect(capturedInstance.lang).toBe('ta-IN');
    expect(capturedInstance.start).toHaveBeenCalled();

    (window as any).SpeechRecognition = original;
  });
});

describe('hasVoiceFor', () => {
  beforeEach(() => {
    vi.mocked(window.speechSynthesis.getVoices).mockReset();
  });

  it('returns true when a matching voice is installed', async () => {
    vi.mocked(window.speechSynthesis.getVoices).mockReturnValue([
      mockVoice('en-US'), mockVoice('hi-IN'),
    ]);
    expect(await hasVoiceFor('hi-IN')).toBe(true);
  });

  it('returns false when no voice matches the requested language at all', async () => {
    vi.mocked(window.speechSynthesis.getVoices).mockReturnValue([mockVoice('en-US')]);
    expect(await hasVoiceFor('kn-IN')).toBe(false);
  });

  it('matches on language prefix, not exact locale string', async () => {
    // A voice registered as generic "hi" should still count for "hi-IN".
    vi.mocked(window.speechSynthesis.getVoices).mockReturnValue([mockVoice('hi')]);
    expect(await hasVoiceFor('hi-IN')).toBe(true);
  });
});

describe('speak', () => {
  beforeEach(() => {
    vi.mocked(window.speechSynthesis.getVoices).mockReset();
    vi.mocked(window.speechSynthesis.speak).mockReset();
  });

  it('returns "unsupported" for empty text without touching speechSynthesis at all', async () => {
    const status = await speak('', 'en-IN');
    expect(status).toBe('unsupported');
    expect(window.speechSynthesis.speak).not.toHaveBeenCalled();
  });

  it('returns "no_voice" and never calls speak() when no matching voice is installed -- the exact bug this was built to catch', async () => {
    vi.mocked(window.speechSynthesis.getVoices).mockReturnValue([mockVoice('en-US')]);
    const status = await speak('ನಮಸ್ಕಾರ', 'kn-IN');
    expect(status).toBe('no_voice');
    expect(window.speechSynthesis.speak).not.toHaveBeenCalled();
  });

  it('returns "spoken" and actually calls speak() when a matching voice exists', async () => {
    vi.mocked(window.speechSynthesis.getVoices).mockReturnValue([mockVoice('en-US')]);
    const status = await speak('Hello', 'en-US');
    expect(status).toBe('spoken');
    expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(1);
  });

  it('cancels any in-progress speech before starting new speech', async () => {
    vi.mocked(window.speechSynthesis.getVoices).mockReturnValue([mockVoice('en-US')]);
    await speak('Hello', 'en-US');
    expect(window.speechSynthesis.cancel).toHaveBeenCalled();
  });
});

describe('stopSpeaking', () => {
  it('calls speechSynthesis.cancel()', () => {
    vi.mocked(window.speechSynthesis.cancel).mockClear();
    stopSpeaking();
    expect(window.speechSynthesis.cancel).toHaveBeenCalled();
  });
});