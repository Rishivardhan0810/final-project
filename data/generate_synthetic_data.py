# PART OF: Data Pipeline -- Data Generation (the very first step; makes
# patients.csv and medications.csv that every other script builds on)
"""
Synthetic patient prescription data generator -- v2.

WHAT CHANGED FROM v1, AND WHY (supervisor feedback after the meeting):

1. "Categorise them properly" -> every drug now has a therapeutic_class
   (e.g. Anticoagulant, ACE inhibitor, SSRI) instead of sitting in a flat
   list with no grouping.

2. "Involve prior medications" -> every patient now has a list of
   concurrent_medications (0-3 other drugs they're already taking),
   shown alongside the alert for context, and summarised as a
   polypharmacy_count feature.

3. "Think like a scientist / behind the science" -> risk is no longer
   one flat rule for every drug. Each drug is flagged
   narrow_therapeutic_index (NTI) or not -- a real pharmacology concept:
   NTI drugs (warfarin, digoxin, levothyroxine, insulin, lithium) have a
   small gap between an effective dose and a harmful one, so smaller
   changes matter more. Risk thresholds scale with this, not a single
   fixed percentage for every drug regardless of what it is.

4. "Focus on formula changes, not companies/packaging" -> drug_changed
   now means the ACTIVE INGREDIENT changed. A separate
   formulation_changed flag captures immediate-release vs
   extended-release swaps of the SAME ingredient (genuinely risk
   relevant). A separate manufacturer_changed flag captures brand/
   generic-maker swaps of the identical formula (NOT risk relevant --
   generated on purpose so the EDA/feature-selection step can PROVE it
   contributes nothing, rather than just asserting it).

5. "Focus on data patterns / algorithm / analysing" -> the richer
   feature set (6 features now instead of 4) gives EDA and feature
   selection more real work to do -- see data/eda.py and
   data/preprocess.py, which decide what to keep based on evidence.
"""

import csv
import random
import uuid
from datetime import date, timedelta

random.seed(42)

