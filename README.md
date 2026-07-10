# ClariMed AI

**AI-assisted preliminary health screening.** Combines an uploaded photo, reported symptoms, and a curated medical knowledge base to suggest what a condition *could* relate to — and, more importantly, which specialist to see.

> ClariMed does **not** diagnose disease or prescribe treatment. It is a preliminary screening tool. Every result directs the user to a qualified healthcare professional.

---

## What it actually does

| | |
|---|---|
| **Coverage** | 46 conditions across 11 body parts |
| **Screening** | Image pixel analysis + symptom matching, fused into a scored result |
| **Explainability** | Visual attention heatmap, exact matched symptoms, evidence basis |
| **Honesty** | Refuses to rank conditions when evidence is thin; refuses to guess outside its knowledge base |
| **Guidance** | Retrieved from curated, doctor-reviewable markdown, phrased by an LLM |
| **Routing** | Suggests the right specialist type (14 specialties) even for out-of-coverage complaints |
| **Privacy** | Consent gate, images never stored, right-to-erasure |
| **Resilience** | Core screening works with no internet; only booking and sync require connectivity |

### Body parts and conditions

| Body part | Conditions |
|---|---|
| Eye (7) | Conjunctivitis, Dry Eye Disease, Cataract, Blepharitis, Stye, Glaucoma, Corneal Ulcer |
| Skin (7) | Acne, Eczema, Contact Dermatitis, Ringworm, Psoriasis, Vitiligo, Cellulitis |
| Nail (4) | Onychomycosis, Paronychia, Ingrown Nail, Nail Psoriasis |
| Oral (4) | Oral Thrush, Mouth Ulcers, Gingivitis, Cold Sores |
| Dental (3) | Tooth Decay, Tooth Sensitivity, Periodontitis |
| ENT (4) | Otitis Media, Sinusitis, Tonsillitis, Allergic Rhinitis |
| Hair / Scalp (3) | Dandruff, Alopecia Areata, Scalp Folliculitis |
| Respiratory (3) | Bronchitis, Asthma, Pneumonia |
| Digestive (3) | Acid Reflux, IBS, Constipation |
| Musculoskeletal (4) | Muscle Strain, Osteoarthritis, Tendinitis, Low Back Pain |
| General Health (4) | Common Cold, Viral Fever, Migraine, Food Poisoning |

Conditions with no reliable visual sign (Respiratory, Digestive, Musculoskeletal, General Health, and some others) are screened from **symptoms only** — the image step is skipped entirely rather than asking for a photo that cannot help.

---

## Honest scope: what is and isn't real

This matters more than a feature list. Read this before evaluating the code.

### What is genuinely implemented

- **Real image analysis.** `ai/vision/image_analysis.py` computes redness, yellowness, whiteness, texture variance, brightness, and blur from actual pixel data. Deterministic, inspectable, no magic.
- **Real scoring.** `ai/rules/condition_engine.py` fuses image features with symptom-keyword overlap against the knowledge base, with a confidence floor and separation thresholds.
- **Real knowledge base.** 46 authored markdown files with YAML frontmatter, parsed at runtime. Nothing is hardcoded in the Python.
- **Real persistence.** SQLite: screenings, appointments, consents, audit log.
- **Real PDF reports**, generated server-side.
- **Real offline fallback.** With no LLM key and no internet, screening and guidance still work end to end.

### What is a deliberate stand-in

- **The image model is a heuristic, not a trained CNN.** There is no `.pth` file, no dataset, no transfer learning yet. The pixel features are real math, but they are not "seeing" the way a trained network does. `training_package/` contains a complete, ready-to-run PyTorch training script (MobileNetV3 transfer learning) and dataset sourcing guide. The integration point in `image_analysis.py` was designed so swapping in a trained model is a contained change.
- **The heatmap is a heuristic attention map, not Grad-CAM.** Real Grad-CAM requires a trained model. The overlay is labeled as heuristic everywhere it appears.
- **Embeddings are hashed bag-of-words, not transformer embeddings.** `ai/rag/embeddings.py` uses feature hashing — real, deterministic, content-derived, and zero-download. Swappable for `BAAI/bge-small-en-v1.5` when the dependency budget allows.
- **The specialist directory is mock data.** No real clinics. Structured to be replaced by a Places/Maps API.

We would rather state these plainly than let a demo imply capabilities the code doesn't have.

---

## How confidence is presented (and why)

