# Part of the backend -- works out what actually changed between a
# patient's last prescription and the new one.
"""
Compares a patient's current prescription against their previous one and
builds a structured report of what changed.

A few things worth knowing about how this works:
- drug_changed only fires on a genuine ingredient change, not a brand
  swap. Manufacturer changes are tracked separately and never affect
  risk -- packaging/company isn't a formula change.
- formulation_changed catches immediate- vs extended-release switches of
  the same drug, which matter clinically even without an ingredient change.
- narrow_therapeutic_index (NTI) drugs -- warfarin, digoxin,
  levothyroxine, insulin, lithium -- have a much smaller margin between
  an effective and a harmful dose, so the same percentage dose change is
  treated as more serious for these than for something like vitamin D.
- concurrent_medications / polypharmacy_count are just context shown to
  the pharmacist alongside the alert; they don't feed into the risk score.

The project plan called for this to be a Spring Boot service, but this
environment can't reach Maven Central, so it's Python/FastAPI here
instead. Same JSON contract either way, so that's a swappable detail,
not something the rest of the system depends on.
"""

from dataclasses import dataclass, field
from typing import Optional

# Drugs considered narrow therapeutic index (NTI): small gap between an
# effective dose and a harmful one, so smaller changes matter more.
# Mirrors data/generate_synthetic_data.py's DRUGS table -- kept as a
# simple lookup here since the live app only needs the NTI flag, not
# the full drug reference table.
NTI_DRUGS = {"Warfarin", "Apixaban", "Digoxin", "Levothyroxine", "Insulin Glargine", "Lithium"}


def is_narrow_therapeutic_index(drug_name: str) -> bool:
    """Checks a drug name against the NTI list above. Case/whitespace
    insensitive, and matches names that START WITH an NTI name followed by
    a word boundary (so "Digoxin 250mcg" still matches). Not plain
    substring matching -- that used to let a bare "Insulin" wrongly match
    "Insulin Glargine" just because one contains the other."""
    normalized = drug_name.strip().lower()
    for nti in NTI_DRUGS:
        nti_lower = nti.lower()
        if normalized == nti_lower or normalized.startswith(nti_lower + " "):
            return True
    return False


@dataclass
class Prescription:
    drug_name: str
    dose_mg: float
    formulation: str
    manufacturer: str
    route: str
    start_date: str
    prescriber: str


@dataclass
class ChangeReport:
    patient_id: str
    drug_changed: bool
    formulation_changed: bool
    manufacturer_changed: bool
    dose_changed: bool
    dose_change_pct: float
    route_changed: bool
    narrow_therapeutic_index: bool
    change_types: list = field(default_factory=list)
    previous: Optional[dict] = None
    current: Optional[dict] = None
    magnitude_summary: str = ""


def compare_prescriptions(patient_id: str, previous: Prescription, current: Prescription) -> ChangeReport:
    drug_changed = previous.drug_name != current.drug_name
    formulation_changed = (not drug_changed) and (previous.formulation != current.formulation)
    manufacturer_changed = previous.manufacturer != current.manufacturer
    dose_changed = previous.dose_mg != current.dose_mg
    dose_change_pct = 0.0
    if previous.dose_mg:
        dose_change_pct = round((previous.dose_mg - current.dose_mg) / previous.dose_mg, 4)
    route_changed = previous.route != current.route

    narrow_therapeutic_index = (
        is_narrow_therapeutic_index(previous.drug_name) or is_narrow_therapeutic_index(current.drug_name)
    )

    # manufacturer_changed is tracked and shown to the pharmacist but
    # deliberately left out of change_types -- a packaging/brand swap on
    # its own shouldn't trigger an alert.
    change_types = []
    if drug_changed:
        change_types.append("drug")
    if formulation_changed:
        change_types.append("formulation")
    if dose_changed:
        change_types.append("dose")
    if route_changed:
        change_types.append("route")

    parts = []
    if drug_changed:
        parts.append(f"drug changed from {previous.drug_name} to {current.drug_name}")
    if formulation_changed:
        parts.append(f"formulation changed from {previous.formulation} to {current.formulation}")
    if dose_changed:
        direction = "reduced" if dose_change_pct > 0 else "increased"
        parts.append(f"dose {direction} from {previous.dose_mg}mg to {current.dose_mg}mg "
                      f"({abs(dose_change_pct) * 100:.0f}%)")
    if route_changed:
        parts.append(f"route changed from {previous.route} to {current.route}")
    if manufacturer_changed and not parts:
        # only worth a mention if it's literally the only difference
        parts.append(f"manufacturer changed from {previous.manufacturer} to {current.manufacturer} "
                      f"(same formula, no risk-relevant change)")
    magnitude_summary = "; ".join(parts) if parts else "no change detected"

    return ChangeReport(
        patient_id=patient_id,
        drug_changed=drug_changed,
        formulation_changed=formulation_changed,
        manufacturer_changed=manufacturer_changed,
        dose_changed=dose_changed,
        dose_change_pct=dose_change_pct,
        route_changed=route_changed,
        narrow_therapeutic_index=narrow_therapeutic_index,
        change_types=change_types,
        previous=previous.__dict__,
        current=current.__dict__,
        magnitude_summary=magnitude_summary,
    )


def classify_risk(*, drug_changed: bool, formulation_changed: bool, dose_changed: bool,
                   dose_change_pct: float, route_changed: bool,
                   narrow_therapeutic_index: bool) -> str:
    """The one risk rule used across the whole project -- main.py calls it
    for the live alert, and both data-generation scripts call it to label
    their datasets, so it can't quietly drift into three different
    versions of "the same" logic. This is a transparent reference rule,
    not a clinically validated scoring system.

    Random Forest and the text model never feed into this -- they're
    shown alongside it for comparison, nothing more.

    Keyword-only args so a call site can't silently mix up the order."""
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


def natural_language_description(report: ChangeReport, condition: str, allergy: str,
                                  concurrent_medications: str = "") -> str:
    """Builds the natural-language sentence fed to the ClinicalBERT-style
    text classifier. Includes concurrent medications for polypharmacy
    context, matching how a pharmacist would actually read the change."""
    context = f"Patient with {condition} (allergy: {allergy})"
    if concurrent_medications:
        context += f", also currently taking {concurrent_medications}"

    if not report.change_types:
        return f"{context}: no risk-relevant prescription change."
    return f"{context}: {report.magnitude_summary}."
