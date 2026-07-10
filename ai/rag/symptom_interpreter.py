"""
ai/rag/symptom_interpreter.py

Turns a free-text symptom description (typed or from voice input) into
matches against our KNOWN symptom checklist for a body part — the same
list already shown as checkboxes in the UI.

CRITICAL SAFETY DESIGN: the LLM here is used strictly as a MAPPER, not a
diagnoser. It is only allowed to select from a provided closed list of
symptoms — it cannot invent new symptoms and is explicitly told not to
name a condition. This keeps the actual diagnosis reasoning entirely
inside condition_engine.py's deterministic, traceable logic. The LLM's
only job is "which of these known symptoms does this text describe" —
a narrow, checkable task, not open-ended medical reasoning.

Falls back to simple offline token matching if no LLM key is configured,
so free-text input still works (just less flexibly) with zero internet.
"""

import os
import json
import re
from typing import List
from dotenv import load_dotenv

# The offline fallback must work even if `openai` isn't installed at all.
# Importing it at module level would make the offline path depend on the
# online library — exactly backwards.
try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

load_dotenv()

_llm_key = os.getenv("CLARIMED_LLM_KEY", "")
_client = OpenAI(api_key=_llm_key, base_url="https://api.groq.com/openai/v1") if (_llm_key and OpenAI) else None

SYSTEM_PROMPT = (
    "You map a patient's free-text description onto a fixed list of known symptoms. "
    "You are NOT a diagnostic tool — never name a disease or condition, only select from "
    "the given symptom list. Respond with ONLY a JSON array of strings, each one an exact "
    "match from the provided list. If nothing matches, respond with an empty array []. "
    "Do not add any symptom not present in the provided list, even if it seems related."
)


def _offline_fallback(text: str, known_symptoms: List[str]) -> List[str]:
    """Simple token-overlap matching, used when no LLM key is configured."""
    text_lower = text.lower()
    matched = []
    for sym in known_symptoms:
        tokens = [t for t in re.findall(r"[a-zA-Z]+", sym.lower()) if len(t) >= 3]
        if any(tok in text_lower for tok in tokens):
            matched.append(sym)
    return matched


def interpret_symptoms(text: str, known_symptoms: List[str]) -> List[str]:
    """
    Returns a subset of known_symptoms that the free-text description matches.
    Never returns anything outside known_symptoms (enforced both by prompt AND
    by a post-hoc filter below, so even a misbehaving LLM response can't leak
    an invented symptom into the scoring engine).
    """
    if not text or not text.strip():
        return []

    if _client is None:
        return _offline_fallback(text, known_symptoms)

    try:
        user_prompt = f"Known symptom list: {json.dumps(known_symptoms)}\n\nPatient description: \"{text}\""
        response = _client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )
        raw = response.choices[0].message.content.strip()
        # strip markdown code fences if the model added them despite instructions
        raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return _offline_fallback(text, known_symptoms)
        # Safety filter: only allow symptoms that are EXACTLY in the known list
        return [s for s in parsed if s in known_symptoms]
    except Exception as e:
        print(f"[symptom_interpreter] LLM call failed, using offline fallback: {e}")
        return _offline_fallback(text, known_symptoms)


if __name__ == "__main__":
    known = ["Ocular Redness", "Watery Eyes", "Itching", "Burning Sensation", "Dryness", "Crust Formation", "Swelling", "Blurred Vision"]
    test_text = "my eyes have been really red and watery for two days, and they itch a lot"
    result = interpret_symptoms(test_text, known)
    print(f"LLM configured: {_client is not None}")
    print(f"Input: {test_text}")
    print(f"Matched symptoms: {result}")