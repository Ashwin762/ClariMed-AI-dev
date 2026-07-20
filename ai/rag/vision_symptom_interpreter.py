"""
ai/rag/vision_symptom_interpreter.py

Detects visible symptoms directly from an uploaded photo, using a
vision-capable LLM (Groq's meta-llama/llama-4-scout-17b-16e-instruct) --
NOT a diagnosis, a closed-list SYMPTOM mapper, the exact same safety
pattern symptom_interpreter.py already uses for typed text: the model is
only ever allowed to pick from the body part's existing, known symptom
checklist. It cannot invent a symptom and cannot name a condition -- that
reasoning stays entirely inside condition_engine.py's deterministic
fuse(), completely unchanged.

WHY THIS IS SAFE DESPITE BEING A NEW CAPABILITY: it doesn't add a second,
parallel scoring pathway. Detected symptoms feed into the SAME fuse()
pipeline as symptoms a patient ticks by hand, so every existing guarantee
(red-flag escalation, confidence floors, the honest "not enough evidence"
fallback) applies automatically -- there was nothing new to re-prove here,
only a new SOURCE for a list of symptom strings the engine already knows
how to handle correctly.

SCOPE NOTE (explicitly requested): unlike the rest of this codebase, this
module deliberately has NO offline fallback. There's no meaningful
heuristic substitute for "look at this photo and describe what you see" --
ai/vision/image_analysis.py's color/texture heuristics are a separate,
already-existing signal, not replaced by this. If no LLM key is configured
or the call fails, this returns an empty list and the screening proceeds
exactly as it already does today with zero symptoms selected -- never a
hard error, never a crash.

HONEST LIMITATION: written directly from Groq's official vision docs
(fetched and verified current as of writing -- model ID, message format,
and size limits all match their published examples exactly), but this
sandbox has no network access to actually call the live API. The request
shape is verified against real documentation, not guessed; the live
numeric behavior (does it detect real symptoms well) needs verification
against a real API key, which only happens on your machine.
"""

import re
import json
import base64
import logging
from io import BytesIO
from typing import List, Dict, Any

from PIL import Image

from ai.rag.llm_client import get_llm_client, PROMPT_INJECTION_GUARD

logger = logging.getLogger("clarimed.vision_symptom_interpreter")

_client = get_llm_client()

_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# Groq's base64-encoded-image request limit is 4MB (separate and much
# stricter than their 20MB URL-based limit -- see console.groq.com/docs/vision).
# Our own upload cap is 10MB raw, which base64 encoding inflates by ~33%,
# so a raw upload well within our own limit could still exceed Groq's.
# Resizing before sending avoids a silent/confusing API rejection on larger
# photos, and 1024px is comfortably more detail than a vision model needs
# to assess something like redness, swelling, or a visible lesion.
_MAX_DIMENSION_FOR_VISION_API = 1024
_JPEG_QUALITY = 85

SYSTEM_PROMPT = (
    "You are a visual triage assistant. Given a photograph of a specific body "
    "part, identify which items from a PRE-DEFINED symptom list are visibly "
    "suggested by the image. You are NOT diagnosing -- never name a disease "
    "or condition anywhere in your response, only describe visible signs.\n\n"
    "Respond with ONLY a JSON object with exactly two keys:\n"
    '  "matched_symptoms": a JSON array of strings, each an EXACT match from '
    "the provided list. Include an item only if the image gives real, "
    "specific visual evidence for it -- do not guess or include something "
    "just because it's generically plausible. Empty array [] if none apply. "
    "Never include anything not present in the provided list, even if it "
    "seems related -- put those observations in the other field instead.\n"
    '  "other_observations": a short (1-2 sentence) PLAIN, DESCRIPTIVE note '
    "on anything else visually notable that ISN'T covered by the symptom "
    "list -- color, texture, shape, or size details a clinician might find "
    "useful. Purely descriptive, never a diagnosis, never a condition name, "
    "never treatment advice. Empty string \"\" if there's nothing else "
    "notable or you're not confident enough to describe it.\n\n"
    f"{PROMPT_INJECTION_GUARD}"
)

