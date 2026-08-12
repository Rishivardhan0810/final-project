"""
Preprocessing -- the step between EDA and training.

What it does, in order:
  1. Load raw medications.csv
  2. Clean / type-check (no missing values, correct dtypes)
  3. Build the feature table
  4. FEATURE SELECTION: keep 6 features, drop 2 (see reasoning below)
  5. Split into train/test ONCE, save both to disk as separate files

Why this is a separate script from training: splitting here and saving
train.csv/test.csv means every model (Random Forest, text classifier)
is trained and evaluated on the exact same patients in the exact same
roles. No script downstream ever re-splits or re-shuffles.

FEATURE SELECTION REASONING (from data/eda_outputs/eda_report.txt):

Kept (6 features):
  - drug_changed, formulation_changed, dose_changed, dose_change_pct,
    route_changed: each carries real signal -- risk_label is a rule
    built directly over these (see generate_synthetic_data.py), and
    the correlation matrix shows no pair above r=0.7, so each
    contributes information the others don't duplicate.
  - narrow_therapeutic_index: pharmacologically grounded (real drugs
    like warfarin/digoxin/levothyroxine have a genuinely smaller safety
    margin), and it's what makes the risk thresholds scale by drug
    rather than applying one flat rule to everything.

Dropped (2 features) -- and this time the evidence for dropping them
is the whole point, not an afterthought:
  - manufacturer_changed: single-feature purity 0.58, well below the
    other structured features (drug_changed/formulation_changed/
    route_changed all sit at 0.72-0.87). This was generated
    DELIBERATELY as a control feature -- a manufacturer/brand swap of
    an identical formula is a packaging change, not a formula change,
    and risk_label's rule never uses it. Its middling purity is
    residual correlation from co-occurring with dose changes in the
    generator, not a genuine independent signal. Dropping it is the
    direct, evidenced answer to "focus on formula changes, not
    companies/packaging."
  - polypharmacy_count: single-feature purity 0.30, barely above the
    0.25 baseline you'd expect from random guessing across 4 classes.
    It's shown to the pharmacist for context (see
    concurrent_medications in the alert) but doesn't drive the risk
    score -- the data confirms it shouldn't, at least not as a simple
    count on its own.
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
    # concurrent_medications is legitimately allowed to be empty (a
    # patient can have zero concurrent medications) -- fill it before
    # the missing-value check below, so those rows aren't wrongly
    # treated as having missing data.
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
