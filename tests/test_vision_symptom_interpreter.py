"""
tests/test_vision_symptom_interpreter.py

Tests ai/rag/vision_symptom_interpreter.py's two-tier design: closed-list
matched_symptoms (safe to score) plus free-text other_observations
(informational only, never scored). What's genuinely testable here without
a real Groq API key: graceful degradation, the closed-list safety filter
(including against a deliberately misbehaving mock response), the
observations field being carried through untouched, and the image
resize/encode logic (pure PIL, no network needed).

NOT testable here, and explicitly not claimed to be: whether a real photo
gets sensible symptom detection or a genuinely useful observation from the
actual Groq vision model. That needs a real API key and real photos, which
only happens on a machine with network access.
"""

import base64
from io import BytesIO
from PIL import Image

import ai.rag.vision_symptom_interpreter as vsi
from ai.rag.vision_symptom_interpreter import (
    is_available, interpret_symptoms_from_image, _prepare_image_for_api,
)


def _tiny_jpeg_bytes() -> bytes:
    img = Image.new("RGB", (50, 50), (200, 50, 50))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class _FakeChoice:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeClient:
    def __init__(self, response_text):
        self.response_text = response_text
        self.chat = self
        self.completions = self

    def create(self, **kw):
        return _FakeResponse(self.response_text)


def test_is_available_returns_a_bool():
    assert isinstance(is_available(), bool)


def test_no_client_configured_returns_empty_result():
    vsi._client = None
    result = interpret_symptoms_from_image(_tiny_jpeg_bytes(), "eye", ["Ocular Redness"])
    assert result == {"matched_symptoms": [], "other_observations": ""}


def test_empty_known_symptoms_returns_empty_result_without_calling_anything():
    vsi._client = _FakeClient('{"matched_symptoms": ["should not matter"], "other_observations": ""}')
    result = interpret_symptoms_from_image(_tiny_jpeg_bytes(), "eye", [])
    assert result == {"matched_symptoms": [], "other_observations": ""}


def test_well_behaved_response_returns_matched_symptoms_and_observation():
    known = ["Ocular Redness", "Watery Eyes", "Swelling"]
    vsi._client = _FakeClient(
        '{"matched_symptoms": ["Ocular Redness", "Swelling"], '
        '"other_observations": "Slight yellowish discharge near the inner corner."}'
    )
    result = interpret_symptoms_from_image(_tiny_jpeg_bytes(), "eye", known)
    assert result["matched_symptoms"] == ["Ocular Redness", "Swelling"]
    assert result["other_observations"] == "Slight yellowish discharge near the inner corner."


def test_closed_list_filter_strips_invented_and_condition_name_entries():
    """The critical safety property for the SCORED field: even if the model
    tries to leak a condition name or invent a symptom outside the list,
    only genuinely valid entries survive in matched_symptoms."""
    known = ["Ocular Redness", "Watery Eyes", "Swelling"]
    vsi._client = _FakeClient(
        '{"matched_symptoms": ["Ocular Redness", "Conjunctivitis", "Some Invented Thing"], '
        '"other_observations": ""}'
    )
    result = interpret_symptoms_from_image(_tiny_jpeg_bytes(), "eye", known)
    assert result["matched_symptoms"] == ["Ocular Redness"]
    assert "Conjunctivitis" not in result["matched_symptoms"]


def test_other_observations_is_not_filtered_against_the_known_list():
    """Unlike matched_symptoms, other_observations is free text by design --
    it's the whole point of the two-tier split. It must be carried through
    untouched (aside from length capping), not filtered against the
    checklist."""
    known = ["Ocular Redness"]
    vsi._client = _FakeClient(
        '{"matched_symptoms": [], '
        '"other_observations": "A small raised bump not covered by the symptom list."}'
    )
    result = interpret_symptoms_from_image(_tiny_jpeg_bytes(), "eye", known)
    assert result["other_observations"] == "A small raised bump not covered by the symptom list."


def test_other_observations_is_length_capped():
    known = ["Ocular Redness"]
    long_text = "x" * 5000
    vsi._client = _FakeClient(f'{{"matched_symptoms": [], "other_observations": "{long_text}"}}')
    result = interpret_symptoms_from_image(_tiny_jpeg_bytes(), "eye", known)
    assert len(result["other_observations"]) <= vsi._MAX_OBSERVATION_CHARS


def test_markdown_fenced_response_is_parsed_correctly():
    known = ["Watery Eyes"]
    vsi._client = _FakeClient('```json\n{"matched_symptoms": ["Watery Eyes"], "other_observations": ""}\n```')
    result = interpret_symptoms_from_image(_tiny_jpeg_bytes(), "eye", known)
    assert result["matched_symptoms"] == ["Watery Eyes"]


def test_malformed_json_degrades_to_empty_result():
    vsi._client = _FakeClient("not valid json")
    result = interpret_symptoms_from_image(_tiny_jpeg_bytes(), "eye", ["Ocular Redness"])
    assert result == {"matched_symptoms": [], "other_observations": ""}


def test_non_object_json_degrades_to_empty_result():
    """A model that returns a bare JSON array (the old single-tier format,
    or just a mistake) instead of the expected object shape must not crash."""
    vsi._client = _FakeClient('["Ocular Redness"]')
    result = interpret_symptoms_from_image(_tiny_jpeg_bytes(), "eye", ["Ocular Redness"])
    assert result == {"matched_symptoms": [], "other_observations": ""}


def test_missing_keys_in_response_degrade_gracefully():
    """A response missing one of the two expected keys must not crash --
    each field defaults sensibly on its own."""
    vsi._client = _FakeClient('{"matched_symptoms": ["Ocular Redness"]}')
    result = interpret_symptoms_from_image(_tiny_jpeg_bytes(), "eye", ["Ocular Redness"])
    assert result["matched_symptoms"] == ["Ocular Redness"]
    assert result["other_observations"] == ""


def test_corrupt_image_degrades_to_empty_result_not_a_crash():
    vsi._client = _FakeClient('{"matched_symptoms": ["Ocular Redness"], "other_observations": ""}')
    result = interpret_symptoms_from_image(b"not a real image at all", "eye", ["Ocular Redness"])
    assert result == {"matched_symptoms": [], "other_observations": ""}


# ---------------------------------------------------------------------------
# Image resize/encode logic -- this genuinely runs (pure PIL, no network)
# ---------------------------------------------------------------------------

def test_large_image_resized_under_groq_base64_limit():
    """Groq's base64-encoded-image limit is 4MB. A large raw upload (our
    own limit is 10MB, which after base64 inflation could exceed Groq's
    limit) must be resized down comfortably under it."""
    large_img = Image.new("RGB", (3000, 2000), (100, 150, 200))
    buf = BytesIO()
    large_img.save(buf, format="JPEG", quality=95)
    large_bytes = buf.getvalue()

    b64 = _prepare_image_for_api(large_bytes)
    decoded_size = len(base64.b64decode(b64))
    assert decoded_size < 4 * 1024 * 1024


def test_resized_image_respects_max_dimension():
    large_img = Image.new("RGB", (3000, 2000), (100, 150, 200))
    buf = BytesIO()
    large_img.save(buf, format="JPEG")
    b64 = _prepare_image_for_api(buf.getvalue())
    resized = Image.open(BytesIO(base64.b64decode(b64)))
    assert max(resized.size) <= 1024


def test_small_image_still_produces_valid_base64():
    b64 = _prepare_image_for_api(_tiny_jpeg_bytes())
    decoded = base64.b64decode(b64)  # must not raise
    Image.open(BytesIO(decoded))  # must be a valid, openable image