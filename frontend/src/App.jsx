// App shell -- switches between the Prescription Review and Audit & Safety
// dashboards, and calls the backend's /api/lookup.
import { useState } from "react";
import LookupScreen from "./LookupScreen";
import RecordScreen from "./RecordScreen";
import AuditDashboard from "./AuditDashboard";
import AuditLogin from "./AuditLogin";
import "./App.css";

const API_BASE = "http://localhost:8000";

// `view` picks which dashboard is showing ("review" or "audit"). Within
// "review", whether `result` is null decides if we're on the lookup form
// or the patient record screen.
//
// auditAuthenticated is just in-memory state, never written to storage --
// a page refresh resets it, so the audit login is always required again.
// Prototype access control only (see AuditLogin.jsx), not real auth.
export default function App() {
  const [view, setView] = useState("review"); // "review" | "audit"
  const [auditAuthenticated, setAuditAuthenticated] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Calls the backend's /api/lookup endpoint with the patient ID + DOB the user typed.
  async function handleLookup({ patient_id, date_of_birth }) {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/lookup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ patient_id, date_of_birth }),
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

  // clears the current patient so the lookup form shows again
  function handleBack() {
    setResult(null);
    setError("");
  }

  // Clear the loaded patient when switching to Audit & Safety, so coming
  // back to Prescription Review always starts fresh at the lookup form
  // instead of silently reopening whoever was last looked up.
  function handleSwitchToAudit() {
    setResult(null);
    setError("");
    setView("audit");
  }

  // clears the auth flag -- AuditLogin reappears since `view` is still "audit"
  function handleAuditLogout() {
    setAuditAuthenticated(false);
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-brand">
          <span className="topbar-mark" aria-hidden="true" />
          <span>PMR &middot; Community Pharmacy</span>
        </div>
        <nav className="topbar-nav">
          <button
            type="button"
            className={`topbar-nav-link ${view === "review" ? "topbar-nav-link-active" : ""}`}
            onClick={() => setView("review")}
          >
            Prescription Review
          </button>
          <button
            type="button"
            className={`topbar-nav-link ${view === "audit" ? "topbar-nav-link-active" : ""}`}
            onClick={handleSwitchToAudit}
          >
            Audit &amp; Safety
          </button>
        </nav>
      </header>

      <main className="app-main">
        {view === "review" && !result && (
          <LookupScreen onLookup={handleLookup} loading={loading} error={error} />
        )}
        {view === "review" && result && (
          <RecordScreen data={result} apiBase={API_BASE} onBack={handleBack} />
        )}
        {view === "audit" && !auditAuthenticated && (
          <AuditLogin onLoginSuccess={() => setAuditAuthenticated(true)} />
        )}
        {view === "audit" && auditAuthenticated && (
          <AuditDashboard apiBase={API_BASE} onLogout={handleAuditLogout} />
        )}
      </main>
    </div>
  );
}
