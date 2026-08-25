# Automated Prescription Comparison System — working prototype

An MSc prototype implementing the project's objectives O2–O5: synthetic
patient/prescription data, a deterministic prescription-change comparison
engine, two secondary ML comparison models (Random Forest and a TF-IDF +
Logistic Regression text model), and a two-screen React alert/audit UI.

**This document describes the system as it is currently implemented.** For
a critical, evidence-based review of how well this implementation satisfies
supervisor feedback (including exact code references), see `FINAL_AUDIT.md`.
For the algorithm-suitability reasoning behind the current risk architecture,
see `ALGORITHM_AUDIT.md` / `_2` / `_3`.

## What's here vs. what the plan specifies

This sandbox environment has a restricted network allowlist (npm/pip
registries and GitHub only — no Maven Central, no huggingface.co). Two
components were substituted so the whole pipeline actually runs
end-to-end; everything else matches the plan as written.

| Component | Plan | Built here | Why |
|---|---|---|---|
| Synthetic data | Synthea v3 (Java) | Python generator, same CSV shape | Synthea needs Maven Central, unreachable here |
| Database | PostgreSQL | SQLite | Same schema (`data/schema.sql`, standard SQL — portable, see the file's own header comment); no server needed for a prototype |
| Comparison engine | Spring Boot (Java) | FastAPI (Python) | Same REST contract; Spring Boot needs Maven Central |
| Random Forest | scikit-learn | scikit-learn | Matches plan exactly |
| ClinicalBERT | Hugging Face pretrained model | TF-IDF + Logistic Regression on the same natural-language sentences | huggingface.co isn't reachable in this environment, so no pretrained clinical embeddings. This is a deliberate, interpretable text baseline, not just a stand-in — see "Algorithm comparison results" below for why its behaviour is itself an informative finding. A real ClinicalBERT fine-tune remains a documented future-upgrade path — see `clinicalbert-addon/`. |
| Alert UI | React + Vite | React 19 + Vite | Matches plan exactly |

If you have normal internet access, `data/generate_synthetic_data.py`
can be replaced by real Synthea output (same column names), and
`backend/risk_models/train_text_classifier.py` can be replaced by a real
ClinicalBERT fine-tune — no other files need to change, since both talk
to the rest of the system through the same CSV/JSON contracts.

## Core workflow

1. **Patient lookup** requires both **Patient ID and date of birth** (two-factor
   identification — a single identifier makes it easier for a typo to pull up
   the wrong patient). Patient name and other details are only displayed
   after a successful match on both fields.
2. Depending on how many prescriptions the matched patient has on record:
   - **2 or more prescriptions**: the two most recent are compared —
     `previous prescription → current prescription → comparison engine →
     structured change features (drug/formulation/dose/route/narrow-therapeutic-index)
     → deterministic rule-based primary risk → Random Forest comparison →
     TF-IDF + Logistic Regression text comparison → pharmacist acknowledgement
     → dispense → audit log`.
   - **Exactly 1 prescription**: there is nothing to compare against, so no
     automated risk classification is attempted (no NONE/LOW/MEDIUM/HIGH is
     ever assigned). The pharmacist must complete an explicit first-prescription
     review before dispensing unlocks.
   - **0 prescriptions**: nothing can be dispensed; the UI states this plainly
     instead of crashing or showing an empty prescription table.

## Risk architecture

- **One shared function, `classify_risk()`** (`backend/comparison_engine.py`),
  is the single deterministic reference risk framework in this project. It is
  imported — not reimplemented — by all three places that need a risk label:
  - `backend/main.py` — the live, primary risk decision shown to the pharmacist.
  - `data/generate_synthetic_data.py` — training/test label generation.
  - `data/real_synthea/adapt_real_synthea.py` — external-validation labels on
    genuine Synthea data.
- **`risk_final` is rule-based.** Random Forest and the text model are computed
  on every request and returned alongside the rule's result (`risk_random_forest`,
  `risk_text_model` in the API response), but **neither can override or escalate
  the primary alert** — they are secondary, displayed comparison signals only.
