# Part of the backend risk models -- trains the text/NLP classifier,
# the other model main.py loads alongside Random Forest.
"""TF-IDF + Logistic Regression text classifier (standing in for a real
ClinicalBERT fine-tune, since this environment has no route to
huggingface.co). Trained on the same train.csv/test.csv split as the
Random Forest, just fed as natural-language sentences instead of
structured columns."""
import os
import sys
import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    accuracy_score, precision_recall_fscore_support, confusion_matrix, classification_report
)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
TRAIN_PATH = os.path.join(HERE, "..", "..", "data", "train.csv")
TEST_PATH = os.path.join(HERE, "..", "..", "data", "test.csv")
MODEL_PATH = os.path.join(HERE, "text_model.joblib")
LABEL = "risk_label"

from comparison_engine import Prescription, compare_prescriptions, natural_language_description  # noqa: E402


def build_sentences(df: pd.DataFrame):
    sentences = []
    for _, row in df.iterrows():
        prev = Prescription(row["previous_drug"], float(row["previous_dose_mg"]),
                             row["previous_formulation"], row["previous_manufacturer"],
                             row["previous_route"], "", "")
        cur = Prescription(row["current_drug"], float(row["current_dose_mg"]),
                            row["current_formulation"], row["current_manufacturer"],
                            row["current_route"], "", "")
        report = compare_prescriptions(row["patient_id"], prev, cur)
        concurrent = row.get("concurrent_medications", "") or ""
        sentences.append(natural_language_description(report, row["condition"], row["allergy"], concurrent))
    return sentences


def main():
    train_df = pd.read_csv(TRAIN_PATH)
    test_df = pd.read_csv(TEST_PATH)

    X_train = build_sentences(train_df)
    y_train = train_df[LABEL]
    X_test = build_sentences(test_df)
    y_test = test_df[LABEL]

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1)),
        ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_test, y_pred, average="macro", zero_division=0
    )

    labels_sorted = sorted(y_train.unique())
    print(f"Train size: {len(y_train)}  Test size: {len(y_test)}")
    print(f"Accuracy:  {acc:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    print(f"F1:        {f1:.4f}")
    print("\nPer-class report:")
    print(classification_report(y_test, y_pred, labels=labels_sorted, zero_division=0))
    print("Confusion matrix (rows=true, cols=pred), labels:", labels_sorted)
    print(confusion_matrix(y_test, y_pred, labels=labels_sorted))
    print("\nExample sentence:", X_test[0])

    joblib.dump(pipeline, MODEL_PATH)
    print(f"\nSaved model -> {MODEL_PATH}")

    return {"accuracy": acc, "precision": precision, "recall": recall, "f1": f1,
            "test_size": len(y_test)}


if __name__ == "__main__":
    main()
