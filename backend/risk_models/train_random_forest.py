"""
Random Forest risk classifier -- trained on the pre-split, pre-cleaned
train.csv / test.csv from data/preprocess.py.

v2: now uses 6 pharmacology-aware features instead of 4 -- adds
formulation_changed (immediate-release vs extended-release swaps) and
narrow_therapeutic_index (does this drug have a small safety margin,
e.g. warfarin/digoxin/levothyroxine). class_weight="balanced" remains
the weighting criterion.
"""
import os
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, precision_recall_fscore_support, confusion_matrix, classification_report
)

HERE = os.path.dirname(os.path.abspath(__file__))
TRAIN_PATH = os.path.join(HERE, "..", "..", "data", "train.csv")
TEST_PATH = os.path.join(HERE, "..", "..", "data", "test.csv")
MODEL_PATH = os.path.join(HERE, "rf_model.joblib")

# Must match data/preprocess.py SELECTED_FEATURES.
FEATURES = ["drug_changed", "formulation_changed", "dose_changed",
            "dose_change_pct", "route_changed", "narrow_therapeutic_index"]
LABEL = "risk_label"


def to_xy(df):
    X = pd.DataFrame({
        "drug_changed": df["drug_changed"].astype(int),
        "formulation_changed": df["formulation_changed"].astype(int),
        "dose_changed": df["dose_changed"].astype(int),
        "dose_change_pct_abs": df["dose_change_pct"].abs(),
        "route_changed": df["route_changed"].astype(int),
        "narrow_therapeutic_index": df["narrow_therapeutic_index"].astype(int),
    })
    y = df[LABEL]
    return X, y


def main():
    train_df = pd.read_csv(TRAIN_PATH)
    test_df = pd.read_csv(TEST_PATH)

    X_train, y_train = to_xy(train_df)
    X_test, y_test = to_xy(test_df)

    clf = RandomForestClassifier(
        n_estimators=200, max_depth=8, random_state=42, class_weight="balanced"
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
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
    print("\nFeature importances:")
    for name, imp in sorted(zip(X_train.columns, clf.feature_importances_), key=lambda t: -t[1]):
        print(f"  {name:26s} {imp:.3f}")

    joblib.dump(clf, MODEL_PATH)
    print(f"\nSaved model -> {MODEL_PATH}")

    return {"accuracy": acc, "precision": precision, "recall": recall, "f1": f1,
            "test_size": len(y_test)}


if __name__ == "__main__":
    main()
