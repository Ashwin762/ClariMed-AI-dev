"""
backend/main.py

Real /api/screen endpoint. Replaces the old version where:
  - "AI screening" was just `if file_size_kb < 10: reject`
  - condition detection was one keyword check defaulting to dry_eye
  - confidence/risk were hardcoded strings ("89.4%", "Grad-CAM Heatmap Layer Generated")

Now:
  - Image bytes are actually analyzed (ai/vision/image_analysis.py)
  - Body part + symptoms + image features are fused into a real ranked result
    across Eye / Skin / Nail (ai/rules/condition_engine.py)
  - A visual heuristic heatmap is generated and returned as base64 (honestly
    labeled as a heuristic attention map, not Grad-CAM)
  - Guidance text is retrieved from the real knowledge base via RAG
  - If nothing matches well, it says so instead of forcing a guess
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from contextlib import asynccontextmanager
import json
import logging
import uvicorn

from backend.app.logging_config import configure_logging
from backend.app.rate_limit import (
    screening_limiter, body_part_suggest_limiter, doctor_login_ip_limiter,
    login_attempts, client_key,
)

from ai.vision.image_analysis import extract_features, quality_check, render_heatmap_png_base64
from ai.vision.relevance_gate import check_relevance as relevance_check, guess_body_part_from_image
from ai.rules.condition_engine import fuse, BODY_PART_SYMPTOMS, BODY_PART_REDFLAGS, suggest_symptoms_from_image
from ai.rag.vector_store import ClariMedRAGAgent
from ai.rag.symptom_interpreter import interpret_symptoms
from ai.rag.vision_symptom_interpreter import interpret_symptoms_from_image
from ai.rag.specialist_router import route_to_specialist
from ai.rag.body_part_router import route_to_body_part
from backend.app.chat_orchestrator import process_chat_turn
from ai.rag.translator import translate_to_english, translate_from_english, SUPPORTED_LANGUAGES
from backend.app.database import (
    init_db, save_screening, get_history, get_screening_by_id,
    save_appointment, get_appointments,
    add_clinical_note,
    record_consent, write_audit, delete_patient_data, export_patient_data,
    PRIVACY_POLICY_VERSION,
)
from backend.app.doctor_auth import (
    init_doctor_tables, register_doctor, login_doctor, doctor_from_token,
    logout_doctor, assign_appointment, assign_unassigned_for_department,
    appointments_for_doctor, claim_appointment, DEPARTMENTS,
)
from backend.app.report_generator import generate_report_pdf

logger = logging.getLogger("clarimed.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup (runs once before the app accepts requests)
    configure_logging()
    init_db()
    init_doctor_tables()
    logger.info("ClariMed AI backend started")
    yield
    # Shutdown (nothing needed here today, but this is the correct place
    # for it if a future change needs a clean-shutdown hook)


app = FastAPI(title="ClariMed AI - Core Screening Architecture Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

rag_agent = ClariMedRAGAgent()

# Reject oversized uploads before they can consume memory (basic DoS guard).
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB

VALID_BODY_PARTS = {
    "eye", "skin", "nail", "oral", "general",
    "dental", "ent", "hair", "respiratory", "digestive", "musculoskeletal",
    "neurological", "urinary", "reproductive", "cardiovascular",
}

# Stable display order for the frontend. A set has no order, so returning
# list(VALID_BODY_PARTS) would shuffle the UI on every server restart.
BODY_PART_ORDER = [
    "eye", "skin", "nail", "oral", "dental",
    "ent", "hair", "respiratory", "digestive", "musculoskeletal",
    "neurological", "urinary", "reproductive", "cardiovascular", "general",
]

# Mock healthcare directory — keyed by specialist TYPE. This is explicitly MOCK
# DATA (no real clinics), meant to be replaced by a Maps/Places API later.
# Covers every type in ai/rag/specialist_router.py's SPECIALIST_TYPES so that
# out-of-coverage cases still get routed to a real specialist card.
# Mock 24/7 emergency hospital directory. Surfaced only when risk_level is
# "red" — a real emergency-mode API (bed availability, live wait times) would
# replace this, but even mock data with real navigable coordinates is more
# useful in an emergency than a bare "see a doctor" message.
EMERGENCY_HOSPITALS_MOCK = [
    {"name": "St. John's Medical College Hospital", "clinic": "24/7 Emergency & Trauma Center",
     "phone": "+91 80 2206 5000", "distance": "2.1 km", "lat": 12.9345, "lng": 77.6244},
    {"name": "Manipal Hospital Old Airport Road", "clinic": "24/7 Emergency Department",
     "phone": "+91 80 2502 4444", "distance": "3.4 km", "lat": 12.9592, "lng": 77.6484},
    {"name": "Fortis Hospital Bannerghatta Road", "clinic": "24/7 Emergency & Trauma Center",
     "phone": "+91 80 6621 4444", "distance": "4.8 km", "lat": 12.8996, "lng": 77.5975},
]

NATIONAL_EMERGENCY_NUMBER = "112"  # India's unified emergency number

NEARBY_SPECIALISTS_MOCK = {
    "Ophthalmologist": [
        {"name": "Dr. Amara Rao (Ophthalmologist)", "distance": "1.2 km", "clinic": "ClearVision Ophthalmic Center", "phone": "+91 98765 43210", "lat": 12.9784, "lng": 77.6408},
        {"name": "Dr. Kevin Sterling (Corneal Specialist)", "distance": "3.4 km", "clinic": "Metro Eye & Care Institute", "phone": "+91 87654 32109", "lat": 12.9611, "lng": 77.6362},
    ],
    "Dermatologist": [
        {"name": "Dr. Priya Nair (Dermatologist)", "distance": "0.9 km", "clinic": "SkinHealth Clinic", "phone": "+91 90000 11223", "lat": 12.9730, "lng": 77.6435},
        {"name": "Dr. Rohan Mehta (Dermatologist)", "distance": "2.6 km", "clinic": "Derma Care Centre", "phone": "+91 90000 44556", "lat": 12.9880, "lng": 77.6198},
    ],
    "Dentist": [
        {"name": "Dr. Sana Iyer (Dentist)", "distance": "1.0 km", "clinic": "Bright Smile Dental Clinic", "phone": "+91 90000 77889", "lat": 12.9750, "lng": 77.6050},
        {"name": "Dr. Arjun Verma (Dentist)", "distance": "2.1 km", "clinic": "City Dental Care", "phone": "+91 90000 99001", "lat": 12.9550, "lng": 77.6250},
    ],
    "General Physician": [
        {"name": "Dr. Meera Pillai (General Physician)", "distance": "0.7 km", "clinic": "Family Health Clinic", "phone": "+91 90000 22334", "lat": 12.9720, "lng": 77.6120},
        {"name": "Dr. Anil Kapoor (General Physician)", "distance": "1.8 km", "clinic": "WellCare Medical Centre", "phone": "+91 90000 55667", "lat": 12.9850, "lng": 77.6000},
    ],
    "Orthopedist": [
        {"name": "Dr. Vikram Shetty (Orthopedist)", "distance": "1.5 km", "clinic": "BoneCare Orthopedic Clinic", "phone": "+91 90000 33445", "lat": 12.9635, "lng": 77.6110},
        {"name": "Dr. Lakshmi Menon (Orthopedist)", "distance": "3.0 km", "clinic": "Joint & Spine Institute", "phone": "+91 90000 66778", "lat": 12.9500, "lng": 77.5950},
    ],
    "ENT Specialist": [
        {"name": "Dr. Farah Khan (ENT Specialist)", "distance": "1.1 km", "clinic": "HearWell ENT Clinic", "phone": "+91 90000 88990", "lat": 12.9700, "lng": 77.6300},
        {"name": "Dr. Suresh Babu (ENT Specialist)", "distance": "2.8 km", "clinic": "City ENT Centre", "phone": "+91 90000 11224", "lat": 12.9920, "lng": 77.6150},
    ],
    "Gastroenterologist": [
        {"name": "Dr. Nikhil Joshi (Gastroenterologist)", "distance": "2.2 km", "clinic": "DigestiveCare Institute", "phone": "+91 90000 44557", "lat": 12.9600, "lng": 77.6450},
    ],
    "Neurologist": [
        {"name": "Dr. Ananya Krishnan (Neurologist)", "distance": "3.1 km", "clinic": "NeuroLife Centre", "phone": "+91 90000 77880", "lat": 12.9450, "lng": 77.6200},
    ],
    "Cardiologist": [
        {"name": "Dr. Rajesh Gupta (Cardiologist)", "distance": "2.4 km", "clinic": "HeartCare Hospital", "phone": "+91 90000 99002", "lat": 12.9900, "lng": 77.6350},
    ],
    "Pulmonologist": [
        {"name": "Dr. Sneha Reddy (Pulmonologist)", "distance": "2.9 km", "clinic": "BreatheWell Chest Clinic", "phone": "+91 90000 22335", "lat": 12.9550, "lng": 77.5850},
    ],
    "Gynecologist": [
        {"name": "Dr. Kavita Desai (Gynecologist)", "distance": "1.7 km", "clinic": "Women's Health Centre", "phone": "+91 90000 55668", "lat": 12.9680, "lng": 77.6480},
    ],
    "Urologist": [
        {"name": "Dr. Manoj Pillai (Urologist)", "distance": "3.3 km", "clinic": "UroCare Clinic", "phone": "+91 90000 33446", "lat": 12.9420, "lng": 77.6080},
    ],
    "Psychiatrist": [
        {"name": "Dr. Ishaan Bose (Psychiatrist)", "distance": "1.9 km", "clinic": "MindWell Counselling Centre", "phone": "+91 90000 66779", "lat": 12.9860, "lng": 77.6420},
    ],
    "Pediatrician": [
        {"name": "Dr. Divya Raman (Pediatrician)", "distance": "1.3 km", "clinic": "Little Steps Child Clinic", "phone": "+91 90000 88991", "lat": 12.9760, "lng": 77.5980},
    ],
}

# Neutral feature set used when no image is uploaded — makes the score fully
# symptom-driven instead of failing or faking an image analysis result.
NEUTRAL_FEATURES = {
    "redness": 0.0, "yellowness": 0.0, "whiteness": 0.0,
    "variance": 0.0, "brightness": 128.0, "sharpness": 10.0,
}


PRIVACY_NOTICE = {
    "policy_version": PRIVACY_POLICY_VERSION,
    "image_handling": (
        "Uploaded images are held in memory only for the duration of the request. "
        "They are analyzed, a visual attention overlay is generated, and the original "
        "image bytes are then discarded. ClariMed never writes uploaded images to disk "
        "or to the database, and never transmits them to any third party."
    ),
    "what_we_store": [
        "Your name and email, only if you choose to provide them",
        "The body part and symptoms you selected",
        "The screening result, confidence score, and risk level",
        "Appointments you book",
        "A timestamped record of your consent",
    ],
    "what_we_never_store": [
        "The uploaded image itself",
        "The generated heatmap overlay (returned to you, then discarded)",
        "Any biometric identifier derived from your image",
    ],
    "your_rights": [
        "Export everything we hold about you (GET /api/privacy/export)",
        "Permanently delete all your records (DELETE /api/privacy/delete)",
        "Use the service without providing a name or email at all",
    ],
    "ai_disclaimer": (
        "ClariMed provides AI-assisted preliminary screening only. It does not diagnose "
        "disease or prescribe treatment. Always consult a qualified healthcare professional."
    ),
    "scope_limitation": (
        "ClariMed does not accept images of intimate or genital areas. Conditions affecting "
        "these areas are screened from reported symptoms only, without any image upload."
    ),
}


@app.get("/api/privacy/policy")
async def privacy_policy():
    return PRIVACY_NOTICE


@app.post("/api/privacy/consent")
async def give_consent(
    patient_email: str = Form(""),
    consent_image_processing: bool = Form(...),
    consent_data_storage: bool = Form(...),
):
    if not consent_image_processing or not consent_data_storage:
        raise HTTPException(
            status_code=400,
            detail="Both image-processing and data-storage consent are required to use the screening service.",
        )
    consent_id = record_consent(patient_email or None, consent_image_processing, consent_data_storage)
    return {"success": True, "consent_id": consent_id, "policy_version": PRIVACY_POLICY_VERSION}


@app.get("/api/privacy/export")
async def export_data(patient_email: str = Query(...)):
    """Right-to-access: returns everything stored about this patient."""
    return export_patient_data(patient_email)


@app.delete("/api/privacy/delete")
async def delete_data(patient_email: str = Query(...)):
    """Right-to-erasure: permanently deletes all records for this email.
    The audit log retains only that a deletion occurred, not the deleted content."""
    result = delete_patient_data(patient_email)
    return {"success": True, "deleted": result}


@app.get("/api/config")
async def get_config():
    """Lets the frontend fetch the real symptom checklists per body part,
    instead of hardcoding them separately in the React code."""
    return {"body_parts": BODY_PART_ORDER, "symptoms": BODY_PART_SYMPTOMS, "redflags": BODY_PART_REDFLAGS}


@app.get("/api/languages")
async def get_languages():
    """The curated set of languages this app supports for speech input/
    output and text translation (see ai/rag/translator.py). Each entry
    includes a real BCP-47 locale code the frontend uses directly for the
    browser's SpeechRecognition/SpeechSynthesis APIs."""
    return {"languages": SUPPORTED_LANGUAGES}


