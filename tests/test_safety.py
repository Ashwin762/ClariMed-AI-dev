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
# Free-text red-flag detection — emergencies described in words, not clicks
# ---------------------------------------------------------------------------

def test_redflags_are_detected_from_free_text_without_a_checkbox():
    """A user describing an emergency in their own words must be caught even
    if they never tick the corresponding checkbox. Uses the same closed-list
    interpreter as symptom matching — red flags are just another closed list."""
    from ai.rules.condition_engine import BODY_PART_REDFLAGS

    cases = [
        ("eye", "I suddenly lost vision in my left eye and it wont come back", "Sudden Vision Loss"),
        ("eye", "my eye hurts really bad and I see halos around every light", "Severe Pain With Halos Around Lights"),
        ("musculoskeletal", "my back hurts and I lost control of my bladder", "Loss Of Bladder Or Bowel Control"),
        ("respiratory", "I genuinely cannot breathe and my lips look blue", "Bluish Lips Or Fingertips"),
        ("digestive", "I just threw up and it looked like blood", "Vomiting Blood"),
    ]
    for bp, text, expected_flag in cases:
        known = BODY_PART_REDFLAGS[bp]
        matched = _offline_fallback(text, known)
        assert expected_flag in matched, (
            f"'{text}' should have triggered '{expected_flag}' for body part '{bp}', "
            f"got {matched}"
        )


def test_redflag_interpreter_never_leaves_its_closed_list():
    """Same safety property as symptom interpretation, applied to red flags:
    the interpreter must never invent a red flag outside the provided list."""
    from ai.rules.condition_engine import BODY_PART_REDFLAGS

    for bp in ALL_BODY_PARTS:
        known = BODY_PART_REDFLAGS[bp]
        for text in [
            "everything is terrible and I might be dying",
            "I have a rare disease nobody has heard of",
            "",
        ]:
            matched = _offline_fallback(text, known)
            for m in matched:
                assert m in known, f"interpreter invented redflag '{m}' for body part '{bp}'"


def test_end_to_end_free_text_emergency_escalates_without_a_checkbox():
    """Full pipeline: free text -> interpreted red flag -> merged into
    redflags -> fuse() escalates risk to red. Mirrors exactly what main.py
    does, without needing FastAPI installed to verify it."""
    from ai.rag.symptom_interpreter import _offline_fallback as interpret
    from ai.rules.condition_engine import BODY_PART_REDFLAGS

    transcript = "I suddenly lost vision in my left eye"
    body_part = "eye"
    symptoms = []  # user ticked nothing
    redflags = []  # user ticked nothing

    known_redflags = BODY_PART_REDFLAGS[body_part]
    interpreted = interpret(transcript, known_redflags)
    for r in interpreted:
        if r not in redflags:
            redflags.append(r)

    assert redflags, "no red flag was interpreted from a clear emergency description"

    result = fuse(body_part, symptoms, dict(NEUTRAL_FEATURES), redflags=redflags)
    assert result["risk_level"] == "red", (
        "an emergency described only in free text, with no checkbox ticked, "
        "did not escalate risk"
    )


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


# ---------------------------------------------------------------------------
# 7. Guidance mode must agree with what the differential tells the user
# ---------------------------------------------------------------------------

def test_guidance_mode_matches_ranking_reliability():
    """REGRESSION GUARD — real user report.

    A bruise photo (fall injury) was screened under Skin. Its coloring scored
    just above the confidence floor against Acne, with no symptom agreement.
    The differential correctly showed 'not confident enough to rank' — but
    the backend still generated a full, committed Acne care plan as guidance.
    The two halves of one response disagreed with each other.

    backend.main.needs_general_guidance() must return True whenever
    ranking_reliable is False, regardless of out_of_coverage, so guidance
    generation and the differential display always agree.
    """
    from backend.main import needs_general_guidance

    cleared_floor_but_unreliable = {"out_of_coverage": False, "ranking_reliable": False}
    assert needs_general_guidance(cleared_floor_but_unreliable) is True, (
        "a match that cleared the confidence floor but isn't reliably ranked "
        "must still get general guidance, not a committed single-condition answer"
    )

    fully_out_of_coverage = {"out_of_coverage": True, "ranking_reliable": False}
    assert needs_general_guidance(fully_out_of_coverage) is True

    genuinely_confident = {"out_of_coverage": False, "ranking_reliable": True}
    assert needs_general_guidance(genuinely_confident) is False, (
        "a genuinely reliable match should still get committed curated-KB guidance"
    )


