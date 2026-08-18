# Dispense Logging & the Pharmacy Database

A record of every change made to `pharmacy.db` this session, why each one was necessary, and why it matters for the project. Written to be used directly in a report.

## Why this work happened

The prototype had an `acknowledgements` table logging when a pharmacist confirmed they'd seen a risk alert — but the **"Dispense" button did nothing**. Clicking it just unlocked visually; no record of the actual dispensing event (who, what drug, for which patient, when) was ever created. For a system whose entire purpose is a safety audit trail, that's the one transaction that most needed to be captured, and it wasn't.

## What changed, in order

**1. Dispensing wasn't recorded at all**
Fix: added a new `dispenses` table and a real `POST /api/dispense` endpoint; wired the frontend's Dispense button to call it instead of being a no-op.

**2. Pharmacist name was never captured for "regular" patients**
The name field only existed inside the alert panel — if a patient had *no* risk alert, no name field appeared anywhere, so a dispense could happen with nobody identified. Fix: added a name field directly to the dispense panel for that case, and made Dispense require a name either way.

**3. The raw tables were hard to read (multiple IDs, joins needed)**
To understand one transaction you had to mentally join `patients` + `acknowledgements`/`dispenses` using `patient_id`/`ack_id` codes. Fix: added a read-only SQL `VIEW` called `activity_log` that pre-joins everything into one flat table with plain-English columns.

**4. An unnecessary technical table cluttered the database browser**
SQLite auto-creates a `sqlite_sequence` bookkeeping table whenever `AUTOINCREMENT` is used, purely to guarantee IDs are never reused after a delete — a guarantee this project doesn't need. Fix: removed `AUTOINCREMENT` from all three tables that had it (plain `INTEGER PRIMARY KEY` still auto-increments via SQLite's own rowid), which stops `sqlite_sequence` from being created at all.

**5. No good way to actually look at any of this**
VS Code's plain text editor can't open a binary `.db` file at all. A MongoDB-style dashboard was considered but rejected (see below). Fix: installed **DB Browser for SQLite**, a free desktop application built specifically for browsing/filtering SQLite files.

## Schema detail: the new `dispenses` table

| Column | Type | What it captures |
|---|---|---|
| `dispense_id` | INTEGER (PK) | Unique row number for this transaction |
| `patient_id` | TEXT (FK) | Which patient this was dispensed to, linking to `patients` |
| `ack_id` | INTEGER (FK, nullable) | The specific alert-acknowledgement that authorized this dispense, if the patient had one. `NULL` when there was no alert to acknowledge. |
| `pharmacist_name` | TEXT | Typed into the "Pharmacist name" field before clicking Dispense — the core requirement this whole feature exists to satisfy |
| `drug_name`, `dose_mg` | TEXT, REAL | What was actually dispensed, read from the patient's current prescription at the moment of the click |
| `dispense_timestamp` | TEXT | UTC timestamp, ISO 8601 format |

### The `activity_log` view

A view is a saved query, not a stored copy of data — it always reflects the current contents of `acknowledgements` and `dispenses` with zero duplication or risk of going out of sync. It unions the two tables together, joins in the patient's name, and labels each row by what happened:

```sql
CREATE VIEW activity_log AS
SELECT 'Acknowledged alert' AS action,
       p.first_name || ' ' || p.last_name AS patient_name,
       a.pharmacist_name, NULL AS drug_name, NULL AS dose_mg,
       a.risk_level, a.ack_timestamp AS happened_at
FROM acknowledgements a JOIN patients p ON p.patient_id = a.patient_id
UNION ALL
SELECT 'Dispensed', p.first_name || ' ' || p.last_name,
       d.pharmacist_name, d.drug_name, d.dose_mg,
       NULL, d.dispense_timestamp
FROM dispenses d JOIN patients p ON p.patient_id = d.patient_id
ORDER BY happened_at DESC;
```

## Why the database wasn't switched to MongoDB

Partway through, switching to MongoDB (for a cleaner-looking dashboard, like MongoDB Compass) was raised as an option. The recommendation was to keep SQLite, for reasons worth stating explicitly in a report as a deliberate architectural decision:

