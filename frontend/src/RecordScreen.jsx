import { useState } from "react";
import AlertPanel from "./AlertPanel";

function fmtDate(iso) {
  if (!iso) return "\u2014";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export default function RecordScreen({ data, apiBase, onBack }) {
  const { patient, prescriptions, alert } = data;
  const [acknowledged, setAcknowledged] = useState(false);
  const [ackBusy, setAckBusy] = useState(false);
  const [pharmacistName, setPharmacistName] = useState("");
  const current = prescriptions[prescriptions.length - 1];

  const dispenseLocked = Boolean(alert) && !acknowledged;

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
          <span className="tag">Condition: {patient.condition || "\u2014"}</span>
          <span className={`tag ${patient.allergy && patient.allergy !== "None recorded" ? "tag-warn" : ""}`}>
            Allergy: {patient.allergy || "\u2014"}
          </span>
          {patient.polypharmacy_count > 0 && (
            <span className="tag">Also on {patient.polypharmacy_count} other medication{patient.polypharmacy_count > 1 ? "s" : ""}</span>
          )}
        </div>
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

      <section className="dispense-panel">
        <button className="btn btn-dispense" disabled={dispenseLocked} title={dispenseLocked ? "Acknowledge the alert above to unlock" : ""}>
          {dispenseLocked ? "\ud83d\udd12 Dispense (locked until acknowledged)" : "Dispense"}
        </button>
        <p className="dispense-hint">
          Barcode scan on collection verifies the box matches this current prescription {"\u2014"} it
          does not check whether the prescription itself has changed. That check happens above.
        </p>
      </section>
    </div>
  );
}
