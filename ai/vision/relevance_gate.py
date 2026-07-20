"""
ai/vision/relevance_gate.py

Two related jobs, both now backed by a vision-capable LLM (Groq's
meta-llama/llama-4-scout -- the same model already used in
ai/rag/vision_symptom_interpreter.py) instead of CLIP:
  1. check_relevance()            -- does this photo plausibly show the
                                       body part the patient CLAIMS it does?
  2. guess_body_part_from_image() -- given ONLY a photo, which body part
                                       does it most likely show?

WHY THIS REPLACED THE EARLIER CLIP-BASED VERSION:
CLIP's zero-shot classification is a single, rigid embedding-similarity
comparison against a fixed text prompt. A prompt like "a close-up photo of
a human eye" creates a narrow target region in embedding space -- a real
bug found in testing: a genuine close-up eye photo was correctly accepted,
but a longer-range (still genuinely an eye) photo of the same eye was
incorrectly rejected, purely because it didn't match the rigid "close-up"
framing the prompt demanded. That's a structural limitation of embedding-
distance matching, not something a threshold tweak can fix.

A full vision-language model can instead be asked directly, in plain
language, to rate how strongly a photo shows each body part -- and
actually REASON about the content (an eye is an eye at a normal distance,
an angle, imperfect lighting) rather than measuring distance to one
narrow phrase. This is fundamentally more flexible for this kind of
judgment call.

This also consolidates onto ONE vision provider (Groq) already proven
elsewhere in this codebase, instead of maintaining two separate vision
stacks (CLIP via torch/transformers, and Groq's VLM) with different
calibration needs -- and drops the torch/transformers/CLIP dependency
requirement entirely.

WHAT'S UNCHANGED FROM THE CLIP VERSION (the two real bugs already found
and fixed there remain fixed here, by the same underlying principle): a
body part only "wins" if it beats every OTHER body part, not just generic
junk -- so a mouth photo still can't slip through under "eye" just because
neither is a document or an animal. And a non-body-part photo (e.g. a
portrait of a person) naturally scores low across ALL 7 candidates rather
than being forced to pick a "winner," since there's no requirement here
that the ratings sum to 100%.

HONEST LIMITATION -- READ BEFORE TRUSTING THIS IN PRODUCTION:
Written directly from Groq's official vision docs (the same verified
request pattern already used in vision_symptom_interpreter.py), but this
sandbox has no network access to actually call the live API. The request
shape is right; the real numeric behavior on real photos can only be
verified on a machine with a working API key -- which is exactly how the
CLIP-era bugs, and the reason for this rewrite, were originally found.

DESIGN PRINCIPLE: never hard-block the screening itself. A false "not
relevant" verdict on a genuine but unusual photo could delay someone with
a real emergency. This still only ever produces a WARNING for the frontend
to show (relevance) or a null suggestion (guessing) -- never a rejection.
"""

import re
import json
import base64
import logging
from io import BytesIO
from typing import Optional, Dict, Any

from PIL import Image

from ai.rag.llm_client import get_llm_client, PROMPT_INJECTION_GUARD

logger = logging.getLogger("clarimed.relevance_gate")

_client = get_llm_client()

_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# Same limits and reasoning as ai/rag/vision_symptom_interpreter.py -- see
# that module for the full explanation of why resizing matters here
# (Groq's base64 image limit is 4MB, stricter than our own 10MB upload cap).
_MAX_DIMENSION_FOR_VISION_API = 1024
_JPEG_QUALITY = 85

# Natural-language labels for both the LLM prompt and patient-facing
# warning messages -- our internal body_part keys ("oral", "ent") aren't
# words a patient would recognize on their own.
_BODY_PART_LABELS = {
    "eye": "eye",
    "skin": "skin",
    "nail": "fingernail or toenail",
    "oral": "mouth (inside)",
    "dental": "teeth",
    "ent": "ear, nose, or throat",
    "hair": "hair or scalp",
}

_RATING_SYSTEM_PROMPT = (
    "You rate how strongly a photo shows visual evidence of each of several "
    "human body parts. You are NOT diagnosing anything -- only judging what "
    "the photo depicts, at any reasonable distance, angle, or lighting (not "
    "just extreme close-ups). Respond with ONLY a JSON object with exactly "
    "these 7 keys -- eye, skin, nail, oral, dental, ent, hair -- each mapped "
    "to an integer 0-100 rating of how strongly the photo shows that body "
    "part specifically. A photo that genuinely shows one clear body part "
    "should have one high rating and the rest low. A photo that doesn't "
    "show any specific human body part close-up at all (e.g. a normal "
    "portrait of a person, an object, an animal, a screenshot) should have "
    "ALL seven ratings low. Do not let ratings sum to 100 artificially -- "
    "rate each independently based on actual visual evidence. "
    f"{PROMPT_INJECTION_GUARD}"
)

# Not calibrated (see module docstring) -- reasonable starting bars that
# genuinely need real-world verification, same as every other threshold in
# this file's predecessor.
_RELEVANCE_CONFIDENCE_THRESHOLD = 45
_GUESS_CONFIDENCE_THRESHOLD = 45


def is_available() -> bool:
    """Whether this feature can run at all -- False means no LLM key is
    configured. Callers must treat that as 'no check performed', never as
    an error."""
    return _client is not None


