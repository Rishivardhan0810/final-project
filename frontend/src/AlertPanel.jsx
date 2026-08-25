// The risk-change card on the record screen -- calls /api/acknowledge
const RISK_COPY = {
  HIGH: { label: "High risk", note: "Formula/formulation switch or large dose change on a narrow-therapeutic-index drug, or any drug switch on one." },
  MEDIUM: { label: "Medium risk", note: "Drug or formulation switch on a standard-margin drug, or a smaller dose change on a narrow-therapeutic-index drug." },
  LOW: { label: "Low risk", note: "Route change only, or a small dose change on a standard-margin drug." },
  NONE: { label: "No risk", note: "No risk-relevant change (a manufacturer-only swap does not count)." },
};

export default function AlertPanel({
  alert, concurrentMedications, acknowledged, ackBusy, pharmacistName, setPharmacistName, onAcknowledge,
}) {
  const risk = RISK_COPY[alert.risk_final] || RISK_COPY.NONE;

  if (acknowledged) {
    return (
      <section className="alert-panel alert-panel-resolved">
        <div className="alert-resolved-row">
          <span className="alert-resolved-icon" aria-hidden="true">&#10003;</span>
          <div>
            <p className="alert-resolved-title">Change acknowledged</p>
            <p className="alert-resolved-sub">
              Logged for {pharmacistName} &middot; risk level {risk.label.toLowerCase()}. Dispense is now unlocked.
            </p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="alert-panel alert-panel-active" role="alert" aria-live="assertive">
      <div className="alert-head">
        <span className="alert-badge">Prescription changed</span>
        <span className={`alert-risk alert-risk-${alert.risk_final}`}>{risk.label}</span>
        {alert.narrow_therapeutic_index && (
          <span className="alert-nti-badge" title="Small margin between an effective and a harmful dose">
            Narrow therapeutic index
          </span>
        )}
      </div>

      <p className="alert-summary">{alert.summary}.</p>
      <p className="alert-risk-note">{risk.note}</p>

      {concurrentMedications ? (
        <p className="alert-context">Also currently taking: {concurrentMedications}</p>
      ) : null}

      <div className="alert-compare">
        <div className="alert-compare-col">
          <p className="alert-compare-label">Previous</p>
          <p className="alert-compare-drug">{alert.previous.drug_name} {alert.previous.dose_mg}mg</p>
          <p className="alert-compare-detail">{alert.previous.formulation} &middot; {alert.previous.route}</p>
          <p className="alert-compare-mfr">{alert.previous.manufacturer}</p>
        </div>
        <div className="alert-compare-arrow" aria-hidden="true">&rarr;</div>
        <div className="alert-compare-col">
          <p className="alert-compare-label">Current (EPS)</p>
          <p className="alert-compare-drug">{alert.current.drug_name} {alert.current.dose_mg}mg</p>
          <p className="alert-compare-detail">{alert.current.formulation} &middot; {alert.current.route}</p>
          <p className="alert-compare-mfr">{alert.current.manufacturer}</p>
        </div>
      </div>

      {alert.manufacturer_changed && (
        <p className="alert-mfr-note">
          Manufacturer also changed ({alert.previous.manufacturer} &rarr; {alert.current.manufacturer}) &mdash;
          same formula, not treated as a risk-relevant change.
        </p>
      )}

      <div className="alert-models">
        <span>Primary alert (rule-based): <strong>{alert.risk_rule}</strong></span>
        <span>Structured comparison (Random Forest): <strong>{alert.risk_random_forest}</strong></span>
        <span>Text comparison (Text model): <strong>{alert.risk_text_model}</strong></span>
        <span>GP: {alert.gp_name}</span>
      </div>
      <p className="alert-model-hint">
        Random Forest and the text model are shown for comparison only &mdash; they do not control
        this alert or unlock dispensing.
      </p>

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
          onClick={onAcknowledge}
        >
          {ackBusy ? "Logging\u2026" : "Acknowledge change"}
        </button>
      </div>
      <p className="alert-ack-hint">Dispense stays locked until this is acknowledged.</p>
    </section>
  );
}
