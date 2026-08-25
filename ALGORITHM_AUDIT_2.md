# Technical Audit 2: Risk-Classification Algorithm (post-fix state)

Read-only inspection. No code was modified while producing this report. This audit reflects the codebase **after** the two changes made in response to `ALGORITHM_AUDIT.md` (centralised NTI matching; Random Forest as the primary risk decision, text model demoted to secondary/comparison-only). Where a finding from the first audit has been resolved, that is stated explicitly rather than re-flagged as open.

---

## 1. Complete decision pipeline, input to displayed risk

```
1. POST /api/lookup {first_name, last_name, date_of_birth}          [backend/main.py]
2. SQL lookup in `patients`, then every row in `prescriptions` for that patient_id,
   ordered by start_date ASC
3. IF fewer than 2 prescriptions exist -> return immediately, alert = None. STOP.
   (No comparison, no risk model runs at all -- see §9/§10.)
4. Take the last two prescriptions as previous/current
5. comparison_engine.compare_prescriptions(previous, current)        [backend/comparison_engine.py]
     -> drug_changed, formulation_changed, dose_changed, dose_change_pct,
        route_changed, manufacturer_changed, narrow_therapeutic_index,
        change_types (list), magnitude_summary (text)
6. IF change_types is empty (nothing clinically relevant changed) -> alert = None. STOP.
7. Build rf_features (6 columns) -> rf_model.predict()                [train_random_forest.py model]
   Build natural_language_description() -> text_model.predict()      [train_text_classifier.py model]
8. final_risk = rf_risk   (Random Forest is now the sole determinant -- see §11)
9. Return {patient, prescriptions, alert: {risk_final, risk_random_forest,
   risk_text_model, summary, previous, current, ...}}
10. Frontend (RecordScreen.jsx / AlertPanel.jsx) renders risk_final as the
    headline badge; risk_random_forest labelled "Primary", risk_text_model
    labelled "Secondary, comparison only"
```

Two structural facts worth stating precisely for a viva: (a) the deterministic rule that *defines* NONE/LOW/MEDIUM/HIGH (§2) is never executed inside this pipeline — it only exists offline, to generate training labels; (b) manufacturer_changed is computed at step 5 and returned in the API response for display, but is excluded from both step 7's feature set and from `change_types`, so it can never trigger or influence an alert.

---

## 2. How NONE / LOW / MEDIUM / HIGH are generated

Two things must be kept separate, because conflating them is the single easiest mistake to make when defending this project:

- **Label generation (offline, training-time only).** `data/generate_synthetic_data.py` and `data/real_synthea/adapt_real_synthea.py` each contain a hand-written deterministic function (currently identical logic in both):
  ```
  IF nothing changed:                          NONE
  ELIF drug changed:                            HIGH if NTI else MEDIUM
  ELIF formulation changed:                     HIGH if NTI else MEDIUM
  ELIF dose changed:
      threshold = 0.25 if NTI else 0.50
      HIGH if |dose_change_pct| >= threshold else (MEDIUM if NTI else LOW)
  ELIF route changed:                           LOW
  ELSE:                                         NONE
  ```
- **Live classification (runtime, every request).** The deployed server never runs the block above. It runs the trained Random Forest (and, for comparison, the text model) on the 6 structured features, and displays whatever the Random Forest predicts.

The Random Forest's job, in other words, is to have learned to reproduce the block above from examples. Whether it actually has, versus merely being handed the answer, is the subject of §4–§6.

---

## 3. Every Random Forest feature, and its clinical/technical relevance

From `backend/main.py`'s `rf_features` dict, matching `backend/risk_models/train_random_forest.py`'s `FEATURES`:

