// frontend/src/i18n/strings.ts
//
// Central registry of translatable UI labels. The LanguageContext fetches
// translations for this WHOLE dictionary in one batch call per language
// switch (see POST /api/translate-ui-strings), rather than each component
// requesting its own strings piecemeal -- one network round-trip, cached
// client-side per language.
//
// SCOPE: covers the app's functional UI (buttons, headings, labels) across
// the landing page's action buttons, the guided wizard's main screens, and
// chat. Deep marketing copy on the landing page (the big headline/
// description) is deliberately left in English for now -- the same pattern
// many real products use (Google's product UI is localized; its long-form
// marketing pages often aren't as thoroughly translated). Can always be
// extended by adding more keys here.

export const UI_STRINGS = {
  // Hero / landing
  hero_cta_wizard: 'Start a guided screening',
  hero_cta_chat: 'Or just chat with ClariMed AI',
  hero_offline_note: 'Screening works offline',

  // Wizard — start step
  wizard_start_heading: "What's bothering you today?",
  wizard_start_subheading: "Describe it in your own words — like you'd tell a doctor. We'll take it from there.",
  wizard_start_placeholder: 'e.g. "my eyes have been red and itchy for two days"',
  wizard_start_photo_cta: "Not sure how to describe it? Upload a photo and watch the AI find it",
  wizard_start_button: 'Start',

  // Wizard — body part step
  wizard_bodypart_heading: "Where's the problem?",
  wizard_bodypart_subheading: 'Choose the area your symptoms relate to.',

  // Wizard — symptoms step
  wizard_symptoms_heading: 'Select Symptoms',
  wizard_symptoms_subheading: 'Tap all that apply.',
  wizard_symptoms_photo_cta: "Have a photo? Upload it to help pre-fill your symptoms (optional)",

  // Wizard — shared navigation
  wizard_continue_button: 'Continue',
  wizard_run_screening_button: 'Run Screening',
  wizard_back_button: 'Previous Step',

  // Wizard — review/results
  wizard_results_heading: 'Your Screening Results',
  wizard_disclaimer: 'AI-assisted preliminary screening only. Not a medical diagnosis.',

  // Chat
  chat_welcome: "Hi, I'm ClariMed AI. What's bothering you today? Describe it however feels natural — you can share a photo too, whenever you're ready.",
  chat_input_placeholder: 'Type your message...',
  chat_listening_placeholder: 'Listening...',
  chat_start_new: 'Start a new conversation',
  chat_exit: 'Exit chat',
  chat_before_we_start: 'Before we start',
  chat_start_chatting_button: 'Start chatting',
  chat_consent_ready: "I understand and I'm ready to start.",
} as const;

export type UIStringKey = keyof typeof UI_STRINGS;