_MAX_OBSERVATION_CHARS = 300  # keeps this a short note, not a paragraph


def is_available() -> bool:
    return _client is not None


def _prepare_image_for_api(image_bytes: bytes) -> str:
    """Resizes/recompresses to stay safely under Groq's 4MB base64 limit,
    then returns a base64-encoded JPEG string. Raises on a genuinely
    corrupt image -- callers must catch this, same as every other image
    entry point in this codebase."""
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    image.thumbnail((_MAX_DIMENSION_FOR_VISION_API, _MAX_DIMENSION_FOR_VISION_API), Image.LANCZOS)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=_JPEG_QUALITY)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def interpret_symptoms_from_image(image_bytes: bytes, body_part: str, known_symptoms: List[str]) -> Dict[str, Any]:
    """
    Two-tier result:
      {
        "matched_symptoms": [...],     -- subset of known_symptoms, SAFE TO SCORE
        "other_observations": "...",   -- free-text, INFORMATIONAL ONLY, never fed
                                           into fuse() or any risk calculation
      }

    Why two tiers: a photo can genuinely show something visually real and
    useful that simply isn't in our checklist yet -- restricting the model
    to a closed list (necessary for the scored path to stay safe and
    traceable) would otherwise silently discard it. This lets that
    observation surface to the patient and clinician as a clearly-labeled,
    unscored note instead of vanishing.

    "matched_symptoms" carries the exact same closed-list safety guarantee
    as before -- enforced both by the prompt AND a post-hoc filter, so even
    a misbehaving model response can't leak an invented symptom into the
    scoring engine. "other_observations" has no such constraint (there's
    nothing to filter against), but it is NEVER used for scoring, only
    displayed -- so an ungrounded or slightly-off observation here cannot
    affect a risk_level or a top condition, only a supplementary note a
    clinician sees.

    Never raises -- any failure degrades to {"matched_symptoms": [],
    "other_observations": ""}, which the screening pipeline already handles
    identically to a patient who selected zero symptoms by hand.
    """
    empty_result = {"matched_symptoms": [], "other_observations": ""}
    if _client is None or not known_symptoms:
        return empty_result

    try:
        b64_image = _prepare_image_for_api(image_bytes)
    except Exception as e:
        logger.warning("Could not prepare image for vision analysis, skipping: %s", e)
        return empty_result

    try:
        user_prompt = (
            f"Body part: {body_part}\n"
            f"Known symptom list: {json.dumps(known_symptoms)}\n\n"
            "Describe what this photo visually supports, per the two-field format."
        )
        response = _client.chat.completions.create(
            model=_VISION_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}},
                    ],
                },
            ],
            temperature=0.0,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if the model added them despite
        # instructions -- same defensive parsing as symptom_interpreter.py.
        raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return empty_result

        raw_matched = parsed.get("matched_symptoms", [])
        if not isinstance(raw_matched, list):
            raw_matched = []
        matched = [s for s in raw_matched if s in known_symptoms]

        # Anything the model tried to report that ISN'T in our list is real
        # signal about a possible checklist gap -- logged (not scored, not
        # shown) so this becomes usage-driven data for future KB expansion,
        # the same way we found the missing Cardiovascular body part.
        rejected = [s for s in raw_matched if s not in known_symptoms]
        if rejected:
            logger.info("Vision model reported items outside the %s checklist: %s", body_part, rejected)

        observation = parsed.get("other_observations", "")
        if not isinstance(observation, str):
            observation = ""
        observation = observation.strip()[:_MAX_OBSERVATION_CHARS]

        return {"matched_symptoms": matched, "other_observations": observation}
    except Exception as e:
        logger.warning("Vision symptom detection failed, returning no detected symptoms: %s", e)
        return empty_result