| Feature | Type | Clinical relevance | Technical relevance |
|---|---|---|---|
| `drug_changed` | bool | A full active-ingredient switch carries inherent risk independent of dose (different pharmacokinetics, different interactions) | Highest single-feature importance in the trained model (0.185) after route/dose — see §5 |
| `formulation_changed` | bool | IR vs. ER changes absorption rate/peak plasma concentration, clinically significant especially combined with NTI status | Captures a signal the original v1 design entirely lacked |
| `dose_changed` | bool | Baseline signal that *something* about dosing changed | Coarse — see `dose_change_pct` below for the informative version |
| `dose_change_pct` (passed as `.abs()`) | continuous | Captures *magnitude*, not just direction — a 2% and a 90% change are clinically very different, a plain boolean can't distinguish them | The only continuous feature; carries real information the booleans can't |
| `route_changed` | bool | Route affects bioavailability and onset (oral vs. subcutaneous vs. IV) | Highest feature importance in the trained model (0.257) |
| `narrow_therapeutic_index` | bool | The core pharmacological concept this whole project is built to demonstrate — NTI drugs (warfarin, digoxin, levothyroxine, insulin, apixaban, lithium) have a small margin between therapeutic and toxic dose | This is also **the exact variable the label-generating rule branches on first for threshold selection** — see §4 |

All six are genuinely observable at prediction time in a real deployment (nothing here is "future information"), so none of them constitute *illegitimate* features. The issue examined next is narrower and more specific than "wrong features."

---

## 4–5. Target leakage, circular reasoning, and genuine vs. reproduced learning

**Finding, stated plainly: the Random Forest's 100% test accuracy is not evidence of generalisable learning. It is the expected, near-inevitable result of a specific evaluation-design property, and this is demonstrable, not speculative.**

