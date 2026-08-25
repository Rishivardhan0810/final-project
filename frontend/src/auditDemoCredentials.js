// The one place the demo audit login credentials live -- imported by
// AuditLogin.jsx.
//
// Deliberately just a plain, visible constant -- no hashing, no server
// check, no real account behind it. This demonstrates where a login gate
// belongs in front of the audit dashboard, not an actual security control.
// See the note on both the login screen and the dashboard itself.
export const DEMO_AUDIT_CREDENTIALS = { username: "audit", password: "demo123" };
