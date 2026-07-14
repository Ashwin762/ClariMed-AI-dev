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
    "eye": ["Ocular Redness", "Watery Eyes", "Itching", "Burning Sensation", "Dryness", "Crust Formation", "Swelling", "Blurred Vision", "Eye Pain", "Light Sensitivity", "Floaters or Flashes of Light", "Eye Strain or Tired Eyes"],
    "skin": ["Itching", "Redness", "Burning Sensation", "Swelling", "Skin Peeling", "Ring-shaped Patch", "White/Pale Patches", "Warmth", "Raised Bumps or Welts", "Painful Lump or Boil", "Skin Growth or Wart", "Dark Patches or Pigmentation"],
    "nail": ["Yellow Nails", "Thickened Nails", "White Spots", "Brittle Nails", "Pain Around Nail", "Swelling", "Nail Injury or Bruising", "Curved or Clubbed Nails"],
    "oral": ["White Patches", "Mouth Ulcers", "Bleeding Gums", "Bad Breath", "Burning Sensation", "Tingling Before Sores", "Pain While Chewing", "Dry Mouth", "Difficulty Swallowing"],
    "dental": ["Tooth Pain", "Tooth Sensitivity", "Dark Spots On Tooth", "Pain While Chewing", "Bleeding Gums", "Receding Gums", "Loose Teeth", "Bad Breath", "Jaw Pain", "Teeth Grinding", "Facial Swelling", "Difficulty Opening Mouth"],
    "ent": ["Ear Pain", "Hearing Difficulty", "Ear Discharge", "Sore Throat", "Difficulty Swallowing", "Nasal Congestion", "Facial Pain", "Sneezing", "Runny Nose", "Itchy Nose", "Swollen Tonsils", "Fever", "Dizziness or Spinning Sensation", "Balance Problems", "Nosebleed", "Ringing in Ears", "Loss of Smell", "Object Stuck in Ear or Nose"],
    "hair": ["Scalp Flaking", "Itchy Scalp", "Hair Loss", "Bald Patches", "Scalp Bumps", "Scalp Redness", "Tender Scalp", "Lice or Nits in Hair"],
    "respiratory": ["Persistent Cough", "Chest Congestion", "Wheezing", "Shortness Of Breath", "Chest Tightness", "Fever", "Chills", "Chest Pain When Breathing", "Coughing At Night", "Coughing Blood", "Night Sweats", "Weight Loss", "Rapid Breathing"],
    "digestive": ["Heartburn", "Abdominal Pain", "Bloating", "Nausea", "Diarrhea", "Constipation", "Acid Taste", "Cramping", "Straining", "Burning Stomach Pain", "Rectal Bleeding", "Rectal Pain or Itching", "Vomiting", "Loss of Appetite", "Fever", "Yellowing of Eyes or Skin", "Black Stools", "Weight Loss"],
    "musculoskeletal": ["Joint Pain", "Muscle Pain", "Stiffness", "Swelling", "Limited Movement", "Pain With Movement", "Back Pain", "Tenderness", "Morning Stiffness", "Joint Swelling", "Leg Pain Radiating from Back", "Shoulder Stiffness", "Joint Redness and Warmth", "Numbness or Tingling in Hand", "Weak Grip", "Heel Pain", "Visible Deformity or Injury", "Chronic Fatigue"],
    "general": ["Fever", "Fatigue", "Headache", "Body Ache", "Sore Throat", "Runny Nose", "Nausea", "Vomiting", "Diarrhea", "Sensitivity to Light", "Rash", "Joint Pain", "Bleeding Gums or Nose", "Yellowing of Skin or Eyes", "Pale Skin", "Swelling of Face or Lips", "Hives or Itchy Rash", "Pain Behind Eyes", "Dizziness", "Rapid Heartbeat", "Chest Tightness", "Excessive Sweating", "Numbness or Tingling"],
    "neurological": ["Seizure or Convulsions", "Loss of Consciousness", "Face Drooping", "Arm Weakness", "Slurred Speech", "Sudden Numbness", "Hand Tremor", "Memory Loss or Confusion", "Difficulty Remembering", "Numbness or Tingling", "Burning Sensation in Limbs"],
    "urinary": ["Burning While Urinating", "Painful Urination", "Frequent Urination", "Cloudy Urine", "Blood in Urine", "Severe Side or Back Pain", "Urine Leakage", "Loss of Bladder Control", "Lower Abdominal Pain"],
    "reproductive": ["Irregular Periods", "Missed Periods", "Heavy Periods", "Painful Periods", "Excessive Facial Hair", "Abnormal Vaginal Discharge", "Vaginal Itching", "Hot Flashes", "Night Sweats", "Vaginal Dryness", "Missed Period or Pregnancy Signs", "Abdominal Pain During Pregnancy"],
}

