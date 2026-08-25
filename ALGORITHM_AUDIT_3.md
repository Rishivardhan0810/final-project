# Technical Audit 3: Algorithm Suitability

Read-only inspection. No code was modified, retrained, or run in a way that produces new results while writing this report. Every accuracy figure below is either quoted from your message or was already verified and printed by the project's own scripts in earlier sessions — none is invented here. Where a claim is a recommendation rather than something the code proves, it is labelled as such.

---

## 1. What exact problem is each algorithm solving?

These are two genuinely different problems, solved by different code, and conflating them is the single most common way this project could be mis-described in a viva.

**A) Prescription-change detection** — `backend/comparison_engine.py`, `compare_prescriptions()`. Not a learned algorithm at all: a pure, deterministic function that takes two `Prescription` objects and computes boolean/numeric facts by direct comparison — `drug_changed = previous.drug_name != current.drug_name`, `dose_change_pct = (previous.dose_mg - current.dose_mg) / previous.dose_mg`, and so on. This step has no accuracy figure because it isn't a classifier — it's arithmetic and string comparison. Its only "intelligence" is the NTI lookup (`is_narrow_therapeutic_index()`), which is itself a deterministic set-membership check, not a model.

**B) Risk classification** — turning the facts from (A) into NONE/LOW/MEDIUM/HIGH. This is where machine learning actually appears: `backend/risk_models/train_random_forest.py` and `train_text_classifier.py`. Random Forest is currently the live decision-maker (`backend/main.py`: `final_risk = rf_risk`); the text model's output is computed and returned but does not influence `final_risk`.

A clean way to state this in a viva: **(A) is 100% rule-based and always will be — there is nothing to learn, because "did the dose number change" is not a pattern, it's a fact. (B) is where the ML/algorithm-choice question actually lives.**

---

## 2. Is Random Forest technically justified for risk classification in THIS project?

**Not simply because accuracy is high — and the accuracy figure specifically should not be used as the justification at all.** The technical justification has to rest on other grounds, examined here honestly:

- **Justified, on structural grounds:** Random Forest (an ensemble of decision trees) naturally represents branching/threshold logic — exactly the shape of the rule that generates the labels (§5). This is a legitimate reason to expect RF to fit this problem *well*, independent of the accuracy number.
- **Not justified, on necessity grounds:** the rule RF is approximating is fully known, deterministic, and already implemented in code (`data/generate_synthetic_data.py`). Machine learning earns its place when the target function is unknown, noisy, or too complex to specify by hand. None of those conditions hold here. RF is solving a problem that a direct function call already solves exactly.
- **The honest position:** RF is a *reasonable* choice for the comparative research question this project asks ("how well can a structured-feature model recover a known clinical rule, versus a free-text model given less information?") but is **not, on its own, evidence that machine learning was the *necessary* or even the *safest* choice for the live decision-making role it currently holds.** §6 makes this distinction actionable.

---

## 3. Random Forest vs. seven alternatives

