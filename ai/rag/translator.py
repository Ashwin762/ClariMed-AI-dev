"""
ai/rag/translator.py

Translation layer for multi-language support. Two directions:
  - translate_to_english()   -- speech/text input, before it ever reaches
                                  symptom interpretation
  - translate_from_english() -- guidance output, before it's shown/spoken
                                  back to the patient

WHY THIS EXISTS, AND WHY IT SITS EXACTLY WHERE IT DOES:
Every closed-list-safe function in this codebase (interpret_symptoms(),
route_to_body_part(), interpret_symptoms_from_image()'s text matching)
works against ENGLISH keyword lists -- including, critically, the OFFLINE
fallback paths, which do simple English word-overlap matching with no
language awareness at all. If a patient speaks in Hindi and that Hindi
text were passed directly into those functions, the offline fallback
would silently match nothing (not fail loudly -- just quietly find zero
symptoms), and even the LLM-based path's multilingual understanding is
unverified rather than a designed, tested capability.

The fix is a translation boundary, not a rewrite of the symptom-matching
system: speech input gets translated to English BEFORE it reaches
interpret_symptoms() etc., so every existing closed-list guarantee,
offline fallback, and safety test continues to operate on English text
exactly as already proven -- multi-language support is additive at the
edges, not a change to the safety-critical core.

SCOPE NOTE: like vision_symptom_interpreter.py, this deliberately has NO
offline fallback for the actual translation step itself -- there's no
meaningful heuristic substitute for "translate this sentence." If no LLM
key is configured or translation fails, both functions return the
ORIGINAL text unchanged (never raise, never block the flow) -- for
translate_to_english(), that means an untranslated non-English string
would reach symptom interpretation and likely match nothing via the
offline fallback, same honest "not enough evidence" outcome as any other
input the system can't confidently interpret, not a crash or a wrong
answer.

HONEST LIMITATION: written using the same hardened LLM client
(ai/rag/llm_client.py, with its Day-1 timeout/retry/prompt-injection
guarding) already proven elsewhere in this codebase, but translation
QUALITY on real non-English input can only be verified on a machine with
a working API key -- this sandbox has no network access to test it.
"""

import logging
from typing import Optional

from ai.rag.llm_client import get_llm_client, PROMPT_INJECTION_GUARD, wrap_patient_text

logger = logging.getLogger("clarimed.translator")

_client = get_llm_client()

# Languages this feature is designed and labeled for. Not an exhaustive list
# of every language the underlying LLM or the browser's Web Speech API could
# technically handle -- a deliberately curated set matching the product's
# actual user base (India), each with a real BCP-47 locale code for the
# frontend's SpeechRecognition/SpeechSynthesis calls.
SUPPORTED_LANGUAGES = {
    "en": {"label": "English", "locale": "en-IN"},
    "hi": {"label": "Hindi", "locale": "hi-IN"},
    "kn": {"label": "Kannada", "locale": "kn-IN"},
    "ta": {"label": "Tamil", "locale": "ta-IN"},
    "te": {"label": "Telugu", "locale": "te-IN"},
    "bn": {"label": "Bengali", "locale": "bn-IN"},
    "mr": {"label": "Marathi", "locale": "mr-IN"},
    "gu": {"label": "Gujarati", "locale": "gu-IN"},
    "ml": {"label": "Malayalam", "locale": "ml-IN"},
}

_LANGUAGE_NAMES = {code: v["label"] for code, v in SUPPORTED_LANGUAGES.items()}

_TRANSLATE_TO_EN_SYSTEM_PROMPT = (
    "You translate patient-provided medical text into clear, plain English. "
    "You are NOT diagnosing or interpreting anything -- only translating "
    "faithfully, preserving the original meaning and any medical detail "
    "exactly. Respond with ONLY the English translation, nothing else -- no "
    "preamble, no explanation, no quotation marks around it. "
    f"{PROMPT_INJECTION_GUARD}"
)

_TRANSLATE_FROM_EN_SYSTEM_PROMPT = (
    "You translate English medical guidance text into the target language, "
    "keeping it warm, clear, and easy to understand for a patient -- not "
    "overly formal or literal. Preserve all medical detail and any urgency "
    "in the original text exactly. Respond with ONLY the translation, "
    "nothing else -- no preamble, no explanation. "
    f"{PROMPT_INJECTION_GUARD}"
)


def is_available() -> bool:
    return _client is not None


def is_supported_language(code: str) -> bool:
    return code in SUPPORTED_LANGUAGES


def translate_to_english(text: str, source_language: str) -> str:
    """
    Translates patient-provided text (typically a speech-to-text transcript)
    into English, before it reaches interpret_symptoms()/route_to_body_part().
    If source_language is already 'en' or unrecognized, or the client isn't
    available, or translation fails for any reason, returns the ORIGINAL
    text unchanged -- never raises, never blocks the screening flow.
    """
    if not text or not text.strip():
        return text
    if source_language == "en" or source_language not in SUPPORTED_LANGUAGES:
        return text
    if _client is None:
        return text

    try:
        lang_name = _LANGUAGE_NAMES[source_language]
        response = _client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": _TRANSLATE_TO_EN_SYSTEM_PROMPT},
                {"role": "user", "content": wrap_patient_text(f"Text in {lang_name}", text)},
            ],
            temperature=0.0,
        )
        translated = response.choices[0].message.content.strip()
        return translated if translated else text
    except Exception as e:
        logger.warning("Translation to English failed (from %s), using original text: %s", source_language, e)
        return text


def translate_from_english(text: str, target_language: str) -> str:
    """
    Translates English guidance text into the patient's selected language,
    before it's displayed or spoken aloud. Same graceful-degradation
    contract as translate_to_english(): any failure returns the original
    English text unchanged, never raises.
    """
    if not text or not text.strip():
        return text
    if target_language == "en" or target_language not in SUPPORTED_LANGUAGES:
        return text
    if _client is None:
        return text

    try:
        lang_name = _LANGUAGE_NAMES[target_language]
        response = _client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": _TRANSLATE_FROM_EN_SYSTEM_PROMPT},
                {"role": "user", "content": wrap_patient_text(f"Translate this English text to {lang_name}", text)},
            ],
            temperature=0.0,
        )
        translated = response.choices[0].message.content.strip()
        return translated if translated else text
    except Exception as e:
        logger.warning("Translation from English failed (to %s), using original text: %s", target_language, e)
        return text