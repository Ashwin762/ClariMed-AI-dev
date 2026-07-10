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
    """The consent gate must exist and must be checked before any processing."""
    src = open(MAIN_PY, encoding="utf-8").read()
    assert "consent_given" in src, "no consent parameter on the screening endpoint"
    # The consent check must appear before the image is read.
    consent_pos = src.index("if not consent_given")
    image_pos = src.index("await file.read()")
    assert consent_pos < image_pos, (
        "the image is read before consent is verified"
    )