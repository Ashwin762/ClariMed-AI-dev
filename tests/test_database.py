"""
tests/test_database.py

Verifies the data-rights guarantees:
  - Consent is recorded with a policy version and timestamp.
  - Right to erasure genuinely erases patient content.
  - The audit log survives erasure (accountability) but never holds content.
"""

import os
import tempfile
import pytest

import backend.app.database as db


@pytest.fixture
def temp_db(monkeypatch):
    """Run each test against a throwaway database file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)  # init_db will create it
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db()
    yield path
    if os.path.exists(path):
        os.unlink(path)


SAMPLE_RESULT = {
    "top": {
        "id": "EYE001", "name": "Conjunctivitis", "share_pct": 63,
        "match_strength": "Moderate match", "specialist": "Ophthalmologist",
    },
    "risk_level": "green",
    "out_of_coverage": False,
}


def test_all_expected_tables_are_created(temp_db):
    with db.get_conn() as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"screenings", "appointments", "consents", "audit_log"} <= tables


def test_consent_is_recorded_with_policy_version(temp_db):
    db.record_consent("a@b.com", True, True)
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM consents").fetchone()
    assert row["policy_version"] == db.PRIVACY_POLICY_VERSION
    assert row["consented_image_processing"] == 1
    assert row["created_at"]


def test_screening_is_persisted_and_retrievable(temp_db):
    sid = db.save_screening(
        "eye", ["Ocular Redness"], [], SAMPLE_RESULT, "guidance",
        patient_email="a@b.com",
    )
    fetched = db.get_screening_by_id(sid)
    assert fetched is not None
    assert fetched["top_condition_name"] == "Conjunctivitis"
    assert fetched["confidence_tier"] == "Moderate match"


def test_export_returns_everything_for_a_patient(temp_db):
    email = "a@b.com"
    db.record_consent(email, True, True)
    sid = db.save_screening("eye", ["Ocular Redness"], [], SAMPLE_RESULT, "g", patient_email=email)
    db.save_appointment("Dr. X", "Tomorrow 10AM", screening_id=sid, patient_email=email)

    exported = db.export_patient_data(email)
    assert len(exported["screenings"]) == 1
    assert len(exported["appointments"]) == 1
    assert len(exported["consents"]) == 1


def test_deletion_erases_all_patient_content(temp_db):
    email = "a@b.com"
    db.record_consent(email, True, True)
    sid = db.save_screening("eye", ["Ocular Redness"], [], SAMPLE_RESULT, "g", patient_email=email)
    db.save_appointment("Dr. X", "Tomorrow 10AM", screening_id=sid, patient_email=email)

    result = db.delete_patient_data(email)
    assert result["screenings_deleted"] == 1
    assert result["appointments_deleted"] == 1
    assert result["consents_deleted"] == 1

    after = db.export_patient_data(email)
    assert after["screenings"] == []
    assert after["appointments"] == []
    assert after["consents"] == []


def test_deletion_does_not_affect_other_patients(temp_db):
    db.save_screening("eye", ["Ocular Redness"], [], SAMPLE_RESULT, "g", patient_email="keep@b.com")
    db.save_screening("eye", ["Ocular Redness"], [], SAMPLE_RESULT, "g", patient_email="delete@b.com")

    db.delete_patient_data("delete@b.com")

    assert len(db.export_patient_data("keep@b.com")["screenings"]) == 1
    assert len(db.export_patient_data("delete@b.com")["screenings"]) == 0


def test_audit_log_survives_deletion(temp_db):
    """Accountability: we must retain the fact a deletion occurred."""
    email = "a@b.com"
    db.record_consent(email, True, True)
    db.delete_patient_data(email)

    with db.get_conn() as conn:
        actions = [r[0] for r in conn.execute("SELECT action FROM audit_log").fetchall()]
    assert "consent_recorded" in actions
    assert "data_deleted" in actions


def test_audit_log_schema_cannot_hold_image_data(temp_db):
    """Structural guarantee: there is nowhere in the audit log to put an image."""
    with db.get_conn() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(audit_log)").fetchall()]
    joined = " ".join(cols).lower()
    for forbidden in ("image", "photo", "blob", "bytes", "picture"):
        assert forbidden not in joined, f"audit_log has a '{forbidden}' column"


def test_screenings_schema_cannot_hold_image_data(temp_db):
    with db.get_conn() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(screenings)").fetchall()]
    joined = " ".join(cols).lower()
    for forbidden in ("image", "photo", "blob", "heatmap", "picture"):
        assert forbidden not in joined, f"screenings has a '{forbidden}' column"


def test_deleting_a_patient_with_no_data_is_safe(temp_db):
    """Must not raise, must report zeroes."""
    result = db.delete_patient_data("nobody@nowhere.com")
    assert result == {
        "screenings_deleted": 0, "appointments_deleted": 0, "consents_deleted": 0,
    }