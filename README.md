# Automated Prescription Comparison System — working prototype

Implementation of the objectives O2–O5 from the project plan: synthetic
data, comparison engine, two risk classifiers, and the PMR alert UI
(Figures 3–5).

## What's here vs. what the plan specifies

This sandbox environment has a restricted network allowlist (npm/pip
registries and GitHub only — no Maven Central, no huggingface.co). Two
components were substituted so the whole pipeline actually runs
end-to-end; everything else matches the plan as written.

| Component | Plan | Built here | Why |
|---|---|---|---|
| Synthetic data | Synthea v3 (Java) | Python generator, same CSV shape | Synthea needs Maven Central, unreachable here |
| Database | PostgreSQL | SQLite | Same schema (`data/schema.sql`); no server needed for a demo |
| Comparison engine | Spring Boot (Java) | FastAPI (Python) | Same REST contract; Spring Boot needs Maven Central |
| Random Forest | scikit-learn | scikit-learn | Matches plan exactly |
| ClinicalBERT | Hugging Face pretrained model | TF-IDF + Logistic Regression on the same sentences | huggingface.co isn't reachable here, so no pretrained clinical embeddings |
| Alert UI | React 18 + Vite | React 18 + Vite | Matches plan exactly |

If you have normal internet access, `data/generate_synthetic_data.py`
can be replaced by real Synthea output (same column names), and
`backend/risk_models/train_text_classifier.py` can be replaced by a real
ClinicalBERT fine-tune — no other files need to change, since both talk
to the rest of the system through the same CSV/JSON contracts.

## Project layout

```
data/
  generate_synthetic_data.py   balanced synthetic patients + paired prescriptions
  eda.py                       class balance, correlation, distributions, leakage check
  preprocess.py                cleaning, feature selection, fixed train/test split
  schema.sql                   relational schema (patients/prescriptions/acknowledgements)
  load_to_db.py                loads CSVs into pharmacy.db (SQLite)
  eda_outputs/                 generated: class_balance.png, correlation_heatmap.png, etc.
  real_synthea/
    medications_raw.csv        genuine Synthea v3+ output (not the generator substitute)
    adapt_real_synthea.py      extracts real change-pairs -> real_test.csv
    real_test.csv              generated: external validation set
backend/
  comparison_engine.py         change-detection logic (drug/dose/frequency/route)
  main.py                      FastAPI app: lookup, alert, acknowledge
  risk_models/
    train_random_forest.py     structured-feature classifier (class-weighted)
    train_text_classifier.py   NLP classifier (ClinicalBERT substitute, class-weighted)
    evaluate.py                comparison table on the fixed synthetic test split
    evaluate_real_synthea.py   external validation against real_test.csv
  tests/
    test_pipeline.py           comparison-engine + data-integrity + leakage tests
frontend/
  src/App.jsx, LookupScreen.jsx, RecordScreen.jsx, AlertPanel.jsx
  React prototype of Figures 3 (lookup), 4 (existing record), 5 (alert)
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
python3 generate_synthetic_data.py   # writes patients.csv, medications.csv (balanced 150/class)
python3 eda.py                       # writes data/eda_outputs/*.png + eda_report.txt
python3 preprocess.py                # cleans, selects features, writes train.csv/test.csv
python3 load_to_db.py                # builds pharmacy.db
```

