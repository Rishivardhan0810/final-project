"""
Comparison engine v2: compares a patient's current EPS prescription
against their most recent previous prescription and returns a
structured, pharmacologically-aware change report.

WHAT CHANGED FROM v1:
- drug_changed now means the ACTIVE INGREDIENT changed (a real formula
  change), not a brand/manufacturer swap.
- formulation_changed captures immediate-release vs extended-release
  switches of the SAME active ingredient -- a genuinely risk-relevant
  change that v1 couldn't see at all.
- manufacturer_changed is tracked separately and explicitly excluded
  from risk scoring -- generated on purpose so the data can prove
  packaging/company changes don't matter, rather than just asserting it.
- narrow_therapeutic_index (NTI) is now part of the comparison: drugs
  like warfarin, digoxin, levothyroxine, insulin, and lithium have a
  small safety margin between an effective and a harmful dose, so the
  same percentage dose change means more for these than for a
  wide-margin drug like vitamin D.
- concurrent_medications / polypharmacy_count give the pharmacist
  fuller context (what else is this patient on?), matching real
  clinical practice where a change is never judged in isolation.

NOTE ON SUBSTITUTION: the project plan specifies Spring Boot (Java).
This sandbox has no network route to Maven Central, so the engine is
implemented in Python instead. The REST contract (JSON in/out) is
identical, so a real Spring Boot service could replace this file
without changing the risk models or the React frontend.
"""

from dataclasses import dataclass, field
from typing import Optional

# Drugs considered narrow therapeutic index (NTI): small gap between an
# effective dose and a harmful one, so smaller changes matter more.
# Mirrors data/generate_synthetic_data.py's DRUGS table -- kept as a
# simple lookup here since the live app only needs the NTI flag, not
# the full drug reference table.
NTI_DRUGS = {"Warfarin", "Apixaban", "Digoxin", "Levothyroxine", "Insulin Glargine", "Lithium"}


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
        previous.drug_name in NTI_DRUGS or current.drug_name in NTI_DRUGS
    )

    # change_types intentionally excludes manufacturer_changed -- a
    # packaging/brand swap is tracked (see manufacturer_changed above,
    # and it's still shown to the pharmacist) but does not, by itself,
    # trigger an alert or contribute to risk scoring.
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
        # Only mention a manufacturer-only swap if nothing else changed,
        # so the sentence is honest that it's the sole difference (and
        # the models can learn this carries no extra risk signal).
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