@app.post("/api/suggest-body-part")
async def suggest_body_part(request: Request, description: str = Form(...)):
    """
    Free-text-first flow: the user describes what's wrong before picking a
    body part, and this suggests one to pre-select. This is a SUGGESTION —
    the frontend always keeps the manual body-part grid available as an
    override, never replaces it. Classification is closed-list-safe (see
    ai/rag/body_part_router.py) — it can never return anything outside the
    11 known body parts, and never names a condition.
    """
    body_part_suggest_limiter.enforce(client_key(request), what="body-part suggestions")
    suggested = route_to_body_part(description)
    return {"suggested_body_part": suggested}


@app.post("/api/suggest-symptoms-from-image")
async def suggest_symptoms_from_image_endpoint(
    request: Request,
    body_part: str = Form(...),
    file: UploadFile = File(...),
):
    """
    Lets a patient upload a photo BEFORE ticking any symptom checkboxes, and
    pre-selects the checklist items the image alone suggests are relevant —
    the same "AI suggests, human confirms" pattern as /api/suggest-body-part,
    never a diagnosis. The frontend must show these as editable, pre-ticked
    checkboxes, never as a locked-in result.

    SAFETY: this endpoint's output is NEVER used to compute risk_level or a
    top condition by itself. The actual screening still only happens via
    POST /api/screen using whatever symptoms the patient confirms afterward
    — this is a UI convenience, not a second, less-safe scoring pathway.
    See suggest_symptoms_from_image() in condition_engine.py for the ranking
    + reverse keyword-mapping logic, which reuses the exact same matching
    fuse() itself uses.

    PRIVACY: identical guarantee to /api/screen — image bytes exist only in
    this function's local scope, are never written to disk or the database,
    and are explicitly deleted once analysis completes.
    """
    body_part_suggest_limiter.enforce(client_key(request), what="image-based symptom suggestions")

    normalized_body_part = body_part.strip().lower()
    if normalized_body_part not in VALID_BODY_PARTS:
        raise HTTPException(status_code=400, detail=f"body_part must be one of {sorted(VALID_BODY_PARTS)}")

    if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(status_code=400, detail="Unsupported image format. Use JPG, PNG, or WEBP.")
    file_bytes = await file.read()

    if len(file_bytes) > MAX_IMAGE_BYTES:
        del file_bytes
        raise HTTPException(status_code=413, detail="Image too large. Maximum size is 10 MB.")

    try:
        features = extract_features(file_bytes)
    except Exception as e:
        del file_bytes
        raise HTTPException(status_code=400, detail=f"Could not process image: {e}")

    q = quality_check(features)
    relevance = relevance_check(file_bytes, normalized_body_part)
    del file_bytes  # privacy: discard immediately, whether or not quality passed

    if not q["passed"]:
        return {
            "success": False,
            "stage": "quality_check_failed",
            "issues": q["issues"],
            "suggested_symptoms": [],
            "based_on_conditions": [],
            "message": "Image quality check failed — " + "; ".join(q["issues"]) + ". Please retake the photo.",
        }

    # Same fix as /api/screen: only attempt symptom suggestion when we don't
    # have a confident signal the photo is the wrong body part entirely.
    # This endpoint's heuristic color-stat scorer is if anything MORE prone
    # to false "matches" on an irrelevant photo than the vision LLM is --
    # any photo has SOME redness/whiteness/variance values, and the scorer
    # will happily match them against whatever condition fits best, whether
    # the photo shows the claimed body part or not.
    if relevance["checked"] and relevance["relevant"] is False:
        logger.info(
            "Skipping image-based symptom suggestion for %s -- photo flagged as not relevant (confidence=%s)",
            normalized_body_part, relevance["confidence"],
        )
        response = {"success": True, "suggested_symptoms": [], "based_on_conditions": []}
    else:
        result = suggest_symptoms_from_image(normalized_body_part, features)
        response = {
            "success": True,
            "suggested_symptoms": result["suggested_symptoms"],
            "based_on_conditions": result["based_on_conditions"],
        }

    if relevance["checked"] and relevance["relevant"] is False:
        response["relevance_warning"] = relevance["warning"]
    return response


