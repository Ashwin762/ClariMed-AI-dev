# Frontend testing

## Setup
Vitest + React Testing Library, chosen as the standard modern pairing for
Vite + React 19 projects. Configured directly inside `vite.config.ts` (no
separate config file) and `src/setupTests.ts` (jest-dom matchers + mocks for
Web Speech APIs, which jsdom doesn't implement at all).

```bash
npm install       # picks up the new devDependencies
npm test          # runs once, for CI
npm run test:watch  # watch mode, for local development
```

## What's covered right now, honestly

This is a **starting point**, not full coverage of the app — the backend has
~158 tests built up carefully across the whole project; the frontend had
zero before this. Covered so far:

- `speech.ts` — full coverage of the actual logic: recognition start/error/
  result handling, and the voice-availability detection that was added
  after a real bug (Kannada TTS silently producing no audio because no
  voice was installed — this is now caught and reported honestly instead
  of failing silently).
- `ReasoningPanel.tsx` — the "show its work" component. Covers the
  percentage math display, the photo-not-relevant honest fallback text,
  matched-keyword rendering, and the ranking-reliability messaging.
- `LanguageSelector.tsx` — renders correctly empty/populated, reflects the
  active language, and calls through to `setLanguage` correctly.
- `LanguageContext.tsx` — the real provider logic: localStorage persistence
  for the language choice, the translation-caching behavior (so a language
  already translated once doesn't re-call the LLM translation endpoint),
  graceful degradation when translation fails, and the English-fallback
  behavior in `t()`.

## What's NOT covered yet

The biggest, most complex components — `Wizard.tsx`, `Chat.tsx`,
`DoctorPortal.tsx` — don't have test coverage yet. They're large, and
properly testing them needs more mocking infrastructure (the `api.ts`
network layer, geolocation, file uploads) than was worth building in this
first pass. Given real runway now, they're the natural next target —
particularly the consent gates (must never allow proceeding without
consent) and the chat orchestration state machine on the frontend side,
since those are the highest-stakes pieces of UI logic in the app.

## An honest note on verification

Every test here was written carefully and reasoned through, but this
sandbox has no network access to actually run `npm install` or `npm test`
-- unlike the backend's pytest suite, which has been run and confirmed
passing after every single change all session, these have not been
executed. Run `npm test` as the first thing after applying these files,
before trusting the count.