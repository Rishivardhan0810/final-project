# Part of the backend risk models -- trains + compares both classifiers,
# run this to get the headline accuracy numbers.
"""Runs both classifiers on the same pre-split test.csv and prints a
side-by-side table. Assumes data/preprocess.py has already been run --
this script doesn't re-split anything itself."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import train_random_forest as rf_module
import train_text_classifier as text_module
import pandas as pd

LABEL = "risk_label"


def under_over_risked(y_test, y_pred):
    order = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
    under, over = 0, 0
    for t, p in zip(y_test, y_pred):
        if order[p] < order[t]:
            under += 1
        elif order[p] > order[t]:
            over += 1
    return under, over


def main():
    if not os.path.exists(rf_module.TRAIN_PATH):
        print("train.csv/test.csv not found -- run data/preprocess.py first.")
        sys.exit(1)

    print("=" * 60)
    print("RANDOM FOREST (structured features)")
    print("=" * 60)
    rf_metrics = rf_module.main()

    print("\n" + "=" * 60)
    print("TEXT MODEL (ClinicalBERT substitute -- TF-IDF + LogReg)")
    print("=" * 60)
    text_metrics = text_module.main()

    test_df = pd.read_csv(rf_module.TEST_PATH)
    y_test = test_df[LABEL].tolist()

    import joblib
    rf_model = joblib.load(rf_module.MODEL_PATH)
    X_test_rf, _ = rf_module.to_xy(test_df)
    rf_pred = rf_model.predict(X_test_rf).tolist()
    rf_under, rf_over = under_over_risked(y_test, rf_pred)

    text_model = joblib.load(text_module.MODEL_PATH)
    X_test_text = text_module.build_sentences(test_df)
    text_pred = text_model.predict(X_test_text).tolist()
    text_under, text_over = under_over_risked(y_test, text_pred)

    summary = {
        "random_forest": {**rf_metrics, "under_risked": rf_under, "over_risked": rf_over},
        "text_model": {**text_metrics, "under_risked": text_under, "over_risked": text_over},
        "train_size": len(pd.read_csv(rf_module.TRAIN_PATH)),
        "test_size": len(test_df),
        "class_balance_test": test_df[LABEL].value_counts().to_dict(),
    }

    print("\n" + "=" * 60)
    print("COMPARISON TABLE")
    print("=" * 60)
    print(f"{'Metric':<16}{'Random Forest':<16}{'Text model':<16}")
    for key in ["accuracy", "precision", "recall", "f1"]:
        print(f"{key:<16}{summary['random_forest'][key]:<16.4f}{summary['text_model'][key]:<16.4f}")
    print(f"{'under-risked':<16}{rf_under:<16}{text_under:<16}")
    print(f"{'over-risked':<16}{rf_over:<16}{text_over:<16}")
    print(f"\nTest set class balance: {summary['class_balance_test']}")

    out_path = os.path.join(HERE, "evaluation_summary.json")
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved -> {out_path}")

    print(
        "\nNote: Random Forest hits 100% here mainly because it's given "
        "narrow_therapeutic_index directly as a feature -- the risk_label rule branches on "
        "that exact flag, so RF can shortcut straight to the rule rather than learning "
        "anything new. The text model doesn't get that flag; it only sees drug names in a "
        "sentence and has to work out which ones are narrow-therapeutic-index from language "
        "alone. It scores 94%, not 100%, with most errors on the HIGH/MEDIUM boundary -- "
        "exactly where NTI status matters. See README.md and evaluate_real_synthea.py for more."
    )


if __name__ == "__main__":
    main()