**2. Train the risk models, evaluate, and test**
```bash
cd ../backend/risk_models
python3 evaluate.py                  # trains both models on train.csv, scores on test.csv
cd ../..
python3 -m pytest backend/tests -v   # correctness + data-integrity + leakage checks
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
Open the printed local URL. Search using any name + DOB from
`data/patients.csv`.

## Data pipeline (run in this order)

Your supervisor's checklist maps onto these steps directly:

| Step | Script | What it does |
|---|---|---|
| Generate | `data/generate_synthetic_data.py` | **Balanced by construction**: quota sampling guarantees exactly 150 examples per class (NONE/LOW/MEDIUM/HIGH), not random weighting. Old version produced 237/150/74/59 — a 4:1 imbalance; this is fixed. |
| Analyse & visualise | `data/eda.py` | Runs **before any model sees the data**. Outputs to `data/eda_outputs/`: `class_balance.png`, `correlation_heatmap.png`, `feature_distributions.png`, and `eda_report.txt` (correlation matrix + a single-feature leakage check). |
| Preprocess | `data/preprocess.py` | Cleans nulls/types, does **feature selection** (drops `frequency_changed`, see reasoning in that file's docstring), and splits into `train.csv`/`test.csv` **once** — every downstream script reuses this exact split so no model sees a different train/test partition than another. Asserts no patient appears in both splits and that the label isn't in the feature list. |
| Load DB | `data/load_to_db.py` | Loads the full (pre-split) data into SQLite for the running app to query. |
| Train + evaluate | `backend/risk_models/evaluate.py` | Trains both models on `train.csv`, scores on `test.csv`, uses `class_weight="balanced"` on both, prints per-class precision/recall/F1 and a confusion matrix. |
| Test | `backend/tests/test_pipeline.py` | Pytest checks: comparison-engine correctness, no missing values, class ratio ≤1.5×, all four classes present in both splits, no class under 10 examples in either split, no patient leakage. Run with `pytest backend/tests -v`. |

Run the whole thing with the VS Code task **"Full pipeline: data → EDA → preprocess → DB → train → evaluate → test"**, or manually in that order.

### Feature selection

`frequency_changed` was dropped after EDA: it had the lowest Random Forest importance (0.074) and its single-value class purity (0.53) was barely above the 0.25 baseline for 4 classes — it wasn't contributing much the other features didn't already cover, and it overlapped with `drug_changed` (r=0.40). The remaining four features (`drug_changed`, `dose_changed`, `dose_change_pct`, `route_changed`) each carry distinct signal, confirmed by the correlation heatmap (no pair above r=0.4).

### On the accuracy numbers — read this before reporting them

After balancing and feature selection, Random Forest scores **93.3%** and the text model scores **98.7%** on held-out test data (was ~98–99% for both before these fixes). That gap is itself informative: dropping `frequency_changed` cost Random Forest recall specifically on LOW-risk (frequency-only) changes, because without that feature, a frequency-only change looks identical to no change at all in the structured data. The text model didn't lose the same accuracy because its input sentences are still full natural-language descriptions that mention frequency changes even though the *structured* feature was dropped — this is a genuine, explainable argument for why free-text/context-aware models can retain signal that a simplified structured feature set loses, which is exactly the comparison your project plan sets out to make.

The remaining high accuracy on both models has one root cause worth stating plainly in your evaluation chapter: **`risk_label` in this synthetic dataset is a deterministic rule defined over the same features (or their text description) the models are trained on** (see `data/eda.py`'s leakage check — `drug_changed` and `dose_change_pct` each show 1.00 single-feature purity). That's not classic train/test leakage (train and test patients never overlap, verified by the test suite), but it does mean the accuracy ceiling here is a property of synthetic-label construction, not evidence either model would perform this well on real prescriptions where a pharmacist's risk judgement depends on more than four signals. State this as a limitation, not a result to be proud of at face value — reviewers will ask about it if you don't.

## External validation on real Synthea data

`data/real_synthea/` holds genuine Synthea v3+ output (not the Python-generated substitute) — 104 real synthetic patients, actual medication dispense records. This directly satisfies your O2 objective's original intent (Synthea-generated data), separately from the balanced generator used for training.

**Why it's validation, not training data**: real Synthea output has no `frequency` field at all (which happens to align with our dropped `frequency_changed` feature) and dose/route have to be extracted from a free-text description via regex — noisier than the synthetic generator's structured columns. More importantly, only ~30 genuine same-condition prescription-change pairs exist across 104 patients, and by chance every one of them is a real drug switch (HIGH risk) — real medication changes for an ongoing condition tend to be switches, not same-drug dose tweaks. That's too small and too single-class to train on, but it's a legitimate **external test**: does a model trained entirely on synthetic data generalise to medication changes it has never seen in any form?

**Result**: Random Forest correctly flagged **29/30 (96.7%)** and the text model **27/30 (90.0%)** of real drug switches as HIGH risk. Run it yourself with the VS Code task **"Full pipeline + real Synthea external validation"**, or manually:
```bash
cd data/real_synthea
python3 adapt_real_synthea.py       # extracts real change-pairs -> real_test.csv
cd ../../backend/risk_models
python3 evaluate_real_synthea.py    # scores the already-trained models against it
```

**The honest limitation to state alongside this result**: this only validates recall on HIGH-risk drug switches — it says nothing about how either model performs on real LOW/MEDIUM/NONE cases, since none happened to appear in this particular 104-patient sample. The balanced synthetic test set remains the only source of evidence for those three classes. Report both results together, not the real-data number alone — a 96.7% headline without that caveat would overstate what was actually tested.

## Design notes

- **Risk decision rule**: HIGH = drug switch or dose reduction ≥50%;
  MEDIUM = any other dose change; LOW = frequency/route change only —
  exactly the thresholds from objective O4.
- **Displayed risk** in the UI is the higher of the two models' outputs
  (fail-safe toward caution), with both individual scores shown for
  transparency.
- **Dispense lock**: the button is disabled via React state until
  `/api/acknowledge` succeeds, mirroring the mandatory-acknowledgement
  requirement in O5.