BODY_PART_REDFLAGS = {
    "eye": ["Sudden Vision Loss", "Severe Pain With Halos Around Lights"],
    "nail": ["Pus Discharge With Fever"],
    "oral": ["Difficulty Swallowing or Breathing"],
    "dental": ["Facial Swelling With Fever", "Difficulty Swallowing or Breathing"],
    "ent": ["Difficulty Breathing", "Unable To Swallow Saliva / Drooling", "Swelling Behind The Ear With Fever", "Sudden Dizziness With Slurred Speech Or Weakness"],
    "hair": ["Spreading Redness With Fever"],
    "respiratory": ["Severe Difficulty Breathing", "Coughing Up Blood", "Bluish Lips Or Fingertips"],
    "digestive": ["Vomiting Blood", "Black Tarry Stools", "Severe Chest Pain", "Severe Localized Abdominal Pain With Fever"],
    "musculoskeletal": ["Loss Of Bladder Or Bowel Control", "Numbness In Groin Or Inner Thighs", "Progressive Leg Weakness", "Visible Deformity Or Inability To Move A Limb After Injury"],
    "general": ["High Fever Above 103°F / 39.4°C", "Stiff Neck With Fever", "Severe Dehydration", "Swelling Of Face Lips Or Throat With Difficulty Breathing", "Bleeding Gums Or Nose With High Fever", "Chest Pain Or Pressure With Anxiety Symptoms"],
    "skin": ["Rapidly Spreading Redness With Fever", "Swelling Of Face Lips Or Throat With Difficulty Breathing"],
    "neurological": ["Seizure Or Loss Of Consciousness", "Face Drooping With Slurred Speech Or Arm Weakness"],
    "urinary": ["Blood In Urine With Severe Pain", "Inability To Urinate"],
    "reproductive": ["Severe Abdominal Pain During Pregnancy", "Heavy Vaginal Bleeding"],
}

# Baseline severity per condition id (overridden to "red" if a red-flag was selected)
RISK_BASE = {
    "EYE001": "green", "EYE002": "green", "EYE003": "yellow", "EYE004": "green",
    "EYE005": "green", "EYE006": "yellow", "EYE007": "yellow",
    "SKIN001": "green", "SKIN002": "yellow", "SKIN003": "yellow", "SKIN004": "yellow", "SKIN005": "yellow",
    "SKIN006": "green", "SKIN007": "yellow",
    "NAIL001": "yellow", "NAIL002": "yellow", "NAIL003": "green", "NAIL004": "green",
    "ORAL001": "green", "ORAL002": "green", "ORAL003": "yellow", "ORAL004": "green",
    "GEN001": "green", "GEN002": "yellow", "GEN003": "green", "GEN004": "yellow",
    "GEN005": "yellow", "GEN006": "yellow", "GEN007": "yellow", "GEN008": "green",
    "GEN009": "yellow",
    "DENT001": "yellow", "DENT002": "green", "DENT003": "yellow",
    "ENT001": "yellow", "ENT002": "green", "ENT003": "yellow", "ENT004": "green",
    "ENT005": "yellow", "ENT006": "green",
    "HAIR001": "green", "HAIR002": "green", "HAIR003": "green",
    "RESP001": "yellow", "RESP002": "yellow", "RESP003": "yellow",
    "DIG001": "green", "DIG002": "green", "DIG003": "green",
    "DIG004": "green", "DIG005": "green",
    "MSK001": "green", "MSK002": "yellow", "MSK003": "green", "MSK004": "green",
    "MSK005": "yellow", "MSK006": "green", "MSK007": "yellow",
    # --- New conditions from teammate KB contribution ---
    "DENT004": "yellow", "DENT005": "green", "DENT006": "green",
    "DIG006": "yellow", "DIG007": "yellow", "DIG008": "green", "DIG009": "yellow",
    "ENT007": "green", "ENT008": "green", "ENT009": "yellow",
    "EYE008": "yellow", "EYE009": "yellow", "EYE010": "green",
    "GEN010": "yellow", "GEN011": "green", "GEN012": "yellow", "GEN013": "green",
    "HAIR004": "green", "HAIR005": "green", "HAIR006": "green",
    "MSK008": "green", "MSK009": "yellow", "MSK010": "green", "MSK011": "green", "MSK012": "green",
    "NAIL005": "yellow", "NAIL006": "green",
    "ORAL005": "green", "ORAL006": "green",
    "RESP004": "yellow", "RESP005": "yellow", "RESP006": "yellow",
    "SKIN008": "yellow", "SKIN009": "green", "SKIN010": "yellow", "SKIN011": "green",
    # --- Brand new body parts ---
    "NEUR001": "yellow", "NEUR002": "yellow", "NEUR003": "green", "NEUR004": "yellow", "NEUR005": "green",
    "URIN001": "green", "URIN002": "yellow", "URIN003": "green", "URIN004": "yellow", "URIN005": "green",
    "REPR001": "green", "REPR002": "green", "REPR003": "green", "REPR004": "yellow", "REPR005": "green",
}

