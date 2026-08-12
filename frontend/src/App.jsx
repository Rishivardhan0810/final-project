import { useState } from "react";
import LookupScreen from "./LookupScreen";
import RecordScreen from "./RecordScreen";
import "./App.css";

const API_BASE = "http://localhost:8000";

// Top-level component: shows the lookup form until a patient is found,
// then swaps to the patient record screen. `result` being null/non-null
// is what decides which screen is on show.
export default function App() {
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Calls the backend's /api/lookup endpoint with the name+DOB the user typed.
  async function handleLookup({ first_name, last_name, date_of_birth }) {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/lookup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ first_name, last_name, date_of_birth }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Lookup failed.");
      }
      const data = await res.json();
      setResult(data);
    } catch (e) {
      setError(e.message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  // "New search" button: clears the current patient so the lookup form shows again.
  function handleBack() {
    setResult(null);
    setError("");
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-brand">
          <span className="topbar-mark" aria-hidden="true" />
          <span>PMR &middot; Community Pharmacy</span>
        </div>
        <div className="topbar-meta">Prescription Change Alert Prototype</div>
      </header>

      <main className="app-main">
        {!result && (
          <LookupScreen onLookup={handleLookup} loading={loading} error={error} />
        )}
        {result && (
          <RecordScreen data={result} apiBase={API_BASE} onBack={handleBack} />
        )}
      </main>
    </div>
  );
}
