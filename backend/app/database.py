"""
backend/app/database.py

Real, lightweight persistence layer using SQLite (built into Python's
standard library — zero extra dependencies, safe for low-spec hardware).

Replaces the previously empty database.py stub. Implements the "Prediction
History" / "Reports" tables from the original product spec.
"""

import sqlite3
import json
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

DB_PATH = "clarimed.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create tables if they don't already exist. Safe to call on every startup."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS screenings (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                patient_name TEXT,
                patient_email TEXT,
                body_part TEXT NOT NULL,
                symptoms_json TEXT,
                redflags_json TEXT,
                top_condition_id TEXT,
                top_condition_name TEXT,
                top_confidence_pct INTEGER,
                confidence_tier TEXT,
                risk_level TEXT,
                out_of_coverage INTEGER,
                result_json TEXT,
                guidance TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_screenings_email
            ON screenings (patient_email)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS consents (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                patient_email TEXT,
                policy_version TEXT NOT NULL,
                consented_image_processing INTEGER NOT NULL,
                consented_data_storage INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                action TEXT NOT NULL,
                patient_email TEXT,
                detail TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS appointments (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                screening_id TEXT,
                patient_name TEXT,
                patient_email TEXT,
                specialist_name TEXT NOT NULL,
                clinic_name TEXT,
                slot TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'confirmed',
                FOREIGN KEY (screening_id) REFERENCES screenings (id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clinical_notes (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                appointment_id TEXT NOT NULL,
                note TEXT NOT NULL,
                FOREIGN KEY (appointment_id) REFERENCES appointments (id)
            )
        """)


# ---------------------------------------------------------------------------
# Consent + audit
# ---------------------------------------------------------------------------

PRIVACY_POLICY_VERSION = "1.0"


def record_consent(
    patient_email: Optional[str],
    consented_image_processing: bool,
    consented_data_storage: bool,
) -> str:
    """Store an explicit, timestamped consent record tied to a policy version.
    Auditable proof that the user agreed before any processing took place."""
    consent_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO consents (id, created_at, patient_email, policy_version,
               consented_image_processing, consented_data_storage)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                consent_id, datetime.now(timezone.utc).isoformat(), patient_email,
                PRIVACY_POLICY_VERSION, int(consented_image_processing), int(consented_data_storage),
            ),
        )
    write_audit("consent_recorded", patient_email, f"policy_v{PRIVACY_POLICY_VERSION}")
    return consent_id


def write_audit(action: str, patient_email: Optional[str] = None, detail: Optional[str] = None):
    """Append-only audit trail. Deliberately never records image data or
    image bytes — only that an action occurred."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO audit_log (id, created_at, action, patient_email, detail) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), datetime.now(timezone.utc).isoformat(), action, patient_email, detail),
        )


def delete_patient_data(patient_email: str) -> Dict[str, int]:
    """Right-to-erasure: removes all screenings, appointments, and consent
    records for this email. The audit log retains only the fact that a
    deletion occurred (required for accountability), not the deleted content."""
    with get_conn() as conn:
        s = conn.execute("DELETE FROM screenings WHERE patient_email = ?", (patient_email,)).rowcount
        a = conn.execute("DELETE FROM appointments WHERE patient_email = ?", (patient_email,)).rowcount
        c = conn.execute("DELETE FROM consents WHERE patient_email = ?", (patient_email,)).rowcount
    write_audit("data_deleted", patient_email, f"screenings={s} appointments={a} consents={c}")
    return {"screenings_deleted": s, "appointments_deleted": a, "consents_deleted": c}


def export_patient_data(patient_email: str) -> Dict[str, Any]:
    """Right-to-access: returns everything stored about this patient."""
    with get_conn() as conn:
        screenings = [dict(r) for r in conn.execute(
            "SELECT * FROM screenings WHERE patient_email = ?", (patient_email,)).fetchall()]
        appointments = [dict(r) for r in conn.execute(
            "SELECT * FROM appointments WHERE patient_email = ?", (patient_email,)).fetchall()]
        consents = [dict(r) for r in conn.execute(
            "SELECT * FROM consents WHERE patient_email = ?", (patient_email,)).fetchall()]
    write_audit("data_exported", patient_email, f"screenings={len(screenings)}")
    return {"screenings": screenings, "appointments": appointments, "consents": consents}



def save_screening(
    body_part: str,
    symptoms: List[str],
    redflags: List[str],
    result: Dict[str, Any],
    guidance: str,
    patient_name: Optional[str] = None,
    patient_email: Optional[str] = None,
) -> str:
    """Persist one screening result. Returns the generated screening id."""
    screening_id = str(uuid.uuid4())
    top = result.get("top")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO screenings (
                id, created_at, patient_name, patient_email, body_part,
                symptoms_json, redflags_json, top_condition_id, top_condition_name,
                top_confidence_pct, confidence_tier, risk_level, out_of_coverage,
                result_json, guidance
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                screening_id,
                datetime.now(timezone.utc).isoformat(),
                patient_name,
                patient_email,
                body_part,
                json.dumps(symptoms),
                json.dumps(redflags),
                top["id"] if top else None,
                top["name"] if top else None,
                top["share_pct"] if top else None,
                top.get("match_strength") if top else None,
                result.get("risk_level"),
                int(result.get("out_of_coverage", False)),
                json.dumps(result),
                guidance,
            ),
        )
    return screening_id


def get_history(patient_email: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch recent screenings, optionally filtered to one patient's email."""
    with get_conn() as conn:
        if patient_email:
            rows = conn.execute(
                "SELECT * FROM screenings WHERE patient_email = ? ORDER BY created_at DESC LIMIT ?",
                (patient_email, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM screenings ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def get_screening_by_id(screening_id: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM screenings WHERE id = ?", (screening_id,)).fetchone()
        return dict(row) if row else None


def save_appointment(
    specialist_name: str,
    slot: str,
    screening_id: Optional[str] = None,
    clinic_name: Optional[str] = None,
    patient_name: Optional[str] = None,
    patient_email: Optional[str] = None,
) -> str:
    """Requires reaching the live scheduling system — this is the part of the
    ecosystem that genuinely needs connectivity, unlike the screening itself."""
    appointment_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO appointments (
                id, created_at, screening_id, patient_name, patient_email,
                specialist_name, clinic_name, slot, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'confirmed')
            """,
            (
                appointment_id, datetime.now(timezone.utc).isoformat(), screening_id,
                patient_name, patient_email, specialist_name, clinic_name, slot,
            ),
        )
    return appointment_id


def get_appointments(patient_email: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        if patient_email:
            rows = conn.execute(
                "SELECT * FROM appointments WHERE patient_email = ? ORDER BY created_at DESC LIMIT ?",
                (patient_email, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM appointments ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def get_appointments_for_doctor(limit: int = 100) -> List[Dict[str, Any]]:
    """Doctor-portal view: every appointment enriched with the AI screening
    that led to it (so the clinician sees the original findings) plus any
    clinical notes already recorded. Read-only join — never mutates.

    Privacy note: this deliberately does NOT surface the patient's uploaded
    image or raw image features. Images are never stored (see the privacy
    layer), and the portal is gated only by a shared password, so it exposes
    only what a clinician needs to triage a referral: symptoms, the AI's
    reasoning, risk level, and guidance.
    """
    with get_conn() as conn:
        appts = conn.execute(
            "SELECT * FROM appointments ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()

        result = []
        for a in appts:
            appt = dict(a)
            screening = None
            if appt.get("screening_id"):
                srow = conn.execute(
                    "SELECT * FROM screenings WHERE id = ?", (appt["screening_id"],)
                ).fetchone()
                if srow:
                    s = dict(srow)
                    # Parse the stored JSON blobs into real structures for the UI,
                    # tolerating any legacy/malformed rows rather than crashing
                    # the whole doctor view over one bad record.
                    for jf in ("symptoms_json", "redflags_json"):
                        if s.get(jf):
                            try:
                                s[jf.replace("_json", "")] = json.loads(s[jf])
                            except (json.JSONDecodeError, TypeError):
                                s[jf.replace("_json", "")] = []
                        else:
                            s[jf.replace("_json", "")] = []
                    screening = {
                        "id": s["id"],
                        "created_at": s["created_at"],
                        "body_part": s.get("body_part"),
                        "symptoms": s.get("symptoms", []),
                        "redflags": s.get("redflags", []),
                        "top_condition_name": s.get("top_condition_name"),
                        "top_confidence_pct": s.get("top_confidence_pct"),
                        "confidence_tier": s.get("confidence_tier"),
                        "risk_level": s.get("risk_level"),
                        "out_of_coverage": s.get("out_of_coverage"),
                        "guidance": s.get("guidance"),
                    }
            notes = conn.execute(
                "SELECT id, created_at, note FROM clinical_notes WHERE appointment_id = ? ORDER BY created_at ASC",
                (appt["id"],),
            ).fetchall()
            appt["screening"] = screening
            appt["notes"] = [dict(n) for n in notes]
            result.append(appt)
        return result


def add_clinical_note(appointment_id: str, note: str) -> Dict[str, Any]:
    """Records a timestamped clinical note against an appointment."""
    note_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        # Guard against notes attached to a non-existent appointment.
        exists = conn.execute(
            "SELECT 1 FROM appointments WHERE id = ?", (appointment_id,)
        ).fetchone()
        if not exists:
            raise ValueError("appointment not found")
        conn.execute(
            "INSERT INTO clinical_notes (id, created_at, appointment_id, note) VALUES (?, ?, ?, ?)",
            (note_id, created_at, appointment_id, note),
        )
    return {"id": note_id, "created_at": created_at, "appointment_id": appointment_id, "note": note}


if __name__ == "__main__":
    import os
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)  # clean slate for this smoke test
    init_db()
    fake_result = {
        "top": {"id": "EYE001", "name": "Conjunctivitis", "share_pct": 63, "match_strength": "Moderate match"},
        "risk_level": "green",
        "out_of_coverage": False,
    }
    sid = save_screening(
        "eye", ["Ocular Redness", "Watery Eyes"], [], fake_result,
        "Sample guidance text.", patient_name="Test Patient", patient_email="test@example.com",
    )
    print("Saved screening id:", sid)
    hist = get_history(patient_email="test@example.com")
    print(f"History for test@example.com: {len(hist)} record(s)")
    print(" ->", hist[0]["top_condition_name"], hist[0]["top_confidence_pct"], "%", hist[0]["confidence_tier"])
    fetched = get_screening_by_id(sid)
    print("Fetched by id ok:", fetched is not None and fetched["id"] == sid)
    os.remove(DB_PATH)
    print("Cleanup done.")