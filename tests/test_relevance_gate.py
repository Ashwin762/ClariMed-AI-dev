"""
tests/test_relevance_gate.py

Tests the vision-LLM-based photo relevance/guessing module (rewritten from
an earlier CLIP-based version -- see the module docstring in
ai/vision/relevance_gate.py for why). Two layers of testing:

1. Graceful degradation -- works whether or not an LLM client is
   configured, the property that matters most structurally, since this
   feature must never be capable of breaking the app.

2. DECISION LOGIC, verified with mocked model ratings (bypassing the real
   API call, which isn't reachable from this sandbox) -- this is how the
   original bugs were caught and fixed, and remains the way to prove this
   version still gets them right, now with a different underlying
   mechanism (0-100 independent ratings per body part, not a softmax that
   has to sum to 100%).

The full numeric behavior on REAL photos still can only be verified on a
machine with a working API key -- that remains true after this rewrite,
same as before.
"""

import ai.vision.relevance_gate as rg
from ai.vision.relevance_gate import is_available, check_relevance, guess_body_part_from_image, _BODY_PART_LABELS


def _mock_ratings(**overrides):
    """A full 7-body-part rating dict, all near-zero by default, so a test
    only needs to specify the candidates it actually cares about. Ratings
    are 0-100 integers and independent -- they do NOT need to sum to 100,
    unlike the old CLIP softmax output."""
    base = {bp: 2 for bp in _BODY_PART_LABELS}
    base.update(overrides)
    return base


def test_is_available_returns_a_bool():
    assert isinstance(is_available(), bool)


def test_check_relevance_never_raises_even_with_garbage_bytes():
    """Core safety contract: this must NEVER throw, regardless of whether a
    client is configured or the input is nonsense -- a soft advisory signal
    must not be capable of crashing a real screening request."""
    result = check_relevance(b"not a real image at all", "eye")
    assert isinstance(result, dict)
    for key in ("checked", "relevant", "confidence", "detected_as", "warning"):
        assert key in result


def test_check_relevance_returns_not_checked_for_unmapped_body_part():
    """A body part with no relevance prompt (e.g. non-photographable ones
    like 'general') must cleanly report checked=False, not error."""
    result = check_relevance(b"anything", "general")
    assert result["checked"] is False
    assert result["relevant"] is None
    assert result["warning"] is None


def test_check_relevance_result_shape_is_consistent():
    """Whether or not the real model is available, the return shape must be
    identical -- callers (main.py) must be able to handle both without
    branching on is_available() themselves."""
    for body_part in ["eye", "skin", "nail", "oral", "dental", "ent", "hair"]:
        result = check_relevance(b"fake bytes", body_part)
        assert set(result.keys()) == {"checked", "relevant", "confidence", "detected_as", "warning"}


def test_every_photographable_body_part_has_a_label():
    """Guards against a silent gap: if a new photographable body part is
    added to the KB but nobody adds a label/prompt here, the relevance
    check silently no-ops for it forever without anyone noticing."""
    expected = {"eye", "skin", "nail", "oral", "dental", "ent", "hair"}
    assert expected.issubset(set(_BODY_PART_LABELS.keys()))


def test_warning_is_only_ever_set_when_not_relevant():
    """When no client is configured (checked=False), warning must be None --
    never populate a user-facing warning from a check that didn't actually
    run."""
    result = check_relevance(b"fake", "eye")
    if not result["checked"]:
        assert result["warning"] is None


def test_guess_body_part_never_raises_with_garbage_bytes():
    result = guess_body_part_from_image(b"not a real image")
    assert isinstance(result, dict)
    assert set(result.keys()) == {"checked", "guessed_body_part", "confidence", "all_scores"}


def test_guess_body_part_degrades_cleanly_without_client():
    result = guess_body_part_from_image(b"fake bytes")
    if not is_available():
        assert result["checked"] is False
        assert result["guessed_body_part"] is None
        assert result["confidence"] is None
        assert result["all_scores"] is None


def test_guess_body_part_never_guesses_outside_the_seven_photographable_parts():
    """Even if it ever DOES return a guess, it must only ever be one of the
    7 body parts it actually has a label for -- never anything else."""
    result = guess_body_part_from_image(b"fake bytes")
    if result["checked"] and result["guessed_body_part"] is not None:
        assert result["guessed_body_part"] in _BODY_PART_LABELS


