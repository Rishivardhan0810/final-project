// Read-only Audit & Safety dashboard -- calls GET /api/audit/summary and
// GET /api/audit/activity
import { useEffect, useState } from "react";

function fmtDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

const RISK_ORDER = ["HIGH", "MEDIUM", "LOW", "NONE"];

// FIRST_PRESCRIPTION_REVIEW is a review type, not a risk level -- give it
// its own neutral badge instead of a risk colour
function riskCell(event) {
  if (event.risk_level === "FIRST_PRESCRIPTION_REVIEW") {
    return <span className="audit-badge audit-badge-review">First prescription reviewed</span>;
  }
  if (event.risk_level) {
    return <span className={`audit-badge audit-badge-risk-${event.risk_level}`}>{event.risk_level}</span>;
  }
  return "—";
}

export default function AuditDashboard({ apiBase, onLogout }) {
  const [summary, setSummary] = useState(null);
  const [activity, setActivity] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [summaryRes, activityRes] = await Promise.all([
          fetch(`${apiBase}/api/audit/summary`),
          fetch(`${apiBase}/api/audit/activity?limit=50`),
        ]);
        if (!summaryRes.ok || !activityRes.ok) throw new Error("Failed to load audit data.");
        const summaryData = await summaryRes.json();
        const activityData = await activityRes.json();
        if (!cancelled) {
          setSummary(summaryData);
          setActivity(activityData.events);
        }
      } catch (e) {
        if (!cancelled) setError(e.message);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [apiBase]);

  return (
    <div className="audit-wrap">
      <div className="audit-header-row">
        <p className="audit-note">
          Prototype access control only &mdash; production deployment would require secure
          server-side authentication and role-based access control.
        </p>
        <button type="button" className="btn btn-ghost" onClick={onLogout}>Log out</button>
      </div>

      {error && <div className="lookup-error" role="alert">{error}</div>}

      <section className="audit-panel">
        <h2>Summary</h2>
        <div className="audit-stat-row">
          <div className="audit-stat-tile">
            <div className="audit-stat-num">{summary ? summary.total_dispenses : "—"}</div>
            <div className="audit-stat-label">Total dispenses</div>
          </div>
          <div className="audit-stat-tile">
            <div className="audit-stat-num">{summary ? summary.total_acknowledgements : "—"}</div>
            <div className="audit-stat-label">Total acknowledgements</div>
          </div>
          <div className="audit-stat-tile">
            <div className="audit-stat-num">{summary ? summary.first_prescription_reviews : "—"}</div>
            <div className="audit-stat-label">First-prescription reviews</div>
          </div>
        </div>

        <h3 className="audit-subheading">Acknowledged risk levels</h3>
        <p className="audit-subnote">
          Counts of risk levels pharmacists have acknowledged &mdash; not every alert the system
          has ever generated. An alert that was shown but never acknowledged isn't counted here.
        </p>
        {summary && (
          <div className="audit-risk-row">
            {RISK_ORDER.map((level) => (
              <span key={level} className={`audit-badge audit-badge-risk-${level}`}>
                {level}: <strong>{summary.acknowledged_risk_counts[level]}</strong>
              </span>
            ))}
          </div>
        )}
      </section>

      <section className="audit-panel">
        <h2>Recent Activity</h2>
        <div className="audit-table-scroll">
          <table className="rx-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Action</th>
                <th>Patient ID</th>
                <th>Pharmacist</th>
                <th>Medication / Dose</th>
                <th>Risk / Review status</th>
              </tr>
            </thead>
            <tbody>
              {activity && activity.length === 0 && (
                <tr><td colSpan={6} className="audit-empty">No activity recorded yet.</td></tr>
              )}
              {activity && activity.map((event, i) => (
                <tr key={i}>
                  <td>{fmtDateTime(event.happened_at)}</td>
                  <td>{event.action}</td>
                  <td>{event.patient_id}</td>
                  <td>{event.pharmacist_name}</td>
                  <td>{event.drug_name ? `${event.drug_name} ${event.dose_mg}mg` : "—"}</td>
                  <td>{riskCell(event)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
