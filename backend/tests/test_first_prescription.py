# Automated tests -- covers the first-prescription and zero-prescription
# handling in backend/main.py.
"""
Each test builds a tiny throwaway SQLite database from the real
data/schema.sql and points backend/main.py's DB_PATH at it, so these
exercise the actual lookup_patient()/acknowledge() code, not a copy of it.
"""
import os
import sys
import sqlite3
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "..", "data")
sys.path.insert(0, os.path.join(HERE, ".."))

import main as main_module  # noqa: E402
from main import lookup_patient, acknowledge, LookupRequest, AckRequest  # noqa: E402

# Every patient built by _build_test_db() below has this fixed DOB --
# lookup now requires patient_id AND date_of_birth together.
TEST_DOB = "2000-01-01"


def _build_test_db(path, n_prescriptions):
    """A minimal database with exactly one patient who has `n_prescriptions`
    prescriptions on record."""
    conn = sqlite3.connect(path)
    with open(os.path.join(DATA_DIR, "schema.sql")) as f:
        conn.executescript(f.read())

    patient_id = str(uuid.uuid4())[:8]
    conn.execute(
        "INSERT INTO patients (patient_id, first_name, last_name, date_of_birth, "
        "condition, allergy, gp_name, concurrent_medications, polypharmacy_count) "
        "VALUES (?, 'Test', 'Patient', '2000-01-01', 'Hypertension', 'None recorded', "
        "'Dr Test', '', 0)",
        (patient_id,),
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
def zero_rx_patient(tmp_path, monkeypatch):
    db_path = tmp_path / "zero_rx.db"
    patient_id = _build_test_db(str(db_path), n_prescriptions=0)
    monkeypatch.setattr(main_module, "DB_PATH", str(db_path))
    return patient_id


@pytest.fixture
def first_rx_patient(tmp_path, monkeypatch):
    db_path = tmp_path / "first_rx.db"
    patient_id = _build_test_db(str(db_path), n_prescriptions=1)
    monkeypatch.setattr(main_module, "DB_PATH", str(db_path))
    return patient_id


@pytest.fixture
def normal_patient(tmp_path, monkeypatch):
    db_path = tmp_path / "normal_rx.db"
    patient_id = _build_test_db(str(db_path), n_prescriptions=2)
    monkeypatch.setattr(main_module, "DB_PATH", str(db_path))
    return patient_id


# ---------------------------------------------------------------------
# first prescription vs. normal case
# ---------------------------------------------------------------------

def test_first_prescription_gets_its_own_status_and_no_risk_label(first_rx_patient):
    result = lookup_patient(LookupRequest(patient_id=first_rx_patient, date_of_birth=TEST_DOB))
    assert result["status"] == "first_prescription"
    assert result["alert"] is None  # no NONE/LOW/MEDIUM/HIGH ever assigned
    assert len(result["prescriptions"]) == 1  # current prescription still returned
    assert "no previous prescription" in result["status_message"].lower()


def test_normal_two_prescription_case_is_status_normal_not_first_prescription(normal_patient):
    """Same result shape, but status must clearly differ from the
    first-prescription case."""
    result = lookup_patient(LookupRequest(patient_id=normal_patient, date_of_birth=TEST_DOB))
    assert result["status"] == "normal"
    assert result["status_message"] is None


# A first-prescription review needs to be acknowledgeable and
# distinguishable from a normal risk acknowledgement, without a schema
# change. Whether the Dispense button itself stays locked until this
# happens is a RecordScreen.jsx concern -- no JS test runner here, so
# that part is checked by hand, not covered below.

def test_first_prescription_review_is_acknowledgeable_and_distinguishable(first_rx_patient):
    result = acknowledge(AckRequest(
        patient_id=first_rx_patient,
        pharmacist_name="Test Pharmacist",
        risk_level="FIRST_PRESCRIPTION_REVIEW",
    ))
    assert result["status"] == "acknowledged"

    conn = sqlite3.connect(main_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT pharmacist_name, risk_level FROM acknowledgements WHERE patient_id = ?",
        (first_rx_patient,),
    ).fetchone()
    conn.close()

    assert row["pharmacist_name"] == "Test Pharmacist"
    assert row["risk_level"] == "FIRST_PRESCRIPTION_REVIEW"
    assert row["risk_level"] not in ("NONE", "LOW", "MEDIUM", "HIGH")


# ---------------------------------------------------------------------
# zero-prescription patient shouldn't crash
# ---------------------------------------------------------------------

def test_zero_prescription_patient_does_not_crash_and_is_labelled(zero_rx_patient):
    result = lookup_patient(LookupRequest(patient_id=zero_rx_patient, date_of_birth=TEST_DOB))
    assert result["status"] == "no_prescriptions"
    assert result["prescriptions"] == []
    assert result["alert"] is None
    assert result["status_message"] == "No prescription available for this patient."


# There's nothing to dispense for a zero-prescription patient. The
# frontend never renders a Dispense button in this state (checked by
# hand, same reason as above) -- at the backend level we can at least
# confirm there's no prescription data for it to source a drug from.

def test_zero_prescription_patient_has_nothing_dispensable(zero_rx_patient):
    result = lookup_patient(LookupRequest(patient_id=zero_rx_patient, date_of_birth=TEST_DOB))
    assert result["prescriptions"] == []