| Approach | Suitability for this problem | Interpretability | Data required | Clinical-safety implication | Computational cost | Explainability to a pharmacist | Expected benefit / disadvantage here |
|---|---|---|---|---|---|---|---|
| **Deterministic rule** (already implemented, offline only — §5) | Excellent — the label *is* this rule | Maximal — every branch is plain-English readable | None | Strongest: zero approximation error, exhaustively testable (small finite input space) | Negligible | Strongest — can cite the exact branch that fired | No training cost, perfectly faithful; doesn't itself demonstrate ML capability |
| **Random Forest** (current primary) | Good structural fit (tree ensemble matches branching rule) | Moderate — feature importances, not individual rules | ~450 rows, already have it | Reproduces the rule near-perfectly *on data shaped like its training set*; no guarantee off that shape | Low | Moderate — importances communicate *what mattered*, not *the exact threshold* | Matches the rule well; adds ensemble complexity the rule itself doesn't need |
| **Logistic Regression** | Weak — can't represent hard branching (e.g. "ignore dose once drug changed") without manual interaction terms | High — coefficients are directly readable | Low | Would likely under-perform, which is informative, not a flaw | Very low | Good, if it worked well | **Valuable as a baseline specifically because it would likely score lower** — direct evidence the rule needs branching logic, strengthening the case for tree-based methods empirically rather than by assertion |
| **Decision Tree (single)** | Excellent — can encode the exact rule directly, more transparently than an ensemble | High — the fitted tree can be printed and compared line-by-line against the hand-written rule | Low | Strong — auditable, and any errors are traceable to one exact split | Very low | Strong — a printed tree is close to a flowchart | Arguably **more honest than RF** for demonstrating rule-recovery, since the mechanism is directly inspectable |
| **Gradient Boosting / XGBoost** | Good fit, same reason as RF | Low-moderate | Low-moderate | No advantage over RF for a deterministic, already-covered label space | Higher (more hyperparameters, longer training) | Weaker than RF (harder to summarise many boosted stumps) | **Not justified** — adds real complexity with no offsetting benefit on this dataset |
| **SVM** | Weak natural fit — largely boolean/categorical features suit trees better than margin-based methods | Low without extra tooling | Low-moderate | No native feature-importance output | Moderate (kernel choice, scaling) | Weak | **Not justified** — no structural advantage, added tuning burden |
| **Simple neural network (small MLP)** | Poor fit for this scale — can represent thresholds but needs more parameters/data to do so cleanly than a tree does | Very low without SHAP/LIME | Higher (thresholds are learned less sample-efficiently by gradient descent than by tree splits) | Weakest of the compared methods here — opaque, harder to certify | Highest relative to benefit (framework/hyperparameter overhead for a 6-feature problem) | Very weak — "hidden unit activations" mean nothing to a pharmacist | **Not justified** — overkill for a small, low-dimensional, deterministically-labelled problem |
| **NLP-only classification** (i.e. a more powerful version of the existing text model, e.g. a real transformer, as *primary*) | Legitimate as a research comparison (already present, secondary); not suitable as sole primary mechanism | Moderate (attention/sentence-level, not threshold-level) | High (transformers want large corpora; this project's 17-drug synthetic vocabulary limits this — see §7) | Weaker than structured methods: reconstructing exact numeric thresholds from free text is a strictly lossy detour when the structured numbers were already available | Highest of all options (pretrained model weights, inference latency) | Middling — the input sentence is readable, the model's reasoning isn't | Real research value (already realised via the current secondary text model); **not** a credible primary-mechanism candidate |

**Read across the table**, the pattern is consistent: methods that structurally match branching/threshold logic (rule, single Decision Tree, Random Forest) do well; methods that don't (Logistic Regression, SVM, NN) would likely underperform in an informative way; and methods with high overhead relative to this problem's actual size (Gradient Boosting, NN, full NLP) aren't justified by anything in this dataset. The deterministic rule and a single Decision Tree are the two strongest performers on the *safety and explainability* columns specifically — worth sitting with, because it directly motivates §6.

---

## 4. Is Random Forest learning something useful, or reconstructing the rule?

**Reconstructing the rule — and this can be stated with confidence, not just suspicion, based on §5's trace.** "Learning something useful" would mean discovering structure not directly handed to it. Here, every one of RF's six inputs is a free variable of the exact function that produced the label (§5). Given that, and given a tree ensemble's capacity to represent branching logic, near-perfect accuracy is the *expected* outcome of this specific evaluation design — not evidence the model discovered anything. This holds for both the synthetic test set *and* the real-Synthea evaluation, because both label sources use the same rule (§5, §7).

This is not a criticism of the code — the rule-recovery *is* the actual, legitimate research finding here, and the project's own `evaluate.py` already prints a version of this caveat. The risk is only in how it gets *described*: "our model achieves 100% accuracy" invites the wrong conclusion; "our model successfully recovers a known deterministic rule from its defining features, which is expected and confirms correct implementation rather than demonstrating novel pattern discovery" is the accurate, defensible framing.

---

## 5. Label leakage / circularity — exact trace

**Ground truth (`data/generate_synthetic_data.py`, inline in `make_prescription_pair()`; identical logic duplicated in `data/real_synthea/adapt_real_synthea.py`'s `risk_label_for()`):**

```
IF NOT (drug_changed OR formulation_changed OR dose_changed OR route_changed): NONE
ELIF drug_changed:            HIGH if narrow_therapeutic_index else MEDIUM
ELIF formulation_changed:     HIGH if narrow_therapeutic_index else MEDIUM
ELIF dose_changed:
    threshold = 0.25 if narrow_therapeutic_index else 0.50
    HIGH if |dose_change_pct| >= threshold else (MEDIUM if narrow_therapeutic_index else LOW)
ELIF route_changed:           LOW
ELSE:                         NONE
```

Free variables of this function: `drug_changed, formulation_changed, dose_changed, dose_change_pct, route_changed, narrow_therapeutic_index`.

**Random Forest's input features**, verified directly in `train_random_forest.py`'s `to_xy()`:
```python
X = pd.DataFrame({
    "drug_changed": ..., "formulation_changed": ..., "dose_changed": ...,
    "dose_change_pct_abs": df["dose_change_pct"].abs(), "route_changed": ...,
    "narrow_therapeutic_index": ...,
})
```

**These are the same six variables**, with `dose_change_pct_abs` matching exactly what the rule branches on (`abs(dose_change_pct)`). There is no feature RF receives that isn't a direct argument to the label function, and no argument to the label function that RF doesn't receive. This is total, one-to-one coverage — the precise definition of circularity via label-defining features, traced exhaustively rather than asserted.

**Is this "leakage" in the classic sense (a feature unavailable at real prediction time)?** No — all six are genuinely observable when comparing two real prescriptions. The issue is narrower: the *evaluation* (train/test accuracy) measures rule-recovery, not clinical predictive validity, because the labels were never independent of the features to begin with.

---

## 6. Should Random Forest remain primary, become comparison-only, or be replaced by the deterministic rule?

**Recommendation: (B), with a specific, minimal mechanism — make the deterministic rule the live primary decision, and keep Random Forest (alongside the text model) as a displayed, non-authoritative comparison signal, exactly analogous to the role the text model already holds today.** This is closer to option (C) in outcome (the rule becomes authoritative) but preserves RF's presence in the running system rather than removing it, which is why it's framed as (B) here — see the justification below for why full removal (a stricter reading of C) is not recommended.

**Why not (A), keep RF as primary, unchanged:**
Once §5's trace is explicit, RF's live authority over pharmacist-facing decisions can't be justified on accuracy grounds (that number reflects rule-recovery, not clinical validity — §4). Its only remaining advantage over the rule is none: the rule is available, is exactly correct on the same input space by construction, requires no model file, no training pipeline, no risk of a stale or corrupted `.joblib`, and is exhaustively auditable. There is no dimension on which RF currently outperforms the rule it was trained to approximate.

**Why not the strict, full reading of (C), remove RF entirely:**
That would lose exactly the thing that makes this a machine-learning dissertation rather than an if-statement: a live, working demonstration of what a trained model does, side by side with a free-text model given deliberately less information (§7), and a real artefact for the "which algorithm is appropriate" comparison this whole audit exists to defend. Removing it would also contradict your own constraint in §8 (strongest defensible architecture *without unnecessarily rebuilding*) — RF and the text model already sit in the API response as parallel fields; the change needed is only about *which one drives `final_risk`*, not about deleting either model.

**The proposed mechanism, stated precisely (not yet implemented):** `backend/main.py`'s `final_risk = rf_risk` line changes to call the deterministic rule directly (the same function already used to generate training labels, centralised the same way NTI detection was centralised in an earlier change — see `is_narrow_therapeutic_index()` for the precedent). `risk_random_forest` and `risk_text_model` remain exactly as they are today: computed, returned, displayed — now clearly framed as two independent research/comparison signals against a provably-correct primary result, rather than one of them silently *being* the primary result.

**Academic justification, stated plainly:** machine learning is the right tool when the target function is unknown or too complex to specify directly. Here, the target function is known, small, and already implemented. Using an ML approximation of a known function as a safety-critical primary decision, when the known function itself is available and cheap to run, is not a strong safety engineering choice — regardless of how faithfully the approximation performs on held-out data drawn from the same generative process. The comparative value of training and evaluating RF (and the text model) against that known function is real and worth keeping — as an experiment, not as the mechanism a pharmacist's alert depends on.

---

## 7. Does the text model add meaningful value at 94% / 30%?

**Yes — keep it, unchanged in role, as secondary/comparison evidence. Do not remove it, and do not change the model to try to close the gap.**

The 94%→30% drop is not evidence the model or the choice of algorithm (TF-IDF + Logistic Regression) is flawed — it's a genuine, informative measurement of domain shift: the model is trained on a fixed 17-drug synthetic vocabulary and has zero subword or semantic generalisation (pure bag-of-words), so unseen real drug names are functionally invisible to it. That is precisely the kind of honest negative result that strengthens a dissertation's methodology chapter — it demonstrates the student understands *why* a lightweight NLP baseline generalises poorly, not merely that it does.

Removing it would remove real evidence; "fixing" it (e.g. swapping in a larger pretrained model) would be a different, larger project change outside today's scope and outside what you asked to be recommended here. The correct action, from the earlier audit and still unimplemented, is a one-line UI caveat noting it's a research comparison signal, not independently validated — a copy-only change, not a model change.

---

## 8. Strongest realistically defensible architecture, without unnecessarily rebuilding

1. **Prescription-change detection**: unchanged — deterministic, already correct (§1A).
2. **Primary risk decision**: the deterministic rule, run directly at inference time (§6) — the single change with the most defensive value for the least implementation cost, reusing logic that already exists.
3. **Random Forest**: retained, retrained on nothing new, displayed as a comparison signal — demonstrates the rule-recovery finding live, not just in an offline report.
4. **Text model**: retained exactly as-is, displayed as a second comparison signal, with an added UI caveat about real-world reliability (already recommended, still unimplemented, a copy-only change).
5. **Everything else** — the database, the first-prescription and dispense workflows, the NTI centralisation, the patient-ID lookup — is already independent of this decision and needs no further change.

This is deliberately the smallest change that converts every finding in this audit from "a limitation to explain defensively" into "a design decision to present confidently."

---

## 9. Demonstrating multiple algorithms were critically compared, not just RF selected

- Present §3's table (or your own version of it) directly in the dissertation, with each algorithm's *disqualification or acceptance reasoned*, not just accuracy-ranked.
- **Actually train and report** a plain Logistic Regression and a single Decision Tree on the identical features/split as RF (cheap — minutes of compute, no new data needed). The expected results (LogReg noticeably weaker, Decision Tree matching RF almost exactly) would turn §3's *argued* claims into *measured* ones — this is the single highest-value, lowest-cost addition available (see §10).
- Write up the audit process itself as part of the methodology: identifying the circularity, testing it precisely (§5), and revising the architecture in response (§6) is a demonstration of critical engagement that a static "we chose RF because accuracy was highest" statement cannot provide, and is often more persuasive in a viva than the comparison table alone.

---

## 10. Additional evaluation that would strengthen the justification

| Evaluation | Value | Cost |
|---|---|---|
| **Baseline comparison** (Logistic Regression + single Decision Tree, same features/split) | High — converts §3/§9's reasoning into measured results | Low |
| **Ablation study** (remove each of the 6 features one at a time, re-measure accuracy and importance shift) | High — empirically shows which features are load-bearing, beyond what built-in feature importances alone show | Low-medium |
| **Cross-validation on the training split** (k-fold, not touching the held-out test set) | Medium — adds a variance estimate around the reported metrics, strengthening statistical rigor claims | Low |
| **Confidence interval on the real-Synthea accuracy** (n=30; a 30% observed rate has a wide interval, roughly 15–49% at 95% confidence) | Medium-high — replaces a bare "30%" with an honest statement of how uncertain that estimate is | Very low (arithmetic only) |
| **Already satisfied — feature importances** | `evaluate.py` already computes and prints these | None needed |
| **Already satisfied — precision/recall/F1/confusion matrices** | Both `evaluate.py` and `evaluate_real_synthea.py` already report all of these per class | None needed |
| Sensitivity analysis on the NTI dose threshold (e.g. regenerate labels at 20%/30% instead of 25%, observe RF's stability) | Lower priority — informative but touches dataset generation, a larger and separate change | Medium |

The two highest-value, lowest-cost items — baseline comparison and the real-data confidence interval — are genuinely worth doing before a viva; both are measurement/reporting additions, not architecture changes.

---

## 11. Priority table of algorithm-related recommendations

| # | Recommendation | Priority |
|---|---|---|
| 1 | Make the deterministic rule the live primary decision; keep RF and text model as displayed comparison signals (§6) | **HIGH** |
| 2 | State the label-circularity finding explicitly in the dissertation text, not only in code comments (§4, §5) | **HIGH** |
| 3 | Train and report Logistic Regression + single Decision Tree baselines on the same split (§9, §10) | **HIGH** |
| 4 | Add a real-Synthea accuracy confidence interval given n=30 (§10) | **MEDIUM** |
| 5 | Add the UI caveat on the text model's secondary/comparison status (from the previous audit, still unimplemented) | **MEDIUM** |
| 6 | Ablation study across the 6 RF features (§10) | **MEDIUM** |
| 7 | k-fold cross-validation on the training split for a variance estimate (§10) | **LOW** |
| 8 | Sensitivity analysis on the NTI dose threshold (§10) | **LOW** |
| 9 | Investigate Gradient Boosting, SVM, or a neural network as replacements for RF | **LOW (not recommended — §3 shows no structural benefit for this dataset)** |

---

## 12. Likely viva questions, with technically honest answers

**"Why Random Forest?"**
> It structurally matches the branching/threshold shape of the clinical rule our labels are built from, and it provided a usable feature-importance ranking during development. I want to be direct, though: that structural fit is the actual justification — the accuracy figure isn't, because our labels are a deterministic function of exactly the features RF receives, so high accuracy there was expected, not evidence of discovered pattern. That's precisely why, in the final architecture, the deterministic rule — not RF — makes the live decision the pharmacist sees; RF remains as a comparison signal that demonstrates it successfully recovers the rule.

**"Why not a rule-based system?"**
> We do use one — it's the primary decision mechanism. Random Forest and the text model are retained specifically as comparative research artefacts: they let us measure how well a structured-feature model and a free-text model can each recover a known clinical rule from different amounts of information, which is a legitimate and, I'd argue, more interesting question than simply asserting "the rule is right, ship it."

**"Why is accuracy 100%?"**
> Because the risk label is generated by a deterministic function of exactly the six features Random Forest is given — there's no missing information and no noise between what the model sees and what computed the label. I traced this explicitly: every free variable of the labelling rule is a Random Forest input, and vice versa. Given that, and given a tree ensemble's capacity to represent branching logic, 100% is the expected result of this evaluation design, not a measure of generalisable predictive skill.

**"Is this clinical validation?"**
> No, and I don't claim it is anywhere in this work. We have two evaluations: a synthetic held-out test (internal rule-recovery validation) and a real-Synthea test (external *data* validation — genuine drug/dose/route facts, but labels still produced by our own rule, not by an independent clinician's judgement). Neither substitutes for a clinician or panel assessing real cases. I use "external data validation" and "clinical validation" as distinct terms throughout specifically to avoid overstating this.

**"Why use ML at all, if the rule already exists?"**
> Two reasons. First, research value: comparing how a structured model and a free-text model each perform at recovering a known rule — and where the free-text model's real-world accuracy drops and why — is itself a legitimate empirical contribution, particularly the 94%-to-30% domain-shift result, which required no rule at all to produce and taught us something the rule couldn't. Second, honesty about scope: I'm not claiming ML was *necessary* for the live decision — I'm using the rule for that, precisely because it's the more defensible engineering choice for a safety-critical decision when the ground truth is already known and cheap to compute. The ML components are there to be studied, not because they're the only way to get the right answer.

**"If RF and text model don't decide anything, why show them to the pharmacist at all?"**
> Transparency and audit value: showing that an independently-trained model agrees (or disagrees) with the rule-based decision is useful corroborating information, and keeping them visible — rather than hidden in an offline report — is what makes the comparative claim inspectable in the live system, not just asserted in a document.

**"What would make you trust an ML model as the primary mechanism instead of the rule?"**
> If the ground truth genuinely couldn't be hand-specified — for instance, if risk labels came from real pharmacists' judgements on cases too varied or too subtly-reasoned to reduce to an explicit rule. That's not this project's situation: our ground truth is fully known and small. In a future version trained on real adjudicated clinical outcomes rather than a hand-written rule, the calculus would be completely different, and a learned model would have a genuine, non-circular justification for primacy.
