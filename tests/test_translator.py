"""
tests/test_translator.py

Tests ai/rag/translator.py. What's genuinely testable without a real LLM
call (this sandbox has no network access): the graceful-degradation
contract, passthrough behavior for English/unrecognized languages, and the
supported-language registry. Translation QUALITY on real non-English text
can only be verified on a machine with a working API key.
"""

from ai.rag.translator import (
    translate_to_english, translate_from_english,
    is_available, is_supported_language, SUPPORTED_LANGUAGES,
)


def test_is_available_returns_a_bool():
    assert isinstance(is_available(), bool)


def test_english_input_passes_through_unchanged_without_calling_anything():
    """No point translating English to English -- must short-circuit before
    ever touching the LLM client."""
    result = translate_to_english("my eye hurts", "en")
    assert result == "my eye hurts"


def test_english_target_passes_through_unchanged():
    result = translate_from_english("This looks like conjunctivitis", "en")
    assert result == "This looks like conjunctivitis"


def test_unrecognized_language_code_passes_through_safely():
    """A language code outside the curated SUPPORTED_LANGUAGES set (e.g. a
    typo, or a language this feature was never designed for) must not
    crash -- just pass the text through untranslated."""
    assert translate_to_english("some text", "xx") == "some text"
    assert translate_from_english("some text", "xx") == "some text"


def test_translation_degrades_to_original_text_without_a_client():
    """Core safety/UX contract: with no LLM client configured (or any
    translation failure), the ORIGINAL text must come back unchanged --
    never an exception, never an empty string, never a crash of the whole
    screening flow over a translation hiccup."""
    hindi_text = "mera aankh dukh raha hai"
    result = translate_to_english(hindi_text, "hi")
    assert result == hindi_text


def test_empty_and_whitespace_text_handled_without_crashing():
    assert translate_to_english("", "hi") == ""
    assert translate_to_english("   ", "hi") == "   "
    assert translate_from_english("", "ta") == ""


def test_every_supported_language_has_a_label_and_locale():
    """Guards against a silent gap: every entry in SUPPORTED_LANGUAGES must
    have both a display label (for the frontend dropdown) and a real BCP-47
    locale code (for SpeechRecognition/SpeechSynthesis)."""
    for code, meta in SUPPORTED_LANGUAGES.items():
        assert "label" in meta and meta["label"]
        assert "locale" in meta and meta["locale"]
        assert "-" in meta["locale"], f"{code}'s locale should be a real BCP-47 tag like 'hi-IN'"


def test_english_is_always_a_supported_language():
    assert is_supported_language("en")


def test_is_supported_language_rejects_unknown_codes():
    assert not is_supported_language("fr")
    assert not is_supported_language("")
    assert not is_supported_language("EN")  # case-sensitive, must not silently accept