# --- Reference drug data -----------------------------------------------
# Each drug: name, therapeutic_class, narrow_therapeutic_index (NTI),
# available formulations (>1 means a formulation-change scenario is
# possible), typical doses (mg), route, associated condition.
DRUGS = [
    {"name": "Warfarin", "class": "Anticoagulant", "nti": True,
     "formulations": ["Standard"], "doses": [1, 2, 3, 5, 10],
     "route": "Oral", "condition": "Atrial fibrillation"},
    {"name": "Apixaban", "class": "Anticoagulant", "nti": True,
     "formulations": ["Standard"], "doses": [2.5, 5],
     "route": "Oral", "condition": "Atrial fibrillation"},
    {"name": "Digoxin", "class": "Cardiac glycoside", "nti": True,
     "formulations": ["Standard"], "doses": [0.0625, 0.125, 0.25],
     "route": "Oral", "condition": "Heart failure"},
    {"name": "Levothyroxine", "class": "Thyroid hormone", "nti": True,
     "formulations": ["Standard"], "doses": [25, 50, 75, 100, 125],
     "route": "Oral", "condition": "Hypothyroidism"},
    {"name": "Insulin Glargine", "class": "Insulin", "nti": True,
     "formulations": ["Standard"], "doses": [10, 20, 30, 40],
     "route": "Subcutaneous", "condition": "Type 1 diabetes"},
    {"name": "Lithium", "class": "Mood stabiliser", "nti": True,
     "formulations": ["Immediate-release", "Extended-release"], "doses": [200, 400, 600, 800],
     "route": "Oral", "condition": "Bipolar disorder"},

    {"name": "Metformin", "class": "Biguanide (antidiabetic)", "nti": False,
     "formulations": ["Immediate-release", "Extended-release"], "doses": [500, 850, 1000],
     "route": "Oral", "condition": "Type 2 diabetes"},
    {"name": "Amlodipine", "class": "Calcium channel blocker", "nti": False,
     "formulations": ["Standard"], "doses": [5, 10],
     "route": "Oral", "condition": "Hypertension"},
    {"name": "Ramipril", "class": "ACE inhibitor", "nti": False,
     "formulations": ["Standard"], "doses": [1.25, 2.5, 5, 10],
     "route": "Oral", "condition": "Hypertension"},
    {"name": "Bisoprolol", "class": "Beta-blocker", "nti": False,
     "formulations": ["Standard"], "doses": [1.25, 2.5, 5, 10],
     "route": "Oral", "condition": "Heart failure"},
    {"name": "Atorvastatin", "class": "Statin", "nti": False,
     "formulations": ["Standard"], "doses": [10, 20, 40, 80],
     "route": "Oral", "condition": "Hyperlipidaemia"},
    {"name": "Salbutamol", "class": "Beta-2 agonist (bronchodilator)", "nti": False,
     "formulations": ["Standard"], "doses": [100, 200],
     "route": "Inhaled", "condition": "Asthma"},
    {"name": "Omeprazole", "class": "Proton pump inhibitor", "nti": False,
     "formulations": ["Immediate-release", "Extended-release"], "doses": [10, 20, 40],
     "route": "Oral", "condition": "GORD"},
    {"name": "Sertraline", "class": "SSRI (antidepressant)", "nti": False,
     "formulations": ["Standard"], "doses": [50, 100, 150],
     "route": "Oral", "condition": "Depression"},
    {"name": "Furosemide", "class": "Loop diuretic", "nti": False,
     "formulations": ["Immediate-release", "Extended-release"], "doses": [20, 40, 80],
     "route": "Oral", "condition": "Heart failure"},
    {"name": "Vitamin D", "class": "Supplement", "nti": False,
     "formulations": ["Standard"], "doses": [400, 800, 1000],
     "route": "Oral", "condition": "Vitamin D deficiency"},
    {"name": "Prednisolone", "class": "Corticosteroid", "nti": False,
     "formulations": ["Standard"], "doses": [5, 10, 20, 40],
     "route": "Oral", "condition": "COPD exacerbation"},
]

MANUFACTURERS = ["Accord Healthcare", "Teva", "Mylan", "Sandoz", "Wockhardt", "Actavis"]
ALLERGIES = ["Penicillin", "None recorded", "Sulphonamides", "NSAIDs", "None recorded", "None recorded"]
GP_NAMES = ["Dr A. Okafor", "Dr S. Patel", "Dr J. McAllister", "Dr R. Chowdhury", "Dr E. Novak", "Dr F. Bianchi"]

FIRST_NAMES = ["James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
               "William", "Elizabeth", "David", "Susan", "Richard", "Jessica", "Joseph", "Sarah",
               "Thomas", "Karen", "Charles", "Nancy", "Aisha", "Mohammed", "Priya", "Wei", "Fatima", "Liam"]
LAST_NAMES = ["Smith", "Jones", "Taylor", "Brown", "Williams", "Wilson", "Johnson", "Davies",
              "Robinson", "Wright", "Thompson", "Evans", "Walker", "White", "Roberts", "Green",
              "Hall", "Wood", "Khan", "Patel", "Singh", "Ahmed", "Kelly", "Baker"]


def random_date(start, end):
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def gen_patients(n):
    patients = []
    for _ in range(n):
        pid = str(uuid.uuid4())[:8]
        dob = random_date(date(1935, 1, 1), date(2008, 12, 31))
        patients.append({
            "patient_id": pid,
            "first_name": random.choice(FIRST_NAMES),
            "last_name": random.choice(LAST_NAMES),
            "date_of_birth": dob.isoformat(),
            "allergy": random.choice(ALLERGIES),
            "gp_name": random.choice(GP_NAMES),
        })
    return patients


