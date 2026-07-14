"""
ai/rag/body_part_router.py

Classifies a free-text symptom description into one of ClariMed's 11 body
parts, so a user can just describe what's wrong instead of picking a
category first. The suggestion pre-selects a body part in the UI — it never
replaces the manual selector, which stays available as an override.

SAFETY DESIGN (same principle as specialist_router.py and symptom_interpreter.py):
The LLM selects from a CLOSED LIST of body parts. It cannot invent a
category, cannot name a condition, and cannot suggest a diagnosis. Its
output is additionally filtered post-hoc against the known list, so even a
misbehaving response can't leak something unexpected into the UI.

This is triage direction, not a diagnosis — the same category of decision
specialist_router.py already makes safely.
"""

import os
import re
from typing import Optional
from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

load_dotenv()

_llm_key = os.getenv("CLARIMED_LLM_KEY", "")
_client = OpenAI(api_key=_llm_key, base_url="https://api.groq.com/openai/v1") if (_llm_key and OpenAI) else None

# The closed list. The LLM may ONLY return one of these exact strings.
BODY_PARTS = [
    "eye", "skin", "nail", "oral", "dental", "ent",
    "hair", "respiratory", "digestive", "musculoskeletal",
    "neurological", "urinary", "reproductive", "general",
]

# Offline fallback: simple keyword -> body part mapping. Deliberately
# conservative — anything unclear routes to "general", which covers
# systemic/unclear complaints and always has a manual override available.
_KEYWORD_ROUTES = [
    (["eye", "vision", "sight", "blurry", "eyesight"], "eye"),
    (["tooth", "teeth", "gum", "dental", "cavity"], "dental"),
    (["mouth", "lips", "tongue", "ulcer in mouth"], "oral"),
    (["ear", "hearing", "nose", "sinus", "throat", "smell", "dizzy", "dizziness", "vertigo", "nosebleed"], "ent"),
    (["hair", "scalp", "dandruff", "bald"], "hair"),
    (["breath", "cough", "wheeze", "chest congestion", "lung"], "respiratory"),
    (["stomach", "abdomen", "digestion", "nausea", "bowel", "diarrhea", "constipation", "vomit", "gastric"], "digestive"),
    (["joint", "muscle", "back", "bone", "sprain", "shoulder", "knee", "leg pain", "sciatica"], "musculoskeletal"),
    (["seizure", "convulsion", "tremor", "memory loss", "confusion", "numbness", "tingling", "stroke", "slurred", "drooping"], "neurological"),
    (["urinat", "urine", "bladder", "kidney stone"], "urinary"),
    (["period", "menstrual", "pregnan", "vaginal", "menopause", "pcos"], "reproductive"),
    (["nail"], "nail"),
    (["skin", "rash", "itch", "acne", "pimple", "bruise", "mole"], "skin"),
    (["fever", "fatigue", "headache", "body ache", "tired", "sick", "chills"], "general"),
]

SYSTEM_PROMPT = (
    "You classify a patient's free-text description into the body part it most likely "
    "concerns, so the right symptom checklist can be shown. You are NOT diagnosing — "
    "never name a disease or condition, never suggest treatment. Respond with EXACTLY "
    "ONE body part from this list, and nothing else (no punctuation, no explanation):\n"
    + "\n".join(BODY_PARTS)
    + "\nIf the complaint is vague, systemic, or doesn't clearly match a specific body "
    "part (e.g. fever, fatigue, feeling unwell), respond 'general'."
)


def _offline_route(text: str) -> str:
    lowered = text.lower()
    for keywords, body_part in _KEYWORD_ROUTES:
        if any(kw in lowered for kw in keywords):
            return body_part
    return "general"


def route_to_body_part(complaint_text: str) -> str:
    """
    Returns one body part from BODY_PARTS. Always returns something —
    defaults to 'general' rather than leaving the user without a suggestion.
    This is a suggestion the UI pre-selects; the manual button grid always
    remains available as an override.
    """
    text = (complaint_text or "").strip()
    if not text:
        return "general"

    if _client is None:
        return _offline_route(text)

    try:
        response = _client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Patient description: \"{text}\""},
            ],
            temperature=0.0,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"[^a-zA-Z]", "", raw).strip().lower()
        for bp in BODY_PARTS:
            if raw == bp:
                return bp
        # LLM returned something unexpected — fall back rather than trust it
        print(f"[body_part_router] Unexpected LLM output '{raw}', using offline route.")
        return _offline_route(text)
    except Exception as e:
        print(f"[body_part_router] LLM call failed, using offline route: {e}")
        return _offline_route(text)


if __name__ == "__main__":
    tests = [
        ("I fell down while playing and got a bruise on my knee", "musculoskeletal or skin"),
        ("my eyes have been really red and itchy", "eye"),
        ("I have a toothache and my gums are bleeding", "dental"),
        ("I've had a fever and body ache for two days", "general"),
        ("my ears have been ringing and I feel dizzy", "ent"),
        ("I've been coughing a lot and feel breathless", "respiratory"),
        ("my stomach hurts and I have diarrhea", "digestive"),
        ("I have a rash on my arm that's really itchy", "skin"),
        ("not sure, just feel unwell", "general"),
    ]
    print(f"LLM configured: {_client is not None}\n")
    for text, expected_hint in tests:
        result = route_to_body_part(text)
        print(f"  {text!r}\n    -> {result}  (expected roughly: {expected_hint})\n")