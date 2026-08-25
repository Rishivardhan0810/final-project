# Part of the backend risk models -- shared helper, not run on its own.
"""Print helpers so the Random Forest and text model report results the
same way, instead of repeating the same formatting in every script."""
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix


def print_classification_summary(y_train, y_test, y_pred, acc, precision, recall, f1):
    """Train/test size, headline metrics, per-class report, confusion matrix."""
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


def print_real_data_report(name, y_true, y_pred):
    """Same idea, for the external real-Synthea validation -- only the classes
    actually present in that small sample can be scored."""
    print("=" * 60)
    print(f"{name} on real Synthea data")
    print("=" * 60)
    print(f"Accuracy: {accuracy_score(y_true, y_pred):.4f}")
    labels_present = sorted(set(y_true) | set(y_pred))
    print(classification_report(y_true, y_pred, labels=labels_present, zero_division=0))
    print("Confusion matrix", labels_present)
    print(confusion_matrix(y_true, y_pred, labels=labels_present))
