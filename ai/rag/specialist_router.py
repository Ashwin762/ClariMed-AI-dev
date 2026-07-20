"""
ai/rag/specialist_router.py

When a case falls OUTSIDE the curated knowledge base (condition_engine's
confidence floor was not met), we still want to tell the patient WHICH KIND
of doctor to see — "just see a doctor" is unhelpful when someone reports
e.g. "pain in left thigh" and has no idea whether that's an orthopedist,
a physiotherapist, or a GP.

SAFETY DESIGN (same principle as symptom_interpreter.py):
The LLM selects from a CLOSED LIST of specialist types. It cannot invent a
specialty, cannot name a condition, and cannot suggest treatment. Its output
is additionally filtered post-hoc against the known list, so even a
misbehaving response can't leak something unexpected into the UI.

Routing to a specialist is NOT a diagnosis — it's triage direction, the same
thing a hospital front desk does before any doctor sees you.
"""

import os
import re
from typing import Optional
from dotenv import load_dotenv

import logging

load_dotenv()

logger = logging.getLogger("clarimed.specialist_router")

from ai.rag.llm_client import get_llm_client, PROMPT_INJECTION_GUARD, wrap_patient_text

_client = get_llm_client()

# The closed list. The LLM may ONLY return one of these exact strings.
SPECIALIST_TYPES = [
    "General Physician",
    "Dermatologist",
    "Ophthalmologist",
    "Dentist",
    "Orthopedist",
    "ENT Specialist",
    "Gastroenterologist",
    "Neurologist",
    "Cardiologist",
    "Pulmonologist",
    "Gynecologist",
    "Urologist",
    "Psychiatrist",
    "Pediatrician",
]

# Offline fallback: simple keyword -> specialist mapping. Deliberately
# conservative — anything unclear routes to General Physician, who can refer on.
_KEYWORD_ROUTES = [
    (["bone", "joint", "knee", "thigh", "shoulder", "back", "muscle", "sprain", "fracture", "hip", "ankle", "wrist"], "Orthopedist"),
    (["ear", "nose", "throat", "sinus", "hearing", "tonsil", "voice", "snoring"], "ENT Specialist"),
    (["stomach", "abdomen", "digestion", "nausea", "vomit", "diarrhea", "constipation", "bowel", "acid", "liver"], "Gastroenterologist"),
    (["headache", "migraine", "seizure", "numbness", "tingling", "dizzy", "memory", "tremor"], "Neurologist"),
    (["chest", "heart", "palpitation", "blood pressure", "cholesterol"], "Cardiologist"),
    (["breath", "cough", "wheeze", "asthma", "lung", "chest congestion"], "Pulmonologist"),
    (["skin", "rash", "itch", "acne", "mole", "eczema"], "Dermatologist"),
    (["eye", "vision", "sight", "blurred"], "Ophthalmologist"),
    (["tooth", "teeth", "gum", "dental", "cavity", "mouth"], "Dentist"),
    (["urine", "urinary", "bladder", "kidney", "prostate"], "Urologist"),
    (["period", "menstrual", "pregnan", "vaginal", "uterus"], "Gynecologist"),
    (["anxiety", "depress", "panic", "mood", "sleep problem", "stress"], "Psychiatrist"),
]

SYSTEM_PROMPT = (
    "You route a patient to the correct TYPE of medical specialist based on their described "
    "complaint. You are NOT diagnosing — never name a disease or condition, never suggest "
    "treatment or medication. Respond with EXACTLY ONE specialist name from this list, and "
    "nothing else (no punctuation, no explanation):\n"
    + "\n".join(SPECIALIST_TYPES)
    + "\nIf the complaint is vague, unclear, or spans multiple systems, respond 'General Physician'.\n"
    + PROMPT_INJECTION_GUARD
)


def _offline_route(text: str) -> str:
    lowered = text.lower()
    for keywords, specialist in _KEYWORD_ROUTES:
        if any(kw in lowered for kw in keywords):
            return specialist
    return "General Physician"


def route_to_specialist(complaint_text: str, selected_symptoms: Optional[list] = None) -> str:
    """
    Returns one specialist type from SPECIALIST_TYPES. Always returns something —
    defaults to General Physician, who can refer onward, rather than leaving the
    patient with no direction at all.
    """
    combined = " ".join(filter(None, [complaint_text or "", " ".join(selected_symptoms or [])])).strip()
    if not combined:
        return "General Physician"

    if _client is None:
        return _offline_route(combined)

    try:
        response = _client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": wrap_patient_text("Patient complaint", combined)},
            ],
            temperature=0.0,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"[^A-Za-z ]", "", raw).strip()
        # Safety filter: only accept an exact match from the closed list
        for s in SPECIALIST_TYPES:
            if raw.lower() == s.lower():
                return s
        # LLM returned something unexpected — fall back rather than trust it
        logger.warning("Unexpected LLM output %r, using offline route.", raw)
        return _offline_route(combined)
    except Exception as e:
        logger.warning("LLM call failed, using offline route: %s", e)
        return _offline_route(combined)


if __name__ == "__main__":
    tests = [
        "pain in my left thigh when I walk",
        "my ears have been ringing for a week",
        "burning feeling in my stomach after eating",
        "not sure, just feel unwell",
    ]
    print(f"LLM configured: {_client is not None}\n")
    for t in tests:
        print(f"  {t!r}\n    -> {route_to_specialist(t)}")