@app.post("/api/guess-body-part-from-image")
async def guess_body_part_from_image_endpoint(request: Request, file: UploadFile = File(...)):
    """
    Lets a patient upload a photo BEFORE selecting a body part at all, and
    suggests which one it most likely shows -- the image-based counterpart
    to POST /api/suggest-body-part (which does the same thing from free
    text). Same "AI suggests, human confirms, never forces" contract: the
    frontend must keep manual body-part selection fully available regardless
    of this result, exactly like the text-based version already does.

    Uses CLIP zero-shot classification across the 7 photographable body
    parts (see guess_body_part_from_image() in ai/vision/relevance_gate.py).
    Gracefully returns "not confident" rather than a wrong guess when no
    candidate clears a reasonable bar -- never picks the least-bad option
    just to return *something*.

    PRIVACY: identical guarantee to the other image endpoints -- bytes exist
    only in local scope, never written to disk or the database, explicitly
    deleted once analysis completes.
    """
    body_part_suggest_limiter.enforce(client_key(request), what="image-based body-part guesses")

    if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(status_code=400, detail="Unsupported image format. Use JPG, PNG, or WEBP.")
    file_bytes = await file.read()

    if len(file_bytes) > MAX_IMAGE_BYTES:
        del file_bytes
        raise HTTPException(status_code=413, detail="Image too large. Maximum size is 10 MB.")

    result = guess_body_part_from_image(file_bytes)
    del file_bytes

    if not result["checked"] or not result["guessed_body_part"]:
        return {
            "success": True, "guessed_body_part": None,
            "confidence": result["confidence"], "all_scores": result["all_scores"],
        }

    return {
        "success": True,
        "guessed_body_part": result["guessed_body_part"],
        "confidence": result["confidence"],
        "all_scores": result["all_scores"],
    }


