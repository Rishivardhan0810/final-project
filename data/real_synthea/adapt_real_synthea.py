"""
Adapts REAL Synthea medications.csv (genuine Synthea v3+ output, not
the Python-generated substitute) into prescription change-pairs
matching this project's v2 schema, so the already-trained models can
be evaluated against genuine synthetic clinical data.

WHAT'S DIFFERENT IN v2:
  - formulation is extracted from the free-text DESCRIPTION (looking
    for "Extended Release" / "ER" / "XR" markers) rather than assumed
    "Standard" for everything.
  - narrow_therapeutic_index is looked up from the same NTI drug list
    the live app uses (backend/comparison_engine.py), matched against
    the extracted drug name.
  - manufacturer: real Synthea's medications.csv has no manufacturer
    field at all, so manufacturer_changed is always False here (marked
    "not available in source data", not silently assumed unchanged).
    This is an honest gap in the real dataset, not a design choice.
  - risk_label is recomputed with the same pharmacology-scaled rule as
    the synthetic generator (thresholds vary by narrow_therapeutic_index).

Why this remains a separate, external evaluation set and NOT added to
training data: only ~30 genuine same-condition change pairs across 104
patients -- too few and too skewed toward drug switches to train on.
"""
import csv
import os
import re
import sys
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_PATH = os.path.join(HERE, "medications_raw.csv")
OUT_PATH = os.path.join(HERE, "real_test.csv")

sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))
from comparison_engine import NTI_DRUGS  # noqa: E402 -- single source of truth for NTI status

ROUTE_KEYWORDS = [
    ("Auto-Injector", "Injection"),
    ("Prefilled Syringe", "Injection"),
    ("Injection", "Injection"),
    ("Chewable Tablet", "Oral"),
    ("Oral Tablet", "Oral"),
    ("Oral Capsule", "Oral"),
    ("Oral Solution", "Oral"),
    ("Oral Gel", "Oral"),
    ("Oral Suspension", "Oral"),
    ("Transdermal", "Topical"),
    ("Topical", "Topical"),
    ("Nasal Spray", "Nasal"),
    ("Inhalant", "Inhaled"),
]

FORMULATION_KEYWORDS = [
    ("Extended Release", "Extended-release"),
    ("Extended-Release", "Extended-release"),
    ("24 HR", "Extended-release"),
    ("12 HR", "Extended-release"),
    ("XR ", "Extended-release"),
    (" ER ", "Extended-release"),
]


def extract_route(desc):
    for kw, route in ROUTE_KEYWORDS:
        if kw.lower() in desc.lower():
            return route
    return "Other"


def extract_formulation(desc):
    for kw, formulation in FORMULATION_KEYWORDS:
        if kw.lower() in desc.lower():
            return formulation
    return "Standard"


def extract_dose(desc):
    """First 'NUMBER MG' occurrence in the description. A proxy, not an
    exact structured dose -- combination drugs will only capture the
    first value."""
    matches = re.findall(r"(\d+\.?\d*)\s*MG\b", desc, re.IGNORECASE)
    return float(matches[0]) if matches else None


def extract_drug_name(desc):
    m = re.match(r"^([A-Za-z][A-Za-z\-]*(?:\s[A-Za-z][A-Za-z\-]*)?)", desc)
    return (m.group(1).strip() if m else desc.split(" ")[0]).lower()


def is_narrow_therapeutic_index(drug_name_lower):
    return any(nti.lower() in drug_name_lower or drug_name_lower in nti.lower() for nti in NTI_DRUGS)


def risk_label_for(drug_changed, formulation_changed, dose_changed, dose_change_pct,
                    route_changed, narrow_therapeutic_index):
    if not (drug_changed or formulation_changed or dose_changed or route_changed):
        return "NONE"
    if drug_changed:
        return "HIGH" if narrow_therapeutic_index else "MEDIUM"
    if formulation_changed:
        return "HIGH" if narrow_therapeutic_index else "MEDIUM"
    if dose_changed:
        threshold = 0.25 if narrow_therapeutic_index else 0.50
        if abs(dose_change_pct) >= threshold:
            return "HIGH"
        return "MEDIUM" if narrow_therapeutic_index else "LOW"
    if route_changed:
        return "LOW"
    return "NONE"