# ---------------------------------------------------------------------------
# Decision logic, verified with mocked vision-LLM ratings. These are the
# actual regression tests for the real bugs found in live testing across
# both the CLIP-era version and this VLM rewrite.
# ---------------------------------------------------------------------------

def test_wrong_body_part_photo_is_correctly_flagged_not_relevant(monkeypatch):
    """A mouth photo uploaded under 'Eye' must be flagged -- the claimed
    body part must beat every OTHER real body part, not just clear a low
    bar on its own."""
    monkeypatch.setattr(rg, "_client", object())  # any non-None sentinel
    monkeypatch.setattr(rg, "_rate_all_body_parts",
                         lambda img: _mock_ratings(eye=20, oral=75))
    result = check_relevance(b"fake", "eye")
    assert result["relevant"] is False
    assert result["detected_as"] == "oral"
    assert "mouth" in result["warning"]


def test_non_body_part_photo_gets_no_guess(monkeypatch):
    """A photo of a person (not a diagnostic close-up of any specific body
    part) must get no guess at all -- ratings independent per body part
    (not required to sum to 100%) is exactly what lets every one of the 7
    genuinely score low together, instead of a softmax being forced to
    hand its probability mass to *something*."""
    monkeypatch.setattr(rg, "_client", object())
    monkeypatch.setattr(rg, "_rate_all_body_parts",
                         lambda img: _mock_ratings(eye=15, skin=10, hair=8))
    result = guess_body_part_from_image(b"fake")
    assert result["guessed_body_part"] is None


def test_genuine_photo_at_normal_framing_still_works(monkeypatch):
    """THE specific bug this rewrite was built to fix: a genuine eye photo
    that ISN'T an extreme close-up (a normal-distance, angled, or
    differently-lit shot) must still be correctly accepted -- a rigid
    CLIP-style 'close-up' requirement is exactly what this replaced."""
    monkeypatch.setattr(rg, "_client", object())
    monkeypatch.setattr(rg, "_rate_all_body_parts",
                         lambda img: _mock_ratings(eye=68))  # confident, not "close-up" specific
    relevance = check_relevance(b"fake", "eye")
    guess = guess_body_part_from_image(b"fake")
    assert relevance["relevant"] is True
    assert relevance["detected_as"] is None
    assert guess["guessed_body_part"] == "eye"


def test_close_call_between_two_real_body_parts_is_not_falsely_confident(monkeypatch):
    """When two body parts rate close together (genuinely ambiguous photo),
    the claimed one must still actually be the top scorer -- a near tie
    where a DIFFERENT body part edges ahead must be flagged, not waved
    through just because the claimed one scored reasonably."""
    monkeypatch.setattr(rg, "_client", object())
    monkeypatch.setattr(rg, "_rate_all_body_parts",
                         lambda img: _mock_ratings(eye=50, ent=55))
    result = check_relevance(b"fake", "eye")
    assert result["relevant"] is False
    assert result["detected_as"] == "ent"


def test_scores_are_clamped_to_valid_range():
    """_rate_all_body_parts must never let a misbehaving model response
    (a rating outside 0-100, or a non-numeric value) propagate -- clamped
    or defaulted, never trusted as-is."""
    import ai.vision.relevance_gate as rg_module
    from io import BytesIO
    from PIL import Image

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
        def __init__(self, text):
            self.text = text
            self.chat = self
            self.completions = self

        def create(self, **kw):
            return _FakeResponse(self.text)

    old_client = rg_module._client
    try:
        rg_module._client = _FakeClient(
            '{"eye": 150, "skin": -20, "nail": "not a number", "oral": 40, '
            '"dental": 10, "ent": 5, "hair": 3}'
        )
        scores = rg_module._rate_all_body_parts(_tiny_jpeg_bytes())
        assert scores["eye"] == 100  # clamped from 150
        assert scores["skin"] == 0   # clamped from -20
        assert scores["nail"] == 0   # non-numeric defaults to 0
        assert scores["oral"] == 40
    finally:
        rg_module._client = old_client