# ---------------------------------------------------------------------------
# Image scoring functions per condition (uses the real pixel features from
# ai/vision/image_analysis.py — redness, yellowness, whiteness, variance)
# ---------------------------------------------------------------------------
IMAGE_SCORERS = {
    "EYE001": lambda f: 0.8 * f["redness"] + 0.2 * f["variance"],                       # Conjunctivitis
    "EYE002": lambda f: 0.4 * f["redness"] + 0.2 * (1 - f["variance"]),                 # Dry Eye
    "EYE003": lambda f: 0.7 * f["whiteness"] + 0.3 * (1 - f["variance"]),               # Cataract (uniform cloudiness)
    "EYE004": lambda f: 0.5 * f["redness"] + 0.4 * f["variance"],                       # Blepharitis
    "EYE005": lambda f: 0.5 * f["redness"] + 0.5 * f["variance"],                       # Stye (localized bump)
    "EYE006": lambda f: 0.4 * f["redness"] + 0.3 * f["whiteness"] + 0.3 * f["variance"],  # Glaucoma (acute signs)
    "EYE007": lambda f: 0.5 * f["redness"] + 0.4 * f["whiteness"] + 0.1 * f["variance"],  # Corneal Ulcer
    "SKIN001": lambda f: 0.7 * f["redness"] + 0.3 * f["variance"],                      # Acne
    "SKIN002": lambda f: 0.5 * f["variance"] + 0.5 * f["redness"],                      # Eczema
    "SKIN003": lambda f: 0.65 * f["redness"] + 0.35 * f["variance"],                    # Contact Dermatitis
    "SKIN004": lambda f: 0.6 * f["variance"] + 0.4 * f["redness"],                      # Ringworm
    "SKIN005": lambda f: 0.6 * f["whiteness"] + 0.4 * f["variance"],                    # Psoriasis
    "SKIN006": lambda f: 0.8 * f["whiteness"] + 0.1 * (1 - f["variance"]),              # Vitiligo (smooth, not scaly)
    "SKIN007": lambda f: 0.7 * f["redness"] + 0.3 * f["variance"],                      # Cellulitis
    "NAIL001": lambda f: 0.75 * f["yellowness"] + 0.25 * f["variance"],                 # Onychomycosis
    "NAIL002": lambda f: 0.7 * f["redness"] + 0.3 * f["variance"],                      # Paronychia
    "NAIL003": lambda f: 0.55 * f["redness"] + 0.2 * f["variance"],                     # Ingrown Nail
    "NAIL004": lambda f: 0.7 * f["whiteness"] + 0.3 * f["variance"],                    # Nail Psoriasis
    "ORAL001": lambda f: 0.75 * f["whiteness"] + 0.25 * f["variance"],                  # Oral Thrush
    "ORAL002": lambda f: 0.4 * f["whiteness"] + 0.4 * f["redness"] + 0.2 * f["variance"],  # Mouth Ulcers
    "ORAL003": lambda f: 0.7 * f["redness"] + 0.3 * f["variance"],                      # Gingivitis
    "ORAL004": lambda f: 0.6 * f["redness"] + 0.4 * f["variance"],                      # Cold Sores
    "DENT001": lambda f: 0.6 * (1 - f["whiteness"]) + 0.4 * f["variance"],              # Tooth Decay (dark spots = low whiteness)
    "DENT003": lambda f: 0.7 * f["redness"] + 0.3 * f["variance"],                      # Periodontitis (gumline redness)
    "ENT003": lambda f: 0.5 * f["redness"] + 0.3 * f["whiteness"] + 0.2 * f["variance"],  # Tonsillitis (red throat + white patches)
    "HAIR001": lambda f: 0.6 * f["whiteness"] + 0.4 * f["variance"],                    # Dandruff (white flakes, textured)
    "HAIR002": lambda f: 0.7 * (1 - f["variance"]) + 0.2 * (1 - f["redness"]),          # Alopecia (smooth, no redness/scaling)
    "HAIR003": lambda f: 0.6 * f["redness"] + 0.4 * f["variance"],                      # Scalp Folliculitis (red bumps)
    "SKIN008": lambda f: 0.6 * f["redness"] + 0.4 * f["variance"],                      # Hives (red raised welts)
    "SKIN009": lambda f: 0.7 * f["variance"] + 0.3 * (1 - f["redness"]),                # Warts (rough texture, not primarily red)
    "SKIN010": lambda f: 0.6 * f["redness"] + 0.4 * f["variance"],                      # Boils (localized red lump)
    "NAIL005": lambda f: 0.6 * (1 - f["whiteness"]) + 0.4 * f["redness"],               # Nail Trauma (dark/bruised or red)
    "ORAL006": lambda f: 0.75 * f["whiteness"] + 0.25 * f["variance"],                  # Leukoplakia (white patch)
    # NOTE: The following conditions intentionally have NO image scorer because
    # they aren't diagnosable from a standard photo — fuse() detects their
    # absence and scores them on symptoms alone rather than unfairly capping
    # them at 50% for lacking an image signal:
    #   GEN001-004, GEN009 (Common Cold, Viral Fever, Migraine, Food Poisoning, Malaria)
    #   GEN005-008   (Dengue, Typhoid, Allergic Reaction, Anemia — systemic, no visual sign)
    #   DENT002      (Tooth Sensitivity — subtle/no visible sign)
    #   ENT001/2/4/5/6 (Otitis Media, Sinusitis, Allergic Rhinitis, Vertigo, Nosebleed — internal/acute)
    #   RESP001-003  (Bronchitis, Asthma, Pneumonia — internal)
    #   DIG001-005   (Acid Reflux, IBS, Constipation, Gastritis, Hemorrhoids — internal/private)
    #   MSK001-007   (Muscle Strain, Osteoarthritis, Tendinitis, Low Back Pain, Sciatica, Frozen Shoulder, Gout)
}


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