def test_a_real_engine_result_with_unreliable_ranking_triggers_general_guidance():
    """End-to-end version of the same guard, using the real scoring engine
    rather than a hand-built dict."""
    from backend.main import needs_general_guidance
    from ai.rules.condition_engine import fuse

    # One weak symptom, no image — thin evidence, mirrors the real report.
    neutral = {"redness": 0.0, "yellowness": 0.0, "whiteness": 0.0,
               "variance": 0.0, "brightness": 128.0, "sharpness": 10.0}
    result = fuse("skin", ["Redness"], neutral, image_provided=False)

    if not result["out_of_coverage"]:
        # If it cleared the floor at all on one weak symptom, it must not be
        # treated as reliably ranked.
        assert result["ranking_reliable"] is False
    assert needs_general_guidance(result) is True


# ---------------------------------------------------------------------------
# Known limitation, contained: generic-word keyword collisions
# ---------------------------------------------------------------------------

def test_generic_keyword_collision_does_not_produce_a_false_confident_answer():
    """
    KNOWN LIMITATION, documented and contained.

    _symptom_score() checks whether a selected symptom shares ANY token with
    a condition's keywords — not how strongly or specifically. A symptom
    like "Leg Pain Radiating from Back" shares the generic word "pain" with
    nearly every musculoskeletal condition, so Sciatica, Frozen Shoulder,
    and Gout can score identically even though "radiating" should point
    specifically to Sciatica. This gets more likely as more conditions
    share a body part's common vocabulary.

    This test does NOT assert the matcher picks the "right" condition —
    it asserts the safety net catches the ambiguity: when candidates tie
    or sit too close together, ranking_reliable must be False, so the UI
    shows an honest unranked list instead of confidently naming the wrong
    condition. This is the correct behavior GIVEN the current matcher's
    precision; improving the matcher itself (e.g. weighting keyword
    specificity) is a separate, larger piece of work.
    """
    neutral = {"redness": 0.0, "yellowness": 0.0, "whiteness": 0.0,
               "variance": 0.0, "brightness": 128.0, "sharpness": 10.0}
    result = fuse("musculoskeletal", ["Leg Pain Radiating from Back"], neutral)

    if not result["out_of_coverage"]:
        assert result["ranking_reliable"] is False, (
            "an ambiguous, generically-matching symptom produced a confidently "
            "ranked result — this would present a specific condition name to "
            "the user without adequate justification"
        )


# ---------------------------------------------------------------------------
# Body-part classification for the free-text-first flow
# ---------------------------------------------------------------------------

def test_body_part_router_never_leaves_the_closed_list():
    from ai.rag.body_part_router import _offline_route, BODY_PARTS
    probes = [
        "I fell down while playing and got a bruise",
        "my eyes are red", "", "   ", "asdkfj alksdjf nonsense",
        "I am from Mars", "not sure, just feel unwell",
    ]
    for p in probes:
        assert _offline_route(p) in BODY_PARTS


def test_body_part_router_defaults_to_general_when_unclear():
    from ai.rag.body_part_router import _offline_route
    assert _offline_route("not sure, just feel unwell") == "general"
    assert _offline_route("") == "general"


def test_body_part_router_accuracy_on_realistic_descriptions():
    """Not a safety property, but a real regression guard — if this drops,
    the free-text-first flow starts pre-selecting the wrong category often
    enough to be annoying rather than helpful."""
    from ai.rag.body_part_router import _offline_route
    cases = [
        ("my eyes have been really red and itchy", "eye"),
        ("I have a toothache and my gums are bleeding", "dental"),
        ("my ears have been ringing and I feel dizzy", "ent"),
        ("I've been coughing a lot and feel breathless", "respiratory"),
        ("my stomach hurts and I have diarrhea", "digestive"),
        ("my hair is falling out a lot lately", "hair"),
        ("my nail turned yellow and thick", "nail"),
        ("there are white patches inside my mouth", "oral"),
    ]
    for text, expected in cases:
        assert _offline_route(text) == expected, f"'{text}' -> expected {expected}"