def pick_concurrent_medications(index_drug, k):
    """Picks k other drugs (not the index drug) this patient is also
    currently taking, for polypharmacy context. Used for display and
    as a summary count feature -- deliberately NOT part of the risk
    rule, so feature selection can show it doesn't help."""
    pool = [d for d in DRUGS if d["name"] != index_drug["name"]]
    k = min(k, len(pool))
    return random.sample(pool, k)


def make_prescription_pair(patient, drug):
    prev_dose = random.choice(drug["doses"])
    prev_formulation = random.choice(drug["formulations"])
    prev_manufacturer = random.choice(MANUFACTURERS)
    prev_start = random_date(date(2025, 1, 1), date(2026, 4, 1))

    change_type = random.choices(
        ["none", "dose_increase", "dose_decrease_small", "dose_decrease_large",
         "drug_switch", "formulation_switch", "manufacturer_switch_only", "route_change"],
        weights=[12, 13, 13, 13, 15, 13, 11, 10], k=1
    )[0]

    cur_dose = prev_dose
    cur_formulation = prev_formulation
    cur_manufacturer = prev_manufacturer
    cur_route = drug["route"]
    cur_drug = drug

    if change_type == "dose_increase":
        higher = [d for d in drug["doses"] if d > prev_dose]
        cur_dose = random.choice(higher) if higher else prev_dose
        cur_manufacturer = random.choice(MANUFACTURERS)
    elif change_type == "dose_decrease_small":
        lower = [d for d in drug["doses"] if 0 < prev_dose - d and (prev_dose - d) / prev_dose < 0.5]
        cur_dose = random.choice(lower) if lower else prev_dose
        cur_manufacturer = random.choice(MANUFACTURERS)
    elif change_type == "dose_decrease_large":
        lower = [d for d in drug["doses"] if d < prev_dose and (prev_dose - d) / prev_dose >= 0.5]
        cur_dose = random.choice(lower) if lower else (drug["doses"][0] if drug["doses"][0] < prev_dose else prev_dose)
        cur_manufacturer = random.choice(MANUFACTURERS)
    elif change_type == "drug_switch":
        alt_pool = [d for d in DRUGS if d["condition"] == drug["condition"] and d["name"] != drug["name"]] \
            or [d for d in DRUGS if d["name"] != drug["name"]]
        cur_drug = random.choice(alt_pool)
        cur_dose = random.choice(cur_drug["doses"])
        cur_formulation = random.choice(cur_drug["formulations"])
        cur_route = cur_drug["route"]
        cur_manufacturer = random.choice(MANUFACTURERS)
    elif change_type == "formulation_switch":
        alt_forms = [f for f in drug["formulations"] if f != prev_formulation]
        if alt_forms:
            cur_formulation = random.choice(alt_forms)
        cur_manufacturer = random.choice(MANUFACTURERS)
    elif change_type == "manufacturer_switch_only":
        alt_mfrs = [m for m in MANUFACTURERS if m != prev_manufacturer]
        cur_manufacturer = random.choice(alt_mfrs) if alt_mfrs else prev_manufacturer
    elif change_type == "route_change":
        cur_route = "Oral" if drug["route"] != "Oral" else "Subcutaneous"

    cur_start = prev_start + timedelta(days=random.randint(14, 120))

    # --- Derive ACTUAL features from real before/after values ---------
    drug_changed = cur_drug["name"] != drug["name"]
    formulation_changed = (not drug_changed) and (cur_formulation != prev_formulation)
    manufacturer_changed = cur_manufacturer != prev_manufacturer
    route_changed = cur_route != drug["route"]
    dose_changed = cur_dose != prev_dose
    dose_pct_change = 0.0 if prev_dose == 0 else (prev_dose - cur_dose) / prev_dose
    narrow_therapeutic_index = drug["nti"] or (drug_changed and cur_drug["nti"])

    concurrent = pick_concurrent_medications(drug, random.choice([0, 1, 1, 2, 2, 3]))
    polypharmacy_count = len(concurrent)

    # --- Risk rule v2: thresholds scale with pharmacology, not a flat rule ---
    if not (drug_changed or formulation_changed or dose_changed or route_changed):
        risk_label = "NONE"
    elif drug_changed:
        risk_label = "HIGH" if narrow_therapeutic_index else "MEDIUM"
    elif formulation_changed:
        risk_label = "HIGH" if narrow_therapeutic_index else "MEDIUM"
    elif dose_changed:
        threshold = 0.25 if narrow_therapeutic_index else 0.50
        if abs(dose_pct_change) >= threshold:
            risk_label = "HIGH"
        else:
            risk_label = "MEDIUM" if narrow_therapeutic_index else "LOW"
    elif route_changed:
        risk_label = "LOW"
    else:
        risk_label = "NONE"

    return {
        "patient_id": patient["patient_id"],
        "condition": drug["condition"],
        "previous_drug": drug["name"],
        "previous_class": drug["class"],
        "previous_dose_mg": prev_dose,
        "previous_formulation": prev_formulation,
        "previous_manufacturer": prev_manufacturer,
        "previous_route": drug["route"],
        "previous_start_date": prev_start.isoformat(),
        "previous_prescriber": patient["gp_name"],
        "current_drug": cur_drug["name"],
        "current_class": cur_drug["class"],
        "current_dose_mg": cur_dose,
        "current_formulation": cur_formulation,
        "current_manufacturer": cur_manufacturer,
        "current_route": cur_route,
        "current_start_date": cur_start.isoformat(),
        "current_prescriber": patient["gp_name"],
        "change_type_label": change_type,
        "drug_changed": drug_changed,
        "formulation_changed": formulation_changed,
        "manufacturer_changed": manufacturer_changed,
        "route_changed": route_changed,
        "dose_changed": dose_changed,
        "dose_change_pct": round(dose_pct_change, 3),
        "narrow_therapeutic_index": narrow_therapeutic_index,
        "concurrent_medications": "; ".join(d["name"] for d in concurrent),
        "polypharmacy_count": polypharmacy_count,
        "risk_label": risk_label,
    }