# --- Match strength, measured on the ABSOLUTE fused score (0..1) ---------
#
# IMPORTANT: this is deliberately NOT computed from the normalized share.
# The share (`share_pct`) only says "how does this candidate rank against the
# others we happened to consider" — with 3 similar candidates everything lands
# near 33%, which a patient reads as "1-in-3 chance I have this." That is not
# what we computed. Match strength answers the question people actually mean:
# "how well do my symptoms and image actually fit this condition?"
STRENGTH_STRONG = 0.75
STRENGTH_MODERATE = 0.50

# Ranking is only meaningful when the top candidate genuinely stands apart.
# Below these, we return an UNRANKED list and the UI hides all numbers.
MIN_TOP_STRENGTH_FOR_RANKING = 0.45
MIN_SEPARATION_FOR_RANKING = 0.08


def match_strength(fused_raw: float) -> str:
    if fused_raw >= STRENGTH_STRONG:
        return "Strong match"
    if fused_raw >= STRENGTH_MODERATE:
        return "Moderate match"
    return "Weak match"


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
         redflags: Optional[List[str]] = None, image_provided: bool = False) -> Dict[str, Any]:
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
            "out_of_coverage": True, "ranking_reliable": False,
            "evidence": {
                "symptoms_reported": len(selected_symptoms), "image_provided": bool(image_provided),
                "matched_signals": 0, "candidates_considered": 0, "separation": 0.0,
            },
            "risk_level": "yellow",
            "risk_reason": f"No knowledge base coverage for body part '{body_part}' yet.",
        }

    scored = []
    for doc in docs:
        img_scorer = IMAGE_SCORERS.get(doc["id"])
        sym_score, matched = _symptom_score(doc, selected_symptoms)

        # CRITICAL: only score the image if one was actually provided.
        #
        # When no image is uploaded, callers pass a neutral placeholder feature
        # dict (all zeros). Several scorers contain inverted terms such as
        # `(1 - whiteness)` or `(1 - variance)` — meaning "dark" or "smooth".
        # Applied to all-zero placeholders those invert to 1.0, so Tooth Decay
        # scored 0.60 and Alopecia Areata scored 0.90 from *no evidence at all*,
        # sailing past the confidence floor. A user selecting a body part and
        # nothing else would be confidently told they had a condition.
        #
        # If there is no image, the condition is scored on symptoms alone —
        # exactly as a non-photographable condition is.
        use_image = img_scorer is not None and image_provided

        if use_image:
            img_score = _clamp01(img_scorer(features))
            fused = IMAGE_WEIGHT * img_score + SYMPTOM_WEIGHT * sym_score
            image_relevant = True
        else:
            # Either the condition isn't photographable (fever, back pain), or
            # no photo was supplied. Score on symptoms alone and don't penalise
            # for an image signal that doesn't exist.
            img_score = None
            fused = sym_score
            image_relevant = False

        scored.append({
            "id": doc["id"],
            "name": doc["disease_name"],
            "specialist": doc["specialist"],
            "emergency_possible": doc["emergency_possible"],
            "fused_raw": fused,
            "img_score": round(img_score, 3) if img_score is not None else None,
            "sym_score": round(sym_score, 3),
            "image_relevant": image_relevant,
            "matched_keywords": matched,
        })

    total = sum(c["fused_raw"] for c in scored) or 1.0
    for c in scored:
        # share_pct = relative ranking share only. Explicitly named so nobody
        # mistakes it for a probability. Used for bar widths, never shown bare.
        c["share_pct"] = round((c["fused_raw"] / total) * 100)
        c["match_strength"] = match_strength(c["fused_raw"])
        c["strength_raw"] = round(c["fused_raw"], 3)
    scored.sort(key=lambda c: c["fused_raw"], reverse=True)

    top = scored[0] if scored else None
    out_of_coverage = (top is None) or (top["fused_raw"] < CONFIDENCE_FLOOR)

    # --- Is the ranking actually meaningful? ---
    # With one symptom and no image, several conditions score nearly the same.
    # Ranking them (and showing numbers) implies a precision we don't have.
    separation = 0.0
    if len(scored) >= 2:
        separation = scored[0]["fused_raw"] - scored[1]["fused_raw"]
    ranking_reliable = bool(
        top
        and not out_of_coverage
        and top["fused_raw"] >= MIN_TOP_STRENGTH_FOR_RANKING
        and (len(scored) < 2 or separation >= MIN_SEPARATION_FOR_RANKING)
    )

    # --- Evidence summary: tells the patient WHY the result is uncertain ---
    matched_signal_count = len(top["matched_keywords"]) if top else 0
    evidence = {
        "symptoms_reported": len(selected_symptoms),
        "image_provided": bool(image_provided),
        "matched_signals": matched_signal_count,
        "candidates_considered": len(docs),
        "separation": round(separation, 3),
    }

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
        "ranking_reliable": ranking_reliable,
        "evidence": evidence,
        "risk_level": risk_level,
        "risk_reason": risk_reason,
    }


