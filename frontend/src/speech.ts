// frontend/src/speech.ts
//
// Thin wrappers around the browser's native Web Speech API
// (SpeechRecognition for speech-to-text, SpeechSynthesis for text-to-speech).
// Deliberately browser-native rather than a cloud API: free, zero new
// backend dependency, and Chrome already supports every language in our
// SUPPORTED_LANGUAGES set out of the box.
//
// HONEST LIMITATION: browser support varies. Chrome/Edge support both APIs
// well; Safari and Firefox are patchier, especially for non-English
// SpeechRecognition. Every function here fails gracefully (returns false /
// calls an error callback) rather than throwing, so a browser without
// support just quietly falls back to typing instead of breaking anything.

export function isSpeechRecognitionSupported(): boolean {
  // @ts-ignore
  return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
}

export function isSpeechSynthesisSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

/**
 * Starts one speech-to-text recognition session. Calls onResult once with
 * the recognized text, then onEnd regardless of success/failure/cancellation
 * (mirroring how a caller would want to reset a "listening..." UI state
 * either way).
 */
export function startListening(
  locale: string,
  onResult: (text: string) => void,
  onEnd: () => void,
  onError?: (message: string) => void
): void {
  // @ts-ignore
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    onError?.('Voice input is not supported in this browser. Try Chrome.');
    onEnd();
    return;
  }
  const recognition = new SpeechRecognition();
  recognition.lang = locale;
  recognition.onresult = (event: any) => {
    const text = event.results?.[0]?.[0]?.transcript;
    if (text) onResult(text);
  };
  recognition.onerror = (event: any) => {
    onError?.(event?.error ? `Voice input error: ${event.error}` : 'Voice input failed.');
  };
  recognition.onend = () => onEnd();
  recognition.start();
}

let _voicesCache: SpeechSynthesisVoice[] | null = null;

function getVoices(): Promise<SpeechSynthesisVoice[]> {
  return new Promise((resolve) => {
    if (!isSpeechSynthesisSupported()) return resolve([]);
    const existing = window.speechSynthesis.getVoices();
    if (existing.length > 0) {
      _voicesCache = existing;
      return resolve(existing);
    }
    // Voices load asynchronously in some browsers (notably Chrome on first
    // page load) -- getVoices() can return an empty array the first time,
    // even though voices genuinely are available a moment later.
    const handler = () => {
      const voices = window.speechSynthesis.getVoices();
      _voicesCache = voices;
      window.speechSynthesis.removeEventListener('voiceschanged', handler);
      resolve(voices);
    };
    window.speechSynthesis.addEventListener('voiceschanged', handler);
    // Fallback in case the event never fires on this browser.
    setTimeout(() => resolve(_voicesCache || []), 1000);
  });
}

/**
 * Checks whether ANY installed voice can plausibly speak the given locale.
 * A real, common failure mode: Windows/Chrome often has no voice installed
 * at all for less common language codes (many Indian languages beyond
 * Hindi), so speechSynthesis.speak() silently produces no audio -- no
 * error, nothing -- which looks exactly like "broken" with no explanation.
 * This lets the caller detect that in advance and say so honestly.
 */
export async function hasVoiceFor(locale: string): Promise<boolean> {
  const voices = await getVoices();
  const langPrefix = locale.split('-')[0].toLowerCase();
  return voices.some((v) => v.lang.toLowerCase().startsWith(langPrefix));
}

/**
 * Speaks text aloud in the given locale. Cancels any currently-speaking
 * utterance first, so rapid taps on a "listen" button don't overlap.
 * Returns a status the caller can use to show an honest message instead of
 * silent failure when no matching voice is installed on this device.
 */
export async function speak(text: string, locale: string): Promise<'spoken' | 'no_voice' | 'unsupported'> {
  if (!isSpeechSynthesisSupported() || !text) return 'unsupported';
  const available = await hasVoiceFor(locale);
  if (!available) return 'no_voice';
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = locale;
  utterance.rate = 0.95; // very slightly slower than default -- easier to follow for medical guidance
  window.speechSynthesis.speak(utterance);
  return 'spoken';
}

export function stopSpeaking(): void {
  if (isSpeechSynthesisSupported()) window.speechSynthesis.cancel();
}