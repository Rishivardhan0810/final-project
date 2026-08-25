# Part of the data pipeline -- one fixed demo patient with exactly one
# prescription, for demonstrating the first-prescription review workflow.
"""
Writes a single hardcoded patient to data/demo_patient.csv. No randomness
needed for one fixed record, which also means it can't interact with
generate_synthetic_data.py's PRNG sequence at all.

This patient can never end up in medications.csv/train.csv/test.csv --
those files are shaped as previous-vs-current pairs, and this patient has
no previous prescription to pair with. See load_to_db.py for how it gets
loaded into the database.
"""
import csv

DEMO_PATIENT = {
    "patient_id": "demo0001",
    "first_name": "Arjun",
    "last_name": "Mehta",
    "date_of_birth": "1980-01-01",
    "condition": "Hypertension",
    "allergy": "None recorded",
    "gp_name": "Dr A. Okafor",
    "concurrent_medications": "",
    "polypharmacy_count": 0,
    "drug_name": "Amlodipine",
    "drug_class": "Calcium channel blocker",
    "dose_mg": 5,
    "formulation": "Standard",
    "manufacturer": "Teva",
    "route": "Oral",
    "start_date": "2026-01-01",
    "prescriber": "Dr A. Okafor",
}


def main(out_dir="."):
    path = f"{out_dir}/demo_patient.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(DEMO_PATIENT.keys()))
        w.writeheader()
        w.writerow(DEMO_PATIENT)
    print(f"Wrote 1 demo patient (exactly one prescription, no previous) -> {path}")


if __name__ == "__main__":
    main()