- **Why the rule is primary, not an ML model**: the target function (what counts
  as a risk-relevant prescription change) is fully known and already implemented
  as code, so there is nothing to learn that isn't already specified exactly.
  Using an ML approximation of a fully-known function as the live safety-critical
  decision would add approximation risk with no offsetting benefit — see
  `ALGORITHM_AUDIT_3.md` for the full reasoning and the exact trace showing why
  Random Forest's near-perfect accuracy is expected, not evidence of "learning."
- **The deterministic rule is a transparent reference framework, not a clinically
  validated instrument.** No result in this project — 100%, or otherwise — should
  be read as clinical validation. See below.

## Algorithm comparison results

These are the current, measured results from `backend/risk_models/evaluation_summary.json`
and `backend/risk_models/baseline_comparison_results.json` (generated by
`backend/risk_models/evaluate.py` and `backend/risk_models/baseline_comparison.py`
respectively; not re-run to produce this document).

**Held-out structured/text comparison** (150-row balanced synthetic test set):

| Model | Accuracy |
|---|---|
| Deterministic reference rule | 1.0000 |
| Logistic Regression | 0.9600 |
| Decision Tree (single) | 1.0000 |
| Random Forest | 1.0000 |
| Text model (TF-IDF + Logistic Regression) | 0.9400 |

**5-fold stratified cross-validation** (training split only, test set never touched):

| Model | Mean CV accuracy |
|---|---|
| Logistic Regression | 0.9556 |
| Decision Tree (single) | 0.9933 |
| Random Forest | 0.9956 |

**External validation on real-Synthea-derived data** (30 genuine prescription-change
pairs, extracted by `data/real_synthea/adapt_real_synthea.py` from real Synthea output —
27 labelled MEDIUM, 3 labelled HIGH by the same shared rule, none involving a
narrow-therapeutic-index drug):

| Model | Accuracy on real-Synthea pairs |
|---|---|
| Random Forest | 1.0000 |
| Text model | 0.3000 |

### Read these numbers correctly

**The structured 100% results (rule, Decision Tree, Random Forest) are strongly
influenced by label circularity, not by any model "learning" clinical judgement.**
`risk_label` is a deterministic function of exactly six structured variables
(`drug_changed`, `formulation_changed`, `dose_changed`, `dose_change_pct`,
`route_changed`, `narrow_therapeutic_index`), and Random Forest's/the Decision
Tree's input features are exactly those same six variables — a one-to-one
match, traced exactly in `ALGORITHM_AUDIT_3.md`. Near-perfect accuracy is the
*expected* result of that overlap, not evidence of discovered pattern. Logistic
Regression's measurably lower score (96%, 95.56% CV) is the informative baseline
here: it shows the rule genuinely needs hard branching logic that a linear model
can't represent without manual interaction terms — real, measured evidence that
tree-based methods structurally fit this problem, rather than an assumption.

**The text model's real-Synthea accuracy (30%) is a domain-shift result, not
a failure of the technique**: it is trained on a fixed 17-drug synthetic
vocabulary with pure bag-of-words (TF-IDF) features and no subword/semantic
generalisation, so real drug names outside that vocabulary are functionally
invisible to it. This is an honest, explainable limitation worth keeping in
a methodology chapter, not a result to hide or "fix" by swapping in a
different model without evidence.

**None of the figures above — including the 100% ones — should be described
as clinical validation anywhere.** Two separate things were measured: internal
rule-recovery on synthetic held-out data, and external *data* validation
(genuine drug/dose/route facts the models never trained on, real-Synthea).
Neither is independent clinician-adjudicated validation, because every label
in both datasets is produced by this project's own rule, not by a clinician's
judgement. See `ALGORITHM_AUDIT_3.md` §12 for the exact terminology this
project uses to keep that distinction explicit.

## Data

