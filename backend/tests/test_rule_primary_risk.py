# Automated tests -- proves the deterministic rule is the primary live
# risk decision, and that Random Forest / the text model can't override it.
"""
Builds a throwaway SQLite database from the real data/schema.sql and
points backend/main.py's DB_PATH at it, exercising the actual
lookup_patient()/acknowledge() code. Random Forest and the text model are
swapped for a fake that always predicts a fixed, deliberately wrong risk
level -- proving the rule holds even when both actively disagree with it,
not just that they happen to agree today.
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
from comparison_engine import classify_risk, compare_prescriptions, Prescription  # noqa: E402

# Every patient built by _build_two_rx_db() below has this fixed DOB --
# lookup now requires patient_id AND date_of_birth together.
TEST_DOB = "2000-01-01"


def _build_two_rx_db(path, previous, current):
    """A patient with exactly two prescriptions (previous + current), so
    lookup_patient() runs the full comparison + risk-scoring path."""
    conn = sqlite3.connect(path)
    with open(os.path.join(DATA_DIR, "schema.sql")) as f:
        conn.executescript(f.read())

    patient_id = str(uuid.uuid4())[:8]
    conn.execute(
        "INSERT INTO patients (patient_id, first_name, last_name, date_of_birth, "
        "condition, allergy, gp_name, concurrent_medications, polypharmacy_count) "
        "VALUES (?, 'Test', 'Patient', '2000-01-01', 'Atrial fibrillation', 'None recorded', "
        "'Dr Test', '', 0)",
        (patient_id,),
    )
    for rx, is_current, start in [(previous, 0, "2026-01-01"), (current, 1, "2026-02-01")]:
        conn.execute(
            "INSERT INTO prescriptions (patient_id, drug_name, drug_class, dose_mg, "
            "formulation, manufacturer, route, start_date, prescriber, is_current) "
            "VALUES (?, ?, 'Test class', ?, ?, 'Teva', ?, ?, 'Dr Test', ?)",
            (patient_id, rx["drug_name"], rx["dose_mg"], rx["formulation"], rx["route"], start, is_current),
        )
    conn.commit()
    conn.close()
    return patient_id


@pytest.fixture
def high_risk_drug_switch_patient(tmp_path, monkeypatch):
    """A switch onto Warfarin (NTI) -- the rule says HIGH (drug_changed on
    an NTI drug), unambiguously, for a clean test case."""
    db_path = tmp_path / "hr.db"
    patient_id = _build_two_rx_db(
        str(db_path),
        previous={"drug_name": "Amlodipine", "dose_mg": 5, "formulation": "Standard", "route": "Oral"},
        current={"drug_name": "Warfarin", "dose_mg": 5, "formulation": "Standard", "route": "Oral"},
    )
    monkeypatch.setattr(main_module, "DB_PATH", str(db_path))
    return patient_id


class _FakeModel:
    """Always predicts a fixed value, regardless of input."""
    def __init__(self, fixed_prediction):
        self.fixed_prediction = fixed_prediction

    def predict(self, X):
        n = len(X) if hasattr(X, "__len__") else 1
        return [self.fixed_prediction] * n


def test_risk_final_equals_rule_risk(high_risk_drug_switch_patient):
    result = lookup_patient(LookupRequest(patient_id=high_risk_drug_switch_patient, date_of_birth=TEST_DOB))
    alert = result["alert"]
    assert alert["risk_final"] == alert["risk_rule"]
    assert alert["risk_final"] == "HIGH"  # Warfarin is NTI -> drug switch -> HIGH by the rule


def test_random_forest_cannot_override_the_rule(high_risk_drug_switch_patient, monkeypatch):
    """Even when the (faked) Random Forest actively disagrees, predicting
    the opposite risk level, risk_final must still follow the rule."""
    monkeypatch.setattr(main_module, "rf_model", _FakeModel("NONE"))
    result = lookup_patient(LookupRequest(patient_id=high_risk_drug_switch_patient, date_of_birth=TEST_DOB))
    alert = result["alert"]
    assert alert["risk_random_forest"] == "NONE"   # the disagreement was recorded...
    assert alert["risk_final"] == "HIGH"            # ...but never used to decide the outcome
    assert alert["risk_final"] != alert["risk_random_forest"]


def test_text_model_cannot_override_the_rule(high_risk_drug_switch_patient, monkeypatch):
    monkeypatch.setattr(main_module, "text_model", _FakeModel("NONE"))
    result = lookup_patient(LookupRequest(patient_id=high_risk_drug_switch_patient, date_of_birth=TEST_DOB))
    alert = result["alert"]
    assert alert["risk_text_model"] == "NONE"
    assert alert["risk_final"] == "HIGH"
    assert alert["risk_final"] != alert["risk_text_model"]


def test_both_model_predictions_are_still_returned(high_risk_drug_switch_patient, monkeypatch):
    monkeypatch.setattr(main_module, "rf_model", _FakeModel("MEDIUM"))
    monkeypatch.setattr(main_module, "text_model", _FakeModel("LOW"))
    result = lookup_patient(LookupRequest(patient_id=high_risk_drug_switch_patient, date_of_birth=TEST_DOB))
    alert = result["alert"]
    assert alert["risk_random_forest"] == "MEDIUM"
    assert alert["risk_text_model"] == "LOW"
    assert alert["risk_final"] == "HIGH"  # still the rule, despite both models disagreeing


def test_existing_acknowledgement_behaviour_intact(high_risk_drug_switch_patient):
    result = acknowledge(AckRequest(
        patient_id=high_risk_drug_switch_patient,
        pharmacist_name="Test Pharmacist",
        risk_level="HIGH",
    ))
    assert result["status"] == "acknowledged"

    conn = sqlite3.connect(main_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT pharmacist_name, risk_level FROM acknowledgements WHERE patient_id = ?",
        (high_risk_drug_switch_patient,),
    ).fetchone()
    conn.close()
    assert row["pharmacist_name"] == "Test Pharmacist"
    assert row["risk_level"] == "HIGH"


def test_classify_risk_matches_via_compare_prescriptions_integration():
    """classify_risk() should still give the right answer fed values from
    a real compare_prescriptions() call, not just hand-built scalars."""
    prev = Prescription("Warfarin", 5, "Standard", "Teva", "Oral", "2026-01-01", "Dr A")
    cur = Prescription("Warfarin", 3, "Standard", "Teva", "Oral", "2026-02-01", "Dr A")
    report = compare_prescriptions("p1", prev, cur)
    # 5 -> 3 mg on an NTI drug = 40% reduction, >= 25% threshold -> HIGH
    assert classify_risk(
        drug_changed=report.drug_changed, formulation_changed=report.formulation_changed,
        dose_changed=report.dose_changed, dose_change_pct=report.dose_change_pct,
        route_changed=report.route_changed, narrow_therapeutic_index=report.narrow_therapeutic_index,
    ) == "HIGH"

    prev2 = Prescription("Vitamin D", 800, "Standard", "Teva", "Oral", "2026-01-01", "Dr A")
    cur2 = Prescription("Vitamin D", 750, "Standard", "Teva", "Oral", "2026-02-01", "Dr A")
    report2 = compare_prescriptions("p2", prev2, cur2)
    # 800 -> 750 mg on a non-NTI drug = 6.25% reduction, < 50% threshold -> LOW
    assert classify_risk(
        drug_changed=report2.drug_changed, formulation_changed=report2.formulation_changed,
        dose_changed=report2.dose_changed, dose_change_pct=report2.dose_change_pct,
        route_changed=report2.route_changed, narrow_therapeutic_index=report2.narrow_therapeutic_index,
    ) == "LOW"


# ---------------------------------------------------------------------
# branch coverage of classify_risk() itself, called directly with
# explicit scalars
# ---------------------------------------------------------------------

def test_classify_risk_none_when_nothing_changed():
    assert classify_risk(
        drug_changed=False, formulation_changed=False, dose_changed=False,
        dose_change_pct=0.0, route_changed=False, narrow_therapeutic_index=False,
    ) == "NONE"


def test_classify_risk_drug_switch_nti_is_high():
    assert classify_risk(
        drug_changed=True, formulation_changed=False, dose_changed=False,
        dose_change_pct=0.0, route_changed=False, narrow_therapeutic_index=True,
    ) == "HIGH"


def test_classify_risk_drug_switch_non_nti_is_medium():
    assert classify_risk(
        drug_changed=True, formulation_changed=False, dose_changed=False,
        dose_change_pct=0.0, route_changed=False, narrow_therapeutic_index=False,
    ) == "MEDIUM"


def test_classify_risk_formulation_change_nti_is_high():
    assert classify_risk(
        drug_changed=False, formulation_changed=True, dose_changed=False,
        dose_change_pct=0.0, route_changed=False, narrow_therapeutic_index=True,
    ) == "HIGH"


def test_classify_risk_formulation_change_non_nti_is_medium():
    assert classify_risk(
        drug_changed=False, formulation_changed=True, dose_changed=False,
        dose_change_pct=0.0, route_changed=False, narrow_therapeutic_index=False,
    ) == "MEDIUM"


def test_classify_risk_dose_change_at_or_above_threshold_is_high():
    # non-NTI threshold is 0.50
    assert classify_risk(
        drug_changed=False, formulation_changed=False, dose_changed=True,
        dose_change_pct=0.50, route_changed=False, narrow_therapeutic_index=False,
    ) == "HIGH"
    # NTI threshold is 0.25
    assert classify_risk(
        drug_changed=False, formulation_changed=False, dose_changed=True,
        dose_change_pct=0.25, route_changed=False, narrow_therapeutic_index=True,
    ) == "HIGH"


def test_classify_risk_dose_change_below_threshold():
    # non-NTI: below 0.50 -> LOW
    assert classify_risk(
        drug_changed=False, formulation_changed=False, dose_changed=True,
        dose_change_pct=0.49, route_changed=False, narrow_therapeutic_index=False,
    ) == "LOW"
    # NTI: below 0.25 -> MEDIUM
    assert classify_risk(
        drug_changed=False, formulation_changed=False, dose_changed=True,
        dose_change_pct=0.24, route_changed=False, narrow_therapeutic_index=True,
    ) == "MEDIUM"


def test_classify_risk_route_only_is_low():
    assert classify_risk(
        drug_changed=False, formulation_changed=False, dose_changed=False,
        dose_change_pct=0.0, route_changed=True, narrow_therapeutic_index=False,
    ) == "LOW"