if __name__ == "__main__":
    bland = {"redness": 0.1, "yellowness": 0.05, "whiteness": 0.05, "variance": 0.1, "brightness": 150, "sharpness": 10}
    red_eye = {"redness": 0.7, "yellowness": 0.1, "whiteness": 0.1, "variance": 0.3, "brightness": 150, "sharpness": 10}

    r1 = fuse("eye", ["Ocular Redness", "Watery Eyes", "Itching"], red_eye, image_provided=True)
    print("Test 1 — rich evidence (3 symptoms + image):")
    print(f"  top={r1['top']['name'] if r1['top'] else None}  ranking_reliable={r1['ranking_reliable']}")
    for c in r1["candidates"]:
        print(f"    {c['id']} {c['name']:20s} strength={c['strength_raw']} ({c['match_strength']})")

    r2 = fuse("eye", [], bland)
    print("\nTest 2 — no evidence -> out_of_coverage:")
    print(f"  out_of_coverage={r2['out_of_coverage']}  top={r2['top']}")

    r3 = fuse("eye", ["Ocular Redness"], red_eye, redflags=["Sudden Vision Loss"], image_provided=True)
    print("\nTest 3 — red flag -> risk red regardless:")
    print(f"  risk_level={r3['risk_level']}")

    # The case that motivated this fix: one symptom, no image, respiratory.
    neutral = {"redness": 0.0, "yellowness": 0.0, "whiteness": 0.0, "variance": 0.0, "brightness": 128, "sharpness": 10}
    r4 = fuse("respiratory", ["Coughing At Night"], neutral)
    print("\nTest 4 — thin evidence (1 symptom, no image) -> ranking must NOT be reliable:")
    print(f"  ranking_reliable={r4['ranking_reliable']}  evidence={r4['evidence']}")
    for c in r4["candidates"]:
        print(f"    {c['name']:20s} strength={c['strength_raw']} ({c['match_strength']})  share={c['share_pct']}%")