Three structurally separate sources of data exist in this project:

| Source | What it is | Used for |
|---|---|---|
| Main synthetic dataset | `data/generate_synthetic_data.py` — 600 synthetic patients, each with one previous/current prescription-change pair, balanced 150/class (NONE/LOW/MEDIUM/HIGH) by quota sampling | ML training and evaluation (`train.csv` = 450 rows, `test.csv` = 150 rows, produced by `data/preprocess.py`) |
| Real-Synthea-derived validation | `data/real_synthea/medications_raw.csv` (genuine Synthea v3+ output) → `data/real_synthea/adapt_real_synthea.py` → `real_test.csv` — 30 genuine prescription-change pairs from 104 real Synthea patients | **External validation only** — never used for training |
| Demo first-prescription fixture | `data/generate_demo_patient.py` — one fixed patient (`demo0001`, "Arjun Mehta") with exactly one prescription and no previous prescription to compare against | **UI/database demonstration only**, for exercising the first-prescription review workflow. Structurally cannot enter `medications.csv`/`train.csv`/`test.csv` (those files are shaped as previous-vs-current pairs; this patient has no previous prescription), so it never affects ML training, class balance, or evaluation. |

When the demo fixture has been generated and `data/load_to_db.py` is run,
`pharmacy.db` contains **601 patients** (600 from the main synthetic dataset
plus the 1 demo patient). If the demo fixture hasn't been generated yet,
`load_to_db.py` loads the 600 and skips the demo patient gracefully (no error).

## Dashboards

The frontend has two separate screens, reached via the top navigation bar:

**1. Prescription Review** — the per-patient clinical workflow:
- Patient ID + date-of-birth lookup
- Previous vs. current prescription display
- Comparison-engine output (what changed, and why it matters)
- Primary rule-based risk alert
- Random Forest and text-model comparison readings (clearly labelled as
  non-authoritative)
- Pharmacist acknowledgement (required before dispensing unlocks)
- Dispense logging

**2. Audit & Safety** — a read-only, aggregate oversight view, gated behind a
prototype login screen:
- Total dispenses
- Total acknowledgements
- First-prescription review count (tracked separately from clinical risk levels)
- Acknowledged risk-level counts (NONE / LOW / MEDIUM / HIGH)
- Recent activity feed (acknowledgements and dispenses, newest first)
- **Patient ID only — patient names are never shown on this dashboard**, since
  it's an aggregate oversight view rather than a per-patient clinical one

### Security limitation of the Audit & Safety login gate

The Audit & Safety dashboard is gated by a login screen (`frontend/src/AuditLogin.jsx`)
using demo credentials defined in `frontend/src/auditDemoCredentials.js`. This is
a **prototype access-control demonstration only**, stated explicitly on both the
login screen and the dashboard itself:

- The gate is **frontend-only** — implemented entirely in React state, never
  persisted (a page refresh always requires logging in again).
- The credentials are **not production-secure** — a plain, visible JavaScript
  constant, readable by anyone who opens browser developer tools or the
  built bundle.
- The backend's `/api/audit/summary` and `/api/audit/activity` endpoints are
  **not server-authenticated at all** — the frontend gate does not, and cannot,
  protect them. Anyone with network access to the API can call them directly.
- A production deployment would require secure server-side authentication and
  role-based access control — neither exists here, and this prototype does not
  claim otherwise.

## Database

SQLite (`data/pharmacy.db`), built from `data/schema.sql`:

| Table | Purpose |
|---|---|
| `patients` | Patient demographic/clinical context (name, DOB, condition, allergy, GP, concurrent medications) |
| `prescriptions` | Every prescription ever recorded for a patient, current and historical, flagged via `is_current` |
| `acknowledgements` | Every time a pharmacist confirmed they reviewed an alert or a first prescription — who, when, and at what risk level (including the `FIRST_PRESCRIPTION_REVIEW` sentinel for first-prescription reviews, which reuses the same column rather than requiring a schema change) |
| `dispenses` | Every actual dispensing transaction — who, what, for whom, when, and (via `ack_id`) which acknowledgement authorised it |

