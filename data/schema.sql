-- Prescription comparison system schema -- v2.
-- Written as standard SQL (runs identically on SQLite here or PostgreSQL
-- in production -- swap AUTOINCREMENT for SERIAL/IDENTITY if porting).

CREATE TABLE IF NOT EXISTS patients (
    patient_id             TEXT PRIMARY KEY,
    first_name             TEXT NOT NULL,
    last_name              TEXT NOT NULL,
    date_of_birth          TEXT NOT NULL,
    condition               TEXT,
    allergy                TEXT,
    gp_name                TEXT,
    concurrent_medications TEXT,   -- other drugs this patient is also on, for polypharmacy context
    polypharmacy_count     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS prescriptions (
    prescription_id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      TEXT NOT NULL REFERENCES patients(patient_id),
    drug_name       TEXT NOT NULL,
    drug_class      TEXT,          -- therapeutic class, e.g. "Anticoagulant"
    dose_mg         REAL NOT NULL,
    formulation     TEXT NOT NULL, -- e.g. "Immediate-release" / "Extended-release" / "Standard"
    manufacturer    TEXT,          -- brand/generic maker -- NOT used in risk scoring, tracked for transparency
    route           TEXT NOT NULL,
    start_date      TEXT NOT NULL,
    prescriber      TEXT,
    is_current      INTEGER NOT NULL DEFAULT 0  -- 1 = current EPS prescription, 0 = historical
);

CREATE TABLE IF NOT EXISTS acknowledgements (
    ack_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      TEXT NOT NULL REFERENCES patients(patient_id),
    pharmacist_name TEXT NOT NULL,
    ack_timestamp   TEXT NOT NULL,
    risk_level      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prescriptions_patient ON prescriptions(patient_id);
