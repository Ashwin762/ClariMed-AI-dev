"""
ai/rules/condition_engine.py

The real scoring engine. Replaces the old single line in main.py:
    if any(x in symptoms for x in ["crust formation", "discharge"]):
        detected_target = "conjunctivitis"

What this does instead:
  1. Loads all 11 curated knowledge-base documents (ai/rag/kb_loader.py)
  2. For the patient's selected body part, scores EVERY matching condition using:
       - image_score : heuristic pixel-derived score (ai/vision/image_analysis.py)
       - symptom_score: overlap between selected symptoms and the doc's
                         authored `keywords` frontmatter (no hardcoded duplicate
                         weight tables needed — it reads your real KB content)
  3. Fuses both into a ranked list, normalized to percentages
  4. Applies a CONFIDENCE FLOOR: if nothing scores well enough, it does NOT
     force a guess — it honestly reports "outside current KB coverage"
  5. Determines a risk level (green/yellow/red), escalating to red on any
     reported red-flag / emergency symptom regardless of the top condition
"""

from __future__ import annotations
import re
from typing import List, Dict, Any, Optional

from ai.rag.kb_loader import load_all_docs

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
CONFIDENCE_FLOOR = 0.30   # below this raw fused score, we refuse to name a condition
IMAGE_WEIGHT = 0.5
SYMPTOM_WEIGHT = 0.5

# ---------------------------------------------------------------------------
# Body-part symptom checklists shown in the UI (kept here so backend + frontend
# can stay in sync on exact wording)
# ---------------------------------------------------------------------------
BODY_PART_SYMPTOMS = {
    "eye": ["Ocular Redness", "Watery Eyes", "Itching", "Burning Sensation", "Dryness", "Crust Formation", "Swelling", "Blurred Vision"],
    "skin": ["Itching", "Redness", "Burning Sensation", "Swelling", "Skin Peeling", "Ring-shaped Patch"],
    "nail": ["Yellow Nails", "Thickened Nails", "White Spots", "Brittle Nails", "Pain Around Nail", "Swelling"],
}

BODY_PART_REDFLAGS = {
    "eye": ["Sudden Vision Loss", "Severe Pain With Halos Around Lights"],
    "skin": ["Rapidly Spreading Redness With Fever"],
    "nail": ["Pus Discharge With Fever"],
}

# Baseline severity per condition id (overridden to "red" if a red-flag was selected)
RISK_BASE = {
    "EYE001": "green", "EYE002": "green",
    "SKIN001": "green", "SKIN002": "yellow", "SKIN003": "yellow", "SKIN004": "yellow", "SKIN005": "yellow",
    "NAIL001": "yellow", "NAIL002": "yellow", "NAIL003": "green", "NAIL004": "green",
}

# ---------------------------------------------------------------------------
# Image scoring functions per condition (uses the real pixel features from
# ai/vision/image_analysis.py — redness, yellowness, whiteness, variance)
# ---------------------------------------------------------------------------
IMAGE_SCORERS = {
    "EYE001": lambda f: 0.8 * f["redness"] + 0.2 * f["variance"],                       # Conjunctivitis
    "EYE002": lambda f: 0.4 * f["redness"] + 0.2 * (1 - f["variance"]),                 # Dry Eye
    "SKIN001": lambda f: 0.7 * f["redness"] + 0.3 * f["variance"],                      # Acne
    "SKIN002": lambda f: 0.5 * f["variance"] + 0.5 * f["redness"],                      # Eczema
    "SKIN003": lambda f: 0.65 * f["redness"] + 0.35 * f["variance"],                    # Contact Dermatitis
    "SKIN004": lambda f: 0.6 * f["variance"] + 0.4 * f["redness"],                      # Ringworm
    "SKIN005": lambda f: 0.6 * f["whiteness"] + 0.4 * f["variance"],                    # Psoriasis
    "NAIL001": lambda f: 0.75 * f["yellowness"] + 0.25 * f["variance"],                 # Onychomycosis
    "NAIL002": lambda f: 0.7 * f["redness"] + 0.3 * f["variance"],                      # Paronychia
    "NAIL003": lambda f: 0.55 * f["redness"] + 0.2 * f["variance"],                     # Ingrown Nail
    "NAIL004": lambda f: 0.7 * f["whiteness"] + 0.3 * f["variance"],                    # Nail Psoriasis
}


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _tokens(s: str) -> List[str]:
    return [t for t in re.findall(r"[a-zA-Z]+", s.lower()) if len(t) >= 3]


def _keyword_overlap(symptom_label: str, keyword: str) -> bool:
    """Loose match: shares a token, or one token is a prefix of the other
    (handles 'redness' vs 'red eye', 'watery eyes' vs 'watery eyes', etc.)"""
    sym_tokens = _tokens(symptom_label)
    kw_tokens = _tokens(keyword)
    for a in sym_tokens:
        for b in kw_tokens:
            if a == b or a.startswith(b) or b.startswith(a):
                return True
    return False


