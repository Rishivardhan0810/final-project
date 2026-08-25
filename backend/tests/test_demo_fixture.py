# Automated tests -- covers data/generate_demo_patient.py and the
# demo-fixture-loading block in data/load_to_db.py.
"""
Calls the real generate_demo_patient.py and load_to_db.py (via a
monkeypatched temp directory), not a reimplementation, so these check the
actual pipeline in both the "fixture present" and "fixture absent" cases.
"""
import os
import sys
import csv
import sqlite3

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "..", "data")
sys.path.insert(0, DATA_DIR)

import generate_demo_patient  # noqa: E402
import load_to_db  # noqa: E402


def _write_minimal_main_dataset(tmp_dir):
    """One ordinary patient with a normal previous/current pair -- just
    enough for load_to_db.main() to run against a throwaway directory."""
    patients_path = os.path.join(tmp_dir, "patients.csv")
    with open(patients_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["patient_id", "first_name", "last_name",
                                           "date_of_birth", "allergy", "gp_name"])
        w.writeheader()
        w.writerow({"patient_id": "real0001", "first_name": "Jane", "last_name": "Doe",
                    "date_of_birth": "1970-01-01", "allergy": "None recorded", "gp_name": "Dr Test"})

    med_fields = ["patient_id", "condition", "previous_drug", "previous_class", "previous_dose_mg",
                  "previous_formulation", "previous_manufacturer", "previous_route",
                  "previous_start_date", "previous_prescriber", "current_drug", "current_class",
                  "current_dose_mg", "current_formulation", "current_manufacturer", "current_route",
                  "current_start_date", "current_prescriber", "concurrent_medications",
                  "polypharmacy_count"]
    with open(os.path.join(tmp_dir, "medications.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=med_fields)
        w.writeheader()
        w.writerow({
            "patient_id": "real0001", "condition": "Hypertension",
            "previous_drug": "Ramipril", "previous_class": "ACE inhibitor", "previous_dose_mg": 5,
            "previous_formulation": "Standard", "previous_manufacturer": "Teva", "previous_route": "Oral",
            "previous_start_date": "2026-01-01", "previous_prescriber": "Dr Test",
            "current_drug": "Ramipril", "current_class": "ACE inhibitor", "current_dose_mg": 10,
            "current_formulation": "Standard", "current_manufacturer": "Teva", "current_route": "Oral",
            "current_start_date": "2026-02-01", "current_prescriber": "Dr Test",
            "concurrent_medications": "", "polypharmacy_count": 0,
        })


def test_generate_demo_patient_writes_exactly_one_expected_row(tmp_path):
    generate_demo_patient.main(out_dir=str(tmp_path))
    csv_path = tmp_path / "demo_patient.csv"
    assert csv_path.exists()

    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    row = rows[0]
    assert row["patient_id"] == "demo0001"
    assert row["first_name"] == "Arjun"
    assert row["last_name"] == "Mehta"
    assert row["date_of_birth"] == "1980-01-01"
    assert row["drug_name"] == "Amlodipine"
    assert row["dose_mg"] == "5"


def test_load_to_db_skips_gracefully_when_fixture_absent(tmp_path, monkeypatch, capsys):
    """The normal load logic should be unaffected, with no exception
    raised, when demo_patient.csv doesn't exist."""
    _write_minimal_main_dataset(str(tmp_path))
    monkeypatch.setattr(load_to_db, "HERE", str(tmp_path))
    monkeypatch.setattr(load_to_db, "DB_PATH", str(tmp_path / "pharmacy.db"))

    import shutil
    shutil.copy(os.path.join(DATA_DIR, "schema.sql"), os.path.join(str(tmp_path), "schema.sql"))

    load_to_db.main()
    captured = capsys.readouterr()
    assert "Demo first-prescription fixture not found; skipping." in captured.out

    conn = sqlite3.connect(str(tmp_path / "pharmacy.db"))
    n_patients = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    conn.close()
    assert n_patients == 1  # only the ordinary patient -- no demo patient inserted


def test_load_to_db_loads_exactly_one_demo_patient_and_one_prescription_when_present(tmp_path, monkeypatch, capsys):
    _write_minimal_main_dataset(str(tmp_path))
    generate_demo_patient.main(out_dir=str(tmp_path))
    monkeypatch.setattr(load_to_db, "HERE", str(tmp_path))
    monkeypatch.setattr(load_to_db, "DB_PATH", str(tmp_path / "pharmacy.db"))

    import shutil
    shutil.copy(os.path.join(DATA_DIR, "schema.sql"), os.path.join(str(tmp_path), "schema.sql"))

    load_to_db.main()
    captured = capsys.readouterr()
    assert "Loaded 1 demo patient (first-prescription case)" in captured.out

    conn = sqlite3.connect(str(tmp_path / "pharmacy.db"))
    conn.row_factory = sqlite3.Row
    n_patients = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    assert n_patients == 2  # the ordinary patient + the demo patient

    demo_rx = conn.execute(
        "SELECT * FROM prescriptions WHERE patient_id = 'demo0001'"
    ).fetchall()
    conn.close()
    assert len(demo_rx) == 1  # exactly one prescription, not a pair
    assert demo_rx[0]["is_current"] == 1
    assert demo_rx[0]["drug_name"] == "Amlodipine"


def test_demo_fixture_never_touches_medications_csv_or_ml_files(tmp_path):
    """Generating the demo fixture should only ever write demo_patient.csv --
    generate_demo_patient.py has no code path that opens medications.csv/
    train.csv/test.csv at all."""
    med_path = tmp_path / "medications.csv"
    med_path.write_text("untouched-sentinel-content")

    generate_demo_patient.main(out_dir=str(tmp_path))

    assert med_path.read_text() == "untouched-sentinel-content"
    assert (tmp_path / "demo_patient.csv").exists()