def main():
    with open(RAW_PATH) as f:
        rows = list(csv.DictReader(f))

    by_patient_reason = collections.defaultdict(list)
    for r in rows:
        if r["REASONDESCRIPTION"]:
            key = (r["PATIENT"], r["REASONDESCRIPTION"])
            by_patient_reason[key].append(r)

    pairs = []
    for (patient_id, condition), meds in by_patient_reason.items():
        meds.sort(key=lambda r: r["START"])
        collapsed = []
        for m in meds:
            if not collapsed or collapsed[-1]["DESCRIPTION"] != m["DESCRIPTION"]:
                collapsed.append(m)
        if len(collapsed) < 2:
            continue

        prev, cur = collapsed[-2], collapsed[-1]
        prev_desc, cur_desc = prev["DESCRIPTION"], cur["DESCRIPTION"]

        prev_drug, cur_drug = extract_drug_name(prev_desc), extract_drug_name(cur_desc)
        prev_dose, cur_dose = extract_dose(prev_desc), extract_dose(cur_desc)
        prev_route, cur_route = extract_route(prev_desc), extract_route(cur_desc)
        prev_formulation, cur_formulation = extract_formulation(prev_desc), extract_formulation(cur_desc)

        if prev_dose is None or cur_dose is None:
            continue

        drug_changed = prev_drug != cur_drug
        formulation_changed = (not drug_changed) and (prev_formulation != cur_formulation)
        dose_changed = prev_dose != cur_dose
        dose_change_pct = 0.0 if prev_dose == 0 else (prev_dose - cur_dose) / prev_dose
        route_changed = prev_route != cur_route
        narrow_therapeutic_index = is_narrow_therapeutic_index(prev_drug) or is_narrow_therapeutic_index(cur_drug)

        pairs.append({
            "patient_id": patient_id,
            "condition": condition,
            "previous_drug": prev_drug,
            "previous_dose_mg": prev_dose,
            "previous_formulation": prev_formulation,
            "previous_route": prev_route,
            "previous_description": prev_desc,
            "current_drug": cur_drug,
            "current_dose_mg": cur_dose,
            "current_formulation": cur_formulation,
            "current_route": cur_route,
            "current_description": cur_desc,
            "drug_changed": drug_changed,
            "formulation_changed": formulation_changed,
            "manufacturer_changed": False,  # not available in real Synthea medications.csv
            "route_changed": route_changed,
            "dose_changed": dose_changed,
            "dose_change_pct": round(dose_change_pct, 3),
            "narrow_therapeutic_index": narrow_therapeutic_index,
            "risk_label": risk_label_for(drug_changed, formulation_changed, dose_changed,
                                          dose_change_pct, route_changed, narrow_therapeutic_index),
        })

    if not pairs:
        print("No usable change-pairs extracted -- nothing to write.")
        return

    with open(OUT_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(pairs[0].keys()))
        w.writeheader()
        w.writerows(pairs)

    counts = collections.Counter(p["risk_label"] for p in pairs)
    nti_count = sum(1 for p in pairs if p["narrow_therapeutic_index"])
    print(f"Extracted {len(pairs)} real prescription-change pairs from {len(by_patient_reason)} "
          f"patient-condition groups ({len(set(r['PATIENT'] for r in rows))} total patients in the raw file).")
    print(f"Risk label distribution: {dict(counts)}")
    print(f"Pairs involving a narrow-therapeutic-index drug: {nti_count}/{len(pairs)}")
    print(f"Saved -> {OUT_PATH}")
    print(
        "\nNOTE: manufacturer_changed is always False here -- real Synthea's medications.csv has "
        "no manufacturer field at all, so this is an honest gap in the source data, not an "
        "assumption. This is used as an EXTERNAL VALIDATION set for the already-trained models, "
        "not for training. See backend/risk_models/evaluate_real_synthea.py."
    )


if __name__ == "__main__":
    main()
