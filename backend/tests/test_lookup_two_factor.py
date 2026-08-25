# Automated tests -- proves two-factor lookup: patient_id AND
# date_of_birth must both match.
"""
Builds a throwaway SQLite database from the real data/schema.sql and
points backend/main.py's DB_PATH at it, exercising the actual
lookup_patient() code.
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
from main import lookup_patient, LookupRequest  # noqa: E402

CORRECT_DOB = "1985-06-15"


def _build_test_db(path, n_prescriptions=2):
    conn = sqlite3.connect(path)
    with open(os.path.join(DATA_DIR, "schema.sql")) as f:
        conn.executescript(f.read())

    patient_id = str(uuid.uuid4())[:8]
    conn.execute(
        "INSERT INTO patients (patient_id, first_name, last_name, date_of_birth, "
        "condition, allergy, gp_name, concurrent_medications, polypharmacy_count) "
        "VALUES (?, 'Jane', 'Doe', ?, 'Hypertension', 'None recorded', 'Dr Test', '', 0)",
        (patient_id, CORRECT_DOB),
    )
    for i in range(n_prescriptions):
        conn.execute(
            "INSERT INTO prescriptions (patient_id, drug_name, drug_class, dose_mg, "
            "formulation, manufacturer, route, start_date, prescriber, is_current) "
            "VALUES (?, 'Amlodipine', 'Calcium channel blocker', 5, 'Standard', 'Teva', "
            "'Oral', ?, 'Dr Test', ?)",
            (patient_id, f"2026-0{i + 1}-01", 1 if i == n_prescriptions - 1 else 0),
        )
    conn.commit()
    conn.close()
    return patient_id


@pytest.fixture
def patient(tmp_path, monkeypatch):
    db_path = tmp_path / "lookup.db"
    patient_id = _build_test_db(str(db_path), n_prescriptions=2)
    monkeypatch.setattr(main_module, "DB_PATH", str(db_path))
    return patient_id


@pytest.fixture
def first_rx_patient(tmp_path, monkeypatch):
    db_path = tmp_path / "lookup_first.db"
    patient_id = _build_test_db(str(db_path), n_prescriptions=1)
    monkeypatch.setattr(main_module, "DB_PATH", str(db_path))
    return patient_id


def test_correct_id_and_correct_dob_succeeds(patient):
    result = lookup_patient(LookupRequest(patient_id=patient, date_of_birth=CORRECT_DOB))
    assert result["patient"]["patient_id"] == patient
    assert result["patient"]["first_name"] == "Jane"
    assert result["patient"]["last_name"] == "Doe"


def test_correct_id_wrong_dob_returns_404(patient):
    with pytest.raises(HTTPException) as exc_info:
        lookup_patient(LookupRequest(patient_id=patient, date_of_birth="1999-01-01"))
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "No matching patient record found."


def test_wrong_id_correct_dob_returns_404(patient):
    with pytest.raises(HTTPException) as exc_info:
        lookup_patient(LookupRequest(patient_id="nonexistent-id", date_of_birth=CORRECT_DOB))
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "No matching patient record found."


def test_first_prescription_workflow_still_works_with_two_factor_lookup(first_rx_patient):
    """First-prescription status logic should still work once two-factor
    lookup finds the patient."""
    result = lookup_patient(LookupRequest(patient_id=first_rx_patient, date_of_birth=CORRECT_DOB))
    assert result["status"] == "first_prescription"
    assert result["alert"] is None
    assert len(result["prescriptions"]) == 1
