# Project Structure Guide

Every file and folder in this repository, what part of the project it belongs to, and what it's actually used for. Files marked **(generated)** are never hand-written — a script produces them, and they can be safely deleted and rebuilt at any time.

**This file describes the CURRENT implementation.** For a critical review of how well the current implementation satisfies supervisor feedback, see `FINAL_AUDIT.md`. For the algorithm-suitability reasoning behind the risk architecture described below, see `ALGORITHM_AUDIT.md` / `_2` / `_3`.

## How the three main parts fit together

- **`data/`** — runs *offline*, once. Builds the synthetic patient dataset, the optional demo fixture, and the database (`pharmacy.db`) the app reads from.
- **`backend/`** — runs *online*, as a live server. Serves the frontend, compares prescriptions, computes the primary rule-based risk decision plus two secondary comparison models, and exposes audit endpoints.
- **`frontend/`** — the web app a pharmacist actually opens in a browser. Has two screens (Prescription Review and Audit & Safety) and talks to the backend over HTTP.

---

## `backend/` — the API server and risk-scoring logic

| File | Used for |
|---|---|
| `main.py` | The FastAPI server itself. Defines every URL the frontend can call: `/api/lookup` (Patient ID + date-of-birth two-factor lookup, prescription comparison, primary rule-based risk scoring plus RF/text comparison readings), `/api/acknowledge` (log that a pharmacist reviewed an alert or a first prescription), `/api/dispense` (log an actual dispensing transaction, linked to the acknowledgement that authorised it), `/api/audit/summary` and `/api/audit/activity` (read-only aggregate data for the Audit & Safety dashboard, `patient_id` only — never patient name), `/api/health` (are the models loaded). This is the file you'd run to start the backend. |
| `comparison_engine.py` | The core logic. `compare_prescriptions()` takes a patient's previous and current prescription and works out what changed (drug, formulation, dose, route) and whether a narrow-therapeutic-index (NTI) drug is involved. `classify_risk()` is the **single shared deterministic risk rule** — the one place risk thresholds are defined, imported (not copied) by `main.py`, `data/generate_synthetic_data.py`, and `data/real_synthea/adapt_real_synthea.py`, so live scoring, synthetic label generation, and real-data validation labels can never silently diverge. |
| `requirements.txt` | The list of Python packages this backend needs (fastapi, scikit-learn, pandas, etc.) — install with `pip install -r backend/requirements.txt`. |

### `backend/risk_models/` — training and evaluating the two secondary ML models