> **The data is genuinely relational.** A dispense *belongs to* a patient; an acknowledgement *belongs to* a patient and may be referenced by a dispense. MongoDB (a document database) doesn't model one-to-many ownership like this any better than a relational database does — it just moves the joining work into application code instead of the database engine.

Migrating would have meant rewriting every query in `main.py` and `load_to_db.py`, redesigning the schema as documents, and running a separate database server — substantial risk to an already-working, tested system, for a change that's purely cosmetic (what the browsing *tool* looks like, not what the database *is*). Installing DB Browser for SQLite delivered the actual goal — an easy, visual way to inspect the data — without touching the architecture at all.

## Tooling journey: why DB Browser for SQLite specifically

1. **VS Code's built-in editor** — Tried first, since it was already open. Failed immediately: `.db` is a binary file format, not text, so VS Code refuses to render it.
2. **"SQLite Viewer" VS Code extension** — Worked, and is what the project's own README already recommended. But the sidebar listing every table (including the technical `sqlite_sequence`) still read as cluttered, and it doesn't auto-refresh when the backend writes new data.
3. **MongoDB Compass (via a full database migration)** — Considered and rejected — see above. Would have solved the "nice dashboard" want at the cost of the entire backend's data layer.
4. **DB Browser for SQLite (installed)** — Free, open-source, standalone desktop app built specifically for this. Gives a proper spreadsheet-style grid with per-column filtering, without changing anything about the running system. This is what's in use now.

## Why this matters to the project

Three points worth making explicitly when writing this up:

**1. It closes a genuine safety/audit gap.** A community pharmacy system that flags risky prescription changes but doesn't record who actually dispensed the medication afterward has an incomplete audit trail — exactly the kind of gap a real clinical governance review would flag. The `dispenses` table, with its link back to the specific acknowledgement that authorized it (`ack_id`), makes it possible to answer "who dispensed this, and had they seen the alert first?" for every transaction.

**2. It demonstrates a real database design pattern, not just a table.** Rather than flattening everything into one wide table, the acknowledgement and dispense events stayed as separate, normalised tables (because not every dispense follows an acknowledgement), and a **view** was used to provide a simple, denormalised read-only presentation on top — the standard way to reconcile "correct normalized storage" with "easy human-readable access" without duplicating data. That's a deliberate design choice worth citing.

**3. It shows iterative refinement driven by real usage.** Each change here was triggered by an actual, observed problem (a no-op button; a missing name field; a confusing browser view; an unnecessary system table) rather than being speculative — and each fix was verified against the real database before being called done. That's a legitimate software engineering narrative for a methodology or evaluation section: identify the gap, make the smallest safe change that closes it, verify against real data.

## Evidence: current state, verified directly against the database

| Patient | Action | Drug | Pharmacist | Had an alert? |
|---|---|---|---|---|
| Charles Roberts | Dispensed | Furosemide 80mg | madhav | Yes |
| Robert White | Dispensed | Prednisolone 20mg | rishi | No |
| Charles Roberts | Dispensed | Furosemide 80mg | rishi | Yes |
| William Taylor | Dispensed | Digoxin 0.125mg | rishi | No |

Confirms both paths work correctly: patients with a flagged risk change (linked to their acknowledgement) and "regular" patients with no alert (dispensed directly, no acknowledgement needed) are both captured.

## Committed & pushed to GitHub

| Commit | Files | Message |
|---|---|---|
| `b83e27d` | `schema.sql`, `main.py`, `RecordScreen.jsx`, `App.css` | Add dispense transaction logging (pharmacist name, drug, patient, timestamp) |
| `9fba07b` | `schema.sql` | Add activity_log view and drop AUTOINCREMENT for a simpler, readable DB structure |

Both are permanent: `data/schema.sql` is the single source of truth, so every future database rebuild (via `load_to_db.py`) recreates the `dispenses` table and `activity_log` view automatically — this isn't a one-off manual patch to the live file.

---
*Reflects work done and verified in this session against the live `pharmacy.db`. Repository: github.com/Rishivardhan0810/final-project.*