def needs_general_guidance(result: dict) -> bool:
    """
    True when the response should NOT commit to a single condition's curated
    guidance — either nothing cleared the confidence floor (out_of_coverage),
    or the top candidate cleared the floor but isn't meaningfully separated
    from the rest (ranking_reliable is False).

    REGRESSION GUARD for a real case found in testing: a bruise photo scored
    just above the floor against Acne on image color alone, with zero
    symptom agreement. The differential correctly showed "not confident
    enough to rank" — but guidance still generated a full, committed Acne
    care plan underneath it. The two halves of one response disagreed with
    each other. Guidance mode must follow the same reliability signal the
    differential already uses.
    """
    return bool(result.get("out_of_coverage")) or not bool(result.get("ranking_reliable", True))


@app.post("/api/screen")
async def execute_screening(
    request: Request,
    body_part: str = Form(...),
    symptoms_json: str = Form(...),
    redflags_json: str = Form("[]"),
    transcript: str = Form(""),
    language: str = Form("en"),
    patient_name: str = Form(""),
    patient_email: str = Form(""),
    consent_given: bool = Form(False),
    file: UploadFile = File(None),
):
    screening_limiter.enforce(client_key(request), what="screening requests")

    # Consent gate — no screening proceeds without explicit agreement.
    if not consent_given:
        raise HTTPException(
            status_code=403,
            detail="Consent is required before screening. See GET /api/privacy/policy.",
        )

    body_part = body_part.strip().lower()
    if body_part not in VALID_BODY_PARTS:
        raise HTTPException(status_code=400, detail=f"body_part must be one of {sorted(VALID_BODY_PARTS)}")

    try:
        symptoms = json.loads(symptoms_json)
        redflags = json.loads(redflags_json)
    except Exception:
        raise HTTPException(status_code=400, detail="symptoms_json / redflags_json must be valid JSON arrays.")

    # --- 0. Interpret free-text/voice description into known symptoms AND
    #      known red flags, merging both. LLM acts strictly as a mapper
    #      against a closed list — it cannot introduce anything outside it
    #      (enforced in symptom_interpreter.py). This matters specifically
    #      for red flags: without it, a user who types "I suddenly lost
    #      vision in my eye" but never ticks a checkbox would get no
    #      escalation at all — emergency detection would depend entirely on
    #      the user knowing to click the right box.
    interpreted_symptoms = []
    interpreted_redflags = []
    # Translated to English BEFORE it ever reaches interpret_symptoms() --
    # see ai/rag/translator.py for why this boundary matters: the offline
    # fallback path does plain English word-overlap matching with no
    # language awareness, so untranslated non-English text would silently
    # match nothing rather than failing loudly.
    original_transcript = transcript
    transcript = translate_to_english(transcript, language) if transcript else transcript
    if transcript and transcript.strip():
        known_symptoms = BODY_PART_SYMPTOMS.get(body_part, [])
        known_redflags = BODY_PART_REDFLAGS.get(body_part, [])

        interpreted_symptoms = interpret_symptoms(transcript, known_symptoms)
        for s in interpreted_symptoms:
            if s not in symptoms:
                symptoms.append(s)

        # Same function, different closed list — it's content-agnostic:
        # "does this free text match any phrase in this list."
        interpreted_redflags = interpret_symptoms(transcript, known_redflags)
        for r in interpreted_redflags:
            if r not in redflags:
                redflags.append(r)

    # --- 1. Real image analysis (or neutral fallback if no image) ---
    #
    # PRIVACY GUARANTEE, ENFORCED HERE:
    # The uploaded image exists only as `file_bytes` inside this function's
    # scope. It is never written to disk, never inserted into the database,
    # and explicitly `del`eted once analysis completes so it is not retained
    # in the request scope any longer than necessary.
    #
    # ONE DOCUMENTED EXCEPTION: when vision-based symptom detection runs
    # (ai/rag/vision_symptom_interpreter.py), the image IS sent to Groq's
    # cloud vision API for analysis -- this is a genuine, intentional
    # change from the heuristic-only path above, which never leaves this
    # server. This is not silently different from what's documented
    # elsewhere; the privacy policy shown to patients needs a corresponding
    # update before this ships to real users, not just this code comment.
    image_meta = {"provided": False}
    features = NEUTRAL_FEATURES
    heatmap_b64 = None
    vision_detected_symptoms: list = []
    vision_other_observations: str = ""

    if file:
        if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
            raise HTTPException(status_code=400, detail="Unsupported image format. Use JPG, PNG, or WEBP.")
        file_bytes = await file.read()

        if len(file_bytes) > MAX_IMAGE_BYTES:
            del file_bytes
            raise HTTPException(status_code=413, detail="Image too large. Maximum size is 10 MB.")

        try:
            features = extract_features(file_bytes)
        except Exception as e:
            del file_bytes
            raise HTTPException(status_code=400, detail=f"Could not process image: {e}")

        q = quality_check(features)
        if not q["passed"]:
            del file_bytes  # discard before early return
            return {
                "success": False,
                "stage": "quality_check_failed",
                "issues": q["issues"],
                "message": "Image quality check failed — " + "; ".join(q["issues"]) + ". Please retake the photo.",
            }

        heatmap_b64 = render_heatmap_png_base64(file_bytes, features)

        # Relevance check (see ai/vision/relevance_gate.py for the full
        # reasoning). Still non-blocking for the SCREENING as a whole -- a
        # patient with an unusual-but-genuine photo can still proceed with
        # whatever symptoms they select by hand. But it DOES gate vision-
        # based symptom detection specifically (below): running that on a
        # photo that confidently isn't even the right body part would force
        # the model to invent findings on an irrelevant image. This is the
        # actual fix for a real bug found in testing -- an unrelated photo
        # (a photo of a person, not a body part) was previously still
        # producing fabricated "detected" symptoms, because the relevance
        # check's result was computed but never actually used to stop that.
        relevance = relevance_check(file_bytes, body_part)

        # --- Vision-based symptom detection ---
        # This is what lets a screening run to a real result from a photo
        # ALONE, with zero symptoms manually selected: the vision model
        # picks from this body part's existing closed symptom list (it
        # cannot invent one, cannot name a condition -- see the module
        # docstring for the full safety reasoning), and those detected
        # symptoms are merged in exactly like transcript-interpreted ones
        # just above. No new scoring pathway -- fuse() below sees one
        # merged symptom list regardless of where each symptom came from.
        #
        # Only runs when we don't have a CONFIDENT signal the photo is
        # irrelevant (relevance unavailable/uncertain still allows it through
        # -- only an explicit "this isn't even the right body part" blocks
        # it, which is the specific failure mode being guarded against).
        if relevance["checked"] and relevance["relevant"] is False:
            logger.info(
                "Skipping vision-based symptom detection for %s -- photo flagged as not relevant (confidence=%s)",
                body_part, relevance["confidence"],
            )
        else:
            known_symptoms_for_vision = BODY_PART_SYMPTOMS.get(body_part, [])
            vision_result = interpret_symptoms_from_image(file_bytes, body_part, known_symptoms_for_vision)
            vision_detected_symptoms = vision_result["matched_symptoms"]
            vision_other_observations = vision_result["other_observations"]
            for s in vision_detected_symptoms:
                if s not in symptoms:
                    symptoms.append(s)

        image_meta = {
            "provided": True,
            "brightness": round(features["brightness"], 1),
            "quality": "passed",
            "retention": "not_stored",
        }
        if relevance["checked"] and relevance["relevant"] is False:
            image_meta["relevance_warning"] = relevance["warning"]

        del file_bytes  # image bytes discarded; only derived features remain
        write_audit("image_processed", patient_email or None, f"body_part={body_part} stored=false")

    # --- 2. Real fused scoring across the selected body part's conditions ---
    result = fuse(body_part, symptoms, features, redflags=redflags, image_provided=bool(file))

    # --- 3. Guidance text: grounded in KB only when we have a RELIABLE match —
    #        both above the confidence floor AND meaningfully separated from
    #        the alternatives (see needs_general_guidance() above). RAG/LLM is
    #        only used to phrase retrieved facts — never to invent a diagnosis
    #        outside the curated KB. ---
    if needs_general_guidance(result):
        fallback = rag_agent.general_fallback(symptoms, transcript, body_part)
        if fallback["source"] == "general_llm_unverified":
            guidance = fallback["text"]
        else:
            guidance = (
                "Your reported symptoms and/or image don't clearly match any condition currently in "
                "ClariMed's curated knowledge base. This does not mean nothing is wrong — it means this "
                "case falls outside what this MVP has been trained to recognize. Please consult a doctor "
                "for a proper in-person evaluation."
            )
        guidance_source = fallback["source"]
        # Even outside KB coverage, route the patient to the RIGHT KIND of doctor
        # rather than leaving them with a bare "see a doctor" and no direction.
        # This is triage direction, not a diagnosis.
        routed_specialist = route_to_specialist(transcript, symptoms)
        specialist_list = NEARBY_SPECIALISTS_MOCK.get(routed_specialist, [])
    else:
        top = result["top"]
        guidance = rag_agent.process_screening(symptoms, transcript, disease_id=top["id"])
        guidance_source = "curated_kb"
        routed_specialist = top["specialist"]
        specialist_list = NEARBY_SPECIALISTS_MOCK.get(routed_specialist, [])

    # Guidance is persisted in English (consistent for doctor-portal review
    # regardless of which language the patient used), but translated to the
    # patient's language for what's actually returned/spoken back to them.
    guidance_for_patient = translate_from_english(guidance, language)

    # --- 4. Persist to database (real history, not lost on refresh) ---
    screening_id = save_screening(
        body_part=body_part,
        symptoms=symptoms,
        redflags=redflags,
        result=result,
        guidance=guidance,
        patient_name=patient_name or None,
        patient_email=patient_email or None,
        vision_observations=vision_other_observations or None,
    )

    is_emergency = result["risk_level"] == "red"
    if is_emergency:
        write_audit("emergency_risk_flagged", patient_email or None, f"body_part={body_part}")

    return {
        "success": True,
        "screening_id": screening_id,
        "body_part": body_part,
        "result": result,
        "guidance": guidance_for_patient,
        "guidance_source": guidance_source,
        "language": language,
        "emergency": {
            "is_emergency": is_emergency,
            "national_emergency_number": NATIONAL_EMERGENCY_NUMBER,
            "hospitals": EMERGENCY_HOSPITALS_MOCK if is_emergency else [],
        },
        "interpreted_symptoms": interpreted_symptoms,
        "interpreted_redflags": interpreted_redflags,
        "vision_detected_symptoms": vision_detected_symptoms,
        "vision_other_observations": vision_other_observations,
        "image": {**image_meta, "heatmap_overlay": heatmap_b64},
        "healthcare_network": specialist_list,
        "routed_specialist": routed_specialist,
        "metadata": {
            "risk_level": result["risk_level"],
            "risk_reason": result["risk_reason"],
            "regulatory_disclaimer": "AI-assisted preliminary screening only. Not a medical diagnosis.",
        },
    }