def _prepare_image_for_api(image_bytes: bytes) -> str:
    """Resizes/recompresses to stay safely under Groq's 4MB base64 limit,
    then returns a base64-encoded JPEG string. Mirrors the identical helper
    in ai/rag/vision_symptom_interpreter.py -- kept as a small, separate
    copy rather than a shared import, since these are two independent
    vision utility modules and the function is only 6 lines."""
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    image.thumbnail((_MAX_DIMENSION_FOR_VISION_API, _MAX_DIMENSION_FOR_VISION_API), Image.LANCZOS)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=_JPEG_QUALITY)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _rate_all_body_parts(image_bytes: bytes) -> Dict[str, int]:
    """
    The one shared scoring pass both public functions use: asks the vision
    model to independently rate the photo against all 7 body parts in a
    single call. Returns a dict of 7 integer scores (0-100), one per body
    part -- NOT required to sum to 100, unlike the old CLIP softmax, which
    is exactly what lets a non-body-part photo score low across the board
    instead of being forced to hand its probability mass to something.

    Raises on failure -- callers must catch this, same as every other image
    entry point in this codebase.
    """
    b64_image = _prepare_image_for_api(image_bytes)
    response = _client.chat.completions.create(
        model=_VISION_MODEL,
        messages=[
            {"role": "system", "content": _RATING_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Rate this photo against all 7 body parts."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}},
                ],
            },
        ],
        temperature=0.0,
    )
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a JSON object, got {type(parsed)}")

    scores = {}
    for bp in _BODY_PART_LABELS:
        value = parsed.get(bp, 0)
        try:
            scores[bp] = max(0, min(100, int(value)))
        except (TypeError, ValueError):
            scores[bp] = 0
    return scores


def check_relevance(image_bytes: bytes, body_part: str) -> Dict[str, Any]:
    """
    Returns:
      {
        "checked": bool,
        "relevant": Optional[bool],
        "confidence": Optional[int],     -- the claimed body part's own 0-100 rating
        "detected_as": Optional[str],    -- what actually scored highest,
                                             if different from body_part
        "warning": Optional[str],
      }

    "relevant" requires the claimed body part to have the HIGHEST rating
    among all 7 (not just beat generic junk) AND clear a minimum bar --
    same principle as the CLIP-era fix for the mouth-claimed-as-eye bug,
    now backed by a model that can recognize a body part at any reasonable
    framing, not just an extreme close-up.

    Never raises -- any failure degrades to {"checked": False, ...}.
    """
    body_part = body_part.lower()
    if body_part not in _BODY_PART_LABELS:
        return {"checked": False, "relevant": None, "confidence": None, "detected_as": None, "warning": None}

    if _client is None:
        return {"checked": False, "relevant": None, "confidence": None, "detected_as": None, "warning": None}

    try:
        scores = _rate_all_body_parts(image_bytes)
        confidence = scores[body_part]
        top_bp = max(scores, key=scores.get)

        relevant = (top_bp == body_part) and (confidence >= _RELEVANCE_CONFIDENCE_THRESHOLD)

        detected_as = None
        warning = None
        if not relevant:
            label = _BODY_PART_LABELS[body_part]
            if top_bp != body_part and scores[top_bp] >= _RELEVANCE_CONFIDENCE_THRESHOLD:
                detected_as = top_bp
                detected_label = _BODY_PART_LABELS[detected_as]
                warning = (
                    f"This photo looks more like it shows your {detected_label} than your {label} — "
                    "if that's not what you meant to upload, please retake it. "
                    "You can still continue if you're confident it's correct."
                )
            else:
                warning = (
                    f"This photo doesn't look like it clearly shows a {label} — "
                    "if that's not what you meant to upload, please retake it. "
                    "You can still continue if you're confident it's correct."
                )

        return {
            "checked": True, "relevant": relevant, "confidence": confidence,
            "detected_as": detected_as, "warning": warning,
        }

    except Exception as e:
        logger.warning("Relevance check failed, skipping: %s", e)
        return {"checked": False, "relevant": None, "confidence": None, "detected_as": None, "warning": None}


def guess_body_part_from_image(image_bytes: bytes) -> Dict[str, Any]:
    """
    Given ONLY a photo -- before any body part has been selected -- guesses
    which of the 7 photographable body parts it most likely shows, or
    correctly declines to guess if nothing clears the confidence bar (e.g.
    a normal person photo, which should rate low across all 7).

    This is a SUGGESTION for the frontend to pre-select on the body-part
    grid -- "AI suggests, human confirms, never forces."

    Returns:
      {
        "checked": bool,
        "guessed_body_part": Optional[str],
        "confidence": Optional[int],               -- top candidate's own 0-100 rating
        "all_scores": Optional[Dict[str, int]],     -- all 7 ratings, for the
                                                        frontend's live bar chart
      }

    Never raises -- degrades to a clean "not checked" result on any failure.
    """
    if _client is None:
        return {"checked": False, "guessed_body_part": None, "confidence": None, "all_scores": None}

    try:
        scores = _rate_all_body_parts(image_bytes)
        top_bp = max(scores, key=scores.get)
        top_confidence = scores[top_bp]

        guessed = top_bp if top_confidence >= _GUESS_CONFIDENCE_THRESHOLD else None

        return {"checked": True, "guessed_body_part": guessed, "confidence": top_confidence, "all_scores": scores}

    except Exception as e:
        logger.warning("Body part guess failed, skipping: %s", e)
        return {"checked": False, "guessed_body_part": None, "confidence": None, "all_scores": None}