The `activity_log` view combines acknowledgements and dispenses with patient
*names* joined in, for readable per-patient browsing. The Audit & Safety
dashboard's endpoints deliberately do **not** reuse this view — they run their
own query selecting `patient_id` instead of patient name, matching the
dashboard's aggregate/de-identified design.

**DB Browser for SQLite** is a development/inspection tool only — useful for
manually browsing `pharmacy.db` while working on the project, but it is not
part of the runtime architecture; the running FastAPI backend talks to SQLite
directly via Python's `sqlite3` module.

## Testing

```
python -m pytest backend/tests -v
```

**56 tests currently pass**, across six files:

| File | Covers |
|---|---|
| `test_pipeline.py` | Comparison-engine correctness, dataset integrity, NTI consistency |
| `test_first_prescription.py` | The first-prescription review workflow |
| `test_demo_fixture.py` | The demo-patient fixture and its graceful-skip loading behaviour |
| `test_rule_primary_risk.py` | That the deterministic rule — not Random Forest or the text model — determines `risk_final`, including active proof (via a fake model that always predicts a fixed wrong value) that neither ML model can override it |
| `test_lookup_two_factor.py` | Patient ID + date-of-birth two-factor lookup behaviour |
| `test_audit_dashboard.py` | The Audit & Safety dashboard's two endpoints, using a deliberately-constructed known dataset |

Frontend:
```
npm run build   # passes
npm run lint    # passes (oxlint)
```
There is currently no frontend test framework installed (`package.json` only
defines `dev`/`build`/`lint`/`preview` scripts) — frontend correctness is
checked via `build`/`lint` plus manual verification, not automated component tests.

## Technology stack

- **Python** — backend, data pipeline, ML models
- **FastAPI** — REST API server (`backend/main.py`)
- **React + Vite** — frontend (`frontend/`)
- **SQLite** — database (`data/pharmacy.db`)
- **scikit-learn** — Random Forest, Logistic Regression, Decision Tree, TF-IDF
- **pytest** — backend test suite (56 tests)

## Project layout

```
data/
  generate_synthetic_data.py   balanced synthetic patients + paired prescriptions (600 pairs)
  generate_demo_patient.py     one fixed demo patient, exactly one prescription (UI demo only)
  eda.py                       class balance, correlation, distributions, leakage check
  preprocess.py                cleaning, feature selection, fixed train/test split
  schema.sql                   relational schema (patients/prescriptions/acknowledgements/dispenses)
  load_to_db.py                loads CSVs (including the demo fixture, if present) into pharmacy.db
  eda_outputs/                 generated: class_balance.png, correlation_heatmap.png, etc.
  real_synthea/
    medications_raw.csv        genuine Synthea v3+ output (not the generator substitute)
    adapt_real_synthea.py      extracts real change-pairs -> real_test.csv, using the shared classify_risk()
    real_test.csv              generated: external validation set (30 pairs)
backend/
  comparison_engine.py         change-detection logic + the single shared classify_risk() risk rule
  main.py                      FastAPI app: patient lookup, comparison, risk scoring, acknowledge, dispense, audit endpoints
  requirements.txt             backend Python dependencies
  risk_models/
    train_random_forest.py     structured-feature classifier (class-weighted)
    train_text_classifier.py   NLP classifier (ClinicalBERT substitute: TF-IDF + Logistic Regression, class-weighted)
    evaluate.py                comparison table on the fixed synthetic test split
    evaluate_real_synthea.py   external validation against real_test.csv
    baseline_comparison.py     experimental comparison: rule vs. Logistic Regression vs. Decision Tree vs. the existing (loaded, not retrained) Random Forest vs. the text model, with 5-fold CV
    report_utils.py            shared metric-printing helpers
  tests/
    test_pipeline.py, test_first_prescription.py, test_demo_fixture.py,
    test_rule_primary_risk.py, test_lookup_two_factor.py, test_audit_dashboard.py
    (56 tests total — see "Testing" above)
frontend/
  src/App.jsx                  app shell — switches between Prescription Review and Audit & Safety, holds auth state
  src/LookupScreen.jsx         Patient ID + date-of-birth lookup form
  src/RecordScreen.jsx         patient record: prescriptions, first-prescription/no-prescription handling, dispense
  src/AlertPanel.jsx           primary rule-based alert + RF/text comparison readings, acknowledgement
  src/AuditLogin.jsx           prototype login gate for the Audit & Safety dashboard
  src/auditDemoCredentials.js  the one place the demo audit credentials are defined
  src/AuditDashboard.jsx       read-only Audit & Safety dashboard
```