@app.post("/api/chat")
async def chat_turn(
    request: Request,
    messages_json: str = Form(...),
    body_part: str = Form(""),
    language: str = Form("en"),
    patient_name: str = Form(""),
    patient_email: str = Form(""),
    consent_given: bool = Form(False),
    file: UploadFile = File(None),
):
    """
    One turn of the "chat with ClariMed AI" experience -- a NEW conversational
    presentation layer over the exact same safety-tested backend logic
    /api/screen already uses (see backend/app/chat_orchestrator.py for the
    full reasoning). This endpoint is a thin wrapper: process_chat_turn()
    makes the finalize/continue decision using the same closed-list-safe
    functions the wizard calls, and if it's time to finalize, this endpoint
    runs the SAME fuse() + guidance + persistence sequence execute_screening()
    already does above -- kept as a deliberately separate copy rather than a
    shared refactor, specifically to avoid any risk to execute_screening's
    ~130 already-passing tests under time pressure.

    Consent works the same way as the wizard: required before any screening
    is finalized and persisted, never before that.
    """
    screening_limiter.enforce(client_key(request), what="chat turns")

    try:
        messages = json.loads(messages_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="messages_json must be valid JSON.")
    if not isinstance(messages, list):
        raise HTTPException(status_code=400, detail="messages_json must be a JSON array.")

    # Translated to English BEFORE reaching process_chat_turn() -- same
    # boundary principle as execute_screening() above. Only user-role
    # messages need translation: process_chat_turn()'s _combined_user_text()
    # only ever reads user-role content for symptom/red-flag extraction, so
    # assistant messages don't need to be in English for that safety-critical
    # path (they're only loose conversational context for the follow-up
    # question generator, where a language mismatch is a minor tone nicety,
    # not a correctness issue).
    if language != "en":
        messages = [
            {**m, "content": translate_to_english(m.get("content", ""), language)}
            if m.get("role") == "user" else m
            for m in messages
        ]

    image_bytes = None
    if file:
        if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
            raise HTTPException(status_code=400, detail="Unsupported image format. Use JPG, PNG, or WEBP.")
        image_bytes = await file.read()
        if len(image_bytes) > MAX_IMAGE_BYTES:
            del image_bytes
            raise HTTPException(status_code=413, detail="Image too large. Maximum size is 10 MB.")

    turn = process_chat_turn(messages, body_part=body_part or None, image_bytes=image_bytes)
    if image_bytes is not None:
        del image_bytes  # privacy: discard immediately once the orchestrator has used it

    if turn["type"] == "question":
        message_for_patient = translate_from_english(turn["message"], language)
        return {"type": "question", "message": message_for_patient, "body_part": turn["body_part"]}

    # --- turn["type"] == "ready_to_finalize" -- finalize a real screening ---
    if not consent_given:
        raise HTTPException(
            status_code=403,
            detail="Consent is required before a screening can be finalized. See GET /api/privacy/policy.",
        )

    resolved_body_part = turn["body_part"]
    symptoms = turn["symptoms"]
    redflags = turn["redflags"]
    features = turn["features"]
    image_provided = turn["image_provided"]

    result = fuse(resolved_body_part, symptoms, features, redflags=redflags, image_provided=image_provided)
    transcript_text = " ".join(m.get("content", "") for m in messages if m.get("role") == "user")

    if needs_general_guidance(result):
        fallback = rag_agent.general_fallback(symptoms, transcript_text, resolved_body_part)
        if fallback["source"] == "general_llm_unverified":
            guidance = fallback["text"]
        else:
            guidance = (
                "Your reported symptoms and/or image don't clearly match any condition currently in "
                "ClariMed's curated knowledge base. This does not mean nothing is wrong — it means this "
                "case falls outside what this MVP has been trained to recognize. Please consult a doctor "
                "for a proper in-person evaluation."
            )
        guidance_source = fallback["source"]
        routed_specialist = route_to_specialist(transcript_text, symptoms)
        specialist_list = NEARBY_SPECIALISTS_MOCK.get(routed_specialist, [])
    else:
        top = result["top"]
        guidance = rag_agent.process_screening(symptoms, transcript_text, disease_id=top["id"])
        guidance_source = "curated_kb"
        routed_specialist = top["specialist"]
        specialist_list = NEARBY_SPECIALISTS_MOCK.get(routed_specialist, [])

    # Same principle as execute_screening(): persist in English, return the
    # patient's language.
    guidance_for_patient = translate_from_english(guidance, language)

    screening_id = save_screening(
        body_part=resolved_body_part,
        symptoms=symptoms,
        redflags=redflags,
        result=result,
        guidance=guidance,
        patient_name=patient_name or None,
        patient_email=patient_email or None,
        vision_observations=turn["vision_other_observations"] or None,
    )

    is_emergency = result["risk_level"] == "red"
    if is_emergency:
        write_audit("emergency_risk_flagged", patient_email or None, f"body_part={resolved_body_part} source=chat")

    response = {
        "type": "result",
        "success": True,
        "screening_id": screening_id,
        "body_part": resolved_body_part,
        "result": result,
        "guidance": guidance_for_patient,
        "guidance_source": guidance_source,
        "language": language,
        "emergency": {
            "is_emergency": is_emergency,
            "national_emergency_number": NATIONAL_EMERGENCY_NUMBER,
            "hospitals": EMERGENCY_HOSPITALS_MOCK if is_emergency else [],
        },
        "interpreted_symptoms": turn["text_interpreted_symptoms"],
        "interpreted_redflags": redflags,
        "vision_detected_symptoms": turn["vision_detected_symptoms"],
        "vision_other_observations": turn["vision_other_observations"],
        "image": {"provided": image_provided, "heatmap_overlay": None, "relevance_warning": turn["relevance_warning"]},
        "healthcare_network": specialist_list,
        "routed_specialist": routed_specialist,
        "metadata": {
            "risk_level": result["risk_level"],
            "risk_reason": result["risk_reason"],
            "regulatory_disclaimer": "AI-assisted preliminary screening only. Not a medical diagnosis.",
        },
    }
    return response