def main(per_class=150, out_dir="."):
    """Quota-sampled generation, same balancing approach as before, now
    over the richer feature/label set above."""
    targets = {"NONE": per_class, "LOW": per_class, "MEDIUM": per_class, "HIGH": per_class}
    counts = {k: 0 for k in targets}
    patients, rows = [], []
    attempts, max_attempts = 0, per_class * 4 * 400

    while any(counts[k] < targets[k] for k in targets) and attempts < max_attempts:
        attempts += 1
        p = gen_patients(1)[0]
        drug = random.choice(DRUGS)
        pair = make_prescription_pair(p, drug)
        label = pair["risk_label"]

        if counts.get(label, 0) >= targets.get(label, 0):
            continue

        counts[label] += 1
        pair["first_name"] = p["first_name"]
        pair["last_name"] = p["last_name"]
        pair["date_of_birth"] = p["date_of_birth"]
        pair["allergy"] = p["allergy"]
        patients.append(p)
        rows.append(pair)

    if attempts >= max_attempts:
        print(f"WARNING: hit max_attempts with counts={counts} (target {per_class} each)")

    combined = list(zip(patients, rows))
    random.shuffle(combined)
    patients, rows = zip(*combined)
    patients, rows = list(patients), list(rows)

    patients_path = f"{out_dir}/patients.csv"
    with open(patients_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(patients[0].keys()))
        w.writeheader()
        w.writerows(patients)

    meds_path = f"{out_dir}/medications.csv"
    with open(meds_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"Generated {len(patients)} patients -> {patients_path}")
    print(f"Generated {len(rows)} prescription pairs -> {meds_path}")
    print(f"Class balance: {counts}")
    print(f"Drugs: {len(DRUGS)} across {len(set(d['class'] for d in DRUGS))} therapeutic classes, "
          f"{sum(1 for d in DRUGS if d['nti'])} narrow-therapeutic-index")


if __name__ == "__main__":
    main()
