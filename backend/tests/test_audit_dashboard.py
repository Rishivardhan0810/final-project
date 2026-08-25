# Automated tests -- covers the read-only Audit & Safety dashboard
# endpoints: GET /api/audit/summary, GET /api/audit/activity.
"""
Builds a throwaway SQLite database with a known, deliberately-constructed
set of acknowledgements and dispenses so every count below is predictable,
and points backend/main.py's DB_PATH at it, exercising the actual
audit_summary()/audit_activity() code.
"""
import os
import sys
import sqlite3
import uuid

import pytest
from fastapi import HTTPException

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "..", "data")
sys.path.insert(0, os.path.join(HERE, ".."))

import main as main_module  # noqa: E402
from main import audit_summary, audit_activity  # noqa: E402


def _build_audit_test_db(path):
    conn = sqlite3.connect(path)
    with open(os.path.join(DATA_DIR, "schema.sql")) as f:
        conn.executescript(f.read())

    patient_ids = []
    for _ in range(2):
        pid = str(uuid.uuid4())[:8]
        patient_ids.append(pid)
        conn.execute(
            "INSERT INTO patients (patient_id, first_name, last_name, date_of_birth, "
            "condition, allergy, gp_name, concurrent_medications, polypharmacy_count) "
            "VALUES (?, 'First', 'Last', '1980-01-01', 'Hypertension', 'None recorded', "
            "'Dr Test', '', 0)",
            (pid,),
        )

    # 1 NONE, 2 LOW, 1 MEDIUM, 3 HIGH, 2 FIRST_PRESCRIPTION_REVIEW = 9 acknowledgements
    ack_plan = (
        ["NONE"] + ["LOW"] * 2 + ["MEDIUM"] + ["HIGH"] * 3 + ["FIRST_PRESCRIPTION_REVIEW"] * 2
    )
    for i, risk_level in enumerate(ack_plan):
        conn.execute(
            "INSERT INTO acknowledgements (patient_id, pharmacist_name, ack_timestamp, risk_level) "
            "VALUES (?, ?, ?, ?)",
            (patient_ids[i % 2], f"Pharmacist {i}", f"2026-01-{i + 1:02d}T10:00:00+00:00", risk_level),
        )

    # 4 dispenses, strictly increasing timestamps -- the last one is the
    # most recent event overall, used to test ordering.
    for i in range(4):
        conn.execute(
            "INSERT INTO dispenses (patient_id, ack_id, pharmacist_name, drug_name, dose_mg, "
            "dispense_timestamp) VALUES (?, NULL, ?, ?, ?, ?)",
            (patient_ids[i % 2], f"Pharmacist {i}", "Amlodipine", 5 + i,
             f"2026-02-{i + 1:02d}T10:00:00+00:00"),
        )

    conn.commit()
    conn.close()
    return patient_ids


@pytest.fixture
def audit_db(tmp_path, monkeypatch):
    db_path = tmp_path / "audit.db"
    patient_ids = _build_audit_test_db(str(db_path))
    monkeypatch.setattr(main_module, "DB_PATH", str(db_path))
    return patient_ids


# ---------------------------------------------------------------------
# GET /api/audit/summary
# ---------------------------------------------------------------------

def test_audit_summary_total_dispense_count(audit_db):
    assert audit_summary()["total_dispenses"] == 4


def test_audit_summary_total_acknowledgement_count(audit_db):
    assert audit_summary()["total_acknowledgements"] == 9


def test_audit_summary_first_prescription_reviews_counted_separately(audit_db):
    result = audit_summary()
    assert result["first_prescription_reviews"] == 2
    # and NOT folded into any of the four clinical risk counts
    assert sum(result["acknowledged_risk_counts"].values()) == 9 - 2


def test_audit_summary_acknowledged_risk_counts_correct(audit_db):
    result = audit_summary()
    assert result["acknowledged_risk_counts"] == {"NONE": 1, "LOW": 2, "MEDIUM": 1, "HIGH": 3}


# ---------------------------------------------------------------------
# GET /api/audit/activity
# ---------------------------------------------------------------------

def test_audit_activity_returns_newest_events_first(audit_db):
    result = audit_activity(limit=50)
    timestamps = [e["happened_at"] for e in result["events"]]
    assert timestamps == sorted(timestamps, reverse=True)
    assert result["events"][0]["happened_at"].startswith("2026-02-04")  # the last dispense


def test_audit_activity_returns_patient_id_not_name(audit_db):
    result = audit_activity(limit=50)
    assert len(result["events"]) > 0
    for event in result["events"]:
        assert "patient_id" in event
        assert "patient_name" not in event
        assert "first_name" not in event
        assert "last_name" not in event
    assert result["events"][0]["patient_id"] in audit_db  # a real patient_id, not a name


def test_audit_activity_respects_limit_parameter(audit_db):
    assert len(audit_activity(limit=3)["events"]) == 3
    assert len(audit_activity(limit=1)["events"]) == 1


def test_audit_activity_default_limit_returns_all_available_events(audit_db):
    # 9 acknowledgements + 4 dispenses = 13 total, well under the default of 50
    assert len(audit_activity()["events"]) == 13


def test_audit_activity_rejects_non_positive_limit(audit_db):
    with pytest.raises(HTTPException) as exc_info:
        audit_activity(limit=0)
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info:
        audit_activity(limit=-5)
    assert exc_info.value.status_code == 400