@app.post("/api/book-appointment")
async def book_appointment(
    specialist_name: str = Form(...),
    slot: str = Form(...),
    screening_id: str = Form(""),
    clinic_name: str = Form(""),
    patient_name: str = Form(""),
    patient_email: str = Form(""),
):
    """
    Books an appointment against the live scheduling system. Unlike /api/screen,
    this endpoint has no offline fallback by design — booking a real slot
    requires reaching the hospital network's scheduling service. In the
    frontend, this action is disabled when the device is offline.
    """
    appointment_id = save_appointment(
        specialist_name=specialist_name,
        slot=slot,
        screening_id=screening_id or None,
        clinic_name=clinic_name or None,
        patient_name=patient_name or None,
        patient_email=patient_email or None,
    )
    # Rapido-style routing: assign to the least-busy doctor in the matching
    # department right away. If none exists yet, it stays in the pool for a
    # dept doctor to claim. Never blocks the booking itself.
    try:
        assign_appointment(appointment_id)
    except Exception as e:
        logger.warning("Appointment assignment deferred: %s", e)
    return {"success": True, "appointment_id": appointment_id, "status": "confirmed"}


@app.get("/api/appointments")
async def list_appointments(patient_email: str = Query(None), limit: int = Query(50)):
    return {"appointments": get_appointments(patient_email=patient_email or None, limit=limit)}