## Opening in VS Code

1. Open the folder (or double-click `rx-alert-system.code-workspace` to open as a workspace).
2. Install the recommended extensions when prompted (Python, ESLint, Prettier, SQLite viewer, REST Client).
3. Run **Terminal → Run Task → "Setup: create Python venv + install backend deps"**, then **"Setup: install frontend deps"**.
4. Run **Terminal → Run Task → "Full pipeline: data → EDA → preprocess → DB → train → evaluate → test"** — generates data, runs EDA, preprocesses, loads the DB, trains both models, prints the comparison table, and runs the test suite.
5. Run **Terminal → Run Task → "Run everything (backend + frontend)"**, or use the **Run and Debug** panel (`F5`) with **"Run full stack (backend + frontend debug)"** to launch both with breakpoints available in the FastAPI code.
6. Open `http://localhost:5173`.

`.vscode/launch.json` also has individual debug configs for each script (data generation, DB load, model evaluation) if you want to step through one piece at a time. The SQLite extension lets you browse `data/pharmacy.db` directly from the sidebar once it's generated.

### Windows notes

- **`npm install` fails with "running scripts is disabled on this system"**: Windows blocks PowerShell scripts by default. Open PowerShell **as administrator** and run:
  ```
  Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
  ```
  Type `Y` when prompted, then re-run the task.
- **Python interpreter**: after "Setup: create Python venv + install backend deps" finishes, VS Code may prompt *"We noticed a new virtual environment"* — click **Yes** to select it. If it doesn't prompt, use `Ctrl+Shift+P` → **"Python: Select Interpreter"** → choose the one inside `.venv`.
- The tasks already account for Windows using `python` (not `python3`) and `.venv\Scripts\` (not `.venv/bin/`) — you shouldn't need to edit `tasks.json` yourself.

## Running it manually (no VS Code)

**1. Generate balanced data, analyse it, preprocess, load the database**
```bash
cd data
pip install -r ../backend/requirements.txt --break-system-packages
python3 generate_synthetic_data.py   # writes patients.csv, medications.csv (balanced 150/class, 600 pairs)
python3 generate_demo_patient.py     # optional: writes demo_patient.csv (one first-prescription demo patient)
python3 eda.py                       # writes data/eda_outputs/*.png + eda_report.txt
python3 preprocess.py                # cleans, selects features, writes train.csv/test.csv
python3 load_to_db.py                # builds pharmacy.db (601 patients if the demo fixture was generated, else 600)
```

**2. Train the risk models, evaluate, and test**
```bash
cd ../backend/risk_models
python3 evaluate.py                  # trains both models on train.csv, scores on test.csv
cd ../..
python3 -m pytest backend/tests -v   # 56 tests: correctness, data integrity, rule-primacy, workflows, dashboards
```

**3. Start the API**
```bash
cd backend
python3 -m uvicorn main:app --reload --port 8000
```
Check `http://localhost:8000/api/health`.

**4. Start the frontend**
```bash
cd ../frontend
npm install
npm run dev
```
Open the printed local URL. Look up a patient using a matching **Patient ID
and date of birth** pair from `data/patients.csv` (or the demo patient,
`patient_id = demo0001`, `date_of_birth = 1980-01-01`, if the demo fixture
was loaded).