def _symptom_score(doc: Dict[str, Any], selected_symptoms: List[str]):
    matched = []
    for sym in selected_symptoms:
        if any(_keyword_overlap(sym, kw) for kw in doc["keywords"]):
            matched.append(sym)
    # Normalize: 3 matched signals ~= full confidence from symptoms alone
    score = _clamp01(len(matched) / 3.0)
    return score, matched


_ALL_DOCS = load_all_docs()


def _docs_for_body_part(body_part: str) -> List[Dict[str, Any]]:
    return [d for d in _ALL_DOCS if d["body_part"] == body_part.lower()]


def fuse(body_part: str, selected_symptoms: List[str], features: Dict[str, Any],
         redflags: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Main entry point. Returns a dict:
      {
        "body_part": ...,
        "candidates": [ {id, name, specialist, pct, img_score, sym_score,
                          matched_keywords, emergency_possible}, ... ]  # sorted desc
        "top": candidate or None,
        "out_of_coverage": bool,
        "risk_level": "green"|"yellow"|"red",
        "risk_reason": str,
      }
    """
    redflags = redflags or []
    docs = _docs_for_body_part(body_part)

    if not docs:
        return {
            "body_part": body_part, "candidates": [], "top": None,
            "out_of_coverage": True, "risk_level": "yellow",
            "risk_reason": f"No knowledge base coverage for body part '{body_part}' yet.",
        }

    scored = []
    for doc in docs:
        img_scorer = IMAGE_SCORERS.get(doc["id"])
        img_score = _clamp01(img_scorer(features)) if img_scorer else 0.0
        sym_score, matched = _symptom_score(doc, selected_symptoms)
        fused = IMAGE_WEIGHT * img_score + SYMPTOM_WEIGHT * sym_score
        scored.append({
            "id": doc["id"],
            "name": doc["disease_name"],
            "specialist": doc["specialist"],
            "emergency_possible": doc["emergency_possible"],
            "fused_raw": fused,
            "img_score": round(img_score, 3),
            "sym_score": round(sym_score, 3),
            "matched_keywords": matched,
        })

    total = sum(c["fused_raw"] for c in scored) or 1.0
    for c in scored:
        c["pct"] = round((c["fused_raw"] / total) * 100)
    scored.sort(key=lambda c: c["fused_raw"], reverse=True)

    top = scored[0] if scored else None
    out_of_coverage = (top is None) or (top["fused_raw"] < CONFIDENCE_FLOOR)

    # --- Risk level ---
    if redflags:
        risk_level = "red"
        risk_reason = "Red-flag / emergency symptom reported — needs urgent in-person evaluation."
    elif out_of_coverage:
        risk_level = "yellow"
        risk_reason = "Findings don't clearly match a known condition in the knowledge base — a professional evaluation is recommended."
    else:
        risk_level = RISK_BASE.get(top["id"], "yellow")
        risk_reason = f"Based on preliminary screening for {top['name']}."

    return {
        "body_part": body_part,
        "candidates": scored[:3],
        "top": None if out_of_coverage else top,
        "out_of_coverage": out_of_coverage,
        "risk_level": risk_level,
        "risk_reason": risk_reason,
    }


if __name__ == "__main__":
    # Quick smoke test with fake feature values (no image needed)
    fake_features_red_eye = {"redness": 0.7, "yellowness": 0.1, "whiteness": 0.1, "variance": 0.3, "brightness": 150, "sharpness": 10}
    r1 = fuse("eye", ["Ocular Redness", "Watery Eyes", "Itching"], fake_features_red_eye)
    print("Test 1 (should lean Conjunctivitis):")
    print(f"  top = {r1['top']['name'] if r1['top'] else None}, risk = {r1['risk_level']}")
    for c in r1["candidates"]:
        print(f"    {c['id']} {c['name']:20s} pct={c['pct']:>3}% matched={c['matched_keywords']}")

    fake_features_bland = {"redness": 0.1, "yellowness": 0.05, "whiteness": 0.05, "variance": 0.1, "brightness": 150, "sharpness": 10}
    r2 = fuse("eye", [], fake_features_bland)
    print("\nTest 2 (no symptoms, bland image -> should be out_of_coverage):")
    print(f"  out_of_coverage = {r2['out_of_coverage']}, top = {r2['top']}")

    r3 = fuse("eye", ["Ocular Redness"], fake_features_red_eye, redflags=["Sudden Vision Loss"])
    print("\nTest 3 (red-flag present -> risk should be red regardless of match):")
    print(f"  risk_level = {r3['risk_level']}")