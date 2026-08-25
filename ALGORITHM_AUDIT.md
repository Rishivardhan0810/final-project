# Technical Audit: Prescription-Change Detection & Risk Classification

Read-only inspection. No code was modified, created, deleted, or reformatted while producing this report.

---

## 1. Prescription Comparison — how each signal is detected

All of this happens in one place: `backend/comparison_engine.py`, function `compare_prescriptions(patient_id, previous, current)`. Both arguments are `Prescription` objects (`drug_name, dose_mg, formulation, manufacturer, route, start_date, prescriber`).

| Signal | Exact logic | Notes |
|---|---|---|
| **Drug change** | `drug_changed = previous.drug_name != current.drug_name` | Plain string inequality on the active-ingredient name. |
| **Dose change** | `dose_changed = previous.dose_mg != current.dose_mg` | Plain float inequality. |
| **Dose % change** | `dose_change_pct = (previous.dose_mg - current.dose_mg) / previous.dose_mg` (0.0 if previous dose is 0) | Positive = reduced, negative = increased. Rounded to 4 dp. |
| **Formulation change** | `formulation_changed = (not drug_changed) and (previous.formulation != current.formulation)` | **Deliberately gated on `not drug_changed`** — if the drug itself changed, a formulation difference is not separately flagged. This is a real design decision, not an oversight (see §2). |
| **Route change** | `route_changed = previous.route != current.route` | Plain string inequality. |
| **Manufacturer change** | `manufacturer_changed = previous.manufacturer != current.manufacturer` | Computed and returned in the API response, but **excluded** from `change_types` (the list that decides whether an alert fires) and excluded from every ML feature set. |
| **NTI involvement** | `narrow_therapeutic_index = previous.drug_name in NTI_DRUGS or current.drug_name in NTI_DRUGS` | `NTI_DRUGS` is a hardcoded, case-sensitive **exact-match set** of 6 strings: `{"Warfarin", "Apixaban", "Digoxin", "Levothyroxine", "Insulin Glargine", "Lithium"}`, defined at the top of `comparison_engine.py`. |

**A precise finding, not covered elsewhere in the code's own comments:** the NTI check here is exact-string-membership. A real EPS feed that ever produced `"warfarin"` (lowercase), `"Warfarin 5mg tablets"`, or any other variant would silently **fail to match** and be treated as non-NTI. Contrast this with `data/real_synthea/adapt_real_synthea.py`, which does the same job with a **different, fuzzy algorithm** (`is_narrow_therapeutic_index`, substring match, case-insensitive) — see §7 for why this matters.

`change_types` (the list `["drug","dose","frequency"... ]` no — actually `["drug","formulation","dose","route"]`, manufacturer excluded) is what `main.py` checks to decide whether to run risk scoring at all (`if report.change_types:`). If nothing changed, `alert` is `None` and nothing downstream runs.

---

## 2. Risk Algorithm — how NONE/LOW/MEDIUM/HIGH are assigned

**Important architectural fact, stated plainly because it affects how §4 and §7 should be read: `comparison_engine.py` does NOT assign a risk label.** It only computes the diff (`drug_changed`, `dose_changed`, etc.) and the NTI flag. The actual NONE/LOW/MEDIUM/HIGH decision the pharmacist sees is produced entirely by the two trained ML models at request time (§6). The deterministic rule below exists **only** to generate training labels offline — it is never executed by the running server.

