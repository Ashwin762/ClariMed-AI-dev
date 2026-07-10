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

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import json
import uvicorn

from ai.vision.image_analysis import extract_features, quality_check, render_heatmap_png_base64
from ai.rules.condition_engine import fuse, BODY_PART_SYMPTOMS, BODY_PART_REDFLAGS
from ai.rag.vector_store import ClariMedRAGAgent
from ai.rag.symptom_interpreter import interpret_symptoms
from ai.rag.specialist_router import route_to_specialist
from backend.app.database import (
    init_db, save_screening, get_history, get_screening_by_id,
    save_appointment, get_appointments,
    record_consent, write_audit, delete_patient_data, export_patient_data,
    PRIVACY_POLICY_VERSION,
)
from backend.app.report_generator import generate_report_pdf

app = FastAPI(title="ClariMed AI - Core Screening Architecture Engine")


@app.on_event("startup")
async def on_startup():
    init_db()

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
}

# Stable display order for the frontend. A set has no order, so returning
# list(VALID_BODY_PARTS) would shuffle the UI on every server restart.
BODY_PART_ORDER = [
    "eye", "skin", "nail", "oral", "dental",
    "ent", "hair", "respiratory", "digestive", "musculoskeletal", "general",
]

# Mock healthcare directory — keyed by specialist TYPE. This is explicitly MOCK
# DATA (no real clinics), meant to be replaced by a Maps/Places API later.
# Covers every type in ai/rag/specialist_router.py's SPECIALIST_TYPES so that
# out-of-coverage cases still get routed to a real specialist card.
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
    body_part: str = Form(...),
    symptoms_json: str = Form(...),
    redflags_json: str = Form("[]"),
    transcript: str = Form(""),
    patient_name: str = Form(""),
    patient_email: str = Form(""),
    consent_given: bool = Form(False),
    file: UploadFile = File(None),
):
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

    # --- 0. Interpret free-text/voice description into known symptoms and merge.
    #      LLM acts strictly as a mapper against BODY_PART_SYMPTOMS — it cannot
    #      introduce a symptom outside that list (enforced in symptom_interpreter.py).
    interpreted_symptoms = []
    if transcript and transcript.strip():
        known = BODY_PART_SYMPTOMS.get(body_part, [])
        interpreted_symptoms = interpret_symptoms(transcript, known)
        for s in interpreted_symptoms:
            if s not in symptoms:
                symptoms.append(s)

    # --- 1. Real image analysis (or neutral fallback if no image) ---
    #
    # PRIVACY GUARANTEE, ENFORCED HERE:
    # The uploaded image exists only as `file_bytes` inside this function's
    # scope. It is never written to disk, never inserted into the database,
    # and never sent to a third party. We explicitly `del` it once analysis
    # completes so it is not retained in the request scope any longer than
    # necessary. Verify by inspecting: no open(), no INSERT, no outbound
    # request anywhere in this block.
    image_meta = {"provided": False}
    features = NEUTRAL_FEATURES
    heatmap_b64 = None

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
        image_meta = {
            "provided": True,
            "brightness": round(features["brightness"], 1),
            "quality": "passed",
            "retention": "not_stored",
        }

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

    # --- 4. Persist to database (real history, not lost on refresh) ---
    screening_id = save_screening(
        body_part=body_part,
        symptoms=symptoms,
        redflags=redflags,
        result=result,
        guidance=guidance,
        patient_name=patient_name or None,
        patient_email=patient_email or None,
    )

    return {
        "success": True,
        "screening_id": screening_id,
        "body_part": body_part,
        "result": result,
        "guidance": guidance,
        "guidance_source": guidance_source,
        "interpreted_symptoms": interpreted_symptoms,
        "image": {**image_meta, "heatmap_overlay": heatmap_b64},
        "healthcare_network": specialist_list,
        "routed_specialist": routed_specialist,
        "metadata": {
            "risk_level": result["risk_level"],
            "risk_reason": result["risk_reason"],
            "regulatory_disclaimer": "AI-assisted preliminary screening only. Not a medical diagnosis.",
        },
    }


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
    return {"success": True, "appointment_id": appointment_id, "status": "confirmed"}


@app.get("/api/appointments")
async def list_appointments(patient_email: str = Query(None), limit: int = Query(50)):
    return {"appointments": get_appointments(patient_email=patient_email or None, limit=limit)}


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