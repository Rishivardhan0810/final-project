"""
Tests covering:
  - comparison_engine correctness (unit tests on known inputs), including
    the new formulation and narrow-therapeutic-index logic
  - dataset integrity: balance, no missing values, no leakage between
    train/test, no patient overlap

Run with: pytest backend/tests -v
"""
import os
import sys
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
DATA_DIR = os.path.join(HERE, "..", "..", "data")

from comparison_engine import Prescription, compare_prescriptions  # noqa: E402


# ---------------------------------------------------------------------
# Comparison engine unit tests
# ---------------------------------------------------------------------

def test_no_change_detected():
    prev = Prescription("Metformin", 500, "Standard", "Teva", "Oral", "2026-01-01", "Dr A")
    cur = Prescription("Metformin", 500, "Standard", "Teva", "Oral", "2026-02-01", "Dr A")
    report = compare_prescriptions("p1", prev, cur)
    assert report.change_types == []
    assert not report.drug_changed
    assert not report.dose_changed


def test_drug_switch_detected():
    prev = Prescription("Warfarin", 5, "Standard", "Teva", "Oral", "2026-01-01", "Dr A")
    cur = Prescription("Apixaban", 5, "Standard", "Teva", "Oral", "2026-02-01", "Dr A")
    report = compare_prescriptions("p2", prev, cur)
    assert report.drug_changed
    assert "drug" in report.change_types


def test_large_dose_reduction_percentage():
    prev = Prescription("Furosemide", 80, "Standard", "Teva", "Oral", "2026-01-01", "Dr A")
    cur = Prescription("Furosemide", 20, "Standard", "Teva", "Oral", "2026-02-01", "Dr A")
    report = compare_prescriptions("p3", prev, cur)
    assert report.dose_changed
    assert report.dose_change_pct == pytest.approx(0.75, abs=0.001)


def test_route_change_detected():
    prev = Prescription("Insulin Glargine", 20, "Standard", "Teva", "Subcutaneous", "2026-01-01", "Dr A")
    cur = Prescription("Insulin Glargine", 20, "Standard", "Teva", "Oral", "2026-02-01", "Dr A")
    report = compare_prescriptions("p4", prev, cur)
    assert report.route_changed
    assert not report.drug_changed
    assert not report.dose_changed


def test_formulation_change_detected_not_confused_with_drug_change():
    """Immediate-release -> extended-release of the SAME drug should be
    formulation_changed, not drug_changed."""
    prev = Prescription("Metformin", 500, "Immediate-release", "Teva", "Oral", "2026-01-01", "Dr A")
    cur = Prescription("Metformin", 500, "Extended-release", "Teva", "Oral", "2026-02-01", "Dr A")
    report = compare_prescriptions("p5", prev, cur)
    assert report.formulation_changed
    assert not report.drug_changed


def test_manufacturer_only_change_not_flagged_as_a_meaningful_change():
    """A brand/generic-maker swap of the identical formula should NOT
    appear in change_types -- this is the 'focus on formula, not
    packaging' behaviour, tested directly."""
    prev = Prescription("Atorvastatin", 20, "Standard", "Teva", "Oral", "2026-01-01", "Dr A")
    cur = Prescription("Atorvastatin", 20, "Standard", "Accord Healthcare", "Oral", "2026-02-01", "Dr A")
    report = compare_prescriptions("p6", prev, cur)
    assert report.manufacturer_changed
    assert report.change_types == []  # tracked, but not a risk-relevant change


def test_narrow_therapeutic_index_flagged_correctly():
    """Warfarin is a known narrow-therapeutic-index drug; Vitamin D is not."""
    prev = Prescription("Warfarin", 5, "Standard", "Teva", "Oral", "2026-01-01", "Dr A")
    cur = Prescription("Warfarin", 3, "Standard", "Teva", "Oral", "2026-02-01", "Dr A")
    report = compare_prescriptions("p7", prev, cur)
    assert report.narrow_therapeutic_index

    prev2 = Prescription("Vitamin D", 800, "Standard", "Teva", "Oral", "2026-01-01", "Dr A")
    cur2 = Prescription("Vitamin D", 400, "Standard", "Teva", "Oral", "2026-02-01", "Dr A")
    report2 = compare_prescriptions("p8", prev2, cur2)
    assert not report2.narrow_therapeutic_index


def test_drug_switch_risk_scales_with_nti_not_uniformly_high():
    """The core 'think like a scientist' requirement: a drug switch is
    only informative about risk when combined with whether an NTI drug
    is involved. Two switches with identical structural features
    (drug_changed=True, same dose/route/formulation) but different NTI
    status must NOT both score the same. This directly guards against
    the bug found in an earlier draft dataset where every drug switch
    was scored HIGH regardless of NTI status."""
    import pandas as pd
    raw_path = os.path.join(DATA_DIR, "medications.csv")
    if not os.path.exists(raw_path):
        pytest.skip("medications.csv not generated -- run data/generate_synthetic_data.py first")
    df = pd.read_csv(raw_path)
    switches = df[df["drug_changed"] == True]  # noqa: E712
    nti_labels = set(switches[switches["narrow_therapeutic_index"] == True]["risk_label"])  # noqa: E712
    non_nti_labels = set(switches[switches["narrow_therapeutic_index"] == False]["risk_label"])  # noqa: E712
    assert len(switches) > 0, "No drug switches were generated -- can't test this"
    assert nti_labels != non_nti_labels or (nti_labels == set() or non_nti_labels == set()), (
        f"Drug switches score identically regardless of NTI status: "
        f"NTI switches -> {nti_labels}, non-NTI switches -> {non_nti_labels}. "
        f"Risk must scale by pharmacology, not just by whether a switch happened."
    )


