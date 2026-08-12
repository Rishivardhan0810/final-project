"""
Exports the natural-language sentences used by the text-model substitute
(TF-IDF) into plain, portable CSVs -- one column `text`, one column
`label` -- for the three splits: train, test, and the real Synthea
external validation set.

These are the SAME sentences the TF-IDF classifier trained on, built by
the same comparison_engine.natural_language_description() function, so
a real ClinicalBERT fine-tune is directly comparable to the TF-IDF
result: same input text, same labels, same three data splits.

Run this locally (not in Colab), then upload the three output CSVs to
your Colab session. See backend/risk_models/clinicalbert_finetune.ipynb
for the fine-tuning notebook itself.
"""
import os
import sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
DATA_DIR = os.path.join(HERE)
REAL_DIR = os.path.join(HERE, "real_synthea")
OUT_DIR = os.path.join(HERE, "clinicalbert_export")
os.makedirs(OUT_DIR, exist_ok=True)

from comparison_engine import Prescription, compare_prescriptions, natural_language_description  # noqa: E402


def synthetic_sentence(row):
    prev = Prescription(row["previous_drug"], float(row["previous_dose_mg"]),
                         row["previous_frequency"], row["previous_route"], "", "")
    cur = Prescription(row["current_drug"], float(row["current_dose_mg"]),
                        row["current_frequency"], row["current_route"], "", "")
    report = compare_prescriptions(row["patient_id"], prev, cur)
    return natural_language_description(report, row["condition"], row["allergy"])


def real_sentence(row):
    prev = Prescription(row["previous_drug"], float(row["previous_dose_mg"]), "", row["previous_route"], "", "")
    cur = Prescription(row["current_drug"], float(row["current_dose_mg"]), "", row["current_route"], "", "")
    report = compare_prescriptions(row["patient_id"], prev, cur)
    return natural_language_description(report, row["condition"], "not recorded")


def export(df, sentence_fn, out_name):
    texts = df.apply(sentence_fn, axis=1)
    out = pd.DataFrame({"text": texts, "label": df["risk_label"]})
    path = os.path.join(OUT_DIR, out_name)
    out.to_csv(path, index=False)
    print(f"{out_name}: {len(out)} rows -> {path}")
    print(f"  label counts: {out['label'].value_counts().to_dict()}")


def main():
    train_df = pd.read_csv(os.path.join(DATA_DIR, "train.csv"))
    test_df = pd.read_csv(os.path.join(DATA_DIR, "test.csv"))
    real_df = pd.read_csv(os.path.join(REAL_DIR, "real_test.csv"))

    export(train_df, synthetic_sentence, "clinicalbert_train.csv")
    export(test_df, synthetic_sentence, "clinicalbert_test.csv")
    export(real_df, real_sentence, "clinicalbert_real_validation.csv")

    print(f"\nAll three files are in {OUT_DIR}/")
    print("Upload these three CSVs to your Colab session, then run "
          "clinicalbert_finetune.ipynb.")


if __name__ == "__main__":
    main()
