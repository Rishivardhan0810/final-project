# Part of the backend -- the FastAPI app itself. Ties together the
# database, the comparison engine, and the two comparison models.
"""
Patient lookup, prescription comparison, risk scoring (rule + Random
Forest + text model), acknowledgement/dispense logging, and the audit
endpoints. This is what the React frontend talks to.
"""
import os
import sqlite3
from datetime import datetime, timezone

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from comparison_engine import Prescription, compare_prescriptions, natural_language_description, classify_risk

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
    patient_id: str
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
    """Looks a patient up by Patient ID + date of birth -- two-factor on
    purpose, so a single typo can't pull up the wrong person's record."""
    # find the patient by ID AND DOB together; if either is wrong, no match
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM patients WHERE patient_id = ? AND date_of_birth = ?",
        (req.patient_id, req.date_of_birth),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="No matching patient record found.")

    # pull every prescription this patient has, oldest first
    patient = dict(row)
    rx_rows = conn.execute(
        "SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY start_date ASC",
        (patient["patient_id"],),
    ).fetchall()
    conn.close()

    prescriptions = [dict(r) for r in rx_rows]

    # A patient with 0 or 1 prescriptions has no previous-vs-current pair to
    # compare, which is not the same thing as "nothing changed" -- there's
    # simply no automated risk classification possible yet, and the
    # frontend needs to show that plainly rather than an empty screen.
    if len(prescriptions) == 0:
        return {
            "patient": patient,
            "prescriptions": prescriptions,
            "alert": None,
            "status": "no_prescriptions",
            "status_message": "No prescription available for this patient.",
        }

    if len(prescriptions) == 1:
        return {
            "patient": patient,
            "prescriptions": prescriptions,
            "alert": None,
            "status": "first_prescription",
            "status_message": (
                "Automated prescription-change comparison cannot be performed because "
                "no previous prescription is available. Pharmacist review of the "
                "medication, dose, formulation and route is required before dispensing."
            ),
        }

    # compare the two most recent prescriptions
    previous_row, current_row = prescriptions[-2], prescriptions[-1]
    previous = Prescription(**{k: previous_row[k] for k in RX_FIELDS})
    current = Prescription(**{k: current_row[k] for k in RX_FIELDS})

    report = compare_prescriptions(patient["patient_id"], previous, current)
    sentence = natural_language_description(
        report, patient["condition"], patient["allergy"], patient.get("concurrent_medications", "")
    )

    # only worth scoring risk if something actually changed
    alert = None
    if report.change_types:
        # Random Forest wants the change as plain numbers/flags...
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

        # The rule decides what the pharmacist actually sees as risk_final.
        # Random Forest and the text model are computed and returned too,
        # but only as comparison signals -- they can't override or escalate
        # this. Random Forest looks accurate mostly because it's trained on
        # exactly the variables this rule branches on, not because it's
        # learned something the rule doesn't already know, so it isn't
        # trustworthy as the primary decision here.
        rule_risk = classify_risk(
            drug_changed=report.drug_changed,
            formulation_changed=report.formulation_changed,
            dose_changed=report.dose_changed,
            dose_change_pct=report.dose_change_pct,
            route_changed=report.route_changed,
            narrow_therapeutic_index=report.narrow_therapeutic_index,
        )
        final_risk = rule_risk

        alert = {
            "change_types": report.change_types,
            "summary": report.magnitude_summary,
            "natural_language": sentence,
            "previous": report.previous,
            "current": report.current,
            "narrow_therapeutic_index": report.narrow_therapeutic_index,
            "manufacturer_changed": report.manufacturer_changed,
            "risk_rule": rule_risk,
            "risk_random_forest": rf_risk,
            "risk_text_model": text_risk,
            "risk_final": final_risk,
            "gp_name": patient["gp_name"],
        }

    return {
        "patient": patient,
        "prescriptions": prescriptions,
        "alert": alert,
        "status": "normal",
        "status_message": None,
    }


@app.post("/api/acknowledge")
def acknowledge(req: AckRequest):
    """Records that a pharmacist reviewed an alert (or a first prescription) --
    this is what unlocks the Dispense button on the frontend."""
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
    """Records an actual dispensing transaction -- separate from an
    acknowledgement since most prescriptions never trigger an alert."""
    conn = get_conn()
    # link to the most recent acknowledgement for this patient, if any, so
    # a dispense can be traced back to whatever authorised it
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


@app.get("/api/audit/summary")
def audit_summary():
    """Read-only summary for the Audit & Safety dashboard. These are counts
    of what pharmacists actually acknowledged, not every alert the system
    has ever computed -- an alert that was shown but never acknowledged
    doesn't leave a trace anywhere. FIRST_PRESCRIPTION_REVIEW is counted
    separately, never folded into the four risk levels."""
    conn = get_conn()
    total_dispenses = conn.execute("SELECT COUNT(*) FROM dispenses").fetchone()[0]
    total_acknowledgements = conn.execute("SELECT COUNT(*) FROM acknowledgements").fetchone()[0]
    first_prescription_reviews = conn.execute(
        "SELECT COUNT(*) FROM acknowledgements WHERE risk_level = 'FIRST_PRESCRIPTION_REVIEW'"
    ).fetchone()[0]

    acknowledged_risk_counts = {"NONE": 0, "LOW": 0, "MEDIUM": 0, "HIGH": 0}
    rows = conn.execute(
        "SELECT risk_level, COUNT(*) AS n FROM acknowledgements "
        "WHERE risk_level IN ('NONE', 'LOW', 'MEDIUM', 'HIGH') GROUP BY risk_level"
    ).fetchall()
    conn.close()
    for row in rows:
        acknowledged_risk_counts[row["risk_level"]] = row["n"]

    return {
        "total_dispenses": total_dispenses,
        "total_acknowledgements": total_acknowledgements,
        "first_prescription_reviews": first_prescription_reviews,
        "acknowledged_risk_counts": acknowledged_risk_counts,
    }


@app.get("/api/audit/activity")
def audit_activity(limit: int = 50):
    """Read-only recent-events feed for the Audit & Safety dashboard. Runs
    its own query rather than the schema's activity_log view, because that
    view joins in patient names -- this one deliberately uses patient_id
    instead, since it's an aggregate oversight view, not a per-patient one."""
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be a positive integer")
    limit = min(limit, 500)  # sensible cap for this prototype's dataset size

    conn = get_conn()
    rows = conn.execute(
        """
        SELECT 'Acknowledged' AS action, patient_id, pharmacist_name,
               NULL AS drug_name, NULL AS dose_mg, risk_level, ack_timestamp AS happened_at
        FROM acknowledgements
        UNION ALL
        SELECT 'Dispensed' AS action, patient_id, pharmacist_name,
               drug_name, dose_mg, NULL AS risk_level, dispense_timestamp AS happened_at
        FROM dispenses
        ORDER BY happened_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return {"events": [dict(r) for r in rows]}


@app.get("/api/health")
def health():
    """Quick check used to confirm the server is up and both models loaded correctly."""
    return {"status": "ok", "rf_model_loaded": rf_model is not None, "text_model_loaded": text_model is not None}
