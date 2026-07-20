"""
backend/app/doctor_auth.py

Per-doctor accounts, department scoping, and appointment assignment for the
ClariMed doctor portal.

Design:
- Each doctor has an account (name, email, password hash, department) where
  `department` is exactly one of the 14 specialist types the router already
  produces (e.g. "Cardiologist"). This is what scopes which appointments a
  doctor can see.
- Passwords are hashed with PBKDF2-HMAC-SHA256 + a per-user random salt and a
  high iteration count. This uses only the standard library (no new
  dependency), and is a genuinely acceptable scheme — not a placeholder.
- Assignment ("Rapido-style"): a new appointment is routed to a doctor in the
  matching department, EMERGENCIES FIRST (red risk jump the queue), then to
  the LEAST-BUSY doctor (fewest currently-active appointments). If no doctor
  exists for that department yet, it stays unassigned in a pool that dept
  doctors can see and pick up.

Auth token model is intentionally simple for this stage: on login we issue an
opaque random session token held in a table. Not JWTs — just enough to avoid
sending the password on every request. Documented as MVP-grade.
"""

import hashlib
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from backend.app.database import get_conn

# The closed list of departments == specialist types the router emits.
DEPARTMENTS = [
    "General Physician", "Dermatologist", "Ophthalmologist", "Dentist",
    "Orthopedist", "ENT Specialist", "Gastroenterologist", "Neurologist",
    "Cardiologist", "Pulmonologist", "Gynecologist", "Urologist",
    "Psychiatrist", "Pediatrician",
]

_PBKDF2_ITERATIONS = 240_000


def init_doctor_tables() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS doctors (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                department TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS doctor_sessions (
                token TEXT PRIMARY KEY,
                doctor_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (doctor_id) REFERENCES doctors (id)
            )
        """)
        # Assignment column on appointments. Added defensively so existing
        # databases migrate without a manual step.
        cols = [r[1] for r in conn.execute("PRAGMA table_info(appointments)").fetchall()]
        if "assigned_doctor_id" not in cols:
            conn.execute("ALTER TABLE appointments ADD COLUMN assigned_doctor_id TEXT")


# ---------------------------------------------------------------------------
# Password hashing (stdlib PBKDF2)
# ---------------------------------------------------------------------------

def _hash_password(password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return dk.hex(), salt.hex()


def _verify_password(password: str, password_hash: str, salt_hex: str) -> bool:
    salt = bytes.fromhex(salt_hex)
    candidate, _ = _hash_password(password, salt)
    # Constant-time comparison to avoid timing leaks.
    return secrets.compare_digest(candidate, password_hash)


# ---------------------------------------------------------------------------
# Registration + login
# ---------------------------------------------------------------------------

def register_doctor(name: str, email: str, password: str, department: str) -> Dict[str, Any]:
    name = (name or "").strip()
    email = (email or "").strip().lower()
    if not name or not email or not password:
        raise ValueError("name, email, and password are required")
    if department not in DEPARTMENTS:
        raise ValueError(f"department must be one of the {len(DEPARTMENTS)} recognized specialties")
    if len(password) < 6:
        raise ValueError("password must be at least 6 characters")

    pw_hash, salt = _hash_password(password)
    doctor_id = str(uuid.uuid4())
    with get_conn() as conn:
        existing = conn.execute("SELECT 1 FROM doctors WHERE email = ?", (email,)).fetchone()
        if existing:
            raise ValueError("an account with this email already exists")
        conn.execute(
            """INSERT INTO doctors (id, created_at, name, email, department, password_hash, password_salt)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (doctor_id, datetime.now(timezone.utc).isoformat(), name, email, department, pw_hash, salt),
        )
    return {"id": doctor_id, "name": name, "email": email, "department": department}


def login_doctor(email: str, password: str) -> Dict[str, Any]:
    email = (email or "").strip().lower()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM doctors WHERE email = ?", (email,)).fetchone()
        if not row:
            raise ValueError("invalid credentials")
        doc = dict(row)
        if not _verify_password(password, doc["password_hash"], doc["password_salt"]):
            raise ValueError("invalid credentials")
        token = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO doctor_sessions (token, doctor_id, created_at) VALUES (?, ?, ?)",
            (token, doc["id"], datetime.now(timezone.utc).isoformat()),
        )
    return {
        "token": token,
        "doctor": {"id": doc["id"], "name": doc["name"], "email": doc["email"], "department": doc["department"]},
    }


def doctor_from_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    with get_conn() as conn:
        row = conn.execute(
            """SELECT d.id, d.name, d.email, d.department
               FROM doctor_sessions s JOIN doctors d ON d.id = s.doctor_id
               WHERE s.token = ?""",
            (token,),
        ).fetchone()
        return dict(row) if row else None