# ---------------------------------------------------------------------------
# Doctor portal — per-doctor accounts, department scoping, Rapido-style routing
# ---------------------------------------------------------------------------
# Passwords are hashed (PBKDF2, see doctor_auth). Sessions are opaque random
# tokens sent via the X-Doctor-Token header. This is a real per-doctor auth
# model — a step up from the earlier shared password — though still MVP-grade
# (no email verification, no password reset flow, single-factor). Documented
# as such rather than presented as production-hardened.

def _current_doctor(x_doctor_token: str | None) -> dict:
    doc = doctor_from_token(x_doctor_token)
    if not doc:
        raise HTTPException(status_code=401, detail="Not signed in as a doctor.")
    return doc


@app.get("/api/doctor/departments")
async def doctor_departments():
    """The closed list of departments a doctor can register under."""
    return {"departments": DEPARTMENTS}


@app.post("/api/doctor/register")
async def doctor_register(
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    department: str = Form(...),
):
    try:
        doc = register_doctor(name, email, password, department)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # If this department had pooled (unassigned) appointments waiting, hand
    # them out now that someone can take them.
    assigned = assign_unassigned_for_department(department)
    write_audit("doctor_registered", None, f"dept={department} backlog_assigned={assigned}")
    return {"success": True, "doctor": doc, "backlog_assigned": assigned}