# ---------------------------------------------------------------------------
# Cardiovascular body part (added after a real gap was found: this body part
# was originally scoped in the team content brief alongside Neurological/
# Urinary/Reproductive, but was the only one of the four never actually built)
# ---------------------------------------------------------------------------

def test_heart_attack_warning_signs_escalates_to_red_without_explicit_redflag():
    """Heart Attack Warning Signs must produce risk_level='red' purely from
    matching as the top condition — waiting for a separate red-flag checkbox
    to be ticked would be the wrong design for a condition whose entire
    definition IS the emergency signal."""
    neutral = {"redness": 0.0, "yellowness": 0.0, "whiteness": 0.0,
               "variance": 0.0, "brightness": 128.0, "sharpness": 10.0}
    result = fuse(
        "cardiovascular",
        ["Chest Pain Radiating to Arm or Jaw", "Cold Sweat"],
        neutral,
    )
    assert result["top"] is not None
    assert result["top"]["name"] == "Heart Attack Warning Signs"
    assert result["risk_level"] == "red"


def test_cardiovascular_body_part_has_conditions():
    from ai.rag.kb_loader import load_all_docs
    docs = load_all_docs()
    cardio = [d for d in docs if d["body_part"] == "cardiovascular"]
    assert len(cardio) >= 5


def test_diabetes_dka_redflag_forces_red_risk():
    neutral = {"redness": 0.0, "yellowness": 0.0, "whiteness": 0.0,
               "variance": 0.0, "brightness": 128.0, "sharpness": 10.0}
    result = fuse(
        "general", ["Excessive Thirst"], neutral,
        redflags=["Rapid Breathing Or Confusion With Excessive Thirst And Urination"],
    )
    assert result["risk_level"] == "red"


def test_body_part_router_short_keywords_dont_match_mid_word():
    """Real bug found and fixed: ENT's keyword 'ear' matched as a plain
    substring inside 'heart' (h-EAR-t), silently misrouting any heart-related
    description to Ear/Nose/Throat instead of Cardiovascular. Left-boundary
    matching fixes this while still allowing intentionally prefix-style
    keywords (e.g. 'urinat' -> urinate/urination) to keep working."""
    from ai.rag.body_part_router import _offline_route
    assert _offline_route("my heart has been racing and pounding") == "cardiovascular"
    assert _offline_route("I have chest pain radiating to my arm") == "cardiovascular"
    # the fix must not break the intentional prefix matches elsewhere
    assert _offline_route("it burns when I urinate") == "urinary"
    assert _offline_route("my eyes have been really red and itchy") == "eye"
    assert _offline_route("my periods have been really irregular") == "reproductive"


def test_corneal_ulcer_vs_cataract_have_meaningful_separation():
    """A real gap: localized (ulcer) vs diffuse (cataract) whiteness patterns
    previously scored too close together (margin of only 0.055) for an
    emergency condition vs a routine chronic one. Locks in the wider margin."""
    from ai.rules.condition_engine import IMAGE_SCORERS
    localized = {"redness": 0.45, "yellowness": 0.05, "whiteness": 0.5, "variance": 0.7, "brightness": 140.0, "sharpness": 12.0}
    diffuse = {"redness": 0.1, "yellowness": 0.05, "whiteness": 0.6, "variance": 0.15, "brightness": 140.0, "sharpness": 12.0}
    ulcer_on_localized = IMAGE_SCORERS["EYE007"](localized)
    cataract_on_localized = IMAGE_SCORERS["EYE003"](localized)
    assert ulcer_on_localized - cataract_on_localized > 0.10, (
        "Corneal Ulcer (emergency) doesn't clearly outscore Cataract (routine) "
        "on a localized, sharp-edged pattern -- the two are too easily confused"
    )


def test_red_flag_escalation_ignores_image_quality_entirely():
    """The real safety property: emergency escalation is symptom/red-flag
    driven, never dependent on how strong or weak the image heuristic score
    happens to be. A weak/unremarkable photo must not suppress a red flag."""
    weak_image = {"redness": 0.1, "yellowness": 0.05, "whiteness": 0.1,
                  "variance": 0.1, "brightness": 130.0, "sharpness": 8.0}
    result = fuse("eye", ["Eye Pain"], weak_image, image_provided=True, redflags=["Sudden Vision Loss"])
    assert result["risk_level"] == "red"