The rule itself lives in two places (`data/generate_synthetic_data.py`, inline in `make_prescription_pair()`, and `data/real_synthea/adapt_real_synthea.py`'s `risk_label_for()`). Both are currently identical:

```
IF nothing changed (drug, formulation, dose, route all unchanged):
    NONE
ELIF drug changed:
    HIGH if NTI else MEDIUM
ELIF formulation changed:
    HIGH if NTI else MEDIUM
ELIF dose changed:
    threshold = 0.25 if NTI else 0.50
    HIGH if |dose_change_pct| >= threshold
    ELSE: MEDIUM if NTI else LOW
ELIF route changed:
    LOW
ELSE:
    NONE
```

### Internal consistency check

- **Priority order is a strict `elif` chain, not an additive score.** If a drug switch also happens to change the dose (common in the generator — see §4/§9), the dose percentage is *ignored entirely*; the drug-switch branch decides. This is clinically defensible (two different drugs' mg values aren't comparable anyway) but means simultaneous changes never compound risk — the system always scores on the single highest-priority signal, never "more things changed = more risk."
- **Uneven tier reachability.** For non-NTI drugs, the dose-change branch can only ever produce LOW or HIGH — there is **no path to MEDIUM via a pure dose change on a non-NTI drug**. A 4% dose increase and a 49% dose increase both score LOW; the very next percentage point jumps straight to HIGH. For NTI drugs, dose changes can only produce MEDIUM or HIGH — never LOW. This is a real coarseness in the rule's gradation, not a bug, but worth being able to answer if asked "why is a 45% dose change on Metformin scored the same as a 5% one?"

---

## 3. Rule-Based vs. Random Forest vs. Text/NLP — what each actually contributes

| Layer | Where | What it does |
|---|---|---|
| **Deterministic rule** | `generate_synthetic_data.py`, `adapt_real_synthea.py` | Defines the *ground-truth label* for every training/evaluation row. **Never runs inside the live server.** |
| **Random Forest** | `backend/risk_models/train_random_forest.py` | Trained on exactly 6 structured features: `drug_changed, formulation_changed, dose_changed, dose_change_pct_abs, route_changed, narrow_therapeutic_index`. This is the live structured-feature classifier `main.py` calls on every request. |
| **Text/NLP model** | `backend/risk_models/train_text_classifier.py` | TF-IDF (1–2 grams) + Logistic Regression, trained on the plain-English sentence `comparison_engine.natural_language_description()` builds. **Critically, that sentence never states NTI status explicitly** — no "narrow therapeutic index" phrase appears anywhere in it. The model must infer NTI-relevant risk purely from drug-name tokens (e.g. learning that "Warfarin" and "Digoxin" co-occur with HIGH labels), which is a genuinely harder, more realistic task than the Random Forest's. |

`main.py` combines the two model outputs with a simple, non-learned rule (§6) — it is not itself a third model, just a decision on top of the other two.

---

## 4. Random Forest — is 100% accuracy genuine learning?

**Short answer: no, and the code already partially says so.** `evaluate.py` prints, verbatim, at the end of every run:

> "Random Forest hits 100% here because it's given narrow_therapeutic_index directly as an input feature -- the risk_label rule branches on that exact flag, so RF can shortcut straight to the rule rather than learning anything transferable."

That self-awareness is a genuine strength of the project as it stands — but it needs to be stated explicitly in the dissertation itself, not just discoverable by reading `evaluate.py`'s console output.

### Precise mechanism (why 100% was inevitable, not impressive)

The ground-truth label is a **deterministic, noiseless function of exactly six variables**: `drug_changed, formulation_changed, dose_changed, dose_change_pct, route_changed, narrow_therapeutic_index`. The Random Forest is handed **exactly those same six variables, unmodified, with no noise and no proxy transformation**, as its entire feature set. There is no missing information, no measurement noise, and no indirection between "what the model sees" and "what generated the label."

This is best described precisely as: **the features are not observations correlated with the label — they are literally the arguments to the function that computes the label.** Given that a Random Forest (an ensemble of decision trees) can represent arbitrary branching/threshold logic, and the training data by construction covers the branching structure (the generator quota-samples across every change type), near-perfect accuracy is the *expected*, unsurprising outcome — not evidence of generalizable clinical intelligence.

- **Is this "feature leakage" in the classic sense (using information unavailable at prediction time)?** No — all six features genuinely are observable at the moment a pharmacist compares two prescriptions in the real system. Using them is not illegitimate.
- **Is it "target leakage" / circular evaluation?** Yes, precisely: because the *labels themselves* were generated by running a rule over these exact features (rather than being independent clinical ground truth — e.g. real pharmacists' risk judgements), evaluating the model on held-out data only tests "can the model recover the function that generated its own training labels," not "does the model predict genuine clinical risk."
- **Overfitting?** Not the right lens here. The model isn't fitting noise; it's correctly fitting a noiseless deterministic function. `max_depth=8` comfortably exceeds the ~4-level nesting of the actual rule, so depth isn't acting as meaningful regularisation against this issue.
- **Does the "external" real-Synthea validation escape this?** **No — and this is the least obvious but most important finding in this section.** `adapt_real_synthea.py` computes `narrow_therapeutic_index` and `risk_label` for the real-data test set using the **same hand-duplicated rule** (§7), not genuine clinical adjudication of the real records. So the 100% Random Forest accuracy reported by `evaluate_real_synthea.py` on "real" data is *equally circular* — it demonstrates the rule generalises across two differently-sourced feature samples, not that the model predicts real clinical risk. This distinction is subtle enough that it is worth stating explicitly if a supervisor asks "but doesn't the real-data validation prove it's not just leakage?"
- **Unrealistic synthetic patterns:** the generator applies exactly one deliberate mutation type per pair (`dose_increase` XOR `drug_switch` XOR `formulation_switch` XOR ... — see the `change_type` weighted choice in `make_prescription_pair()`), though a `drug_switch` frequently *incidentally* also changes dose/route/formulation as a side effect of the new drug having its own dose/route/formulation options. Deliberately-simultaneous multi-dimensional changes (e.g. a real-world switch that changes drug, route, *and* dose at once, on purpose) are under-represented as a distinct category.

**Conclusion:** Random Forest is an architecturally reasonable model family for this feature shape (mixed boolean/continuous, tree-like branching structure). The 100% figure is not evidence of "genuine learning" — it is the expected result of a classifier reproducing a deterministic function from its own exact input variables, on both the synthetic test set and the nominally-external real-data set. This is a dissertation-framing issue (§10, category C), not a code defect.

---

## 5. NLP / Text Model — TF-IDF + Logistic Regression

**Is the algorithm choice appropriate as a lightweight baseline?** Yes. TF-IDF + Logistic Regression is a standard, well-justified, low-dependency stand-in for a heavier pretrained model, explicitly documented as necessary because this sandbox has no route to huggingface.co for a real ClinicalBERT. This is a defensible, conventional choice for a baseline, not a weak one.

### Why 94% (synthetic) drops to 30% (real, n=30)

This is genuine domain shift, **compounded by several concrete, code-level factors** worth naming individually rather than attributing the whole gap to "the model is bad":

1. **Vocabulary mismatch.** Training sentences are built from a fixed, 17-drug synthetic vocabulary (`Warfarin`, `Digoxin`, ...). Real drug names come from `extract_drug_name()` regex-parsing free-text Synthea descriptions and lower-casing them — genuinely different tokens the TF-IDF vectorizer never saw during fitting (the earlier version of the ClinicalBERT export script noted real names like "leucovorin, fosfomycin, lisinopril" are completely absent from the training vocabulary — a concrete, quotable example).
2. **Class-distribution mismatch, not just size.** The synthetic test set is perfectly balanced (~37–38 examples per class, 4 classes). The real validation set is `{'MEDIUM': 27, 'HIGH': 3}` — **zero NONE or LOW examples, and only the hardest decision boundary (MEDIUM vs HIGH) is being tested.** Comparing 94% (easy 4-class balanced) against 30% (hard 2-class, most-confusable-pair-only) is not a fully like-for-like comparison — some of the apparent drop reflects the *shape* of the evaluation set, not purely degraded model quality.
3. **Small sample size.** n=30 means a single flipped prediction moves accuracy by >3 points; the 30% figure has wide statistical uncertainty.
4. **Missing/placeholder fields.** Real data has no `manufacturer` or `concurrent_medications`; `evaluate_real_synthea.py`'s `build_sentence()` passes `"not recorded"` for manufacturer/allergy — a token string that **never appears in any training sentence**, and the "also currently taking..." clause never appears at all for real pairs. This changes the surface shape of real sentences beyond just vocabulary.

**Does text construction/preprocessing contribute to the problem?** Yes, materially — points 2 and 4 above are evaluation-construction artifacts, not fundamental model weaknesses, and are worth separating from genuine vocabulary domain-shift (point 1) when writing this up.

**Is this a genuine generalisation problem?** Yes, and expectedly so — TF-IDF is a pure bag-of-words method with zero subword or semantic generalisation; it cannot recognise an unseen drug name is "like" a seen one. This is precisely the argument for the `clinicalbert-addon/` future-work path already present in the repo: a real pretrained model uses subword tokenisation and medical-domain pretraining, so it could plausibly generalise to unseen drug names in a way TF-IDF structurally cannot. No model change was made here, per your instruction — this is presented as an explanation, not a recommendation to act on now.

---

## 6. Final Alert Decision

In `backend/main.py`:

```python
order = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
final_risk = max([rf_risk, text_risk], key=lambda r: order.get(r, 0))
```

A simple, non-learned rule: whichever of the two models' outputs is more severe wins. This only executes when `report.change_types` is non-empty (i.e. only on prescriptions that structurally changed at all).

### Is this technically and clinically defensible?

**In principle, yes** — "fail-safe toward the more cautious of two opinions" is a standard, well-accepted precautionary design pattern in medication-safety systems; false positives (unnecessary alerts) are conventionally treated as far less harmful than false negatives (missed genuine risk).

**In practice, on the evidence gathered in this repository, it has a demonstrable downside.** `evaluate_real_synthea.py`'s own confusion matrix for the text model on real data is:

```
              predicted HIGH   predicted MEDIUM
true HIGH          3               0
true MEDIUM       21               6
```

The text model wrongly predicted HIGH for 21 of 27 genuinely-MEDIUM real cases. The Random Forest got all 27 of those correct. Because `final_risk = max(rf, text)`, **every one of those 21 cases displays as HIGH to the pharmacist — the weaker model's error overrides the stronger model's correct answer, every time, by construction.** This is not a hypothetical concern; it is directly evidenced in this repository's own real-data evaluation output.

This is a legitimate, citable finding: the max-based ensemble can only ever push the displayed risk *up* relative to either individual model, meaning any weakness in either model manifests as system-wide over-alerting, never under-alerting — which sounds safe in the abstract, but has a real, named cost in the clinical-alerting literature (**alert fatigue**: pharmacists become desensitised to alerts that are frequently over-cautious, potentially reducing attentiveness to genuine HIGH-risk cases). This is worth discussing candidly as a design trade-off rather than an unqualified strength.

---

## 7. Duplicated or Contradictory Logic

Four concrete instances found by direct inspection:

| # | What's duplicated | Locations | Currently consistent? |
|---|---|---|---|
| 1 | The risk-classification rule itself | `generate_synthetic_data.py` (inline in `make_prescription_pair`) and `adapt_real_synthea.py` (`risk_label_for()`) | Yes, currently identical — but two independently hand-maintained copies with no shared source. |
| 2 | The NTI drug list | `comparison_engine.py`'s `NTI_DRUGS` set, and `generate_synthetic_data.py`'s per-drug `"nti": True/False` field in its own `DRUGS` list | Yes, currently the same 6 drugs in both — `generate_synthetic_data.py` deliberately avoids importing `backend/` code (documented, to remain a standalone Synthea-replaceable script), so this may be an *intentional* trade-off rather than an oversight. |
| 3 | **NTI matching algorithm** | `comparison_engine.py` uses **exact set membership**; `adapt_real_synthea.py`'s `is_narrow_therapeutic_index()` uses **fuzzy substring matching** on the *same* imported `NTI_DRUGS` set | **This is a genuine inconsistency, not just duplication** — two different comparison algorithms applied to nominally the same reference data. See §1. |
| 4 | — | Checked and **not** found duplicated: `main.py` does not reimplement the rule (it only calls `comparison_engine.py` + the two trained models); the frontend (`AlertPanel.jsx`'s `RISK_COPY`) is a pure static display lookup with no computation; the training/preprocessing scripts consume `risk_label` as-is and never recompute it. | | Clean — no issue found here. |

Items 1–2 are DRY violations with no current contradiction (category D/A-adjacent, low urgency). Item 3 is the one concrete, evidence-based inconsistency worth flagging as an actual code issue.

---

## 8. Alternative Algorithms — what else could have been used, and would it help?

Given §4's finding that the label is an exact deterministic function of the features provided, **the specific classifier choice matters less than that fact** — almost any sufficiently expressive supervised model would reach ~100% under this setup. Assessed individually:

- **Logistic Regression** — would likely **not** reach 100%, because the true rule has hard branching (e.g. "ignore dose entirely if the drug changed") that a linear decision boundary can't represent without explicit interaction terms. Ironically, this makes plain Logistic Regression a *more instructive* choice for a dissertation than Random Forest: its imperfection would make the leakage/circularity issue visible rather than masked by a perfect score.
- **Decision Tree (single, unensembled)** — would almost certainly also reach ~100%, and arguably more transparently than Random Forest: a single tree of sufficient depth can directly encode the nested if/elif rule, and the resulting tree structure could be printed and compared side-by-side against the hand-written rule as a literal demonstration of "the model learned to invert the label function." This would have been a stronger choice than Random Forest specifically for illustrating the rule-recovery finding.
- **Random Forest (current choice)** — reasonable, general-purpose, handles the mixed feature types well, and its `feature_importances_` output is used constructively in `evaluate.py`. Its main strength (ensemble robustness against noisy/overfit signal) is largely moot when the target function is exactly deterministic and noiseless.
- **Gradient Boosting / XGBoost** — would very likely also reach ~100% for the same structural reason. Would add real complexity (more hyperparameters, less interpretability, longer training/dependency footprint) without addressing or illuminating the actual limitation. Not justified here — this is the kind of complexity the brief asked to flag as unnecessary.
- **SVM** — a weaker natural fit for a largely boolean/categorical feature space; would need deliberate kernel engineering to represent the same threshold structure, and offers no native interpretability advantage over tree-based methods. Not clearly justified for this problem shape.
- **Pure rule-based system (run the deterministic rule directly at inference time, skip training a model)** — a legitimate alternative worth naming candidly: since the label already *is* a hand-written rule, and that rule already exists in code (§2), one honest architectural option would be to simply execute it live instead of training Random Forest to reverse-engineer it. This would be 100% faithful, fully transparent, and instantly auditable — at the cost of removing the "compare a structured-feature model against a free-text model" comparison that appears to be an explicit part of this dissertation's research question (RF vs. TF-IDF+LogReg as two different *modelling paradigms* applied to the same underlying problem). If that comparison is the actual research question, training both models — rather than just running the rule — is the right call; it's worth being explicit in the write-up about *why* an ML approach was chosen over simply running the rule directly.
- **NLP alternatives (Word2Vec/GloVe + classifier, or a real pretrained transformer like ClinicalBERT/BioBERT)** — TF-IDF is appropriate as a dependency-light baseline under the sandbox's no-internet constraint. A pretrained transformer remains the most promising direction specifically for closing the real-data generalisation gap in §5, because subword tokenisation and medical pretraining could partially recognise unseen drug names in a way TF-IDF structurally cannot. This is exactly the rationale already documented in `clinicalbert-addon/`.

---

## 9. Technology Stack Suitability

| Technology | Verdict | Reasoning |
|---|---|---|
| Python | Appropriate | Standard for both the ML/data tooling and the API layer. |
| FastAPI | Appropriate | Lightweight, modern, automatic interactive docs (`/docs`), well-documented substitution for the originally-planned Spring Boot given the sandbox's lack of Maven Central access — the REST contract is preserved, so the substitution doesn't compromise the architecture. |
| React / Vite | Appropriate | Standard modern SPA stack, proportionate to the app's actual complexity (3 screens, simple local state) — no under- or over-engineering. |
| SQLite | Appropriate for a prototype, **not for production** | Zero-setup, file-based, schema written as portable standard SQL (documented as swappable to PostgreSQL). Already explicitly documented in the README as a prototype substitution. Would need replacing before any real multi-pharmacist concurrent-write deployment, due to SQLite's writer-locking model — but that's a known, already-acknowledged limitation, not a new finding. |
| scikit-learn | Appropriate | Conventional, well-documented, correctly scoped for this size of structured-data ML and TF-IDF+LogReg pipeline. |
| pytest | Appropriate | Sensibly used — 17 tests covering both comparison-engine unit correctness and dataset-level integrity/leakage checks. |

No technology substitution is warranted anywhere in this stack.

---

## 10. Required Changes

**A** = genuine algorithm/code problem · **B** = evaluation limitation · **C** = dissertation/explanation problem · **D** = optional improvement

| Issue | Severity | File(s) affected | Code change required? | Category | Why | Recommended action |
|---|---|---|---|---|---|---|
| NTI matching uses two different algorithms (exact-match vs. fuzzy substring) on nominally the same reference list | **MEDIUM** | `backend/comparison_engine.py`, `data/real_synthea/adapt_real_synthea.py` | Yes | A | Same drug name could be classified NTI in one code path and not the other for real-world name variants | Unify to one shared matching function, imported by both |
| Risk-classification rule hand-duplicated in two files | **MEDIUM** | `data/generate_synthetic_data.py`, `data/real_synthea/adapt_real_synthea.py` | Yes | A/D | Currently consistent, but no shared source — silent drift risk if either is edited alone | Extract to one shared function |
| NTI drug list hand-duplicated | **LOW** | `data/generate_synthetic_data.py`, `backend/comparison_engine.py` | Optional | D | Currently consistent; likely an intentional trade-off (generator stays import-free from `backend/`) | Document the trade-off explicitly if keeping it duplicated |
| The deterministic rule never runs at live inference time — the deployed system relies entirely on trained models to approximate it | **MEDIUM–HIGH** (for the defense) | N/A (architectural fact) | No | C | Could be misunderstood by a reader/supervisor as "the app is rule-based" when only *label generation* is rule-based | State explicitly in the dissertation: rule defines training labels; deployed system uses trained approximations |
| Random Forest's 100% accuracy reflects exact feature/label circularity, not generalisable learning — and this holds for the "external" real-Synthea evaluation too, since its labels are also rule-derived | **HIGH** (for the defense) | `backend/risk_models/train_random_forest.py`, `data/generate_synthetic_data.py`, `data/real_synthea/adapt_real_synthea.py` | No | C/B | A supervisor who explicitly said the algorithm would be checked will very plausibly ask "why 100%?" | State the circularity explicitly (code partially already does, via `evaluate.py`'s printed note) — carry that acknowledgment into the written dissertation |
| Text model's 94%→30% drop is real domain shift, compounded by an unbalanced/2-class-only real test set and n=30 sample size | **LOW–MEDIUM** | `data/real_synthea/adapt_real_synthea.py`, `backend/risk_models/evaluate_real_synthea.py` | No | B | Comparing 4-class-balanced accuracy against 2-class-only accuracy isn't fully like-for-like | Explain both contributing factors (vocabulary shift *and* evaluation-set shape) separately when reporting this result |
| `max(rf, text)` final-risk rule provably amplifies the weaker model's errors on real data (21/27 real MEDIUM cases shown as HIGH) | **MEDIUM** | `backend/main.py` | Optional | A/D | Defensible fail-safe design in principle, but has a demonstrated, evidenced over-alerting cost | Discuss candidly as a trade-off (alert fatigue); optionally consider confidence-weighting or flagging model *disagreement* itself, as future work |
| Non-NTI dose changes can only reach LOW or HIGH — no MEDIUM path via dose alone | **LOW** | `data/generate_synthetic_data.py`, `data/real_synthea/adapt_real_synthea.py` | Optional | D | Coarse but not incorrect gradation | Optional: add an intermediate percentage band |
| Synthetic generator applies one deliberate mutation type per pair, under-representing intentionally-simultaneous multi-dimensional real-world changes | **LOW** | `data/generate_synthetic_data.py` | No | B | Narrows training/eval diversity somewhat | Optional future data-generation enhancement |
| Technology stack (Python/FastAPI/React-Vite/SQLite/scikit-learn/pytest) | **NO CHANGE REQUIRED** | N/A | No | — | All choices are proportionate and well-justified for this scope | SQLite→PostgreSQL only if/when moving toward real production use (already documented) |

---

## Bottom line

The comparison logic (§1) is correct, well-factored into a single shared engine, and the deliberate `formulation_changed`/`drug_changed` interaction is a genuine design decision, not a bug. The risk *rule* (§2) is internally consistent in its priority ordering, if coarse in places. The two-model architecture (§3) is a legitimate comparative design. The single most important thing to be able to defend clearly to a supervisor is **§4 and §10's central finding**: near-perfect accuracy here is expected given how the labels were constructed, not evidence of strong generalisable prediction — and the project's own `evaluate.py` output already says as much. The one genuine, evidence-based **code** inconsistency worth fixing is the NTI matching-algorithm mismatch (§7, item 3); everything else is either a defensible design trade-off (§6's max-rule), a duplication-but-not-contradiction (§7, items 1–2), or a framing point for the write-up rather than the code (§4, §5).