| File | Used for |
|---|---|
| `train_random_forest.py` | Trains the Random Forest classifier — takes the same structured yes/no features `classify_risk()` branches on (drug changed? dose changed by how much? is it an NTI drug?) and predicts NONE/LOW/MEDIUM/HIGH. Saves the trained model to `rf_model.joblib`. Random Forest is a **secondary comparison model** — it does not decide the live alert. |
| `train_text_classifier.py` | Trains the second secondary model — a TF-IDF + Logistic Regression classifier (the ClinicalBERT substitute) that reads a plain-English sentence describing the change instead of structured features. Saves to `text_model.joblib`. |
| `evaluate.py` | Runs both training scripts back to back, then prints a side-by-side comparison table (accuracy, precision, recall, F1) on the same held-out test set. Produces `evaluation_summary.json`. |
| `evaluate_real_synthea.py` | A second, separate evaluation — scores the *already-trained* models against genuine real-world Synthea data (not the synthetic generator's output), to check the models generalise beyond the data they were trained on. Never retrains anything. |
| `baseline_comparison.py` | Experimental algorithm-comparison script for the dissertation's algorithm-justification chapter: compares the deterministic rule, Logistic Regression, a single Decision Tree, and the existing (loaded, **never retrained**) Random Forest and text models, with 5-fold stratified cross-validation. Writes `baseline_comparison_results.json`/`.csv`. Entirely separate from the live application — never imports or modifies `main.py` or `comparison_engine.py`, never touches `evaluation_summary.json`. |
| `report_utils.py` | Small shared helper functions for printing metrics consistently — used internally by the scripts above, never run on its own. |
| `rf_model.joblib` **(generated)** | The actual trained Random Forest, saved to disk so `main.py` doesn't have to retrain it on every server restart. |
| `text_model.joblib` **(generated)** | The actual trained text classifier, same idea. |
| `evaluation_summary.json` **(generated)** | The metrics from the last time `evaluate.py` was run. |
| `baseline_comparison_results.json`, `.csv` **(generated)** | The metrics from the last time `baseline_comparison.py` was run. |

### `backend/tests/` — 56 tests total, run with `pytest backend/tests -v`

| File | Covers |
|---|---|
| `test_pipeline.py` | Comparison-engine correctness, dataset integrity, NTI (narrow-therapeutic-index) consistency between the synthetic generator and the live app |
| `test_first_prescription.py` | The first-prescription review workflow (exactly one prescription on record — no automated risk classification, mandatory pharmacist review) |
| `test_demo_fixture.py` | The demo-patient fixture generation and its graceful-skip loading behaviour when absent |
| `test_rule_primary_risk.py` | That `classify_risk()` — not Random Forest or the text model — determines `risk_final`, including active proof (a fake model that always predicts a fixed wrong value) that neither ML model can override the rule, plus full branch-coverage of `classify_risk()` itself |
| `test_lookup_two_factor.py` | Patient ID + date-of-birth two-factor lookup: correct/correct succeeds, either field wrong fails, first-prescription workflow still works |
| `test_audit_dashboard.py` | The Audit & Safety dashboard's two endpoints, using a deliberately-constructed known dataset (exact counts, ordering, `patient_id`-not-name, `limit` handling) |

---

## `data/` — building the dataset and the database

| File | Used for |
|---|---|
| `generate_synthetic_data.py` | **Step 1.** Generates 600 synthetic patients, each paired with one previous/current prescription-change record (17 drugs, therapeutic classes, NTI flags, formulations, manufacturers). Uses the shared `classify_risk()` from `backend/comparison_engine.py` to generate risk labels — not a separate copy of that logic. Writes `patients.csv` and `medications.csv`. This is the substitute for real Synthea output the project plan originally called for. |
| `generate_demo_patient.py` | **Optional step.** Writes exactly one fixed, non-randomised demo patient (`demo0001`, "Arjun Mehta") with exactly one prescription and no previous prescription to compare against, to `demo_patient.csv` — used only to demonstrate the first-prescription review workflow in the running UI/database. Cannot enter the paired ML dataset by construction (that dataset is shaped as previous-vs-current pairs; this patient has no previous prescription). |
| `eda.py` | **Step 2.** Exploratory Data Analysis — checks the generated data is balanced, checks which features actually carry signal, before any model is trained on it. Writes results into `eda_outputs/`. |
| `preprocess.py` | **Step 3.** Cleans the data, selects features, and splits everything into a fixed `train.csv`/`test.csv` so every model is trained and tested on the exact same patients. |
| `load_to_db.py` | **Step 4.** Reads `patients.csv` and `medications.csv` into `pharmacy.db`, then loads `demo_patient.csv` too if it exists (skipped gracefully, no error, if it doesn't). |
| `schema.sql` | The database blueprint — defines every table (`patients`, `prescriptions`, `acknowledgements`, `dispenses`) and the `activity_log` view (patient-name-joined, used for per-patient browsing — deliberately **not** reused by the Audit & Safety dashboard's endpoints, which use `patient_id` instead). Written as standard SQL, portable to PostgreSQL if needed later. `load_to_db.py` runs this file to build the database structure before loading any data. |
| `medications.csv`, `patients.csv` **(generated)** | The raw output of `generate_synthetic_data.py` — 600 patients and 600 prescription-change pairs, before splitting. |
| `demo_patient.csv` **(generated, optional)** | The single demo patient's record, output of `generate_demo_patient.py`. |
| `train.csv`, `test.csv` **(generated)** | The fixed split of the main synthetic dataset (450/150 rows), produced by `preprocess.py`, used to train and evaluate both secondary ML models. The demo patient is never in these files. |
| `pharmacy.db` **(generated)** | **The actual live database.** The one file the running backend reads from and writes to (patient lookups, acknowledgements, dispenses all happen here). Contains 601 patients if the demo fixture was generated and loaded (600 main + 1 demo), or 600 if not. |
| `eda_outputs/` **(generated folder)** | Diagnostic output from `eda.py`: `class_balance.png`, `correlation_heatmap.png`, `feature_distributions.png`, and `eda_report.txt`. |

### `data/real_synthea/` — external validation using genuine data

| File | Used for |
|---|---|
| `medications_raw.csv` | Genuine Synthea-generated medical records (not made up by this project) — kept as-is, real input data, not something to regenerate. |
| `adapt_real_synthea.py` | Converts that raw real-world data into the same shape as the synthetic prescription-change pairs, using the same shared `is_narrow_therapeutic_index()`/`classify_risk()` functions from `backend/comparison_engine.py` — not a separate reimplementation — so real-data labels can never silently diverge from live/synthetic labels. |
| `real_test.csv` **(generated)** | The output of the script above — 30 real prescription-change pairs, used only by `evaluate_real_synthea.py`, never for training. |

---

## `frontend/` — the web app a pharmacist actually uses

| File | Used for |
|---|---|
| `src/main.jsx` | The very first file that runs — mounts the React app onto the web page. You'll basically never need to touch this. |
| `src/App.jsx` | The app's outer shell. Switches between the two dashboards (Prescription Review / Audit & Safety) via top navigation, holds the in-memory (never persisted) audit-login authentication state, and is the only place that calls `/api/lookup`. |
| `src/LookupScreen.jsx` | The first Prescription Review screen — a form for **Patient ID and date of birth** (not name — two-factor identification, see `README.md`). |
| `src/RecordScreen.jsx` | The patient record screen — name/condition/allergy banner, current and historical prescription tables, the first-prescription review panel, the no-prescription panel, and the Dispense button (calls `/api/dispense`). |
| `src/AlertPanel.jsx` | The alert card shown when a prescription change was flagged — shows the primary rule-based risk level, what changed, the Random Forest and text-model comparison readings (labelled non-authoritative), and the Acknowledge button (calls `/api/acknowledge`). |
| `src/AuditLogin.jsx` | The prototype login gate shown before the Audit & Safety dashboard — Username/Password form checked against `auditDemoCredentials.js`, with an explicit on-screen note that this is prototype-only access control. |
| `src/auditDemoCredentials.js` | The one place the demo audit login credentials are defined (`{ username: "audit", password: "demo123" }`) — a plain, visible constant, deliberately not a real secret. |
| `src/AuditDashboard.jsx` | The read-only Audit & Safety dashboard — summary stats, acknowledged risk-level counts, recent activity feed (`patient_id` only), and a Log out button. Calls `GET /api/audit/summary` and `GET /api/audit/activity`. |
| `src/App.css` | Every visual style for the whole app lives in this one file — colours, layout, risk badges, dashboard styling, all of it. |
| `public/favicon.svg`, `public/icons.svg` | Small image assets used by the page itself. |
| `src/assets/hero.png`, `src/assets/vite.svg` | Leftover default images from the Vite project template — not currently used anywhere in the app. |
| `package.json` | Dependencies (React, Vite) and shortcut commands (`npm run dev`, `npm run build`, `npm run lint`). No frontend test framework is installed. |
| `package-lock.json` | The exact, pinned versions of every dependency. |
| `vite.config.js` | Configuration for Vite, the build tool. |
| `index.html` | The single, mostly-empty HTML page that `main.jsx` mounts the whole React app into. |
| `.oxlintrc.json` | Configuration for Oxlint, the code-style checker (`npm run lint`). |
| `node_modules/` **(generated, not in git)** | Every downloaded dependency. Deletable any time — rebuilt with `npm install`. |

---

## `clinicalbert-addon/` — optional, not used by the running app

Kept intentionally as a documented future-upgrade path (a real ClinicalBERT fine-tune, instead of the TF-IDF substitute the running app currently uses, because this environment can't reach huggingface.co). Nothing in `backend/` or `data/` imports anything from this folder — it has no effect on the live application, tests, or evaluation results described in `README.md`.

| File | Used for |
|---|---|
| `data/export_for_clinicalbert.py` | Would export the same training sentences the TF-IDF model uses, into a shape a real ClinicalBERT fine-tuning job could consume. |
| `data/clinicalbert_export/*.csv` | The exported output of that script — pre-generated train/test/real-validation CSVs. |
| `backend/risk_models/clinicalbert_finetune.ipynb` | A Jupyter notebook sketching out what the actual fine-tuning job would look like, if run somewhere with internet access to Hugging Face. |

---

## Root-level files

| File | Used for |
|---|---|
| `README.md` | The main project overview — setup instructions, core workflow, risk architecture, current algorithm-comparison results, data provenance, dashboards, database, testing, and technology stack. |
| `PROJECT_STRUCTURE.md` | This file. |
| `DATABASE_REPORT.md` | A writeup of the dispense-logging feature and database design, from an earlier session — still describes the current `acknowledgements`/`dispenses` schema accurately; does not cover the audit-dashboard endpoints or the login gate added afterward. |
| `ALGORITHM_AUDIT.md`, `ALGORITHM_AUDIT_2.md`, `ALGORITHM_AUDIT_3.md` | Three sequential, read-only technical audits of the risk-classification algorithm — culminating in the label-circularity finding and the recommendation (now implemented) to make the deterministic rule the live primary decision, with Random Forest and the text model as secondary comparison signals. |
| `FINAL_AUDIT.md` | A final, read-only technical and supervisor-feedback audit checking the current implementation against every point of supervisor feedback, with exact code evidence, an algorithm/technology justification, an evaluation-gap analysis (measured vs. demonstrated vs. inferred vs. not proven), a security/PSEL review, and viva-preparation material. |
| `rx-alert-system.code-workspace` | A VS Code workspace file — opening this instead of the plain folder gives you the recommended extensions and pre-configured run tasks. |
| `.gitignore` | Tells git which files to never track — all the **(generated)** files/folders listed above, plus `node_modules/`, `__pycache__/`, `.pytest_cache/`, and similar disposable output. |