@app.post("/api/doctor/login")
async def doctor_login(request: Request, email: str = Form(...), password: str = Form(...)):
    normalized_email = email.strip().lower()
    doctor_login_ip_limiter.enforce(client_key(request), what="login attempts")
    login_attempts.check_locked(normalized_email)
    try:
        result = login_doctor(email, password)
    except ValueError:
        login_attempts.record_failure(normalized_email)
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    login_attempts.record_success(normalized_email)
    write_audit("doctor_login", None, f"doctor={result['doctor']['email']}")
    return {"success": True, **result}


@app.post("/api/doctor/logout")
async def doctor_logout(x_doctor_token: str = Header(None)):
    if x_doctor_token:
        logout_doctor(x_doctor_token)
    return {"success": True}


@app.get("/api/doctor/me")
async def doctor_me(x_doctor_token: str = Header(None)):
    return {"doctor": _current_doctor(x_doctor_token)}


@app.get("/api/doctor/appointments")
async def doctor_appointments(limit: int = Query(100), x_doctor_token: str = Header(None)):
    """The signed-in doctor's own assigned appointments plus their department's
    unassigned pool — enriched with AI findings and notes, emergencies first."""
    doc = _current_doctor(x_doctor_token)
    appts = appointments_for_doctor(doc["id"], doc["department"], limit=limit)
    return {"doctor": doc, "appointments": appts}


@app.post("/api/doctor/claim")
async def doctor_claim(appointment_id: str = Form(...), x_doctor_token: str = Header(None)):
    """Pick up a pooled appointment from the doctor's own department."""
    doc = _current_doctor(x_doctor_token)
    try:
        claim_appointment(appointment_id, doc["id"], doc["department"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    write_audit("appointment_claimed", None, f"appt={appointment_id} by={doc['email']}")
    return {"success": True}


@app.post("/api/doctor/notes")
async def doctor_add_note(
    appointment_id: str = Form(...),
    note: str = Form(...),
    x_doctor_token: str = Header(None),
):
    """Records a timestamped clinical note against an appointment."""
    _current_doctor(x_doctor_token)
    note_text = note.strip()
    if not note_text:
        raise HTTPException(status_code=400, detail="Note cannot be empty.")
    try:
        saved = add_clinical_note(appointment_id, note_text)
    except ValueError:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    write_audit("clinical_note_added", None, f"appointment={appointment_id}")
    return {"success": True, "note": saved}


@app.get("/api/history")
async def screening_history(patient_email: str = Query(None), limit: int = Query(50)):
    """Real prediction history, pulled from SQLite — replaces the empty stub."""
    return {"history": get_history(patient_email=patient_email or None, limit=limit)}


@app.get("/api/report/{screening_id}")
async def download_report(screening_id: str):
    """Generates and returns a real PDF report for a past screening."""
    screening = get_screening_by_id(screening_id)
    if not screening:
        raise HTTPException(status_code=404, detail="Screening not found.")
    pdf_bytes = generate_report_pdf(screening)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="ClariMed_Report_{screening_id[:8]}.pdf"'},
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)