## Data pipeline (run in this order)

Your supervisor's checklist maps onto these steps directly:

| Step | Script | What it does |
|---|---|---|
| Generate | `data/generate_synthetic_data.py` | **Balanced by construction**: quota sampling guarantees exactly 150 examples per class (NONE/LOW/MEDIUM/HIGH). Uses the single shared `classify_risk()` rule from `backend/comparison_engine.py` to generate labels — not a separate copy of the logic. |
| Generate demo fixture (optional) | `data/generate_demo_patient.py` | Writes one fixed, non-randomised patient with exactly one prescription, for demonstrating the first-prescription review workflow. Structurally cannot enter the paired ML dataset. |
| Analyse & visualise | `data/eda.py` | Runs **before any model sees the data**. Outputs to `data/eda_outputs/`: `class_balance.png`, `correlation_heatmap.png`, `feature_distributions.png`, and `eda_report.txt` (correlation matrix + a single-feature leakage check). |
| Preprocess | `data/preprocess.py` | Cleans nulls/types, does **feature selection**, and splits into `train.csv`/`test.csv` **once** — every downstream script reuses this exact split so no model sees a different train/test partition than another. Asserts no patient appears in both splits and that the label isn't in the feature list. |
| Load DB | `data/load_to_db.py` | Loads the full (pre-split) data, plus the demo fixture if present, into SQLite for the running app to query. |
| Train + evaluate | `backend/risk_models/evaluate.py` | Trains both models on `train.csv`, scores on `test.csv`, uses `class_weight="balanced"` on both, prints per-class precision/recall/F1 and a confusion matrix. |
| Baseline comparison (experimental) | `backend/risk_models/baseline_comparison.py` | Adds Logistic Regression and a single Decision Tree to the comparison, plus 5-fold CV — see "Algorithm comparison results" above. Loads the existing Random Forest/text models rather than retraining them. |
| Test | `backend/tests/` | 56 pytest tests — see "Testing" above. |

Run the whole thing with the VS Code task **"Full pipeline: data → EDA → preprocess → DB → train → evaluate → test"**, or manually in that order.

### Feature selection

`frequency_changed` was dropped after EDA: it had the lowest Random Forest importance and its single-value class purity was barely above the 4-class baseline — it overlapped substantially with `drug_changed` and wasn't contributing distinct signal. The remaining structured features (`drug_changed`, `formulation_changed`, `dose_changed`, `dose_change_pct`, `route_changed`, `narrow_therapeutic_index`) each carry distinct signal.

## External validation on real Synthea data

`data/real_synthea/` holds genuine Synthea v3+ output (not the Python-generated
substitute) — 104 real synthetic patients, actual medication records. This
directly satisfies the O2 objective's original intent (Synthea-generated data),
separately from the balanced generator used for training.

**Why it's validation, not training data**: real Synthea output has no
manufacturer field at all (tracked honestly as "not available in source data",
never assumed), and dose/route/formulation have to be extracted from a
free-text description via regex — noisier than the synthetic generator's
structured columns. Only 30 genuine same-condition prescription-change pairs
exist across 104 patients — too few, and too narrow in class coverage, to
train on, but a legitimate **external test**: does a model trained entirely
on synthetic data generalise to prescription changes it has never seen in
any form?

**Result** (see "Algorithm comparison results" above for the full table and
the required caveats): of the 30 real pairs (27 MEDIUM, 3 HIGH by the shared
rule, none involving a narrow-therapeutic-index drug), Random Forest scored
1.0000 and the text model scored 0.3000. **The honest limitation to state
alongside this result**: this validates generalisation only on the
MEDIUM/HIGH boundary — no real LOW/NONE cases occurred in this 104-patient
sample. The balanced synthetic test set remains the only source of evidence
for those two classes, and this remains external *data* validation, not
clinical validation (see above).