The precise mechanism: `risk_label` is a **deterministic, noiseless function of exactly these same six variables** (§2). The Random Forest is handed those same six variables, unmodified, with zero noise and zero indirection between "what the model observes" and "what computed the label." A tree-ensemble model is, by construction, capable of representing arbitrary threshold/branching logic — which is exactly the shape of the rule in §2 — and the training data (by construction of the synthetic generator's quota-sampling) covers that branching structure directly. Under those conditions, near-perfect accuracy is not a sign of a powerful classifier; it would be *more* surprising if accuracy were lower.

This is best named precisely as **circular evaluation via label-defining features**, not classic target leakage (which usually means "a feature that wouldn't be available at prediction time" — not the case here) and not overfitting (the model is correctly fitting a noiseless function, not memorising noise).

**A finding a careful examiner would ask about, and that the first audit under-stated:** the "external" real-Synthea validation does **not** escape this circularity. `adapt_real_synthea.py` computes `risk_label` for the real-data test set using the *same hand-written rule*, applied to real drug/dose/route facts extracted from genuine records — not independent clinical adjudication. So 100% Random Forest accuracy on `real_test.csv` demonstrates the rule generalises across a second sample of feature combinations; it does **not** demonstrate the model predicts genuine, independently-verified clinical risk. Neither evaluation in this repository currently constitutes clinical validation (§12 makes this distinction explicit).

**Encouragingly**, the project's own `evaluate.py` already prints this caveat verbatim at the end of every run — this is worth citing directly in a viva as evidence of methodological self-awareness, provided the written dissertation states it just as explicitly rather than only the console output.

---

## 6. Are the six RF inputs individually appropriate?

Yes, in isolation — each is real, observable, and clinically motivated (§3). The appropriateness *problem* isn't any individual feature; it's that **all six of them, together, are exactly and only the free variables of the function that produced the label** (§4–5). Removing any single one wouldn't fix this — the label would still be a deterministic function of whichever subset remained, just a slightly different one. This is a property of how the *ground truth was constructed*, not of feature selection.

---

## 7. Random Forest vs. alternatives — which is actually appropriate here?

| Algorithm | Would it also hit ~100% under this label construction? | Verdict for this prototype |
|---|---|---|
| **Logistic Regression** | Likely **no** — the true rule has hard branches (e.g. "ignore dose entirely once drug_changed is true") that a linear decision boundary can't represent without explicit interaction terms. | Ironically the *most instructive* baseline: its imperfection would make the circularity visible rather than mask it. Worth including as an appendix comparison, not as the primary model. |
| **Decision Tree (single)** | Yes, almost certainly, and more transparently than an ensemble — a single tree of sufficient depth can directly encode the nested rule, and the resulting tree can be printed and compared side-by-side against the hand-written rule. | Arguably the *more honest* choice for demonstrating "the model learned to invert the label function," since the mechanism is directly inspectable. |
| **Random Forest (current choice)** | Yes. | Reasonable general-purpose choice, provides `feature_importances_` (used constructively — §3's table cites real numbers from it), robust to the small dataset. Its ensemble-robustness strength is largely moot when the target function is exactly deterministic. |
| **Gradient Boosting / XGBoost** | Yes, for the same structural reason. | **Not justified here** — adds hyperparameter complexity, reduced interpretability, and a heavier dependency, without illuminating or fixing the actual limitation. This is the textbook case of complexity that doesn't earn its cost. |
| **Rule-based classification (run §2's rule directly, live)** | N/A — would be 100% *by definition*, transparently and auditably. | A legitimate alternative architecture worth naming candidly: since the label already *is* a hand-written rule, one honest option would be to execute it directly at inference time instead of training a model to approximate it. The reason ML was used instead is presumably to enable the RF-vs-text-model comparison that is itself part of this dissertation's research question — that reasoning should be stated explicitly in the write-up rather than left implicit. |

**Recommendation for this prototype specifically:** Random Forest remains a defensible choice *given the project's comparative research framing* (structured-feature model vs. free-text model), but the dissertation should not present its 100% score as validating the algorithm choice over alternatives — under this label construction, algorithm choice among the tree-based/ensemble family is nearly immaterial to the headline number. Gradient Boosting would add complexity with no offsetting benefit and is not recommended.

---

## 8. Internal consistency of the risk rule, and clinically questionable edge cases

- **Priority is a strict `elif` chain, not additive.** If a drug switch also happens to change the dose (a frequent side effect in the generator, since a newly-chosen drug has its own independent dose range), the dose percentage is ignored entirely — the drug-switch branch decides regardless of magnitude. Defensible (two different drugs' mg values aren't directly comparable) but means simultaneous changes never compound risk.
- **Uneven tier reachability.** For a non-NTI drug, a *pure* dose change can only ever land on LOW or HIGH — there is no path to MEDIUM via dose alone (the 50% threshold is a hard cliff; 4% and 49% both score LOW). For an NTI drug, a pure dose change can only land on MEDIUM or HIGH — never LOW. This is coarse gradation, not an error, but a examiner-questionable design point worth being able to explain (see §13/§14 D6).
- **`formulation_changed` is deliberately suppressed when `drug_changed` is true** (`(not drug_changed) and ...` in `comparison_engine.py`). This is intentional — a formulation observation on a drug that's simultaneously being switched isn't independently meaningful — but is easy to mistake for a bug if not read carefully; worth flagging as a documented design decision.

---

## 9. Handling of a patient's FIRST prescription (no previous to compare)

Traced directly in `backend/main.py`, `lookup_patient()`:

```python
prescriptions = [dict(r) for r in rx_rows]
if len(prescriptions) < 2:
    return {"patient": patient, "prescriptions": prescriptions, "alert": None}
```

**This is the entirety of the handling.** If a patient has zero or one prescription on record, the function returns immediately. No comparison runs, no risk model runs, `alert` is `None` — exactly the same value returned when a *later* prescription is compared and found to have no risk-relevant change. The API response gives the frontend no way to distinguish "we checked, and it's fine" from "we had nothing to check against." `RecordScreen.jsx` renders no alert panel and no message in either case (`{alert && <AlertPanel .../>}` — simply doesn't render).

**A genuine robustness gap, not just a UX one:** if a patient has exactly zero prescriptions (not one — a data-integrity edge case, not produced by the current synthetic generator but not prevented either), `RecordScreen.jsx` line `const current = prescriptions[prescriptions.length - 1];` evaluates to `undefined`, and the very next render (`current.drug_name` in the "Current EPS prescription" table) throws a runtime `TypeError`. This does not occur in the current demo dataset (every generated patient has exactly 2 prescription rows) but is a real latent fragility, verified directly against the code rather than assumed.

---

## 10. Does a first-time prescription receive any medication/dose validation?

**No. This must be stated without qualification: no such validation exists anywhere in the codebase.**

Verified by direct inspection, not inferred:
- `main.py`'s only handling of a first prescription is the early-return shown in §9 — no code path runs the comparison engine, either risk model, or any other check when `len(prescriptions) < 2`.
- There is no absolute dose-range reference table anywhere in `backend/`. The only per-drug dose lists that exist (`DRUGS` in `data/generate_synthetic_data.py`) are used exclusively to *generate* synthetic data and are never imported by `backend/` code — they are not a live validation reference.
- `patient["allergy"]` is passed into `natural_language_description()` purely as **display/sentence-context text** (`grep`-confirmed: it appears only in that one f-string). It is never compared against `current.drug_name`, never used as a feature, never cross-referenced against any allergen or drug-class table anywhere in the repository.

**The practical consequence, stated directly:** a dangerously incorrect first-ever dose of a narrow-therapeutic-index drug, or a first prescription that directly conflicts with a recorded allergy, would currently pass through this system with **zero** algorithmic involvement — no alert, no flag, no signal of any kind, identical in every respect to a completely uneventful first prescription. This is arguably the single most significant scope boundary of the current prototype, and it should be stated as such in the dissertation rather than left to be discovered by an examiner.

---

## 11. Is keeping the TF-IDF + Logistic Regression model, as a secondary signal, justified?

**With the Random Forest now primary (Change 2), the risk profile of keeping the text model has genuinely improved — it can no longer independently trigger or escalate an alert.** Whether it's still *justified to display* is a separate question, assessed on its own merits:

**In favour of keeping it:**
- Legitimate comparative research value: it demonstrates, honestly, that a feature-engineered model and a free-text model reach different real-world reliability despite similar synthetic performance (94% vs. 30% — §5's circularity does *not* apply to the text model the same way, since it is never given `narrow_therapeutic_index` explicitly and must infer NTI-relevant risk from drug-name tokens alone — this is a genuinely more meaningful, less circular result than the RF's).
- Now provably inert with respect to patient safety (verified directly: 450 real lookups checked, `risk_final == risk_random_forest` in all 450 — see the previous session's verification).

**Against, or requiring mitigation:**
- The frontend currently displays `risk_text_model` with **no caveat about its known real-world unreliability** (30% on external data, with a strong bias toward false HIGH — 21/27 real MEDIUM cases). A pharmacist glancing at "Secondary, comparison only (Text model): HIGH" with no further context could still be influenced by it even though it's labelled secondary. A one-line UI caveat (e.g. "research comparison only, not independently validated") would meaningfully strengthen this justification without any model or logic change.

**Verdict: justified to keep, with the recommendation in §14 to add a UI-level reliability caveat** — this is a low-cost, non-code-logic change (copy only) that closes the remaining gap between "provably can't cause harm" and "can't be misread as authoritative."

---

## 12. External data validation vs. genuine clinical validation — a distinction that must be explicit

This project currently has exactly two evaluation results, and neither is clinical validation:

1. **Synthetic test-set evaluation** (`evaluate.py`) — tests whether the models reproduce the hand-written rule on held-out synthetic examples. This is **internal/rule-recovery validation**, not clinical validation: the "ground truth" was never a clinician's judgement, it was a function this project wrote.
2. **Real-Synthea evaluation** (`evaluate_real_synthea.py`) — uses **genuine** drug/dose/route facts, extracted from real (synthetic-population, but structurally realistic) medical records. This is real *data*. But the **labels** scored against are still produced by the same hand-written rule (§2), applied to those real facts — not by an independent clinician or panel reviewing the real cases and assigning a risk level. This is correctly described as **external data validation** (does the model behave sensibly on data it wasn't trained on) — it is **not** clinical validation (does the model's judgement agree with a qualified human's judgement of real clinical risk), and the dissertation should use those two terms deliberately and never interchangeably.

**No clinical validation exists in this project at any point**, and none should be claimed. This is a normal, expected limitation for an MSc-scope prototype using synthetic/semi-synthetic data — it only becomes a problem if the write-up implies otherwise.

---

## 13. What a university examiner could reasonably challenge

Ranked by how likely and how hard-hitting each question is:

1. **"Why does your model get 100% accuracy — doesn't that suggest something is wrong?"** — Yes, and you should say so before being asked (§4–5).
2. **"Does your real-data validation prove the model works clinically?"** — No; walk them through §12's distinction unprompted.
3. **"What happens on a patient's very first prescription?"** — Nothing; the system performs no check at all (§9–10). Be ready to state this as a named limitation, not defend it as acceptable.
4. **"Why is Random Forest better than Logistic Regression or XGBoost here?"** — It isn't, particularly, under this label construction (§7); the honest answer is about the comparative research framing, not classifier superiority.
5. **"Why does a 45% dose increase score the same as a 5% one for a non-NTI drug?"** — The rule's dose-threshold gradation is coarse by design (§8); acknowledge it as a known simplification.
6. **"If the text model is unreliable, why is it still in the product at all?"** — Point to §11: it's provably non-authoritative post-fix, has comparative research value, and (once added) carries a UI caveat.

---

## 14. All findings, ranked

| # | Finding | Priority |
|---|---|---|
| F1 | No medication/dose/allergy validation of any kind exists for a patient's first prescription — silent, zero-signal pass-through | **CRITICAL** (for defensibility of clinical claims — not necessarily for code correctness, since this is a documented scope boundary, not a bug) |
| F2 | Random Forest's 100% accuracy (synthetic *and* real-Synthea) reflects circular evaluation via label-defining features, not generalisable learning | **CRITICAL** (for the dissertation defense specifically) |
| F3 | Frontend gives no distinct signal for "first prescription, not checked" vs. "checked, no risk found" — both render identically (no alert panel) | **HIGH** |
| F4 | `RecordScreen.jsx` would throw a runtime error if a patient has zero prescriptions (not one) — latent, not currently triggered by the synthetic dataset | **MEDIUM** |
| F5 | Real-Synthea "external validation" is data-external but label-circular — must not be described as clinical validation | **HIGH** (framing/explanation, not code) |
| F6 | Text model displayed with no caveat about its known real-world unreliability, despite no longer being able to affect the primary decision | **MEDIUM** |
| F7 | Dose-based risk gradation is coarse (no MEDIUM reachable via pure dose change for non-NTI; no LOW reachable via pure dose change for NTI) | **LOW** |
| F8 | Gradient Boosting / XGBoost would add complexity without addressing F2 or improving on Random Forest for this label construction | **LOW** (informational — supports not making this change) |

---

## A. Findings (summary)

The comparison logic and risk rule are internally coherent and well-factored (§1–2, §8). Both Random Forest and the text model are architecturally reasonable choices, but the Random Forest's headline accuracy is a property of circular evaluation, not evidence of clinical generalisation (§4–7, §12) — true for both the synthetic and the "external" real-data test. The single most consequential functional gap is that first-time prescriptions receive **no algorithmic scrutiny whatsoever** (§9–10) — the entire safety mechanism this project builds simply does not engage for the first prescription a patient ever receives in the system.

## B. Recommended changes (not implemented — for your decision)

1. Add an explicit "first prescription — no prior record to compare, not automatically checked" signal to the API response and frontend, so this case is visibly distinct from "checked, no risk found." *(Low code cost, closes F1/F3.)*
2. Guard `RecordScreen.jsx`'s `current` access for the zero-prescriptions case. *(Trivial, closes F4.)*
3. Add a one-line UI caveat next to the text model's secondary score. *(Copy-only, closes F6.)*
4. In the dissertation text (not code): state F2 and F5 explicitly, in your own words, before an examiner raises them.
5. Optional, not necessary: an appendix experiment comparing Random Forest against a single Decision Tree and plain Logistic Regression on the same features, specifically to *demonstrate* §4's circularity finding empirically rather than only argue it.

## C. Algorithm justification (dissertation-ready)

> This system separates label *construction* from label *prediction*. Ground-truth risk labels for training were generated by a deterministic, pharmacologically-motivated rule (Appendix/§2) that scales its dose-change threshold by whether a narrow-therapeutic-index drug is involved — reflecting the clinical reality that NTI drugs (warfarin, digoxin, levothyroxine, insulin, apixaban, lithium) tolerate substantially less variation before the risk of toxicity or sub-therapeutic dosing becomes significant. Two independent classifiers were then trained to *predict* that label from two different input representations: a Random Forest over six structured, clinically-motivated features, and a TF-IDF + Logistic Regression model over a free-text description of the same change, deliberately withholding the explicit NTI flag from the latter to test whether risk-relevant signal could be recovered from language alone. Both were evaluated on a held-out synthetic split and, separately, on real-world-derived Synthea data never seen during training. The Random Forest reproduces the labelling rule with very high fidelity on both; the text model achieves materially lower but non-trivial accuracy on real data, evidencing genuine (if limited) language-based generalisation rather than rule-copying. Random Forest was retained as the system's primary decision-maker, with the text model demoted to a secondary, non-authoritative comparison signal, following the finding that a naive max-of-both fusion rule allowed the text model's real-world false-positive tendency to override the Random Forest's correct predictions. The system's near-perfect synthetic accuracy is explicitly understood as an artefact of evaluating a model against labels constructed from its own input features, not as evidence of validated clinical performance; no claim of clinical validation is made anywhere in this work, and the prototype's current inability to assess a patient's first prescription (where no prior record exists for comparison) is documented as a deliberate scope boundary for future work, not an oversight.

## D. Likely viva questions and strong, technically accurate answers

**Q1: Your Random Forest gets 100% accuracy. Isn't that a red flag?**
> Yes, and I'd expect it to be, given how the labels were constructed. The risk label is a deterministic function of exactly the six features the model receives — the model isn't predicting an independent outcome from indirect evidence, it's recovering a known function from its own arguments. I verified this isn't standard overfitting (there's no noise to overfit to) or classic target leakage (all six features are genuinely available at prediction time in a real deployment) — it's best described as circular evaluation via label-defining features. The 100% figure demonstrates the model *can* represent the rule; it does not demonstrate clinical predictive validity.

**Q2: Doesn't your real Synthea validation prove it generalises, though?**
> It proves the rule-recovery result holds on a second, independently-sourced set of feature combinations — which is useful evidence the model isn't simply memorising the synthetic training set. But the ground-truth labels for that real-data set were also produced by the same hand-written rule, applied to real drug/dose/route facts, not by a clinician's independent judgement. So it's external *data* validation, not clinical validation, and I'm careful to keep those two terms distinct in my write-up.

**Q3: What happens if a patient is prescribed a dangerous drug for the very first time?**
> Currently, nothing — and I want to be direct about that rather than let it be discovered. The entire risk-detection mechanism is comparison-based: it looks at a previous and a current prescription and reasons about what changed. With no previous prescription, there's nothing to compare, so the system returns no alert at all, indistinguishable from a genuinely uneventful case. This is the most significant scope boundary of the current prototype, and addressing it would require an entirely different mechanism — an absolute dose/allergy validation layer — which is out of scope for this dissertation but is exactly the right next step for future work.

**Q4: Why Random Forest and not Logistic Regression or Gradient Boosting?**
> Given how the label was constructed, almost any sufficiently expressive classifier reaches similar accuracy — the specific choice among tree-based/ensemble methods is nearly immaterial to the headline number. I chose Random Forest for its interpretability via feature importances and its natural fit to the rule's branching structure, and specifically avoided Gradient Boosting because it would add real complexity — more hyperparameters, less interpretability — without addressing or illuminating the underlying circularity. Logistic Regression is actually the more interesting comparison: because it can't represent the rule's hard branches without explicit interaction terms, it would likely *not* reach 100%, which would make the circularity issue visible rather than mask it — that's a experiment I'd flag as valuable future work.

**Q5: Why keep the text model if it's only 30% accurate on real data?**
> Two reasons. First, comparative value: it shows that a model without direct access to the NTI flag has to infer risk-relevant signal from language alone, and 94% synthetic vs. 30% real-data accuracy is a genuine, informative measurement of the domain-shift gap between a fixed synthetic vocabulary and real-world drug names — that's a legitimate research finding, not a failure to hide. Second, safety: after finding that combining it with Random Forest via a max-of-both rule let its false positives override the Random Forest's correct answers, I changed the fusion logic so Random Forest is the sole primary decision and the text model's output is returned purely as a secondary, non-authoritative comparison value — it can no longer influence what a pharmacist is told to act on.
