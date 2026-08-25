// Prototype login gate in front of the Audit & Safety dashboard --
// client-side only, not real authentication
import { useState } from "react";
import { DEMO_AUDIT_CREDENTIALS } from "./auditDemoCredentials";

export default function AuditLogin({ onLoginSuccess }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  function submit(e) {
    e.preventDefault();
    if (username === DEMO_AUDIT_CREDENTIALS.username && password === DEMO_AUDIT_CREDENTIALS.password) {
      setError("");
      onLoginSuccess();
    } else {
      setError("Incorrect username or password.");
    }
  }

  return (
    <div className="lookup-wrap">
      <div className="lookup-card">
        <p className="lookup-eyebrow">Audit &amp; Safety</p>
        <h1 className="lookup-title">Audit login required</h1>
        <p className="audit-note">
          Prototype access control only &mdash; production deployment would require secure
          server-side authentication and role-based access control.
        </p>

        <form onSubmit={submit} className="lookup-form">
          <label className="field">
            <span>Username</span>
            <input value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>

          {error && <div className="lookup-error" role="alert">{error}</div>}

          <button type="submit" className="btn btn-primary">Log in</button>
        </form>

        <details className="lookup-demo">
          <summary>Demo credentials</summary>
          <p>
            Username: <code>{DEMO_AUDIT_CREDENTIALS.username}</code> &middot; Password:{" "}
            <code>{DEMO_AUDIT_CREDENTIALS.password}</code>
          </p>
        </details>
      </div>
    </div>
  );
}
