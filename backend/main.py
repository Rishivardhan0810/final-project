# PART OF: Backend -- API Server (the FastAPI app the frontend talks to;
# ties together the database, the comparison engine, and both risk models)
"""
FastAPI service: patient lookup, prescription comparison, risk scoring
(Random Forest + text/ClinicalBERT-substitute), and acknowledgement
logging. Serves the React alert prototype.

v2: patient records now include concurrent medications (polypharmacy
context) and prescriptions carry formulation/manufacturer/therapeutic
class, matching the richer comparison_engine.
"""
import os
import sqlite3
from datetime import datetime, timezone

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from comparison_engine import Prescription, compare_prescriptions, natural_language_description

# File locations, worked out relative to this file so it runs the same
# regardless of which folder you launch it from.
HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "..", "data", "pharmacy.db")
RF_MODEL_PATH = os.path.join(HERE, "risk_models", "rf_model.joblib")
TEXT_MODEL_PATH = os.path.join(HERE, "risk_models", "text_model.joblib")
# The columns a database prescription row needs to become a Prescription object.
RX_FIELDS = ("drug_name", "dose_mg", "formulation", "manufacturer", "route", "start_date", "prescriber")

app = FastAPI(title="Prescription Comparison Alert API")
# Allow the React app (running on a different port) to call this API.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# Load both trained models once, when the server starts, so every request
# reuses them instead of reloading from disk each time. If a model hasn't
# been trained yet, we fall back to None and report "UNKNOWN" risk instead
# of crashing the whole API.
rf_model = joblib.load(RF_MODEL_PATH) if os.path.exists(RF_MODEL_PATH) else None
text_model = joblib.load(TEXT_MODEL_PATH) if os.path.exists(TEXT_MODEL_PATH) else None


def get_conn():
    """Open a fresh SQLite connection where rows behave like dicts (row['column'])."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


class LookupRequest(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: str  # YYYY-MM-DD


class AckRequest(BaseModel):
    patient_id: str
    pharmacist_name: str
    risk_level: str


class DispenseRequest(BaseModel):
    patient_id: str
    pharmacist_name: str
    drug_name: str
    dose_mg: float


@app.post("/api/lookup")
def lookup_patient(req: LookupRequest):
    """Name + DOB lookup -- one record at a time, per UK GDPR constraint noted in the plan."""
    # Step 1: find the patient by name + date of birth. If nobody matches, say so and stop.
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM patients WHERE first_name = ? AND last_name = ? AND date_of_birth = ?",
        (req.first_name, req.last_name, req.date_of_birth),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="No matching patient record found.")

    # Step 2: pull every prescription this patient has ever had, oldest first.
    patient = dict(row)
    rx_rows = conn.execute(
        "SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY start_date ASC",
        (patient["patient_id"],),
    ).fetchall()
    conn.close()

    # If there's no earlier prescription to compare against, there's nothing to alert on.
    prescriptions = [dict(r) for r in rx_rows]
    if len(prescriptions) < 2:
        return {"patient": patient, "prescriptions": prescriptions, "alert": None}

    # Step 3: compare the two most recent prescriptions (previous vs. current EPS one).
    previous_row, current_row = prescriptions[-2], prescriptions[-1]
    previous = Prescription(**{k: previous_row[k] for k in RX_FIELDS})
    current = Prescription(**{k: current_row[k] for k in RX_FIELDS})

    report = compare_prescriptions(patient["patient_id"], previous, current)
    sentence = natural_language_description(
        report, patient["condition"], patient["allergy"], patient.get("concurrent_medications", "")
    )

    # Step 4: only bother scoring risk if something actually changed.
    alert = None
    if report.change_types:
        # The Random Forest wants the change as plain numbers/flags...
        rf_features = pd.DataFrame([{
            "drug_changed": int(report.drug_changed),
            "formulation_changed": int(report.formulation_changed),
            "dose_changed": int(report.dose_changed),
            "dose_change_pct_abs": abs(report.dose_change_pct),
            "route_changed": int(report.route_changed),
            "narrow_therapeutic_index": int(report.narrow_therapeutic_index),
        }])
        # ...while the text model reads the same change as an English sentence.
        rf_risk = rf_model.predict(rf_features)[0] if rf_model is not None else "UNKNOWN"
        text_risk = text_model.predict([sentence])[0] if text_model is not None else "UNKNOWN"

        # Final displayed risk: the higher of the two model outputs (fail-safe toward caution)
        order = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
        final_risk = max([rf_risk, text_risk], key=lambda r: order.get(r, 0))

        alert = {
            "change_types": report.change_types,
            "summary": report.magnitude_summary,
            "natural_language": sentence,
            "previous": report.previous,
            "current": report.current,
            "narrow_therapeutic_index": report.narrow_therapeutic_index,
            "manufacturer_changed": report.manufacturer_changed,
            "risk_random_forest": rf_risk,
            "risk_text_model": text_risk,
            "risk_final": final_risk,
            "gp_name": patient["gp_name"],
        }

    return {"patient": patient, "prescriptions": prescriptions, "alert": alert}


@app.post("/api/acknowledge")
def acknowledge(req: AckRequest):
    """Called when the pharmacist confirms they've seen the alert -- this is what
    unlocks the Dispense button on the frontend. Every acknowledgement is logged
    with who did it and when, so there's an audit trail."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO acknowledgements (patient_id, pharmacist_name, ack_timestamp, risk_level) "
        "VALUES (?, ?, ?, ?)",
        (req.patient_id, req.pharmacist_name, datetime.now(timezone.utc).isoformat(), req.risk_level),
    )
    conn.commit()
    conn.close()
    return {"status": "acknowledged"}


@app.post("/api/dispense")
def dispense(req: DispenseRequest):
    """Called when the pharmacist actually hands over the medication -- the real
    transaction record, distinct from (but usually preceded by) an
    acknowledgement, since most prescriptions never trigger an alert at all.
    Every dispense is logged with who did it, what was dispensed, for which
    patient, and when."""
    conn = get_conn()
    # Link to the most recent acknowledgement for this patient, if any, so a
    # dispense can be traced back to the alert that authorized it.
    ack_row = conn.execute(
        "SELECT ack_id FROM acknowledgements WHERE patient_id = ? ORDER BY ack_id DESC LIMIT 1",
        (req.patient_id,),
    ).fetchone()
    conn.execute(
        "INSERT INTO dispenses (patient_id, ack_id, pharmacist_name, drug_name, dose_mg, dispense_timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (req.patient_id, ack_row["ack_id"] if ack_row else None, req.pharmacist_name,
         req.drug_name, req.dose_mg, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    return {"status": "dispensed"}


@app.get("/api/health")
def health():
    """Quick check used to confirm the server is up and both models loaded correctly."""
    return {"status": "ok", "rf_model_loaded": rf_model is not None, "text_model_loaded": text_model is not None}
