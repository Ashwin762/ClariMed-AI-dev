"""
tests/test_doctor_auth.py

Covers per-doctor accounts, password security, department scoping, and the
Rapido-style (emergency-first, least-busy) appointment assignment.
"""

import pytest
import backend.app.database as db
import backend.app.doctor_auth as da


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    path = str(tmp_path / "test.db")
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db()
    da.init_doctor_tables()
    return path


# --- registration + auth security ---

def test_register_and_login(temp_db):
    da.register_doctor("Dr Asha", "asha@x.com", "secret123", "Cardiologist")
    result = da.login_doctor("asha@x.com", "secret123")
    assert result["doctor"]["department"] == "Cardiologist"
    assert len(result["token"]) > 20


def test_password_never_stored_in_plaintext(temp_db):
    da.register_doctor("Dr B", "b@x.com", "mypassword", "Neurologist")
    with db.get_conn() as conn:
        row = dict(conn.execute("SELECT * FROM doctors WHERE email = ?", ("b@x.com",)).fetchone())
    assert "mypassword" not in str(row)
    assert row["password_hash"] != "mypassword"
    assert len(row["password_hash"]) == 64  # sha256 hex


def test_wrong_password_rejected(temp_db):
    da.register_doctor("Dr C", "c@x.com", "correct", "Urologist")
    with pytest.raises(ValueError):
        da.login_doctor("c@x.com", "wrong")


def test_duplicate_email_rejected(temp_db):
    da.register_doctor("Dr D", "d@x.com", "pass123", "Dermatologist")
    with pytest.raises(ValueError):
        da.register_doctor("Dr D2", "d@x.com", "pass456", "Dermatologist")


def test_invalid_department_rejected(temp_db):
    with pytest.raises(ValueError):
        da.register_doctor("Dr E", "e@x.com", "pass123", "Wizard")


def test_short_password_rejected(temp_db):
    with pytest.raises(ValueError):
        da.register_doctor("Dr F", "f@x.com", "abc", "Cardiologist")


def test_token_resolves_to_doctor(temp_db):
    da.register_doctor("Dr G", "g@x.com", "pass123", "ENT Specialist")
    token = da.login_doctor("g@x.com", "pass123")["token"]
    doc = da.doctor_from_token(token)
    assert doc["email"] == "g@x.com"
    assert da.doctor_from_token("garbage-token") is None


def test_logout_invalidates_token(temp_db):
    da.register_doctor("Dr H", "h@x.com", "pass123", "Orthopedist")
    token = da.login_doctor("h@x.com", "pass123")["token"]
    da.logout_doctor(token)
    assert da.doctor_from_token(token) is None


# --- assignment: least-busy balancing ---

def test_least_busy_balancing(temp_db):
    a = da.register_doctor("Dr A", "a@x.com", "pass123", "Cardiologist")
    b = da.register_doctor("Dr B", "b@x.com", "pass123", "Cardiologist")
    assigned = []
    for i in range(6):
        aid = db.save_appointment(specialist_name="Cardiologist", slot=f"S{i}")
        assigned.append(da.assign_appointment(aid))
    from collections import Counter
    counts = Counter(assigned)
    # 6 appointments across 2 doctors, least-busy each time -> 3/3
    assert sorted(counts.values()) == [3, 3]


def test_appointment_with_no_department_doctor_stays_pooled(temp_db):
    aid = db.save_appointment(specialist_name="Pulmonologist", slot="S1")
    assert da.assign_appointment(aid) is None


def test_backlog_assigned_when_doctor_registers(temp_db):
    # appointments arrive before any doctor exists
    for i in range(3):
        db.save_appointment(specialist_name="Gynecologist", slot=f"S{i}")
    count = da.assign_unassigned_for_department("Gynecologist")
    assert count == 0  # no doctor yet
    da.register_doctor("Dr G", "g@x.com", "pass123", "Gynecologist")
    count = da.assign_unassigned_for_department("Gynecologist")
    assert count == 3


# --- scoped view: own + pool, emergencies first ---

