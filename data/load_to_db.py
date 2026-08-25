# Part of the data pipeline -- builds pharmacy.db, the file the running
# app actually reads from.
"""Loads patients.csv / medications.csv into SQLite using schema.sql."""
import csv
import sqlite3
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "pharmacy.db")


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    with open(os.path.join(HERE, "schema.sql")) as f:
        conn.executescript(f.read())

    # condition/concurrent_medications/polypharmacy_count live in
    # medications.csv, not patients.csv -- grab them from the first
    # matching row per patient
    med_context = {}
    with open(os.path.join(HERE, "medications.csv")) as f:
        for row in csv.DictReader(f):
            pid = row["patient_id"]
            if pid not in med_context:
                med_context[pid] = {
                    "condition": row["condition"],
                    "concurrent_medications": row["concurrent_medications"],
                    "polypharmacy_count": row["polypharmacy_count"],
                }

    with open(os.path.join(HERE, "patients.csv")) as f:
        for row in csv.DictReader(f):
            ctx = med_context.get(row["patient_id"], {})
            conn.execute(
                "INSERT INTO patients (patient_id, first_name, last_name, date_of_birth, "
                "condition, allergy, gp_name, concurrent_medications, polypharmacy_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (row["patient_id"], row["first_name"], row["last_name"], row["date_of_birth"],
                 ctx.get("condition", ""), row["allergy"], row["gp_name"],
                 ctx.get("concurrent_medications", ""), int(ctx.get("polypharmacy_count", 0) or 0)),
            )

    with open(os.path.join(HERE, "medications.csv")) as f:
        for row in csv.DictReader(f):
            pid = row["patient_id"]
            conn.execute(
                "INSERT INTO prescriptions (patient_id, drug_name, drug_class, dose_mg, "
                "formulation, manufacturer, route, start_date, prescriber, is_current) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (pid, row["previous_drug"], row["previous_class"], float(row["previous_dose_mg"]),
                 row["previous_formulation"], row["previous_manufacturer"], row["previous_route"],
                 row["previous_start_date"], row["previous_prescriber"]),
            )
            conn.execute(
                "INSERT INTO prescriptions (patient_id, drug_name, drug_class, dose_mg, "
                "formulation, manufacturer, route, start_date, prescriber, is_current) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (pid, row["current_drug"], row["current_class"], float(row["current_dose_mg"]),
                 row["current_formulation"], row["current_manufacturer"], row["current_route"],
                 row["current_start_date"], row["current_prescriber"]),
            )

    # Optional demo fixture -- one patient, one prescription, for
    # demonstrating the first-prescription review workflow. Never touches
    # medications.csv, so it can't affect the ML dataset. Skipped quietly
    # if generate_demo_patient.py hasn't been run yet.
    demo_path = os.path.join(HERE, "demo_patient.csv")
    if os.path.exists(demo_path):
        with open(demo_path) as f:
            for row in csv.DictReader(f):
                conn.execute(
                    "INSERT INTO patients (patient_id, first_name, last_name, date_of_birth, "
                    "condition, allergy, gp_name, concurrent_medications, polypharmacy_count) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (row["patient_id"], row["first_name"], row["last_name"], row["date_of_birth"],
                     row["condition"], row["allergy"], row["gp_name"],
                     row["concurrent_medications"], int(row["polypharmacy_count"])),
                )
                conn.execute(
                    "INSERT INTO prescriptions (patient_id, drug_name, drug_class, dose_mg, "
                    "formulation, manufacturer, route, start_date, prescriber, is_current) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                    (row["patient_id"], row["drug_name"], row["drug_class"], float(row["dose_mg"]),
                     row["formulation"], row["manufacturer"], row["route"], row["start_date"],
                     row["prescriber"]),
                )
        print(f"Loaded 1 demo patient (first-prescription case) from {demo_path}")
    else:
        print("Demo first-prescription fixture not found; skipping.")

    conn.commit()

    n_patients = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    n_rx = conn.execute("SELECT COUNT(*) FROM prescriptions").fetchone()[0]
    print(f"Loaded {n_patients} patients and {n_rx} prescriptions into {DB_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
