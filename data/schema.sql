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

-- The actual dispensing transaction -- separate from acknowledgements
-- because not every dispense follows an alert (most prescriptions never
-- change), but every dispense must still record who did it and for whom.
CREATE TABLE IF NOT EXISTS dispenses (
    dispense_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id          TEXT NOT NULL REFERENCES patients(patient_id),
    ack_id               INTEGER REFERENCES acknowledgements(ack_id), -- most recent acknowledgement for this patient at dispense time, if any
    pharmacist_name      TEXT NOT NULL,
    drug_name            TEXT NOT NULL,
    dose_mg              REAL NOT NULL,
    dispense_timestamp   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prescriptions_patient ON prescriptions(patient_id);
CREATE INDEX IF NOT EXISTS idx_dispenses_patient ON dispenses(patient_id);
