"""
tests/test_safety.py

SAFETY-CRITICAL TESTS.

These verify the properties that, if broken, could cause real harm:

  1. A red-flag symptom ALWAYS escalates risk to "red", regardless of what
     the screening engine otherwise concluded. A regression here means a
     patient reporting "loss of bladder control with back pain" (cauda
     equina) or "halos around lights" (acute glaucoma) gets told it's mild.

  2. The confidence floor is enforced. The system must refuse to name a
     condition when nothing matches well, rather than forcing a guess.

  3. The LLM's closed-list constraints hold. The symptom interpreter and
     specialist router must NEVER return a value outside their allowed set,
     even if the model returns garbage.

  4. Non-photographable conditions are never penalised for lacking an image.

If any test in this file fails, do not ship.
"""

import pytest

from ai.rules.condition_engine import (
    fuse, BODY_PART_SYMPTOMS, BODY_PART_REDFLAGS, CONFIDENCE_FLOOR,
    IMAGE_SCORERS, RISK_BASE, match_strength,
)
from ai.rag.kb_loader import load_all_docs
from ai.rag.specialist_router import SPECIALIST_TYPES, _offline_route, route_to_specialist
from ai.rag.symptom_interpreter import _offline_fallback

from tests.conftest import NEUTRAL_FEATURES, RED_FEATURES


ALL_BODY_PARTS = sorted(BODY_PART_SYMPTOMS.keys())


# ---------------------------------------------------------------------------
# 1. Red-flag escalation — the single most important safety property
# ---------------------------------------------------------------------------

def test_every_body_part_has_at_least_one_redflag():
    """A body part with no red flags can never escalate. That's a silent hazard."""
    for bp in ALL_BODY_PARTS:
        flags = BODY_PART_REDFLAGS.get(bp, [])
        assert flags, f"body part '{bp}' has no red-flag symptoms defined"


def test_redflag_always_escalates_risk_to_red():
    """For EVERY body part, EVERY red flag must force risk_level == 'red',
    no matter what the underlying screening result was."""
    for bp in ALL_BODY_PARTS:
        symptoms = BODY_PART_SYMPTOMS[bp][:1]
        for flag in BODY_PART_REDFLAGS[bp]:
            result = fuse(bp, symptoms, dict(NEUTRAL_FEATURES), redflags=[flag])
            assert result["risk_level"] == "red", (
                f"red flag '{flag}' on body part '{bp}' did NOT escalate risk "
                f"(got '{result['risk_level']}')"
            )


def test_redflag_escalates_even_when_top_condition_is_low_risk():
    """A green-baseline condition must still go red if a red flag is present.
    Regression guard: risk must not be read from RISK_BASE when flags exist."""
    # Conjunctivitis (EYE001) has a 'green' baseline.
    assert RISK_BASE["EYE001"] == "green"
    result = fuse(
        "eye", ["Ocular Redness", "Watery Eyes"], dict(RED_FEATURES),
        redflags=["Sudden Vision Loss"],
    )
    assert result["risk_level"] == "red"
    assert "urgent" in result["risk_reason"].lower() or "emergency" in result["risk_reason"].lower()


def test_redflag_escalates_even_when_out_of_coverage():
    """No symptoms, no image, but a red flag reported -> still red, not yellow."""
    result = fuse("eye", [], dict(NEUTRAL_FEATURES), redflags=["Sudden Vision Loss"])
    assert result["risk_level"] == "red"


def test_no_redflags_does_not_produce_red_by_accident():
    """Sanity check the inverse: absence of red flags shouldn't produce red."""
    result = fuse("eye", ["Ocular Redness"], dict(RED_FEATURES), redflags=[])
    assert result["risk_level"] in ("green", "yellow")


# ---------------------------------------------------------------------------
# 2. Confidence floor — refuse to guess
# ---------------------------------------------------------------------------

def test_no_symptoms_no_image_is_out_of_coverage():
    """With zero evidence the system must not name a condition."""
    for bp in ALL_BODY_PARTS:
        result = fuse(bp, [], dict(NEUTRAL_FEATURES))
        assert result["out_of_coverage"] is True, f"'{bp}' named a condition with no evidence"
        assert result["top"] is None


def test_out_of_coverage_never_returns_a_top_condition():
    """Structural invariant: out_of_coverage implies top is None."""
    for bp in ALL_BODY_PARTS:
        for syms in ([], BODY_PART_SYMPTOMS[bp][:1]):
            result = fuse(bp, syms, dict(NEUTRAL_FEATURES))
            if result["out_of_coverage"]:
                assert result["top"] is None


