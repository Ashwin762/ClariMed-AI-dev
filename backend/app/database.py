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
                top["pct"] if top else None,
                top.get("confidence_tier") if top else None,
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


if __name__ == "__main__":
    import os
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)  # clean slate for this smoke test
    init_db()
    fake_result = {
        "top": {"id": "EYE001", "name": "Conjunctivitis", "pct": 63, "confidence_tier": "Moderate Confidence"},
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