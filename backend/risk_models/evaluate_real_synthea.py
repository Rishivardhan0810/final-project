# Part of the backend risk models -- external validation against
# genuine Synthea data, separate from the synthetic generator's output.
"""Scores the already-trained Random Forest and text models against
data/real_synthea/real_test.csv (genuine Synthea output the models have
never seen). Not a retrain or re-split -- just answers "how well does a
model trained on synthetic data generalise to real records?"."""
import os
import sys
import joblib
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, classification_report

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
REAL_TEST_PATH = os.path.join(HERE, "..", "..", "data", "real_synthea", "real_test.csv")
RF_MODEL_PATH = os.path.join(HERE, "rf_model.joblib")
TEXT_MODEL_PATH = os.path.join(HERE, "text_model.joblib")

from comparison_engine import Prescription, compare_prescriptions, natural_language_description  # noqa: E402


def build_sentence(row):
    prev = Prescription(row["previous_drug"], float(row["previous_dose_mg"]),
                         row["previous_formulation"], "not recorded", row["previous_route"], "", "")
    cur = Prescription(row["current_drug"], float(row["current_dose_mg"]),
                        row["current_formulation"], "not recorded", row["current_route"], "", "")
    report = compare_prescriptions(row["patient_id"], prev, cur)
    return natural_language_description(report, row["condition"], "not recorded")


def main():
    if not os.path.exists(REAL_TEST_PATH):
        print("real_test.csv not found -- run data/real_synthea/adapt_real_synthea.py first.")
        sys.exit(1)
    if not (os.path.exists(RF_MODEL_PATH) and os.path.exists(TEXT_MODEL_PATH)):
        print("Trained models not found -- run backend/risk_models/evaluate.py first (trains on synthetic data).")
        sys.exit(1)

    df = pd.read_csv(REAL_TEST_PATH)
    y_true = df["risk_label"].tolist()
    print(f"Real Synthea validation set: {len(df)} genuine prescription-change pairs")
    print(f"Risk label distribution in real data: {df['risk_label'].value_counts().to_dict()}")
    print(f"Pairs involving a narrow-therapeutic-index drug: {int(df['narrow_therapeutic_index'].sum())}/{len(df)}\n")

    rf_model = joblib.load(RF_MODEL_PATH)
    X_rf = pd.DataFrame({
        "drug_changed": df["drug_changed"].astype(int),
        "formulation_changed": df["formulation_changed"].astype(int),
        "dose_changed": df["dose_changed"].astype(int),
        "dose_change_pct_abs": df["dose_change_pct"].abs(),
        "route_changed": df["route_changed"].astype(int),
        "narrow_therapeutic_index": df["narrow_therapeutic_index"].astype(int),
    })
    rf_pred = rf_model.predict(X_rf).tolist()

    text_model = joblib.load(TEXT_MODEL_PATH)
    sentences = df.apply(build_sentence, axis=1).tolist()
    text_pred = text_model.predict(sentences).tolist()

    print("=" * 60)
    print("RANDOM FOREST on real Synthea data")
    print("=" * 60)
    print(f"Accuracy: {accuracy_score(y_true, rf_pred):.4f}")
    labels_present = sorted(set(y_true) | set(rf_pred))
    print(classification_report(y_true, rf_pred, labels=labels_present, zero_division=0))
    print("Confusion matrix", labels_present)
    print(confusion_matrix(y_true, rf_pred, labels=labels_present))

    print("\n" + "=" * 60)
    print("TEXT MODEL on real Synthea data")
    print("=" * 60)
    print(f"Accuracy: {accuracy_score(y_true, text_pred):.4f}")
    labels_present = sorted(set(y_true) | set(text_pred))
    print(classification_report(y_true, text_pred, labels=labels_present, zero_division=0))
    print("Confusion matrix", labels_present)
    print(confusion_matrix(y_true, text_pred, labels=labels_present))

    print(
        "\nNote: the pharmacology-scaled rule spreads these real validation pairs across "
        "MEDIUM and HIGH -- none of the drug switches captured here involve a "
        "narrow-therapeutic-index drug, so they land on MEDIUM rather than HIGH. There are "
        "still no real LOW/NONE cases in this sample -- the synthetic test set (evaluate.py) "
        "remains the only evidence for those two classes. manufacturer_changed is always "
        "False here since real Synthea's medications.csv has no manufacturer field at all."
    )


if __name__ == "__main__":
    main()