def test_confidence_floor_is_actually_applied():
    """Any named top condition must score at or above the floor."""
    for bp in ALL_BODY_PARTS:
        result = fuse(bp, BODY_PART_SYMPTOMS[bp][:3], dict(RED_FEATURES))
        if not result["out_of_coverage"]:
            assert result["top"]["fused_raw"] >= CONFIDENCE_FLOOR


def test_out_of_coverage_still_yields_a_safe_risk_level():
    """Unknown must never be presented as 'green' / low risk."""
    result = fuse("eye", [], dict(NEUTRAL_FEATURES))
    assert result["risk_level"] in ("yellow", "red")


# ---------------------------------------------------------------------------
# 3. Closed-list constraints on LLM-assisted components
# ---------------------------------------------------------------------------

def test_specialist_router_offline_never_leaves_the_closed_list():
    probes = [
        "pain in my left thigh", "my ears ring", "burning stomach",
        "", "asdfghjkl nonsense", "I feel unwell", "chest hurts",
        "blood in urine", "anxious and panicking", "my tooth aches",
    ]
    for p in probes:
        assert _offline_route(p) in SPECIALIST_TYPES


def test_specialist_router_public_api_never_leaves_the_closed_list():
    """route_to_specialist() must be safe even with no LLM configured."""
    for p in ["pain in my left thigh", "", "   ", "zzzz"]:
        assert route_to_specialist(p) in SPECIALIST_TYPES


def test_specialist_router_defaults_to_general_physician_when_unclear():
    """Ambiguity must route somewhere safe that can refer onward — never
    a random guess at a narrow specialty."""
    assert _offline_route("not sure, just feel unwell") == "General Physician"
    assert _offline_route("") == "General Physician"


def test_symptom_interpreter_offline_never_invents_a_symptom():
    """The interpreter may only return symptoms from the provided list."""
    for bp in ALL_BODY_PARTS:
        known = BODY_PART_SYMPTOMS[bp]
        for text in [
            "everything hurts everywhere",
            "I have a rare tropical disease",
            "",
            "redness and swelling and pain and fever and nausea",
        ]:
            matched = _offline_fallback(text, known)
            for m in matched:
                assert m in known, f"interpreter invented symptom '{m}' for body part '{bp}'"


def test_symptom_interpreter_returns_empty_for_empty_input():
    assert _offline_fallback("", BODY_PART_SYMPTOMS["eye"]) == []


# ---------------------------------------------------------------------------
# 4. Non-photographable conditions must not be penalised
# ---------------------------------------------------------------------------

NON_PHOTOGRAPHABLE_PREFIXES = ("GEN", "RESP", "DIG", "MSK")


def test_non_photographable_conditions_have_no_image_scorer():
    """If one of these ever gains an image scorer, it would be scored on
    pixel noise from a photo that cannot possibly show the condition."""
    for cid in IMAGE_SCORERS:
        assert not cid.startswith(NON_PHOTOGRAPHABLE_PREFIXES), (
            f"{cid} has an image scorer but is not photographable"
        )


def test_symptom_only_conditions_can_reach_full_strength():
    """A perfect symptom match with no image must not be capped at 50%.
    Regression guard for the image-weight fairness fix."""
    result = fuse("general", ["Fever", "Body Ache", "Fatigue"], dict(NEUTRAL_FEATURES))
    top = result["top"]
    assert top is not None
    assert top["image_relevant"] is False
    assert top["img_score"] is None
    assert top["strength_raw"] >= 0.99, (
        f"symptom-only condition capped at {top['strength_raw']} — image weight leaked in"
    )


def test_symptom_only_conditions_report_image_not_relevant():
    for bp in ("general", "respiratory", "digestive", "musculoskeletal"):
        result = fuse(bp, BODY_PART_SYMPTOMS[bp][:2], dict(NEUTRAL_FEATURES))
        for c in result["candidates"]:
            assert c["image_relevant"] is False
            assert c["img_score"] is None


def test_image_scorers_never_run_when_no_image_was_provided():
    """REGRESSION GUARD.

    Several scorers contain inverted terms like `(1 - whiteness)`. Applied to
    the all-zero placeholder feature dict used when no photo is uploaded,
    those invert to 1.0. Tooth Decay scored 0.60 and Alopecia Areata scored
    0.90 from no evidence whatsoever — past the confidence floor.

    With no image, no condition may be scored on image features.
    """
    for bp in ALL_BODY_PARTS:
        result = fuse(bp, BODY_PART_SYMPTOMS[bp][:1], dict(NEUTRAL_FEATURES), image_provided=False)
        for c in result["candidates"]:
            assert c["image_relevant"] is False, (
                f"{c['id']} claims image relevance with no image provided"
            )
            assert c["img_score"] is None, (
                f"{c['id']} produced an image score of {c['img_score']} with no image"
            )