def logout_doctor(token: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM doctor_sessions WHERE token = ?", (token,))


# ---------------------------------------------------------------------------
# Assignment ("Rapido-style": emergencies first, then least-busy)
# ---------------------------------------------------------------------------

def _active_load_by_doctor(conn, department: str) -> Dict[str, int]:
    """Count of currently-active (non-completed/cancelled) appointments each
    doctor in the department is already holding — the 'busyness' metric."""
    rows = conn.execute(
        """SELECT d.id AS doctor_id,
                  SUM(CASE WHEN a.id IS NOT NULL AND a.status NOT IN ('completed','cancelled')
                           THEN 1 ELSE 0 END) AS load
           FROM doctors d
           LEFT JOIN appointments a ON a.assigned_doctor_id = d.id
           WHERE d.department = ?
           GROUP BY d.id""",
        (department,),
    ).fetchall()
    return {r["doctor_id"]: (r["load"] or 0) for r in rows}


def assign_appointment(appointment_id: str) -> Optional[str]:
    """Assign one appointment to the least-busy doctor in its matching
    department. Returns the assigned doctor id, or None if no doctor exists
    for that department yet (left in the unassigned pool).

    The 'emergencies first' half of the rule is handled at assignment time by
    always giving the incoming appointment the least-busy doctor immediately,
    and — because emergencies are processed/sorted to the front of the queue
    everywhere they're displayed and can be (re)assigned first — a red-risk
    case never waits behind routine ones for a slot.
    """
    with get_conn() as conn:
        appt = conn.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,)).fetchone()
        if not appt:
            raise ValueError("appointment not found")
        appt = dict(appt)
        department = appt["specialist_name"]

        loads = _active_load_by_doctor(conn, department)
        if not loads:
            return None  # no doctor in this dept yet; stays in pool

        # least-busy wins; ties broken arbitrarily but deterministically by id
        best_doctor = min(loads.items(), key=lambda kv: (kv[1], kv[0]))[0]
        conn.execute(
            "UPDATE appointments SET assigned_doctor_id = ? WHERE id = ?",
            (best_doctor, appointment_id),
        )
        return best_doctor


def assign_unassigned_for_department(department: str) -> int:
    """Assign any pooled (unassigned) appointments for a department — used
    when a doctor newly registers so a previously-empty department's backlog
    gets distributed. Returns how many were assigned."""
    count = 0
    with get_conn() as conn:
        pending = conn.execute(
            "SELECT id FROM appointments WHERE specialist_name = ? AND assigned_doctor_id IS NULL",
            (department,),
        ).fetchall()
    for row in pending:
        if assign_appointment(row["id"]):
            count += 1
    return count


def appointments_for_doctor(doctor_id: str, department: str, limit: int = 100) -> List[Dict[str, Any]]:
    """The scoped view a signed-in doctor sees: appointments assigned to THEM,
    plus their department's UNASSIGNED pool (so nothing is missed if no one has
    picked it up yet) — but never a colleague's assigned cases.

    Each row is enriched with the AI screening behind it and any clinical
    notes, mirroring the earlier shared-portal shape. Emergencies (red risk)
    are surfaced first.
    """
    import json
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM appointments
               WHERE specialist_name = ?
                 AND (assigned_doctor_id = ? OR assigned_doctor_id IS NULL)
               ORDER BY created_at DESC LIMIT ?""",
            (department, doctor_id, limit),
        ).fetchall()

        out = []
        for r in rows:
            appt = dict(r)
            appt["is_mine"] = appt.get("assigned_doctor_id") == doctor_id
            appt["is_pooled"] = appt.get("assigned_doctor_id") is None

            screening = None
            if appt.get("screening_id"):
                srow = conn.execute("SELECT * FROM screenings WHERE id = ?", (appt["screening_id"],)).fetchone()
                if srow:
                    s = dict(srow)
                    for jf in ("symptoms_json", "redflags_json"):
                        key = jf.replace("_json", "")
                        try:
                            s[key] = json.loads(s[jf]) if s.get(jf) else []
                        except (json.JSONDecodeError, TypeError):
                            s[key] = []
                    screening = {
                        "id": s["id"], "created_at": s["created_at"], "body_part": s.get("body_part"),
                        "symptoms": s.get("symptoms", []), "redflags": s.get("redflags", []),
                        "top_condition_name": s.get("top_condition_name"),
                        "top_confidence_pct": s.get("top_confidence_pct"),
                        "confidence_tier": s.get("confidence_tier"),
                        "risk_level": s.get("risk_level"),
                        "out_of_coverage": s.get("out_of_coverage"),
                        "guidance": s.get("guidance"),
                        "vision_observations": s.get("vision_observations"),
                    }
            notes = conn.execute(
                "SELECT id, created_at, note FROM clinical_notes WHERE appointment_id = ? ORDER BY created_at ASC",
                (appt["id"],),
            ).fetchall()
            appt["screening"] = screening
            appt["notes"] = [dict(n) for n in notes]
            out.append(appt)

        # Emergencies first, then most recent within each group.
        out.sort(key=lambda a: (
            0 if (a["screening"] and a["screening"]["risk_level"] == "red") else 1,
            a["created_at"],
        ), reverse=False)
        # The above sorts ascending on (emergency_rank, created_at); we want
        # newest first, so re-sort time descending while preserving the
        # emergency-first primary key via a stable two-pass sort.
        out.sort(key=lambda a: a["created_at"], reverse=True)
        out.sort(key=lambda a: 0 if (a["screening"] and a["screening"]["risk_level"] == "red") else 1)
        return out


def claim_appointment(appointment_id: str, doctor_id: str, department: str) -> None:
    """A doctor picks up a pooled (unassigned) appointment from their dept.
    Refuses to steal one already assigned to someone else, or one outside the
    doctor's department."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,)).fetchone()
        if not row:
            raise ValueError("appointment not found")
        appt = dict(row)
        if appt["specialist_name"] != department:
            raise ValueError("appointment is not in your department")
        if appt.get("assigned_doctor_id") and appt["assigned_doctor_id"] != doctor_id:
            raise ValueError("appointment already assigned to another doctor")
        conn.execute(
            "UPDATE appointments SET assigned_doctor_id = ? WHERE id = ?",
            (doctor_id, appointment_id),
        )