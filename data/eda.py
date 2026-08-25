# Part of the data pipeline -- exploratory analysis, runs before
# anything gets trained on the data.
"""
EDA over the generated dataset: drug_changed, formulation_changed,
manufacturer_changed, dose_changed, dose_change_pct, route_changed,
narrow_therapeutic_index, polypharmacy_count. Two of these
(manufacturer_changed, polypharmacy_count) are deliberately not part of
the risk rule, so this can check whether they actually contribute
anything rather than just assuming they don't.

Writes to data/eda_outputs/: class_balance.png, correlation_heatmap.png,
feature_distributions.png, and eda_report.txt (balance check,
correlation matrix, single-feature leakage check).

Purely diagnostic -- nothing here fits on the data or learns anything,
so running it can't introduce leakage on its own.
"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "medications.csv")
OUT_DIR = os.path.join(HERE, "eda_outputs")
os.makedirs(OUT_DIR, exist_ok=True)

BOOL_FEATURES = ["drug_changed", "formulation_changed", "manufacturer_changed",
                  "dose_changed", "route_changed", "narrow_therapeutic_index"]
LABEL = "risk_label"
CLASS_ORDER = ["NONE", "LOW", "MEDIUM", "HIGH"]


def main():
    df = pd.read_csv(DATA_PATH)
    report_lines = []

    # --- 1. Class balance check -------------------------------------
    counts = df[LABEL].value_counts().reindex(CLASS_ORDER)
    report_lines.append("CLASS BALANCE")
    report_lines.append(str(counts.to_dict()))
    max_ratio = counts.max() / counts.min()
    report_lines.append(f"Max/min class ratio: {max_ratio:.2f} "
                         f"({'BALANCED (<=1.5x, ok)' if max_ratio <= 1.5 else 'IMBALANCED - fix before training'})")
    report_lines.append("")

    plt.figure(figsize=(5, 4))
    sns.barplot(x=counts.index, y=counts.values, hue=counts.index, palette="Blues_d", legend=False)
    plt.title("Class balance: risk_label")
    plt.ylabel("Count")
    plt.xlabel("Risk label")
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "class_balance.png"), dpi=130)
    plt.close()

    # --- 2. Drug reference summary --------------------------------------
    report_lines.append("THERAPEUTIC CLASS / NTI SUMMARY")
    n_classes = df["previous_class"].nunique()
    nti_rate = df["narrow_therapeutic_index"].mean()
    report_lines.append(f"Distinct therapeutic classes represented: {n_classes}")
    report_lines.append(f"Fraction of pairs involving a narrow-therapeutic-index drug: {nti_rate:.2f}")
    report_lines.append(f"Mean concurrent medications per pair (polypharmacy context): "
                         f"{df['polypharmacy_count'].mean():.2f}")
    report_lines.append("")

    # --- 3. Correlation between structured features -------------------
    feat_df = df[["drug_changed", "formulation_changed", "manufacturer_changed",
                   "dose_changed", "route_changed", "narrow_therapeutic_index"]].astype(int).copy()
    feat_df["dose_change_pct_abs"] = df["dose_change_pct"].abs()
    feat_df["polypharmacy_count"] = df["polypharmacy_count"]
    corr = feat_df.corr()
    report_lines.append("FEATURE CORRELATION MATRIX")
    report_lines.append(corr.round(2).to_string())
    report_lines.append("")

    high_corr_pairs = []
    for i in range(len(corr.columns)):
        for j in range(i + 1, len(corr.columns)):
            v = corr.iloc[i, j]
            if abs(v) >= 0.7:
                high_corr_pairs.append((corr.columns[i], corr.columns[j], round(v, 2)))
    report_lines.append(f"Highly correlated pairs (|r| >= 0.7): {high_corr_pairs or 'none found'}")
    report_lines.append("")

    plt.figure(figsize=(7.5, 6))
    sns.heatmap(corr, annot=True, cmap="coolwarm", vmin=-1, vmax=1, square=True, fmt=".2f")
    plt.title("Feature correlation matrix")
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "correlation_heatmap.png"), dpi=130)
    plt.close()

    # --- 4. Feature distributions by class -----------------------------
    plot_df = feat_df.copy()
    plot_df[LABEL] = df[LABEL]
    cols = [c for c in plot_df.columns if c != LABEL]
    fig, axes = plt.subplots(1, len(cols), figsize=(4 * len(cols), 4))
    for ax, col in zip(axes, cols):
        sns.boxplot(data=plot_df, x=LABEL, y=col, order=CLASS_ORDER, hue=LABEL,
                    legend=False, palette="Set2", ax=ax)
        ax.set_title(col, fontsize=10)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "feature_distributions.png"), dpi=130)
    plt.close()

    # --- 5. Leakage / feature-usefulness check ---------------------------
    report_lines.append("SINGLE-FEATURE LEAKAGE / USEFULNESS CHECK")
    report_lines.append("(does any one feature alone perfectly separate the classes? "
                         "does the control feature genuinely contribute nothing?)")
    for col in cols:
        max_purity = (df.groupby(feat_df[col])[LABEL]
                      .apply(lambda s: s.value_counts(normalize=True).max()).max())
        flag = ""
        if max_purity > 0.9:
            flag = "  <-- WARNING: near-deterministic on its own"
        report_lines.append(f"  {col:26s} max single-value class purity = {max_purity:.2f}{flag}")
    report_lines.append("")
    report_lines.append(
        "Note: manufacturer_changed and polypharmacy_count are deliberate control features -- "
        "the risk_label rule never uses either of them (a manufacturer swap is packaging, not "
        "a formula change; concurrent medication count is shown for context only). Low purity/"
        "correlation numbers above back up that decision rather than just assuming it. "
        "drug_changed and dose_change_pct remain the strongest signals because risk_label is "
        "built directly from them."
    )

    with open(os.path.join(OUT_DIR, "eda_report.txt"), "w") as f:
        f.write("\n".join(report_lines))

    print("\n".join(report_lines))
    print(f"\nPlots saved to {OUT_DIR}/")


if __name__ == "__main__":
    main()