def _emergency_screening():
    return db.save_screening(
        body_part="cardiovascular", symptoms=["Chest Pain"], redflags=["Crushing Chest Pain"],
        result={"top": {"id": "CARD002", "name": "Chest Pain", "share_pct": 80, "match_strength": "Strong"},
                "risk_level": "red", "out_of_coverage": False},
        guidance="ER now",
    )


def _routine_screening():
    return db.save_screening(
        body_part="cardiovascular", symptoms=["Palpitations"], redflags=[],
        result={"top": {"id": "CARD003", "name": "Palpitations", "share_pct": 55, "match_strength": "Moderate"},
                "risk_level": "yellow", "out_of_coverage": False},
        guidance="monitor",
    )


def test_emergency_sorted_first(temp_db):
    doc = da.register_doctor("Dr A", "a@x.com", "pass123", "Cardiologist")
    r = db.save_appointment(specialist_name="Cardiologist", slot="S1",
                            screening_id=_routine_screening(), patient_name="Routine")
    da.assign_appointment(r)
    e = db.save_appointment(specialist_name="Cardiologist", slot="S2",
                            screening_id=_emergency_screening(), patient_name="Emergency")
    da.assign_appointment(e)
    view = da.appointments_for_doctor(doc["id"], "Cardiologist")
    assert view[0]["patient_name"] == "Emergency"


def test_doctor_sees_own_and_pool_not_colleagues(temp_db):
    a = da.register_doctor("Dr A", "a@x.com", "pass123", "Cardiologist")
    b = da.register_doctor("Dr B", "b@x.com", "pass123", "Cardiologist")
    # one assigned to each (balancing), plus one pooled
    a1 = db.save_appointment(specialist_name="Cardiologist", slot="S1", patient_name="P1")
    da.assign_appointment(a1)
    a2 = db.save_appointment(specialist_name="Cardiologist", slot="S2", patient_name="P2")
    da.assign_appointment(a2)
    # Dr A's view: should include A's own + any pool, but NOT B's assigned
    view = da.appointments_for_doctor(a["id"], "Cardiologist")
    for appt in view:
        # never shows an appointment assigned to a different doctor
        assert appt["assigned_doctor_id"] in (a["id"], None)


def test_claim_pooled_appointment(temp_db):
    doc = da.register_doctor("Dr A", "a@x.com", "pass123", "Neurologist")
    # book for a dept, then unassign to simulate a pool entry
    aid = db.save_appointment(specialist_name="Neurologist", slot="S1", patient_name="Pooled")
    with db.get_conn() as conn:
        conn.execute("UPDATE appointments SET assigned_doctor_id = NULL WHERE id = ?", (aid,))
    da.claim_appointment(aid, doc["id"], "Neurologist")
    view = da.appointments_for_doctor(doc["id"], "Neurologist")
    claimed = [a for a in view if a["id"] == aid][0]
    assert claimed["is_mine"] is True


def test_cannot_claim_other_department(temp_db):
    doc = da.register_doctor("Dr A", "a@x.com", "pass123", "Cardiologist")
    aid = db.save_appointment(specialist_name="Neurologist", slot="S1")
    with pytest.raises(ValueError):
        da.claim_appointment(aid, doc["id"], "Cardiologist")


def test_cannot_steal_assigned_appointment(temp_db):
    a = da.register_doctor("Dr A", "a@x.com", "pass123", "Cardiologist")
    b = da.register_doctor("Dr B", "b@x.com", "pass123", "Cardiologist")
    aid = db.save_appointment(specialist_name="Cardiologist", slot="S1")
    da.assign_appointment(aid)  # goes to one of them
    with db.get_conn() as conn:
        owner = dict(conn.execute("SELECT assigned_doctor_id FROM appointments WHERE id=?", (aid,)).fetchone())
    other = b["id"] if owner["assigned_doctor_id"] == a["id"] else a["id"]
    with pytest.raises(ValueError):
        da.claim_appointment(aid, other, "Cardiologist")