An early version showed a normalized ranking share as a percentage — e.g. *"Asthma 33%"*. With three near-equal candidates, everything lands near 33%. Patients read that as *"one-in-three chance I have asthma."* That is not what was computed.

The system now:

- Reports **match strength** (Strong / Moderate / Weak) from the **absolute** fused score, not a relative share.
- **Suppresses ranking entirely** when the top candidate doesn't meaningfully separate from the rest, showing an unranked *"conditions that share your symptoms"* list with no numbers.
- Displays the **evidence basis** — *"Based on 1 symptom and no image · 3 conditions considered"* — so uncertainty is legible.
- States explicitly: *match strength is how well symptoms fit a condition, not the chance you have it.*

---

## Safety design

The LLM never makes the medical decision.

| Component | LLM role | Constraint |
|---|---|---|
| Condition scoring | **None** | Fully deterministic rules + pixel math |
| Symptom interpretation | Maps free text onto a **closed list** of known symptoms | Post-filtered; cannot introduce an unknown symptom |
| Specialist routing | Selects from a **closed list** of 14 specialties | Post-filtered; cannot invent a specialty or name a disease |
| Guidance text | Rephrases retrieved knowledge-base content | Prompted to add no facts outside the provided document |
| Out-of-coverage fallback | General context only | No diagnosis, no medication names, always defers to a doctor; rendered in a visually distinct "unverified" tier |

Other safeguards:

- **Confidence floor.** If nothing matches well, the system says so rather than forcing a guess.
- **Red-flag escalation.** Emergency symptoms (loss of bladder control with back pain, halos around lights, coughing blood) escalate risk to red regardless of the screening result.
- **Trust tiers are never blended.** Curated-knowledge-base answers and general-LLM answers are visually and textually distinct.

---

## Privacy

- **Consent is required.** `/api/screen` returns `403` without it. Consent is stored, timestamped, and versioned.
- **Images are never stored.** Every code path holding image bytes ends in an explicit `del`. No `open()`, no `INSERT`, no outbound request. This is verifiable by reading ~40 lines of `backend/main.py`.
- **Right to erasure.** `DELETE /api/privacy/delete` wipes all screenings, appointments, and consent records. The audit log retains only that a deletion occurred — accountability preserved, content erased.
- **Right to access.** `GET /api/privacy/export` returns everything stored about a patient.
- **Scope limitation.** ClariMed does not accept images of intimate or genital areas. Conditions affecting these areas would be screened from symptoms only. This is stated in the policy the user sees before consenting.

---

## Architecture

```
Photo + Symptoms + Body Part
            │
            ▼
   image_analysis.py          ← real pixel features (redness, texture, tint)
            │
            ▼
   condition_engine.py        ← deterministic fusion, confidence floor,
            │                    red-flag escalation, ranking reliability
            ▼
   vector_store.py (RAG)      ← retrieves the matched condition's KB document
            │
            ▼
   LLM (phrasing only)        ← optional; offline fallback if unavailable
            │
            ▼
   Result + Guidance + Specialist + PDF
```

```
clarimed-ai/
├── ai/
│   ├── vision/image_analysis.py     # pixel feature extraction, quality gate, heatmap
│   ├── rules/condition_engine.py    # scoring, fusion, confidence floor, red flags
│   └── rag/
│       ├── kb_loader.py             # parses the authored markdown knowledge base
│       ├── embeddings.py            # offline hashed embeddings
│       ├── kb_initializer.py        # seeds ChromaDB
│       ├── vector_store.py          # retrieval + LLM phrasing + offline fallback
│       ├── symptom_interpreter.py   # free text → known symptoms (closed list)
│       └── specialist_router.py     # complaint → specialist type (closed list)
├── backend/
│   ├── main.py                      # FastAPI endpoints
│   └── app/
│       ├── database.py              # SQLite: screenings, appointments, consent, audit
│       └── report_generator.py      # PDF reports
├── knowledge_base/disease/          # 46 authored .md files, 11 body parts
├── frontend/src/                    # React + Vite + TypeScript + Tailwind
└── training_package/                # CNN training handoff (not yet run)
```

---

## Setup

### Requirements

- Python 3.11 (3.14 is **not** supported — several dependencies lack wheels for it)
- Node.js 18+

### Backend