def test_no_condition_is_named_from_a_placeholder_image_alone():
    """Zero symptoms, no image: every body part must be out_of_coverage.
    Directly guards the Tooth Decay / Cataract / Alopecia false positives."""
    for bp in ALL_BODY_PARTS:
        result = fuse(bp, [], dict(NEUTRAL_FEATURES), image_provided=False)
        assert result["out_of_coverage"] is True, (
            f"'{bp}' named '{result['top']['name'] if result['top'] else '?'}' "
            "from a placeholder image and no symptoms"
        )


def test_image_scoring_resumes_when_an_image_is_provided():
    """The guard must not permanently disable image scoring."""
    result = fuse(
        "skin", ["Redness"],
        {"redness": 0.9, "yellowness": 0.05, "whiteness": 0.05,
         "variance": 0.35, "brightness": 150.0, "sharpness": 12.0},
        image_provided=True,
    )
    photographable = [c for c in result["candidates"] if c["image_relevant"]]
    assert photographable, "no condition used the image even though one was provided"
    assert all(c["img_score"] is not None for c in photographable)


# ---------------------------------------------------------------------------
# 5. Presentation honesty — match strength must not be a probability
# ---------------------------------------------------------------------------

def test_thin_evidence_suppresses_ranking():
    """One symptom, no image -> the system must NOT claim a reliable ranking.
    This is the bug that showed 'Asthma 33%' to a patient reporting one symptom."""
    result = fuse("respiratory", ["Coughing At Night"], dict(NEUTRAL_FEATURES))
    assert result["ranking_reliable"] is False
    assert result["evidence"]["symptoms_reported"] == 1
    assert result["evidence"]["image_provided"] is False


def test_strong_distinct_evidence_allows_ranking():
    """The suppression must not be permanent — genuinely separable cases rank."""
    result = fuse(
        "nail", ["Yellow Nails", "Thickened Nails", "Brittle Nails"],
        {"redness": 0.05, "yellowness": 0.9, "whiteness": 0.1,
         "variance": 0.4, "brightness": 150.0, "sharpness": 12.0},
        image_provided=True,
    )
    assert result["ranking_reliable"] is True
    assert result["top"]["name"] == "Onychomycosis"


def test_match_strength_is_absolute_not_relative():
    """Match strength must derive from the absolute score, never the share."""
    assert match_strength(0.95) == "Strong match"
    assert match_strength(0.60) == "Moderate match"
    assert match_strength(0.10) == "Weak match"


def test_fuse_always_returns_the_full_result_shape():
    """The frontend destructures these keys. A missing key is a white screen."""
    required = {
        "body_part", "candidates", "top", "out_of_coverage",
        "ranking_reliable", "evidence", "risk_level", "risk_reason",
    }
    # Normal path
    r1 = fuse("eye", ["Ocular Redness"], dict(RED_FEATURES))
    assert required <= set(r1)
    # Unknown body part -> early return path (a real past bug)
    r2 = fuse("nonexistent_body_part", ["whatever"], dict(NEUTRAL_FEATURES))
    assert required <= set(r2)
    assert r2["out_of_coverage"] is True


def test_evidence_reports_image_provided_accurately():
    r_no = fuse("eye", ["Ocular Redness"], dict(RED_FEATURES), image_provided=False)
    r_yes = fuse("eye", ["Ocular Redness"], dict(RED_FEATURES), image_provided=True)
    assert r_no["evidence"]["image_provided"] is False
    assert r_yes["evidence"]["image_provided"] is True


# ---------------------------------------------------------------------------
# 6. Emergency-capable conditions must be flagged as such in the KB
# ---------------------------------------------------------------------------

EMERGENCY_CONDITIONS = {
    "EYE006",  # Glaucoma
    "EYE007",  # Corneal Ulcer
    "SKIN007",  # Cellulitis
    "RESP002",  # Asthma
    "RESP003",  # Pneumonia
    "MSK004",  # Low Back Pain (cauda equina red flags)
}


def test_known_emergency_conditions_are_marked_emergency_possible():
    docs = {d["id"]: d for d in load_all_docs()}
    for cid in EMERGENCY_CONDITIONS:
        assert cid in docs, f"expected condition {cid} missing from knowledge base"
        assert docs[cid]["emergency_possible"] is True, (
            f"{cid} ({docs[cid]['disease_name']}) can be an emergency but is not marked as such"
        )