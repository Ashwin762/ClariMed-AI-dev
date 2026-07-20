"""
tests/test_image_privacy.py

Verifies the privacy guarantee that ClariMed makes to users:

    "Uploaded images are held in memory only for the duration of the request.
     They are never written to disk, never inserted into the database, and
     never transmitted to a third party."

A promise in a policy document is worth nothing. These tests make it an
enforced property of the codebase — if someone later adds `open(path, 'wb')`
inside the image-handling block, or passes `file_bytes` into a database call,
the suite fails.

Two layers:
  1. Behavioural — feature extraction returns only derived numbers, never
     the original bytes.
  2. Static — the source of the image-handling block is parsed and checked
     for persistence calls and for a matching `del` on every path.
"""

import ast
import io
import os
import re

import pytest
from PIL import Image, ImageDraw, ImageFilter

from ai.vision.image_analysis import extract_features, quality_check


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_PY = os.path.join(REPO_ROOT, "backend", "main.py")


def _make_test_image(color=(190, 70, 60), size=(120, 120)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 1. Behavioural: derived features only, never the original image
# ---------------------------------------------------------------------------

def test_extract_features_returns_only_derived_numbers():
    """The feature dict must not smuggle the original bytes through."""
    raw = _make_test_image()
    features = extract_features(raw)

    for key, value in features.items():
        assert not isinstance(value, (bytes, bytearray)), (
            f"feature '{key}' contains raw bytes — the image is leaking through"
        )


def test_extract_features_has_the_expected_keys():
    """condition_engine's scorers index these directly. A missing key is a
    runtime KeyError mid-screening (this has happened: 'darkness')."""
    features = extract_features(_make_test_image())
    required = {"redness", "yellowness", "whiteness", "variance", "brightness", "sharpness"}
    assert required <= set(features)


def test_image_scorers_only_use_existing_feature_keys():
    """Every scorer must run against a real feature dict without KeyError.
    Regression guard for scorers referencing 'darkness'/'brightness_norm'."""
    from ai.rules.condition_engine import IMAGE_SCORERS
    features = extract_features(_make_test_image())
    for cid, scorer in IMAGE_SCORERS.items():
        try:
            value = scorer(features)
        except KeyError as e:
            pytest.fail(f"IMAGE_SCORERS['{cid}'] references nonexistent feature {e}")
        assert isinstance(value, (int, float)), f"{cid} scorer returned {type(value)}"


def test_quality_gate_rejects_a_blank_image():
    """A flat, textureless image has no edges — it must fail the blur check."""
    flat = _make_test_image(color=(128, 128, 128))
    features = extract_features(flat)
    result = quality_check(features)
    assert result["passed"] is False
    assert result["issues"]


def test_quality_gate_rejects_a_very_dark_image():
    dark = _make_test_image(color=(5, 5, 5))
    features = extract_features(dark)
    result = quality_check(features)
    assert result["passed"] is False
    assert any("dark" in i.lower() for i in result["issues"])


def test_quality_gate_does_not_reject_a_smooth_but_focused_photo():
    """REGRESSION GUARD — real user report.

    A correctly-focused photo of a bruise (soft radial color gradient, no
    hard edges) was rejected as 'blurry'. The old threshold (4.0) sat
    between a sharp-but-untextured photo (~0.9) and a genuinely noisy
    photo (~6.8), rejecting an entire class of legitimate medical photos:
    bruises, smooth rashes, vitiligo patches, anything without heavy
    sensor grain. The threshold is now 0.5, calibrated against measured
    in-focus vs. camera-shake scores across three content types.
    """
    img = Image.new("RGB", (300, 300), (200, 180, 170))
    draw = ImageDraw.Draw(img)
    for r in range(150, 0, -3):
        t = r / 150
        color = (int(90 + 60 * t), int(60 + 40 * t), int(120 + 30 * t))
        draw.ellipse([150 - r, 150 - r, 150 + r, 150 + r], fill=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    features = extract_features(buf.getvalue())
    result = quality_check(features)
    assert result["passed"] is True, (
        f"a correctly-focused smooth-subject photo was rejected "
        f"(sharpness={features['sharpness']:.3f}); the false-rejection bug has returned"
    )


def test_quality_gate_still_rejects_genuine_camera_shake_on_a_smooth_subject():
    """The fix must not become so lenient it stops catching real blur."""
    img = Image.new("RGB", (300, 300), (200, 180, 170))
    draw = ImageDraw.Draw(img)
    for r in range(150, 0, -3):
        t = r / 150
        color = (int(90 + 60 * t), int(60 + 40 * t), int(120 + 30 * t))
        draw.ellipse([150 - r, 150 - r, 150 + r, 150 + r], fill=color)
    img = img.filter(ImageFilter.GaussianBlur(6))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    features = extract_features(buf.getvalue())
    result = quality_check(features)
    assert result["passed"] is False, "genuinely blurred photo was incorrectly accepted"


# ---------------------------------------------------------------------------
# 2. Static: no persistence of image bytes anywhere in the handling block
# ---------------------------------------------------------------------------

def _image_handling_source() -> str:
    """Extract the block of main.py that holds `file_bytes`."""
    src = open(MAIN_PY, encoding="utf-8").read()
    start = src.index("if file:")
    # The block ends where the fused scoring begins.
    end = src.index("result = fuse(")
    return src[start:end]


def test_main_py_has_an_image_handling_block():
    block = _image_handling_source()
    assert "file_bytes" in block


FORBIDDEN_PERSISTENCE_PATTERNS = [
    (r"\bopen\s*\(", "file open()"),
    (r"\.write\s*\(", "a .write() call"),
    (r"\bINSERT\b", "a SQL INSERT"),
    (r"save_screening\s*\(.*file_bytes", "passing image bytes to the database"),
    (r"requests\.", "an outbound requests call"),
    (r"httpx\.", "an outbound httpx call"),
    (r"urlopen", "an outbound urlopen call"),
    (r"boto3", "cloud storage upload"),
    (r"shutil\.copy", "a file copy"),
]


def test_image_block_contains_no_persistence_calls():
    """The strong guarantee: nothing in the image-handling block may write
    the image anywhere or send it off-machine."""
    block = _image_handling_source()
    for pattern, description in FORBIDDEN_PERSISTENCE_PATTERNS:
        match = re.search(pattern, block)
        assert match is None, (
            f"image handling block contains {description} "
            f"(matched {pattern!r} at offset {match.start()}). "
            "Uploaded images must never be persisted or transmitted."
        )


def test_every_path_holding_image_bytes_deletes_them():
    """`file_bytes` must be explicitly deleted on every exit path from the
    block — including the early returns for oversized and low-quality images."""
    block = _image_handling_source()
    del_count = len(re.findall(r"\bdel\s+file_bytes\b", block))
    assert del_count >= 4, (
        f"found only {del_count} `del file_bytes` statements. Expected one on "
        "each exit path: oversize reject, extract failure, quality-gate reject, "
        "and the normal completion path."
    )


def test_file_bytes_never_stored_on_a_variable_that_outlives_the_request():
    """Guard against `self.last_image = file_bytes` style mistakes."""
    block = _image_handling_source()
    tree = ast.parse("def _f():\n" + "\n".join("    " + l for l in block.splitlines()))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value_src = ast.dump(node.value)
            if "file_bytes" in value_src:
                for target in node.targets:
                    # Assigning file_bytes to an attribute or subscript means
                    # it escapes the function scope.
                    assert not isinstance(target, (ast.Attribute, ast.Subscript)), (
                        "image bytes assigned to an attribute or container — "
                        "they may outlive the request"
                    )


def test_image_metadata_returned_to_client_contains_no_filename():
    """The uploaded filename can itself be identifying (e.g. 'rash_on_ravi.jpg').
    We report retention status instead."""
    block = _image_handling_source()
    assert "file.filename" not in block, (
        "the uploaded filename is being returned to the client; it can be identifying"
    )
    assert '"retention": "not_stored"' in block or "'retention': 'not_stored'" in block, (
        "image_meta should declare its retention status explicitly"
    )


def test_a_max_upload_size_is_enforced():
    src = open(MAIN_PY, encoding="utf-8").read()
    assert "MAX_IMAGE_BYTES" in src, "no upload size limit defined"
    block = _image_handling_source()
    assert "MAX_IMAGE_BYTES" in block, "upload size limit defined but never checked"


def test_screening_requires_consent():
    """The consent gate must exist and must be checked before any processing,
    specifically within the actual screening endpoint (execute_screening).
    Scoped to that function rather than the whole file, since other endpoints
    (e.g. the image-based symptom-suggestion pre-fill helper) legitimately
    have their own, earlier `await file.read()` calls without a consent gate
    -- the same way /api/suggest-body-part doesn't require consent, because
    neither is the actual screening submission that gets persisted."""
    src = open(MAIN_PY, encoding="utf-8").read()
    assert "consent_given" in src, "no consent parameter on the screening endpoint"

    start = src.index("async def execute_screening")
    end = src.index("\n\n\n", start)
    func_src = src[start:end]

    consent_pos = func_src.index("if not consent_given")
    image_pos = func_src.index("await file.read()")
    assert consent_pos < image_pos, (
        "within execute_screening, the image is read before consent is verified"
    )


# ---------------------------------------------------------------------------
# Same privacy rigor, applied to the newer image-based symptom-suggestion
# endpoint -- it touches image bytes too, so it must meet the identical bar.
# ---------------------------------------------------------------------------

def _suggest_symptoms_source() -> str:
    """Extract the block of main.py that holds file_bytes inside the
    image-based symptom-suggestion endpoint specifically."""
    src = open(MAIN_PY, encoding="utf-8").read()
    start = src.index("async def suggest_symptoms_from_image_endpoint")
    end = src.index("\n\n\n", start)
    return src[start:end]


def test_suggest_symptoms_endpoint_exists_and_reads_an_image():
    block = _suggest_symptoms_source()
    assert "await file.read()" in block


def test_suggest_symptoms_endpoint_deletes_file_bytes_on_every_path():
    """Same guarantee as the main screening endpoint: file_bytes must be
    deleted on every exit path -- oversize reject, extract failure, and the
    normal completion path (this endpoint returns straight through on a
    failed quality check rather than early-returning before deletion, but
    the delete must still happen before that return)."""
    block = _suggest_symptoms_source()
    del_count = len(re.findall(r"\bdel\s+file_bytes\b", block))
    assert del_count >= 3, (
        f"found only {del_count} `del file_bytes` statements in the image "
        "suggestion endpoint. Expected one on each exit path: oversize "
        "reject, extract failure, and before the quality-gate result."
    )


def test_suggest_symptoms_endpoint_never_calls_fuse_directly():
    """Structural safety guarantee: this endpoint must never compute a
    risk_level or call fuse() itself. It's a checkbox pre-fill only -- the
    real screening result always comes from a separate, later call to
    POST /api/screen using whatever symptoms the patient actually confirms.

    Strips the docstring before searching -- the docstring itself explains
    this guarantee in prose (mentioning both words), which would otherwise
    be a false-positive match for a check that's supposed to look at code."""
    block = _suggest_symptoms_source()
    code_only = re.sub(r'"""[\s\S]*?"""', "", block, count=1)
    assert "fuse(" not in code_only
    assert "risk_level" not in code_only


def test_suggest_symptoms_endpoint_does_not_persist_anything():
    """No database write calls anywhere in this endpoint -- it's a pure,
    stateless suggestion, not something that creates a record."""
    block = _suggest_symptoms_source()
    for forbidden in ("save_screening", "INSERT INTO", "write_audit"):
        assert forbidden not in block, f"found unexpected persistence call: {forbidden}"


def test_suggest_symptoms_endpoint_is_gated_on_relevance_check():
    """Same real bug as execute_screening's version, found in a different
    endpoint: the symptoms-step 'upload a photo to pre-fill' feature
    computed relevance but never used it to stop suggest_symptoms_from_image()
    from running on a confidently-irrelevant photo. This one is arguably
    worse -- it uses the heuristic color-stat scorer, which produces SOME
    redness/whiteness/variance values for any photo at all, irrelevant or
    not.

    Strips the docstring before searching -- it mentions
    suggest_symptoms_from_image() in prose, which would otherwise be a
    false-positive match for a check that's supposed to look at code only
    (same class of bug as the earlier fuse()-mention false positive)."""
    block = _suggest_symptoms_source()
    code_only = re.sub(r'"""[\s\S]*?"""', "", block, count=1)
    relevance_pos = code_only.index("relevance = relevance_check(")
    call_pos = code_only.index("suggest_symptoms_from_image(")
    assert relevance_pos < call_pos, (
        "relevance check must be computed before suggest_symptoms_from_image runs"
    )
    between = code_only[relevance_pos:call_pos]
    assert 'relevance["relevant"] is False' in between, (
        "suggest_symptoms_from_image isn't actually gated on the relevance result"
    )


def test_vision_symptom_detection_is_gated_on_relevance_check():
    """Real bug found in testing: an irrelevant photo (e.g. a photo of a
    person posing, not a diagnostic close-up) still produced fabricated
    'detected' symptoms, because relevance_check()'s result was computed
    but never actually used to stop vision-based symptom detection from
    running anyway. Structural check that the fix is really in place:
    the relevance check must run BEFORE, and its result must gate, the
    call to interpret_symptoms_from_image()."""
    src = open(MAIN_PY, encoding="utf-8").read()
    start = src.index("async def execute_screening")
    end = src.index("\n\n\n", start)
    func_src = src[start:end]

    relevance_pos = func_src.index("relevance = relevance_check(")
    vision_call_pos = func_src.index("interpret_symptoms_from_image(")
    assert relevance_pos < vision_call_pos, (
        "relevance check must be computed before vision-based symptom detection runs"
    )

    # The vision call must be inside a branch that checks relevance first --
    # not just computed-and-ignored (the original bug).
    between = func_src[relevance_pos:vision_call_pos]
    assert 'relevance["relevant"] is False' in between, (
        "vision-based symptom detection isn't actually gated on the relevance result"
    )