```bash
py -3.11 -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

pip install -r backend/requirements.txt

# Build the vector store from the knowledge base
python -m ai.rag.kb_initializer

# Run
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Interactive API docs: <http://127.0.0.1:8000/docs>

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The Vite dev server proxies `/api/*` to port 8000.

### Optional: LLM phrasing

Copy `.env.example` to `.env` and add a Groq API key:

```
CLARIMED_LLM_KEY=gsk_...
```

**The app is fully functional without this.** Without a key, guidance is generated from a structured offline fallback built directly from the knowledge base, and symptom interpretation falls back to token matching. The LLM is a quality upgrade, not a dependency.

---

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/config` | Body parts, symptom checklists, red flags |
| `GET` | `/api/privacy/policy` | Machine-readable privacy policy |
| `POST` | `/api/privacy/consent` | Record timestamped, versioned consent |
| `GET` | `/api/privacy/export` | Right to access — export all patient data |
| `DELETE` | `/api/privacy/delete` | Right to erasure |
| `POST` | `/api/screen` | Run a screening (requires `consent_given`) |
| `GET` | `/api/history` | Past screenings |
| `GET` | `/api/report/{id}` | Download a PDF report |
| `POST` | `/api/book-appointment` | Book a specialist slot |
| `GET` | `/api/appointments` | List appointments |

---

## Testing

```bash
pip install -r backend/requirements.txt
pytest
```

**60 tests. No database, no web server, no LLM key, no internet required** — the safety-critical properties must be verifiable on any machine, at any time.

| File | Guards |
|---|---|
| `tests/test_safety.py` | Red-flag escalation across **every** body part and **every** flag; the confidence floor; the closed-list constraints on the symptom interpreter and specialist router; symptom-only conditions never penalised for lacking an image |
| `tests/test_image_privacy.py` | Static analysis of `main.py`: no `open()`, no `INSERT`, no outbound request in the image-handling block; a `del file_bytes` on every exit path; consent verified *before* the image is read |
| `tests/test_knowledge_base.py` | No duplicate condition IDs; every condition has keywords, an overview, a disclaimer, a risk baseline, and a recognised specialist; no orphaned scorers |
| `tests/test_database.py` | Consent is versioned and timestamped; erasure genuinely erases; the audit log survives erasure but structurally cannot hold image data |

The privacy tests are the point. The claim *"we never store your photo"* is not a promise in a policy document — it is a property the test suite enforces. Add `open(path, 'wb')` to the image block and `pytest` fails.

**This suite has already earned its keep.** On its first run it caught a real bug: several image scorers use inverted terms like `(1 - whiteness)` for "dark", and when no photo was uploaded they were being applied to a neutral all-zero placeholder — inverting to `1.0`. Tooth Decay scored `0.60` and Alopecia Areata scored `0.90` **from no evidence at all**, clearing the confidence floor. A user who picked a body part and nothing else would have been confidently told they had a condition. Image scorers now never run without an image, and two regression tests pin that behaviour.

Individual modules also remain directly runnable for quick manual checks:

```bash
python -m ai.rag.kb_loader             # parses all 46 KB documents
python -m ai.rules.condition_engine    # scoring, confidence floor, red flags
python -m ai.rag.specialist_router     # complaint → correct specialist
python -m ai.rag.kb_initializer        # seeds ChromaDB (needs chromadb)
```

---

## Roadmap

**Next**
- Train a real CNN (MobileNetV3 transfer learning) — package is ready in `training_package/`
- Replace the heuristic heatmap with true Grad-CAM once a model exists
- Doctor portal: review queue with patient summary, symptoms, AI findings, and risk score
- Conversational interface replacing the step wizard

**Later**
- Real maps integration for the specialist directory
- Emergency mode: nearest hospital, one-tap call, navigation
- Follow-up tracking with image comparison over time
- Health score and trend
- Family accounts

**Deliberately deferred, with reasons**
- **Digital medical locker** — storing images conflicts with the current no-storage guarantee. Doing this properly needs encrypted storage with separate explicit opt-in consent, not a silent policy change.
- **Live queue tracking** — requires real-time infrastructure and, more importantly, real doctors actually using the system. Impressive as a mockup, hollow under scrutiny.
- **Intimate-area image screening** — the medical need is real, but the required safeguards (age verification, clinician review, moderation, DPDP Act and IT Act §66E compliance) are beyond this project's scope. These conditions can be supported as symptom-only categories instead.

---

## Disclaimer

ClariMed AI provides AI-assisted preliminary screening only. It does not diagnose disease, prescribe treatment, or replace a qualified healthcare professional. Results are informational and must be confirmed by a licensed clinician. Suspected emergencies require immediate in-person medical care, not this tool.