# ---------------------------------------------------------------------
# Dataset integrity tests (run after generate_synthetic_data.py + preprocess.py)
# ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def raw_data():
    path = os.path.join(DATA_DIR, "medications.csv")
    if not os.path.exists(path):
        pytest.skip("medications.csv not generated -- run data/generate_synthetic_data.py first")
    return pd.read_csv(path)


@pytest.fixture(scope="module")
def train_test():
    train_path = os.path.join(DATA_DIR, "train.csv")
    test_path = os.path.join(DATA_DIR, "test.csv")
    if not (os.path.exists(train_path) and os.path.exists(test_path)):
        pytest.skip("train.csv/test.csv not built -- run data/preprocess.py first")
    return pd.read_csv(train_path), pd.read_csv(test_path)


def test_no_missing_values(raw_data):
    # concurrent_medications is legitimately empty for patients with zero
    # concurrent medications (polypharmacy_count == 0) -- an empty string
    # in the CSV reads back as NaN in pandas, which is expected, not a
    # data quality problem. Every other column must have no nulls.
    other_cols = [c for c in raw_data.columns if c != "concurrent_medications"]
    assert raw_data[other_cols].isnull().sum().sum() == 0
    zero_polypharmacy = raw_data[raw_data["polypharmacy_count"] == 0]
    assert raw_data["concurrent_medications"].isnull().sum() == len(zero_polypharmacy), (
        "concurrent_medications is blank for rows other than polypharmacy_count == 0"
    )


def test_class_balance_within_tolerance(raw_data):
    counts = raw_data["risk_label"].value_counts()
    ratio = counts.max() / counts.min()
    assert ratio <= 1.5, f"Classes are imbalanced: {counts.to_dict()} (ratio {ratio:.2f})"


def test_all_four_classes_present(raw_data):
    assert set(raw_data["risk_label"].unique()) == {"NONE", "LOW", "MEDIUM", "HIGH"}


def test_at_least_two_therapeutic_classes_and_one_nti_drug_present(raw_data):
    """Sanity check that the richer drug reference table actually made
    it into the generated data, not just the code."""
    assert raw_data["previous_class"].nunique() >= 2
    assert raw_data["narrow_therapeutic_index"].any()


def test_manufacturer_changes_exist_but_dont_drive_risk_alone(raw_data):
    """Confirms manufacturer-only swaps are actually generated (so the
    'focus on formula not packaging' claim has real data behind it) and
    that a manufacturer-only change (nothing else different) is scored
    NONE, not a false alarm."""
    mfr_only = raw_data[
        raw_data["manufacturer_changed"]
        & ~raw_data["drug_changed"] & ~raw_data["formulation_changed"]
        & ~raw_data["dose_changed"] & ~raw_data["route_changed"]
    ]
    assert len(mfr_only) > 0, "No manufacturer-only change pairs were generated"
    assert (mfr_only["risk_label"] == "NONE").all()


def test_no_patient_overlap_between_train_and_test(train_test):
    train_df, test_df = train_test
    overlap = set(train_df["patient_id"]) & set(test_df["patient_id"])
    assert not overlap, f"{len(overlap)} patients leaked across train/test"


def test_all_classes_present_in_both_splits(train_test):
    train_df, test_df = train_test
    assert set(train_df["risk_label"].unique()) == {"NONE", "LOW", "MEDIUM", "HIGH"}
    assert set(test_df["risk_label"].unique()) == {"NONE", "LOW", "MEDIUM", "HIGH"}


def test_no_class_missing_or_tiny_in_either_split(train_test):
    """Guards against the '20 vs 80' scenario -- every class must have a
    reasonable minimum count in both train and test."""
    train_df, test_df = train_test
    for split_name, df in [("train", train_df), ("test", test_df)]:
        counts = df["risk_label"].value_counts()
        assert counts.min() >= 10, f"{split_name} split has a near-empty class: {counts.to_dict()}"


# ---------------------------------------------------------------------
# Real Synthea external validation set (optional -- only if present)
# ---------------------------------------------------------------------

def test_real_synthea_adapter_output_well_formed():
    real_path = os.path.join(DATA_DIR, "real_synthea", "real_test.csv")
    if not os.path.exists(real_path):
        pytest.skip("real_test.csv not built -- run data/real_synthea/adapt_real_synthea.py first")
    df = pd.read_csv(real_path)
    assert len(df) > 0
    assert df["risk_label"].isin(["NONE", "LOW", "MEDIUM", "HIGH"]).all()
    assert df["dose_change_pct"].notna().all()
