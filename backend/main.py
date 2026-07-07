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

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import json
import uvicorn

from ai.vision.image_analysis import extract_features, quality_check, render_heatmap_png_base64
from ai.rules.condition_engine import fuse, BODY_PART_SYMPTOMS, BODY_PART_REDFLAGS
from ai.rag.vector_store import ClariMedRAGAgent

app = FastAPI(title="ClariMed AI - Core Screening Architecture Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

rag_agent = ClariMedRAGAgent()

VALID_BODY_PARTS = {"eye", "skin", "nail"}

# Mock healthcare directory — keyed by specialist TYPE (not per-disease), so it
# actually covers all 11 conditions instead of only 2. This is explicitly MOCK
# DATA (no real clinics), meant to be replaced by a Maps/Places API later.
NEARBY_SPECIALISTS_MOCK = {
    "Ophthalmologist": [
        {"name": "Dr. Amara Rao (Ophthalmologist)", "distance": "1.2 km", "clinic": "ClearVision Ophthalmic Center", "phone": "+91 98765 43210"},
        {"name": "Dr. Kevin Sterling (Corneal Specialist)", "distance": "3.4 km", "clinic": "Metro Eye & Care Institute", "phone": "+91 87654 32109"},
    ],
    "Dermatologist": [
        {"name": "Dr. Priya Nair (Dermatologist)", "distance": "0.9 km", "clinic": "SkinHealth Clinic", "phone": "+91 90000 11223"},
        {"name": "Dr. Rohan Mehta (Dermatologist)", "distance": "2.6 km", "clinic": "Derma Care Centre", "phone": "+91 90000 44556"},
    ],
}

# Neutral feature set used when no image is uploaded — makes the score fully
# symptom-driven instead of failing or faking an image analysis result.
NEUTRAL_FEATURES = {
    "redness": 0.0, "yellowness": 0.0, "whiteness": 0.0,
    "variance": 0.0, "brightness": 128.0, "sharpness": 10.0,
}


@app.get("/api/config")
async def get_config():
    """Lets the frontend fetch the real symptom checklists per body part,
    instead of hardcoding them separately in the React code."""
    return {"body_parts": list(VALID_BODY_PARTS), "symptoms": BODY_PART_SYMPTOMS, "redflags": BODY_PART_REDFLAGS}


@app.post("/api/screen")
async def execute_screening(
    body_part: str = Form(...),
    symptoms_json: str = Form(...),
    redflags_json: str = Form("[]"),
    transcript: str = Form(""),
    file: UploadFile = File(None),
):
    body_part = body_part.strip().lower()
    if body_part not in VALID_BODY_PARTS:
        raise HTTPException(status_code=400, detail=f"body_part must be one of {sorted(VALID_BODY_PARTS)}")

    try:
        symptoms = json.loads(symptoms_json)
        redflags = json.loads(redflags_json)
    except Exception:
        raise HTTPException(status_code=400, detail="symptoms_json / redflags_json must be valid JSON arrays.")

    # --- 1. Real image analysis (or neutral fallback if no image) ---
    image_meta = {"provided": False}
    features = NEUTRAL_FEATURES
    heatmap_b64 = None

    if file:
        if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
            raise HTTPException(status_code=400, detail="Unsupported image format. Use JPG, PNG, or WEBP.")
        file_bytes = await file.read()
        try:
            features = extract_features(file_bytes)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not process image: {e}")

        q = quality_check(features)
        if not q["passed"]:
            return {
                "success": False,
                "stage": "quality_check_failed",
                "issues": q["issues"],
                "message": "Image quality check failed — " + "; ".join(q["issues"]) + ". Please retake the photo.",
            }

        heatmap_b64 = render_heatmap_png_base64(file_bytes, features)
        image_meta = {
            "provided": True,
            "file_name": file.filename,
            "brightness": round(features["brightness"], 1),
            "quality": "passed",
        }

    # --- 2. Real fused scoring across the selected body part's conditions ---
    result = fuse(body_part, symptoms, features, redflags=redflags)

    # --- 3. Guidance text: grounded in KB if we have a confident match,
    #        otherwise an honest "outside coverage" response (see condition_engine
    #        confidence floor). RAG/LLM is only used to phrase retrieved facts —
    #        never to invent a diagnosis outside the curated KB. ---
    if result["out_of_coverage"]:
        guidance = (
            "Your reported symptoms and/or image don't clearly match any condition currently in "
            "ClariMed's curated knowledge base. This does not mean nothing is wrong — it means this "
            "case falls outside what this MVP has been trained to recognize. Please consult a doctor "
            "for a proper in-person evaluation."
        )
        specialist_list = []
    else:
        top = result["top"]
        guidance = rag_agent.process_screening(symptoms, transcript, disease_id=top["id"])
        specialist_list = NEARBY_SPECIALISTS_MOCK.get(top["specialist"], [])

    return {
        "success": True,
        "body_part": body_part,
        "result": result,
        "guidance": guidance,
        "image": {**image_meta, "heatmap_overlay": heatmap_b64},
        "healthcare_network": specialist_list,
        "metadata": {
            "risk_level": result["risk_level"],
            "risk_reason": result["risk_reason"],
            "regulatory_disclaimer": "AI-assisted preliminary screening only. Not a medical diagnosis.",
        },
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)