// Patient record screen -- banner, prescription tables, and the Dispense
// button (calls /api/dispense)
import { useState } from "react";
import AlertPanel from "./AlertPanel";

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export default function RecordScreen({ data, apiBase, onBack }) {
  const { patient, prescriptions, alert, status, status_message } = data;
  const [acknowledged, setAcknowledged] = useState(false);
  const [ackBusy, setAckBusy] = useState(false);
  const [pharmacistName, setPharmacistName] = useState("");
  const [dispenseBusy, setDispenseBusy] = useState(false);
  const [dispensed, setDispensed] = useState(false);

  // status comes from the backend: "no_prescriptions" (patient exists but
  // has none on record), "first_prescription" (exactly one -- nothing to
  // compare against yet), or "normal" (two or more -- the usual
  // compare-and-score flow).
  const isNoPrescriptions = status === "no_prescriptions";
  const isFirstPrescription = status === "first_prescription";
  const current = prescriptions.length > 0 ? prescriptions[prescriptions.length - 1] : null;

  // concurrent_medications comes straight from the patient record (already
  // returned by /api/lookup) -- just split into a readable list here, no
  // interaction logic of any kind.
  const concurrentMedsList = (patient.concurrent_medications || "")
    .split(";")
    .map((m) => m.trim())
    .filter(Boolean);

  // Dispense is locked if: there's an unacknowledged risk alert, this is an
  // unreviewed first prescription, or there's no prescription to dispense at all.
  const dispenseLocked =
    isNoPrescriptions || (Boolean(alert) && !acknowledged) || (isFirstPrescription && !acknowledged);

  // only the plain "nothing changed" case needs its own name field here --
  // the alert flow and first-prescription flow already collect it
  const needsInlineDispenseName = !alert && !isFirstPrescription && !isNoPrescriptions;

  async function handleDispense() {
    if (!pharmacistName.trim() || !current) return;
    setDispenseBusy(true);
    try {
      await fetch(`${apiBase}/api/dispense`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_id: patient.patient_id,
          pharmacist_name: pharmacistName.trim(),
          drug_name: current.drug_name,
          dose_mg: current.dose_mg,
        }),
      });
      setDispensed(true);
    } catch {
      // demo prototype: confirm locally even if the log call fails
      setDispensed(true);
    } finally {
      setDispenseBusy(false);
    }
  }

  async function handleAcknowledge() {
    if (!pharmacistName.trim()) return;
    setAckBusy(true);
    try {
      await fetch(`${apiBase}/api/acknowledge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_id: patient.patient_id,
          pharmacist_name: pharmacistName.trim(),
          risk_level: alert.risk_final,
        }),
      });
      setAcknowledged(true);
    } catch {
      // demo prototype: acknowledge locally even if the log call fails
      setAcknowledged(true);
    } finally {
      setAckBusy(false);
    }
  }

  // reuses the same /api/acknowledge endpoint as a risk-alert
  // acknowledgement -- risk_level has no NONE/LOW/MEDIUM/HIGH constraint,
  // so this sentinel keeps a first-prescription review distinguishable in
  // the audit trail without needing a schema change
  async function handleAcknowledgeFirstPrescription() {
    if (!pharmacistName.trim()) return;
    setAckBusy(true);
    try {
      await fetch(`${apiBase}/api/acknowledge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_id: patient.patient_id,
          pharmacist_name: pharmacistName.trim(),
          risk_level: "FIRST_PRESCRIPTION_REVIEW",
        }),
      });
      setAcknowledged(true);
    } catch {
      // demo prototype: acknowledge locally even if the log call fails
      setAcknowledged(true);
    } finally {
      setAckBusy(false);
    }
  }

  return (
    <div className="record-wrap">
      <div className="record-toolbar">
        <button className="btn btn-ghost" onClick={onBack}>&larr; New search</button>
      </div>

      <section className="patient-banner">
        <div>
          <h1>{patient.first_name} {patient.last_name}</h1>
          <p className="patient-meta">
            DOB {fmtDate(patient.date_of_birth)} &middot; Patient ID {patient.patient_id} &middot; GP {patient.gp_name}
          </p>
        </div>
        <div className="patient-tags">
          <span className="tag">Condition: {patient.condition || "—"}</span>
          <span className={`tag ${patient.allergy && patient.allergy !== "None recorded" ? "tag-warn" : ""}`}>
            Allergy: {patient.allergy || "—"}
          </span>
          {patient.polypharmacy_count > 0 && (
            <span className="tag">Also on {patient.polypharmacy_count} other medication{patient.polypharmacy_count > 1 ? "s" : ""}</span>
          )}
        </div>
      </section>

      <section className="concurrent-meds-panel">
        <h2>Concurrent medications</h2>
        {concurrentMedsList.length > 0 ? (
          <ul className="concurrent-meds-list">
            {concurrentMedsList.map((med) => (
              <li key={med}>{med}</li>
            ))}
          </ul>
        ) : (
          <p className="concurrent-meds-empty">No concurrent medications recorded.</p>
        )}
        <p className="concurrent-meds-note">
          Drug–drug interaction checking is not automated in this prototype. Pharmacist
          clinical review is required.
        </p>
      </section>

      {alert && (
        <AlertPanel
          alert={alert}
          concurrentMedications={patient.concurrent_medications}
          acknowledged={acknowledged}
          ackBusy={ackBusy}
          pharmacistName={pharmacistName}
          setPharmacistName={setPharmacistName}
          onAcknowledge={handleAcknowledge}
        />
      )}

      {isFirstPrescription && !acknowledged && (
        <section className="first-rx-panel" role="alert">
          <p className="first-rx-title">First prescription &mdash; no previous record available</p>
          <p className="first-rx-explain">{status_message}</p>
          <div className="alert-ack-row">
            <label className="field field-inline">
              <span>Your name</span>
              <input
                value={pharmacistName}
                onChange={(e) => setPharmacistName(e.target.value)}
                placeholder="Pharmacist name"
              />
            </label>
            <button
              className="btn btn-acknowledge"
              disabled={!pharmacistName.trim() || ackBusy}
              onClick={handleAcknowledgeFirstPrescription}
            >
              {ackBusy ? "Logging…" : "First prescription reviewed"}
            </button>
          </div>
        </section>
      )}

      {isFirstPrescription && acknowledged && (
        <section className="first-rx-resolved">
          <span className="alert-resolved-icon" aria-hidden="true">&#10003;</span>
          <div>
            <p className="alert-resolved-title">First prescription reviewed</p>
            <p className="alert-resolved-sub">Logged for {pharmacistName} &middot; Dispense is now unlocked.</p>
          </div>
        </section>
      )}

      {isNoPrescriptions && (
        <section className="no-rx-panel">{status_message}</section>
      )}

      {current && (
        <section className="rx-panel">
          <h2>Current EPS prescription</h2>
          <table className="rx-table">
            <thead>
              <tr><th>Drug</th><th>Class</th><th>Dose</th><th>Formulation</th><th>Route</th><th>Manufacturer</th><th>Start date</th></tr>
            </thead>
            <tbody>
              <tr>
                <td>{current.drug_name}</td>
                <td>{current.drug_class}</td>
                <td>{current.dose_mg}mg</td>
                <td>{current.formulation}</td>
                <td>{current.route}</td>
                <td>{current.manufacturer}</td>
                <td>{fmtDate(current.start_date)}</td>
              </tr>
            </tbody>
          </table>

          <h2 className="rx-history-heading">Prescription history</h2>
          <table className="rx-table rx-table-history">
            <thead>
              <tr><th>Drug</th><th>Class</th><th>Dose</th><th>Formulation</th><th>Route</th><th>Manufacturer</th><th>Start date</th></tr>
            </thead>
            <tbody>
              {[...prescriptions].reverse().map((rx) => (
                <tr key={rx.prescription_id} className={rx.is_current ? "row-current" : ""}>
                  <td>{rx.drug_name}</td>
                  <td>{rx.drug_class}</td>
                  <td>{rx.dose_mg}mg</td>
                  <td>{rx.formulation}</td>
                  <td>{rx.route}</td>
                  <td>{rx.manufacturer}</td>
                  <td>{fmtDate(rx.start_date)}{rx.is_current ? " (current)" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {!isNoPrescriptions && (
        <section className="dispense-panel">
          {dispensed ? (
            <p className="dispense-confirm">
              <span aria-hidden="true">&#10003;</span> Dispensed by {pharmacistName.trim()} &middot;{" "}
              {current.drug_name} {current.dose_mg}mg logged for {patient.first_name} {patient.last_name}.
            </p>
          ) : (
            <>
              {needsInlineDispenseName && (
                <label className="field field-inline">
                  <span>Pharmacist name</span>
                  <input
                    value={pharmacistName}
                    onChange={(e) => setPharmacistName(e.target.value)}
                    placeholder="Pharmacist name"
                  />
                </label>
              )}
              <button
                className="btn btn-dispense"
                disabled={dispenseLocked || !pharmacistName.trim() || dispenseBusy}
                title={dispenseLocked ? "Review or acknowledge the panel above to unlock" : !pharmacistName.trim() ? "Enter your name to dispense" : ""}
                onClick={handleDispense}
              >
                {dispenseLocked
                  ? "🔒 Dispense (locked until reviewed)"
                  : dispenseBusy
                    ? "Logging…"
                    : "Dispense"}
              </button>
            </>
          )}
          <p className="dispense-hint">
            Barcode scan on collection verifies the box matches this current prescription {"—"} it
            does not check whether the prescription itself has changed. That check happens above.
          </p>
        </section>
      )}
    </div>
  );
}
