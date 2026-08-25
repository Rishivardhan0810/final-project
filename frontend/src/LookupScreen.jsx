// Patient lookup screen -- the search form shown first
import { useState } from "react";

export default function LookupScreen({ onLookup, loading, error }) {
  const [patientId, setPatientId] = useState("");
  const [dob, setDob] = useState("");

  function submit(e) {
    e.preventDefault();
    onLookup({ patient_id: patientId.trim(), date_of_birth: dob });
  }

  return (
    <div className="lookup-wrap">
      <div className="lookup-card">
        <p className="lookup-eyebrow">Patient lookup</p>
        <h1 className="lookup-title">Find a patient record</h1>
        <p className="lookup-help">
          One record at a time. Both Patient ID and date of birth are required, in line with UK
          GDPR handling of patient-identifiable data.
        </p>

        <form onSubmit={submit} className="lookup-form">
          <label className="field">
            <span>Patient ID</span>
            <input value={patientId} onChange={(e) => setPatientId(e.target.value)} required autoFocus />
          </label>
          <label className="field">
            <span>Date of birth</span>
            <input type="date" value={dob} onChange={(e) => setDob(e.target.value)} required />
          </label>

          {error && <div className="lookup-error" role="alert">{error}</div>}

          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? "Searching…" : "Open patient record"}
          </button>
        </form>

        <details className="lookup-demo">
          <summary>Demo data {"—"} no real patient names used</summary>
          <p>
            This prototype runs on synthetic patients generated for development. Open{" "}
            <code>data/patients.csv</code> and copy a matching <code>patient_id</code> and{" "}
            <code>date_of_birth</code> pair from the same row to try a lookup.
          </p>
        </details>
      </div>
    </div>
  );
}
