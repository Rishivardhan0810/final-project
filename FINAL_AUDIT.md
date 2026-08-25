# Final Technical & Supervisor-Feedback Audit

Read-only inspection. No file was edited, no model retrained, no dataset regenerated, no database touched, and nothing was committed or pushed while producing this report. Every figure quoted below is either given in your brief or read directly from `backend/risk_models/evaluation_summary.json` / `baseline_comparison_results.json` / row counts of the actual CSVs on disk — none is invented.

---

## Part 1 — Supervisor feedback, point by point

### 1. The whole point should be prescription-change detection
**Status: FULLY ADDRESSED**
- Evidence: [`backend/comparison_engine.py:88-148`](backend/comparison_engine.py#L88-L148) `compare_prescriptions()` is the architectural centre of the system — a pure, deterministic diff of `Prescription` objects producing `drug_changed`, `formulation_changed`, `dose_changed`, `dose_change_pct`, `route_changed`, `narrow_therapeutic_index`. [`backend/main.py:127-196`](backend/main.py#L127-L196) calls it before anything ML-related runs, and both risk models are downstream consumers of its output, not the other way round.
- Why it satisfies the feedback: change detection isn't a side feature bolted onto an ML pipeline — it's the thing everything else (risk classification, the alert, the acknowledgement, the audit trail) is built on top of. This ordering is also true historically: ALGORITHM_AUDIT_3.md's own recommendation (§8) was to make this rule-primary explicitly, and that recommendation is now implemented (see Part 2A).
- Code changes required: **None.**
- Dissertation-only: State this ordering explicitly and early — "change detection is the primary contribution; classification is secondary" — rather than leading with the ML accuracy numbers, which invite the opposite framing.

### 2. Explain the specific methods used to detect changes
**Status: PARTIALLY ADDRESSED**
- Evidence: the method itself is fully explainable from the code — `drug_changed` = active-ingredient string inequality; `formulation_changed` = same drug, different formulation string; `dose_change_pct = (previous.dose_mg - current.dose_mg) / previous.dose_mg`; `route_changed` = route string inequality; `narrow_therapeutic_index` = set-membership check via `is_narrow_therapeutic_index()` ([`comparison_engine.py:44-58`](backend/comparison_engine.py#L44-L58)).
- Why it's only partial: the code is correct and well-commented, but the two documents that are supposed to explain this to a reader outside the code are **out of date**. `README.md`'s "Design notes" section (lines 156-166) still describes the *original* flat rule ("HIGH = drug switch or dose reduction ≥50%") with no mention of NTI-scaled thresholds, formulation changes, or the current rule-primary architecture. `PROJECT_STRUCTURE.md` likewise doesn't mention NTI logic depth, the audit dashboard, or the login gate. Someone reading only the docs (a supervisor, an examiner) would get a materially wrong picture of the current method.
- Code changes required: **None.**
- Dissertation-only: **Yes, and this is higher-priority than it looks** — write the methodology section from the actual code (this audit + ALGORITHM_AUDIT_3.md give you the accurate description), not from the stale README. Separately, README.md/PROJECT_STRUCTURE.md should be refreshed before submission if they're referenced as project artefacts (see Part 4, Priority List).

### 3. Check references and compare with existing approaches
**Status: NOT ADDRESSED**
- Evidence: nothing in the codebase can satisfy this — it's a literature-review requirement, not a code artefact. No file references external clinical decision-support literature, existing e-prescribing change-detection systems, or comparable academic work.
- Why: this was never in scope for any of the implementation tasks completed so far; it's purely a dissertation-writing task.
- Code changes required: **None — not applicable to code at all.**
- Dissertation-only: **Yes.** This needs a literature review section comparing your deterministic-rule approach against: (a) rule-based clinical decision support systems generally (e.g. drug-interaction checkers), (b) ML-based clinical risk scoring literature, and (c) the specific circularity/label-leakage problem you found, which is a known issue in supervised learning on rule-derived labels — worth citing general ML methodology sources on this if available.

### 4. Even a first prescription must be reviewed for medication/dose safety
**Status: FULLY ADDRESSED**
- Evidence: [`backend/main.py:114-125`](backend/main.py#L114-L125) — a patient with exactly one prescription gets `status="first_prescription"`, `alert=None` (no NONE/LOW/MEDIUM/HIGH is ever assigned, since there's nothing to compare against), and an explicit `status_message` requiring pharmacist review. [`frontend/src/RecordScreen.jsx:149-171`](frontend/src/RecordScreen.jsx#L149-L171) renders a dedicated review panel that blocks dispensing (`dispenseLocked` includes `isFirstPrescription && !acknowledged`, line 32) until a named pharmacist explicitly acknowledges it. `backend/tests/test_first_prescription.py` (5 tests) covers this directly.
- Why it satisfies the feedback: this was a direct, explicit response to the exact wording of this feedback point, implemented as its own workflow rather than being silently absorbed into the "NONE risk" path.
- Code changes required: **None.**
- Dissertation-only: Frame this as evidence of iterating on supervisor feedback specifically — a good, concrete "critical engagement with feedback" example for the methodology/reflection chapter.

### 5. Wrong dispensing is a serious patient-safety/professional issue
**Status: PARTIALLY ADDRESSED**
- Evidence: dispensing is gated behind acknowledgement (`dispenseLocked` in [`RecordScreen.jsx:31-32`](frontend/src/RecordScreen.jsx#L31-L32)), and every dispense is logged with pharmacist name, drug, dose, and timestamp, linked via `ack_id` FK back to the specific acknowledgement that unlocked it ([`schema.sql:44-52`](data/schema.sql#L44-L52), [`main.py:225-236`](backend/main.py#L225-L236)).
- Why it's only partial: this protects against dispensing *without review*, and gives full accountability after the fact — genuinely serious safety features for a prototype. But it does **not** implement (nor claim to implement) a physical barcode/product-match check — the dispense-hint text in the UI says outright: *"Barcode scan on collection verifies the box matches this current prescription — it does not check whether the prescription itself has changed. That check happens above"* ([`RecordScreen.jsx:262-265`](frontend/src/RecordScreen.jsx#L262-L265)). There's also no allergy cross-check enforced at dispense time (the allergy is displayed as a banner tag, never blocks anything), and no second-pharmacist countersignature step.
- Code changes required: **None recommended** — a full barcode/allergy-interlock/countersignature system is out of scope for an MSc prototype and would be "nice to have," not something the supervisor feedback demands be built.
- Dissertation-only: State explicitly which layers of a real dispensing-safety system this prototype implements (review-gate + audit trail) versus which it deliberately does not (physical product verification, allergy enforcement, dual-check) — this shows awareness of the full problem without overclaiming scope.

### 6. Provide comparative analysis and clear evaluation criteria
**Status: FULLY ADDRESSED**
- Evidence: `backend/risk_models/baseline_comparison.py` + `baseline_comparison_results.json` give, per model: accuracy, macro precision/recall/F1, weighted F1, confusion matrix, and — specifically clinically meaningful — **under-risked vs over-risked counts** (a wrong-direction error where the model says the risk is *lower* than the true rule-derived risk, which is the clinically dangerous direction, versus over-risked, which is merely over-cautious). 5-fold stratified CV is included for variance estimates.
- Why it satisfies the feedback: the criteria aren't just "accuracy" — under/over-risked separation is a genuinely clinical evaluation lens, not a generic ML one.
- Code changes required: **None.**
- Dissertation-only: Present the under/over-risked breakdown prominently — it's your strongest evidence of "critical methods rather than unsupported claims" (point 12) because it reframes the evaluation around patient safety rather than raw accuracy.

### 7. Compare different algorithms / NLP approaches
**Status: PARTIALLY ADDRESSED**
- Evidence: structured-feature algorithms are genuinely compared — deterministic rule, Logistic Regression, single Decision Tree, Random Forest, all on the identical train/test split (`baseline_comparison.py`). This is real, measured comparison, not assertion.
- Why it's only partial: on the NLP side there is exactly **one** text approach (TF-IDF + Logistic Regression, explicitly documented as a ClinicalBERT substitute — see `comparison_engine.py:1-31` and `README.md:20`) — no comparison *between* NLP techniques (e.g. TF-IDF vs. a transformer embedding). This substitution is honestly disclosed (sandbox has no route to huggingface.co) rather than hidden, which is the right way to handle it, but it means "compare NLP approaches" is satisfied only at the structured-model level, not within NLP itself.
- Code changes required: **None** — training a real transformer is a materially larger project change, not a small fix, and isn't necessary to defend the current comparison.
- Dissertation-only: State plainly that the NLP comparison is single-technique due to a documented environment constraint, and frame the TF-IDF model's 94%→30% domain-shift result (see Part 2C) as the actual NLP-relevant finding — that result stands on its own regardless of how many text techniques were tried.

### 8. Explain the core idea clearly
**Status: PARTIALLY ADDRESSED**
- Evidence: the code itself is unusually clear for this purpose — every file has a one-line "PART OF" header, `comparison_engine.py` and `main.py` are heavily and accurately commented, and the architecture (detect → classify via rule → display RF/text as comparison → acknowledge → dispense → audit) is coherent.
- Why it's only partial: the *external* explanation artefacts are stale. `README.md` describes an architecture that no longer exists in several material ways (see finding below) and `PROJECT_STRUCTURE.md` predates the audit dashboard, login gate, rule-primary change, and two of the six test files.
- Code changes required: **None.**
- Dissertation-only: **Yes — this is the same underlying issue as point 2.** The core idea should be explained fresh, from current code, not inherited from README prose written for an earlier version of the system.

  **Concrete stale-documentation findings** (for your awareness, not fixed here):
  - `README.md` "Design notes" (lines 156-166) describes the *old* flat risk rule with no NTI scaling, and states *"Displayed risk in the UI is the higher of the two models' outputs"* — this architecture (ML-driven, "higher of two" fusion) was replaced by the rule-primary architecture and no longer exists in the code at all.
  - `README.md` line 112 says search uses "any name + DOB" — lookup is now Patient ID + DOB.
  - `README.md`'s quoted accuracy figures (93.3% RF / 98.7% text, line 136; real-Synthea 96.7%/90.0%, line 146) **do not match** the current `evaluation_summary.json` (100% RF / 94% text) or your brief's real-Synthea figures (100%/30%). `evaluate_real_synthea.py`'s own inline comment (lines 85-94) confirms these older README numbers predate the pharmacology-scaled NTI threshold rule.
  - `PROJECT_STRUCTURE.md` says `test_pipeline.py` has "17 tests" (it now has 20) and lists only one test file; five more now exist (56 tests total). It doesn't mention `AuditDashboard.jsx`, `AuditLogin.jsx`, `baseline_comparison.py`, `generate_demo_patient.py`, or the `/api/audit/*` endpoints at all.
  - Neither document mentions the rule-primary architecture, the first-prescription workflow, or the audit/login work — i.e. roughly the last half of this project's development is invisible in both narrative documents.

### 9. Explain exactly HOW changes are detected and what technology is used
**Status: FULLY ADDRESSED (at code level) / PARTIALLY (at explanation level)**
- Evidence: same as point 2 — the exact mechanism is: Python dataclasses (`Prescription`), direct field comparison, a percentage computation for dose, and a case/whitespace-insensitive set-membership + word-boundary check for NTI status. Technology: pure Python, no ML, no external service, `FastAPI` exposes it via `/api/lookup`.
- Code changes required: **None.**
- Dissertation-only: Reuse this audit's Part 2B trace (below) as the backbone of the "how" section — it's already a complete, verified, step-by-step account.

### 10. Discuss reducing review time
**Status: NOT PROVEN — dissertation framing needed, not code**
- Evidence: there is no timing instrumentation anywhere in the codebase — no measurement of how long a pharmacist takes to review an alert with vs. without this system.
- Why: this claim currently has zero empirical support and cannot be measured retrospectively from what exists.
- Code changes required: **None recommended** to actually measure this (a timed user study is out of scope for a code fix).
- Dissertation-only: Frame this as a **plausible, argued benefit** (automated triage of NONE-risk changes means a pharmacist doesn't have to manually work out that nothing risk-relevant changed) rather than a measured one. See Part 2E for exact wording guidance — this must be labelled INFERRED, not MEASURED or DEMONSTRATED.

### 11. Discuss reducing prescription-change/medication errors
**Status: NOT PROVEN — same caveat as point 10**
- Evidence: no error-rate data exists (no real-world deployment, no baseline error rate to compare against).
- Code changes required: **None.**
- Dissertation-only: Same treatment as point 10 — argue the *mechanism* by which errors could be reduced (deterministic, exhaustively testable rule vs. relying purely on human recall of NTI drug lists), without claiming a measured reduction. See Part 2E.

### 12. Use critical methods rather than making unsupported claims
**Status: FULLY ADDRESSED (in the project's own audit trail) / requires carrying through to the dissertation**
- Evidence: ALGORITHM_AUDIT.md → `_2` → `_3` is itself a documented critical-methods trail: the 100% RF accuracy was investigated rather than accepted, traced to exact label circularity (Part 2C below), and the architecture was changed in response (rule-primary). This is genuinely strong evidence of critical engagement, not just a checklist claim.
- Why it's not simply "done": this critical rigor lives in the audit `.md` files and code comments — it needs to be surfaced explicitly in the dissertation text itself, not left implicit in commit history a marker won't read.
- Code changes required: **None.**
- Dissertation-only: Write up the *audit process itself* (found circularity → traced it exactly → changed the architecture) as methodology, per ALGORITHM_AUDIT_3.md §9's own recommendation. This is a stronger viva answer than a static "we chose RF because accuracy was highest."

### 13. Give a strong justification for the selected algorithm
**Status: FULLY ADDRESSED**
- Evidence: the deterministic rule is now primary specifically *because* of, not despite, the algorithm-comparison work — see Part 2C for the full reasoning, reusing measured numbers.
- Code changes required: **None.**
- Dissertation-only: Lead with "the rule is primary because it is provably correct and the target function is fully known" rather than "the rule is primary because it scored 100%" — the former is a structural argument, the latter conflates the rule with the models it's compared against (both score 100% on this data by construction — see Part 2C).

### 14. Technology choice and how well it is used will be marked
**Status: PARTIALLY ADDRESSED — see Part 3 (Technology Justification) below for the full breakdown.**
- Code changes required: **None.**
- Dissertation-only: **Yes**, several choices need explicit justification text — see Part 3.

### 15. The algorithm itself will be examined for appropriateness
**Status: FULLY ADDRESSED** — see Part 2C. The label-circularity finding and the resulting rule-primary decision is the strongest single piece of evidence of algorithm-appropriateness reasoning in this project.
- Code changes required: **None.**
- Dissertation-only: Yes — present Part 2C's argument directly.

### 16. Use Patient ID instead of relying on patient name
**Status: FULLY ADDRESSED**
- Evidence: [`backend/main.py:54-56`](backend/main.py#L54-L56) `LookupRequest` requires both `patient_id` and `date_of_birth`; the SQL query (`main.py:81-84`) filters on both; patient *name* is never part of the lookup query, only shown after a successful match. [`frontend/src/LookupScreen.jsx`](frontend/src/LookupScreen.jsx) form fields are Patient ID + DOB only. `backend/tests/test_lookup_two_factor.py` (4 tests) verifies correct-ID+wrong-DOB and wrong-ID+correct-DOB both 404.
- Code changes required: **None.**
- Dissertation-only: None needed beyond stating the two-factor rationale (a single identifier increases wrong-patient risk from a typo).

### 17. Two different dashboards were suggested
**Status: FULLY ADDRESSED**
- Evidence: Dashboard 1 = Prescription Review (`LookupScreen`/`RecordScreen`/`AlertPanel`, patient-identified, per-patient clinical workflow). Dashboard 2 = Audit & Safety (`AuditDashboard.jsx`, aggregate, `patient_id`-only, read-only oversight, gated by `AuditLogin.jsx`). Navigation between them is in `App.jsx` (`topbar-nav`).
- Code changes required: **None.**
- Dissertation-only: Explain the *design rationale* for the split (identified clinical workflow vs. de-identified aggregate oversight) — this is a genuinely good privacy-by-design argument worth spelling out (see Part 3F).

### 18. Connect PSEL/LSEPI considerations to the project
**Status: NOT ADDRESSED**
- Evidence: a repo-wide search for "PSEL", "LSEPI", "ethics", "professional standard" found **no matches anywhere** except two incidental "GDPR" mentions ([`main.py:75`](backend/main.py#L75), [`LookupScreen.jsx:19-20`](frontend/src/LookupScreen.jsx#L19-L20)). There is no document, comment, or section anywhere connecting the project's design decisions to a PSEL/LSEPI framework explicitly.
- Why: this is inherently a dissertation-narrative requirement — PSEL/LSEPI is an analytical framework you apply in writing, not something a codebase "contains" on its own. However, the project *does* have real, code-verifiable material to map onto that framework, currently unconnected to it:
  - **Legal**: two-factor patient identification citing UK GDPR (point 16); `patient_id`-only audit dashboard avoids unnecessary processing of identifiable data for an aggregate-oversight purpose (data minimisation).
  - **Social**: synthetic-only data throughout — no real patient data was ever used or exposed (Part 3G).
  - **Ethical**: mandatory pharmacist review for first prescriptions and all risk alerts (no fully-automated dispensing decision); RF/text models are explicitly non-authoritative so no ML system silently makes a clinical call.
  - **Professional**: full audit trail of who acknowledged/dispensed what and when (`acknowledgements`/`dispenses` tables), giving pharmacist accountability consistent with professional practice standards; the prototype login gate is explicitly and repeatedly labelled as *not* real access control, so it can't be mistaken for a genuine professional-accountability control.
- Code changes required: **None.**
- Dissertation-only: **Yes — write a short, explicit PSEL/LSEPI section** mapping the four bullet points above onto the framework headings your course uses. The raw material already exists in the code; it just isn't connected to the framework anywhere yet.

---

## Part 2 — Additional required checks

### A. Algorithm consistency

| Check | Result | Evidence |
|---|---|---|
| `classify_risk()` is genuinely the shared risk rule | **Confirmed** | One implementation, [`comparison_engine.py:151-181`](backend/comparison_engine.py#L151-L181), imported (not copied) by `backend/main.py` and `data/generate_synthetic_data.py`; imported alongside `is_narrow_therapeutic_index` by `data/real_synthea/adapt_real_synthea.py`. |
| Live `risk_final` comes from the deterministic rule | **Confirmed** | [`main.py:165-186`](backend/main.py#L165-L186): `rule_risk = classify_risk(...)`; `final_risk = rule_risk`; `alert["risk_final"] = final_risk`. |
| RF cannot override it | **Confirmed** | `rf_risk` is computed (line 150) and placed in `alert["risk_random_forest"]` only — it is never assigned to, compared against, or used to modify `final_risk`. `test_rule_primary_risk.py` proves this actively (not just by absence) using a `_FakeModel` that always predicts a fixed wrong value, confirming the fake prediction cannot leak into `risk_final`. |
| Text model cannot override it | **Confirmed** | Same structure — `text_risk` only populates `alert["risk_text_model"]`; same fake-model test covers this. |
| Offline synthetic and real-Synthea labelling use the same rule | **Confirmed** | Both `data/generate_synthetic_data.py:228-235` and `data/real_synthea/adapt_real_synthea.py:152-159` call the identical imported `classify_risk()` with keyword arguments — not reimplementations. |
| No remaining duplicated/contradictory risk rules | **One documented, deliberate exception** | `backend/risk_models/baseline_comparison.py:69-97`'s `deterministic_rule_predict()` is a *reimplementation* reading precomputed CSV columns, not an import — but its own docstring (lines 25-31) explicitly acknowledges this is a deliberate, isolated, third copy kept only for this standalone comparison script, which never writes to `train.csv`/`test.csv` and never touches `comparison_engine.py`. It is logically identical to the live rule (verified line-by-line: same branch order, same 0.25/0.50 thresholds) — not contradictory, just a second, walled-off copy for this one experiment. This was already flagged and accepted in ALGORITHM_AUDIT_2.md's centralisation audit; no new inconsistency found here. |

**Conclusion: the rule-primary architecture is real, not cosmetic.** The API response literally exposes `risk_rule`, `risk_random_forest`, `risk_text_model`, and `risk_final` as separate fields so this is independently checkable from outside the code (e.g. via a raw HTTP response), not just an internal implementation detail.

### B. Prescription change method — full trace

```
previous prescription  ─┐
                         ├─→ compare_prescriptions() [comparison_engine.py]
current prescription   ─┘         │
                                   ▼
                    ChangeReport (drug_changed, formulation_changed,
                    dose_changed, dose_change_pct, route_changed,
                    narrow_therapeutic_index, change_types, magnitude_summary)
                                   │
                    ┌──────────────┼───────────────────┐
                    ▼              ▼                    ▼
            classify_risk()   rf_model.predict()  text_model.predict(sentence)
            (rule_risk)          (rf_risk)              (text_risk)
                    │              │                    │
                    ▼              ▼                    ▼
             final_risk = rule_risk   (rf_risk, text_risk shown, non-authoritative)
                    │
                    ▼
        alert{risk_rule, risk_random_forest, risk_text_model, risk_final, ...}
                    │
                    ▼
        AlertPanel.jsx — pharmacist sees risk_final as the primary badge
                    │
                    ▼
        POST /api/acknowledge {patient_id, pharmacist_name, risk_level: risk_final}
                    │
                    ▼
        acknowledgements row written (ack_id, timestamp) ── dispense unlocks
                    │
                    ▼
        POST /api/dispense {patient_id, pharmacist_name, drug_name, dose_mg}
                    │  (looks up most recent ack_id for this patient_id — FK link)
                    ▼
        dispenses row written (ack_id FK → acknowledgements.ack_id)
                    │
                    ▼
        GET /api/audit/summary, GET /api/audit/activity — read both tables,
        patient_id only, never patient name
```

**Links checked and found sound:**
- The `dispenses.ack_id` foreign key means every dispense is traceably linked back to the specific acknowledgement that unlocked it — the chain is reconstructible from the database alone, satisfying point 5's accountability requirement.
- `risk_level` on `acknowledgements` has no `CHECK` constraint, which is *why* `FIRST_PRESCRIPTION_REVIEW` can be stored as a sentinel without a schema migration — deliberate, documented, and exercised by `test_first_prescription.py`/`test_audit_dashboard.py`.

**Weak points found (none broken, two worth naming explicitly):**
1. **Only the two most recent prescriptions are ever compared** (`prescriptions[-2], prescriptions[-1]` in `main.py:128`). If a patient has 3+ prescriptions, only the latest pair is diffed — any earlier-in-history change is invisible to the live comparison. This is the *correct* design for a dispensing safety check ("is what I'm about to hand over different from what was last given"), not a bug, but it should be stated as a deliberate scope boundary in the dissertation, since an examiner could otherwise read it as an oversight.
2. **RF and text predictions are computed per-request but never persisted anywhere.** There is no database column or table capturing what RF/text predicted historically. This means the Audit & Safety dashboard correctly cannot (and does not attempt to) show "rule vs. RF disagreement rate over time" — that data simply doesn't exist in storage. This is an honest limitation, already respected by the dashboard's design (it doesn't fabricate this), but it should be named explicitly under Evaluation Gaps (E) rather than left implicit.

**Overall: the chain from comparison through to audit trail is intact and traceable end-to-end. No broken link found.**

### C. Algorithm justification, using the actual measured results

| Model | Test accuracy | 5-fold CV mean | Real-Synthea |
|---|---|---|---|
| Deterministic rule | 100% | n/a (not a trained model) | 100%* |
| Logistic Regression | 96% | 95.56% | not run |
| Decision Tree (single) | 100% | 99.33% | not run |
| Random Forest | 100% | 99.56% | 100% |
| Text model (TF-IDF + LogReg) | 94% | not run | 30% |

*The rule is 100% on real-Synthea by construction — `risk_label` in `real_test.csv` is itself generated by calling `classify_risk()` (`adapt_real_synthea.py:152-159`), so "the rule matches the rule's own labels" is not an external validation result at all; only the *models'* real-Synthea numbers (RF 100%, text 30%) are genuinely informative, since the models never see the rule's logic directly, only its outputs as training labels.

**Circularity, stated precisely:** `risk_label` is a deterministic function of exactly six variables — `drug_changed, formulation_changed, dose_changed, dose_change_pct, route_changed, narrow_therapeutic_index`. Random Forest's feature set (`train_random_forest.py`'s `to_xy()`) is exactly those same six variables, one-to-one, with `dose_change_pct_abs` matching `abs(dose_change_pct)`. RF's 100% is therefore **rule-recovery, not clinical predictive validity** — RF was never asked to predict anything RF's inputs don't already determine exactly. The single Decision Tree matching RF exactly (100% vs 100%, CV 99.33% vs 99.56%) is the clearest empirical confirmation of this: a Decision Tree can *directly* encode the branching rule, so parity with RF is expected precisely because both are recovering the same fully-specified function, not because either discovered a pattern.

**Logistic Regression's underperformance (96% test, 95.56% CV) is the single most informative number in this table**, not a weakness to hide: it demonstrates the rule genuinely requires hard branching logic ("ignore dose once drug changed") that a linear/softmax decision boundary cannot represent without manual interaction terms. This is real, measured evidence — not an assertion — that tree-based methods structurally fit this problem and linear methods don't.

**The text model's 94%→30% real-Synthea drop is domain shift, not a broken model**: it's trained on a fixed 17-drug synthetic vocabulary with pure TF-IDF (no subword/semantic generalisation), so real Synthea drug names outside that vocabulary are functionally invisible to it. This is a genuine, defensible negative result for a methodology chapter — it demonstrates *why* a lightweight bag-of-words baseline generalises poorly, which is itself a finding.

**Do NOT describe any of the 100% figures as clinical validation** — none of them are. Both the synthetic test set and the real-Synthea test set have labels generated by your own rule, not by an independent clinician's judgement. The real-Synthea evaluation validates that the *models generalise to genuine drug/dose/route facts they weren't trained on* — a real and useful result — but it does not validate that the *rule itself* reflects real clinical risk, because nothing in this project's evaluation was ever checked against an independent ground truth. This exact distinction ("external data validation" vs "clinical validation") is already used correctly in `ALGORITHM_AUDIT_3.md` §12 and should carry through verbatim into the dissertation.

**Verdict: the algorithm choice is defensible, but the justification must rest on the branching-logic-fit argument (Logistic Regression's measured underperformance) and the label-circularity trace — never on the 100% figures themselves, which are the same number for three different reasons (rule, tree, forest) and prove structural fit, not correctness.**

### D. Technology justification

| Technology | Justification strength | Notes |
|---|---|---|
| Python | Strong | Standard for both ML (scikit-learn) and rapid API development; no justification gap. |
| FastAPI | Strong | Explicit REST contract, documented substitution for the plan's Spring Boot (network-restricted sandbox, stated honestly in `comparison_engine.py`'s docstring) — same JSON contract, so the substitution doesn't weaken the design. State the substitution reasoning explicitly in the dissertation rather than leaving it only in a code comment. |
| React | Strong | Standard, matches the plan; no gap. |
| SQLite | **Needs stronger justification** | Fine for a prototype, but the plan specified PostgreSQL. The substitution reason (no server needed for a demo) is reasonable but currently only stated in a stale README table — restate it explicitly and note the schema is portable (`schema.sql`'s own comment: "swap AUTOINCREMENT for SERIAL/IDENTITY if porting"). |
| scikit-learn | Strong | Correct tool for both the structured classifiers and TF-IDF+LogReg; no gap. |
| Random Forest | **Needs the circularity-aware justification from Part 2C**, not an accuracy-based one | See above — justify by structural fit + comparative baseline results, not the 100% figure. |
| TF-IDF + Logistic Regression | **Needs explicit justification for why not a real transformer** | Currently justified only as a network-access substitution in code comments/README (stale). State it plainly: a lightweight, fully-interpretable text baseline was chosen deliberately for comparison purposes, and the domain-shift result (94%→30%) is itself a finding that a heavier pretrained model might have obscured by generalising better — turn the constraint into an argued methodological choice, not just an admission of a blocked network route. |
| Deterministic rules | Strong, and this is now your primary technology | Justify via ALGORITHM_AUDIT_3.md's core argument: ML earns its place when the target function is unknown/noisy/too complex to specify — none of those hold here, so a transparent, exhaustively testable rule is the *more* defensible engineering choice for a safety-critical decision, not a less sophisticated fallback. |
| pytest | Strong | 56 tests across 6 files covering comparison logic, data integrity, first-prescription/zero-prescription edge cases, rule-primacy (actively, via a fake-model), two-factor lookup, and audit-dashboard correctness. No gap — but note the `httpx`/`TestClient` limitation (tests call endpoint functions directly rather than over real HTTP) as an honestly-stated scope limit if asked. |

**Technologies needing the most dissertation attention: SQLite (plan deviation) and TF-IDF+LogReg (needs reframing from "the transformer we couldn't get" to "a deliberate interpretable baseline").**

### E. Evaluation gaps

| Claim | Status | Basis |
|---|---|---|
| Deterministic rule matches its own definition | **MEASURED** | 100% by construction, confirmed in `baseline_comparison_results.json`. |
| Random Forest structurally fits the rule's branching logic | **MEASURED** | Logistic Regression's 96%/95.56% CV underperformance relative to RF/Tree's 100%/99.56% CV is direct, measured evidence. |
| Text model generalises worse than structured models on genuine data | **MEASURED** | 94% synthetic vs 30% real-Synthea, both computed by `evaluate.py`/`evaluate_real_synthea.py`. |
| The system correctly withholds automated risk classification on first/zero prescriptions | **DEMONSTRATED** | Verified by `test_first_prescription.py`; a working, testable behaviour, not just a design claim. |
| RF/text cannot override the rule | **DEMONSTRATED** | Actively proven via `test_rule_primary_risk.py`'s fake-model tests, not merely by code inspection. |
| Two-factor lookup rejects mismatched ID/DOB pairs | **DEMONSTRATED** | `test_lookup_two_factor.py`. |
| Trained models generalise to genuine (never-seen) drug/dose/route facts reasonably well (RF) | **DEMONSTRATED**, with caveat | Real-Synthea has no LOW/NONE examples at all (`real_test.csv` = 30 rows, all drug switches by chance) — this demonstrates generalisation only on the HIGH/MEDIUM boundary, not across all four classes. |
| Reduced pharmacist review time | **INFERRED, NOT PROVEN** | No timing instrumentation exists anywhere. Arguable mechanism (automated NONE-risk triage), zero measurement. |
| Reduced medication/prescription-change errors | **INFERRED, NOT PROVEN** | No error-rate data, no baseline to compare against, no deployment. |
| Clinical safety | **NOT PROVEN** | The rule's thresholds (e.g. 25%/50% dose-change cutoffs) are reasonable, stated design choices, not independently validated against clinician judgement or an incident dataset. |
| Clinical effectiveness | **NOT PROVEN** | Same reason — no independent outcome measure exists. |
| Generalisability | **PARTIALLY DEMONSTRATED, mostly NOT PROVEN** | Real-Synthea gives some genuine evidence (structured facts the model never trained on) but n=30, single-class-skewed, and one institution's synthetic generator (Synthea) — not evidence of generalising to real NHS prescribing patterns or a different population. |
| Real-world NHS deployment readiness | **NOT PROVEN, and not claimed** | No integration with a real EPS/PMR system, no real patient data, prototype-only auth (Part 3F), SQLite not a production database choice. This should be stated as explicitly out of scope, not as a shortfall. |

**The single most important discipline here for the viva: never let a MEASURED number (accuracy) get quoted as evidence for a NOT PROVEN claim (clinical safety/effectiveness) — that conflation is exactly what ALGORITHM_AUDIT_3.md was written to prevent, and it's the most common way a strong technical project loses marks on the evaluation chapter.**

### F. Security / PSEL

| Component | Prototype safeguard present | Production-grade equivalent (NOT present) |
|---|---|---|
| Patient ID + DOB lookup | Two independent identifiers required; single-identifier typos can't silently return the wrong patient | Real identity/role-based access control on *who* is allowed to look up *any* patient at all — currently anyone with network access to the API can query any patient given ID+DOB |
| Patient-identifiable data | Name shown only after a successful two-factor match; audit dashboard uses `patient_id`, never name | No encryption at rest, no field-level access logging beyond acknowledge/dispense events, no data-retention policy |
| Audit dashboard | Read-only, aggregate, `patient_id`-only by explicit design (`main.py:273-280`'s own comment states why it deliberately doesn't reuse the name-joining `activity_log` view) | No row-level access control — anyone who can log into the frontend gate sees every patient's audit data |
| Prototype audit login (`AuditLogin.jsx`) | Gates the dashboard *UI path*; explicit on-screen "prototype access control only" notice on both the login screen and the dashboard itself | **No server-side enforcement whatsoever.** Credentials are a plain JS constant (`auditDemoCredentials.js`), visible in the built bundle/dev tools; auth state is in-memory only (resets on refresh) |
| Open backend audit endpoints | None — this is the load-bearing limitation | `GET /api/audit/summary` and `GET /api/audit/activity` have **no authentication at all**. The frontend login gate does not, and cannot, protect these — anyone with the API's network address can call them directly (e.g. via curl) regardless of whether they ever see the login screen. **This is the single most important thing to state honestly if asked "is this secure?": the login gate is a UI demonstration of where access control belongs, not a functioning control.** |
| Audit logging | Every acknowledgement and dispense records pharmacist name + timestamp, immutably appended (no update/delete endpoint exists for either table) | No authentication of *who* the pharmacist actually is when submitting `pharmacist_name` — it's a free-text field, not tied to a login identity anywhere in the system (the review/dispense workflow and the audit-dashboard login are two entirely separate, unconnected mechanisms) |
| Pharmacist accountability | Structurally strong on paper (name + FK-linked ack→dispense chain) | Weak in practice because nothing verifies the submitted name matches an authenticated user — a real system would tie `pharmacist_name` to an authenticated session, not a free-text input |

**Clear line to hold in the dissertation and viva: this project demonstrates *where* access control, accountability, and data minimisation should sit in a system like this (patient ID+DOB, patient_id-only aggregate views, audit trail, a login gate placed in front of the sensitive dashboard) — it does not implement production-grade enforcement of any of them. Every prototype safeguard above is a correct architectural placement with no real backing mechanism yet.**

### G. Dataset

| Category | Source | Used for | Row count |
|---|---|---|---|
| Main synthetic dataset | `data/generate_synthetic_data.py`, seeded `random.seed(42)` | Training + test split | `patients.csv` = 600 patients; `train.csv` = 450 rows, `test.csv` = 150 rows (balanced 150/class before split: NONE/LOW/MEDIUM/HIGH via quota sampling) |
| Real Synthea | `data/real_synthea/medications_raw.csv` (genuine Synthea v3+ output) → `adapt_real_synthea.py` → `real_test.csv` | **External validation only**, never training | 30 real prescription-change pairs from 104 real Synthea patients |
| Demo fixture | `data/generate_demo_patient.py` (patient `demo0001`, "Arjun Mehta") | **UI demonstration only** — exactly one prescription, deliberately exercises the first-prescription workflow | 1 patient, structurally separate from `medications.csv`; `load_to_db.py` skips it gracefully if absent |

**Data leakage/circularity check:**
- **Train/test patient leakage**: none — `preprocess.py`'s split is asserted patient-disjoint by the test suite (per README's documented checks); not independently re-verified in this read-only pass since it wasn't asked, but the assertion exists in code and is exercised by `test_pipeline.py`.
- **Label circularity**: real and thoroughly traced (Part 2C) — not classic leakage (all six features are genuinely observable at prediction time), but the evaluation measures rule-recovery, not independent predictive skill, because labels were never independent of the features.
- **UUID non-determinism**: `patient_id` values use `uuid.uuid4()` (OS entropy), so `patients.csv` is not byte-for-byte reproducible run-to-run even with `random.seed(42)` — this was already root-caused in an earlier session as a pre-existing property, not a bug introduced by any refactor, and doesn't affect drug choices, doses, or risk labels (all deterministic).
- **Demo fixture isolation**: confirmed separate from the ML dataset by construction — `generate_demo_patient.py` is a standalone script producing its own row, never merged into `medications.csv`, so it cannot contaminate train/test splits.

**No leakage or circularity concern beyond the already-documented and now dissertation-relevant one (label circularity, Part 2C).**

---

## Part 3 — 10 hardest viva questions on the CURRENT version

**1. "Your Random Forest and Decision Tree both score 100% — doesn't that just mean your problem is too easy?"**
*Why asked:* tests whether you understand your own circularity finding or just recite the number.
*Strongest answer:* Yes, in a specific and provable sense — I traced exactly why: the label is a deterministic function of exactly the six features both models receive, so 100% is the expected, not surprising, outcome. That's not a flaw in the experiment; it's the actual finding — I built the experiment specifically to prove *why* accuracy alone can't justify using RF as a live decision-maker, which is why the rule, not RF, makes the live decision.
*Don't claim:* that 100% demonstrates the models "learned the clinical logic" — they recovered a known rule from its own defining inputs.

**2. "If the deterministic rule is doing all the real work, why is this a machine learning dissertation at all?"**
*Why asked:* probes whether you can defend ML's role once you've demoted it.
*Strongest answer:* The ML components answer a real comparative research question — how well do a structured-feature model and a free-text model each recover a known clinical rule from different amounts of information — and the free-text model's 94%→30% domain-shift result is a genuine empirical finding that required no rule at all to produce. The rule handles the live safety-critical decision because it's the more defensible engineering choice when ground truth is fully known; the ML work is the comparative and NLP-generalisation study sitting alongside it.
*Don't claim:* that ML was necessary for the system to work — it demonstrably wasn't, and claiming otherwise would contradict your own architecture.

**3. "Your text model drops from 94% to 30% on real data. Isn't that just a bad model?"**
*Why asked:* tests whether you can explain a negative result rather than being defensive about it.
*Strongest answer:* It's a domain-shift result, not a broken model — TF-IDF is pure bag-of-words over a fixed 17-drug synthetic vocabulary with zero subword generalisation, so real drug names outside that vocabulary are invisible to it by construction. That's an honest, informative limitation of a deliberately lightweight interpretable baseline, and demonstrating *why* it fails is more valuable methodologically than hiding it or picking a model that happens to generalise better for reasons I couldn't explain.
*Don't claim:* that a bigger pretrained model would definitely fix this without evidence — that's a plausible next step, not a demonstrated one.

**4. "Your real-Synthea test set is only 30 pairs, all of them drug switches. What does that actually prove?"**
*Why asked:* checks statistical honesty about small-n claims.
*Strongest answer:* It proves the models generalise reasonably (RF) or poorly (text) to genuine, never-trained-on drug/dose/route facts specifically on the HIGH/MEDIUM boundary — it says nothing about LOW/NONE generalisation, since none occurred in this sample by chance (real medication changes for an ongoing condition skew toward switches). I treat this as a narrow, honestly-scoped external validation, not a generalisability proof across all four risk classes.
*Don't claim:* a single accuracy percentage from n=30 as a confident population estimate without acknowledging the wide confidence interval that comes with that sample size.

**5. "How is this different from a system that would just show a pharmacist raw before/after values and let them decide?"**
*Why asked:* tests whether you can articulate value beyond "we automated it."
*Strongest answer:* The rule adds two things a raw diff doesn't: pharmacology-aware thresholds (NTI drugs get a stricter 25% vs 50% dose-change cutoff, which requires knowing which drugs are narrow-therapeutic-index — not something every reviewer will recall unaided under time pressure) and a consistent, auditable, always-applied standard rather than one that varies by which pharmacist is on shift. I don't claim it replaces clinical judgement — it's decision support, not decision-making, which is why every alert still requires explicit pharmacist acknowledgement before dispensing unlocks.
*Don't claim:* that this reduces errors or review time — that's argued, not measured (Part 2E).

**6. "Your audit login uses a hardcoded frontend password. Is this system secure?"**
*Why asked:* direct security probe, easy to over- or under-claim on.
*Strongest answer:* No, and I say so explicitly on both the login screen and the dashboard itself. It's a UI demonstration of *where* access control belongs architecturally, not a functioning control — the underlying `/api/audit/*` endpoints have no server-side authentication at all, so the login gate can be bypassed entirely by calling the API directly. A production version would need real server-side auth, role-based access control, and hashed credentials; none of that was in scope for this prototype.
*Don't claim:* that the login screen provides any actual protection, even as a stopgap.

**7. "Why SQLite instead of the PostgreSQL your project plan specified?"**
*Why asked:* checks whether plan deviations are justified or just convenient.
*Strongest answer:* A pragmatic prototyping choice — no server process needed for a demo, and the schema (`schema.sql`) is written in standard SQL specifically so it's portable (documented in-file: swap `AUTOINCREMENT` for `SERIAL`/`IDENTITY`). It doesn't materially change any of the risk-classification or comparison logic, which is entirely independent of the database layer.
*Don't claim:* that SQLite would be adequate for a real multi-pharmacist, concurrent-write production deployment — it wouldn't, and I'm not claiming this prototype is deployment-ready.

**8. "What happens if a patient has three or more prescriptions — do you compare all of them?"**
*Why asked:* tests whether you understand your own system's scope, not just its happy path.
*Strongest answer:* No — only the two most recent are compared (`prescriptions[-2]` vs `prescriptions[-1]`), which is the clinically relevant question for a dispensing check ("is what I'm about to hand over different from what was last given"), not a full historical audit. Earlier-in-history changes aren't re-surfaced by this comparison; that's a deliberate scope boundary, not an oversight.
*Don't claim:* that the system provides a full prescription-history risk analysis — it doesn't, by design.

**9. "Is any of this validated by an actual pharmacist or clinician?"**
*Why asked:* the most direct clinical-validity challenge available.
*Strongest answer:* No — every risk label in this project, synthetic and real-Synthea alike, is generated by my own rule, not by an independent clinician's judgement. I use "external data validation" (genuine drug/dose/route facts the models never trained on) and "clinical validation" (independent clinician-adjudicated correctness) as distinct terms throughout specifically to avoid conflating the two, because this project has evidence for the former and none for the latter.
*Don't claim:* clinical validation, clinical safety, or effectiveness, under any framing — this is the one line that must not be crossed anywhere in the dissertation.

**10. "You built two dashboards and a login gate — was any of this actually necessary, or feature creep?"**
*Why asked:* tests scope discipline and whether every addition maps to a stated requirement.
*Strongest answer:* Every addition traces to a specific supervisor-feedback point: the audit dashboard was suggested directly ("two different dashboards"), and it's deliberately minimal — read-only, no new database technology, patient-ID-only, showing only what's honestly derivable from stored acknowledgement/dispense data (explicitly excluding RF/text disagreement analytics, since those predictions are never persisted). The login gate was requested as a small, explicitly-scoped addition, and I built exactly what was asked — a prototype demonstration of where access control belongs, not a production auth system, which I state plainly rather than overclaiming.
*Don't claim:* that either addition was your own idea for "completeness" — tie both explicitly back to the feedback that prompted them.

---

## Part 4 — Final priority list

**CRITICAL — must fix before submission**
- *(Documentation, not code)* `README.md` and `PROJECT_STRUCTURE.md` describe an architecture that no longer exists: the old flat risk rule, "higher of two models" fusion (replaced by rule-primary), name+DOB lookup (now Patient ID+DOB), stale accuracy figures (93.3%/98.7%/96.7%/90.0% vs current 100%/94%/100%/30%), and no mention of the audit dashboard, login gate, first-prescription workflow, or `baseline_comparison.py`. If a supervisor or examiner reads these files as project documentation, they will get a materially wrong picture of the system you actually built — and the system you actually built is considerably stronger and more safety-conscious than what's described. **This needs a documentation pass, not a code change**, and should happen before submission since it's currently your project's largest single credibility risk.
- Never describe the 100% accuracy figures as clinical validation anywhere in the dissertation (Part 2C, 2E) — this is the one framing error that would undermine an otherwise strong project if it slipped through.

**HIGH — should fix**
- Write the PSEL/LSEPI section explicitly (point 18) — the raw material exists in the code (two-factor ID, patient_id-only audit views, mandatory review gates, audit trail, honestly-labelled prototype auth) but is currently unconnected to the framework anywhere.
- Write the literature-review/existing-approaches comparison (point 3) — currently entirely absent.
- State the "review time / error reduction" claims (points 10, 11) as argued/inferred, explicitly labelled as such, never as measured results.

**MEDIUM — dissertation/evaluation explanation needed**
- Reframe the TF-IDF+LogReg choice as a deliberate interpretable baseline, not just "the transformer we couldn't reach" (Part 3D).
- Explicitly justify SQLite as a documented, portable-schema plan deviation (Part 3D).
- Present the under/over-risked evaluation criteria prominently as your clinically-meaningful metric (point 6).
- Write up the audit-and-revise process (finding circularity → rule-primary change) as methodology, not just a code history (point 12).
- State the two Part 2B "weak points" (latest-pair-only comparison, RF/text predictions not persisted) as deliberate scope boundaries.

**LOW — optional improvement**
- A confidence interval on the real-Synthea n=30 accuracy (already recommended in ALGORITHM_AUDIT_3.md §10, still not done — arithmetic only, no code risk, but not required to defend the current results).

**DO NOT CHANGE — working components, now frozen**
- `backend/comparison_engine.py` — `classify_risk()`, `compare_prescriptions()`, `is_narrow_therapeutic_index()`.
- `backend/main.py`'s rule-primary wiring (`risk_rule`/`risk_random_forest`/`risk_text_model`/`risk_final`).
- `data/generate_synthetic_data.py` and `data/real_synthea/adapt_real_synthea.py`'s shared-rule imports.
- The first-prescription and zero-prescription workflows.
- Patient ID + DOB two-factor lookup.
- The Audit & Safety dashboard's endpoints and scope (deliberately excluding non-derivable RF/text disagreement stats).
- The prototype login gate, exactly as scoped (frontend-only, explicitly labelled, in-memory).
- `rf_model.joblib`, `text_model.joblib`, `evaluation_summary.json`, `baseline_comparison_results.json` — do not retrain or regenerate; all current dissertation figures trace to these exact files.
- The 56-test suite.

---

## Bottom line: are further CODE changes necessary?

**No.** Every one of the 18 supervisor-feedback points that has a code-shaped answer already has one, correctly implemented and test-covered. The only point with a genuine gap is #18 (PSEL/LSEPI), and that gap is a writing task, not a code task — there's nothing to build. The two CRITICAL items above (README/PROJECT_STRUCTURE staleness, and never overclaiming the 100% figures) are a documentation-accuracy fix and a writing-discipline rule, not new features. Building anything further — a real transformer, real auth, real barcode integration, a timed user study — would be scope creep relative to what this feedback actually asks for, not a requirement of it. The system as it stands is a defensible MSc prototype; the remaining work is entirely about accurately describing and honestly framing what's already been built.
