# Part of the data pipeline -- cleans the data and produces the fixed
# train.csv/test.csv both risk models train on.
"""
The step between EDA and training: load medications.csv, clean/type-check
it, pick which features to keep, then split into train/test once and
save both to disk so every downstream model sees the exact same split.

Feature selection (see data/eda_outputs/eda_report.txt for the numbers):

Kept: drug_changed, formulation_changed, dose_changed, dose_change_pct,
route_changed, narrow_therapeutic_index. Each carries real signal --
risk_label is built directly from these -- and no pair is correlated
above r=0.7, so they're not just duplicating each other.

Dropped: manufacturer_changed (purity 0.58, well below the other
features at 0.72-0.87 -- it's a packaging/brand swap, not a formula
change, and risk_label never uses it) and polypharmacy_count (purity
0.30, barely above the 0.25 you'd expect from guessing across 4
classes -- useful context for the pharmacist, not a risk signal).
"""
import os
import pandas as pd
from sklearn.model_selection import train_test_split

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_PATH = os.path.join(HERE, "medications.csv")
TRAIN_PATH = os.path.join(HERE, "train.csv")
TEST_PATH = os.path.join(HERE, "test.csv")

# Feature selection: manufacturer_changed and polypharmacy_count
# dropped, see module docstring for the evidence.
SELECTED_FEATURES = ["drug_changed", "formulation_changed", "dose_changed",
                      "dose_change_pct", "route_changed", "narrow_therapeutic_index"]
LABEL = "risk_label"
TEXT_COLS = ["condition", "allergy", "previous_drug", "previous_class", "previous_dose_mg",
             "previous_formulation", "previous_manufacturer", "previous_route",
             "current_drug", "current_class", "current_dose_mg", "current_formulation",
             "current_manufacturer", "current_route", "concurrent_medications"]


def clean(df: pd.DataFrame) -> pd.DataFrame:
    # concurrent_medications can genuinely be empty (zero concurrent
    # meds) -- fill it first so those rows don't fail the missing-value
    # check below
    df["concurrent_medications"] = df["concurrent_medications"].fillna("")

    before = len(df)
    df = df.dropna(subset=SELECTED_FEATURES + [LABEL] + TEXT_COLS).copy()
    dropped = before - len(df)
    if dropped:
        print(f"Dropped {dropped} rows with missing values")

    for col in ["drug_changed", "formulation_changed", "dose_changed",
                "route_changed", "narrow_therapeutic_index"]:
        df[col] = df[col].astype(bool).astype(int)
    df["dose_change_pct"] = df["dose_change_pct"].astype(float)
    df[LABEL] = df[LABEL].astype(str)
    return df


def main():
    df = pd.read_csv(RAW_PATH)
    df = clean(df)

    keep_cols = SELECTED_FEATURES + [LABEL] + TEXT_COLS + ["patient_id"]
    df = df[keep_cols]

    train_df, test_df = train_test_split(
        df, test_size=0.25, random_state=42, stratify=df[LABEL]
    )

    train_df.to_csv(TRAIN_PATH, index=False)
    test_df.to_csv(TEST_PATH, index=False)

    print(f"Train: {len(train_df)} rows -> {TRAIN_PATH}")
    print(f"Test:  {len(test_df)} rows -> {TEST_PATH}")
    print("Train class balance:", train_df[LABEL].value_counts().to_dict())
    print("Test class balance: ", test_df[LABEL].value_counts().to_dict())
    print(f"Selected features ({len(SELECTED_FEATURES)}): {SELECTED_FEATURES}")
    print("Dropped: manufacturer_changed, polypharmacy_count (see docstring for evidence)")

    # sanity check: no patient appears in both splits
    overlap = set(train_df["patient_id"]) & set(test_df["patient_id"])
    assert not overlap, f"LEAKAGE: {len(overlap)} patients appear in both train and test"
    print("Leakage check passed: no patient appears in both train and test.")

    # sanity check: label column not accidentally present in feature set
    assert LABEL not in SELECTED_FEATURES, "LEAKAGE: label present in feature list"
    print("Leakage check passed: label is not part of the feature set.")


if __name__ == "__main__":
    main()
