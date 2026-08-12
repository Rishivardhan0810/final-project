import { useState } from "react";

export default function LookupScreen({ onLookup, loading, error }) {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [dob, setDob] = useState("");

  function submit(e) {
    e.preventDefault();
    onLookup({ first_name: firstName.trim(), last_name: lastName.trim(), date_of_birth: dob });
  }

  return (
    <div className="lookup-wrap">
      <div className="lookup-card">
        <p className="lookup-eyebrow">Patient lookup</p>
        <h1 className="lookup-title">Find a patient record</h1>
        <p className="lookup-help">
          One record at a time. Search by name and date of birth, in line with UK GDPR handling
          of patient-identifiable data.
        </p>

        <form onSubmit={submit} className="lookup-form">
          <label className="field">
            <span>First name</span>
            <input value={firstName} onChange={(e) => setFirstName(e.target.value)} required autoFocus />
          </label>
          <label className="field">
            <span>Last name</span>
            <input value={lastName} onChange={(e) => setLastName(e.target.value)} required />
          </label>
          <label className="field">
            <span>Date of birth</span>
            <input type="date" value={dob} onChange={(e) => setDob(e.target.value)} required />
          </label>

          {error && <div className="lookup-error" role="alert">{error}</div>}

          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? "Searching\u2026" : "Open patient record"}
          </button>
        </form>

        <details className="lookup-demo">
          <summary>Demo data {"\u2014"} no real patient names used</summary>
          <p>
            This prototype runs on 520 synthetic patients generated for development. Try any name
            from the synthetic dataset with its matching date of birth. Ask the person who set up
            this demo for a sample name if you don't have one, or open <code>data/patients.csv</code>{" "}
            to pick one directly.
          </p>
        </details>
      </div>
    </div>
  );
}
