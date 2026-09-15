import { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

function formatRand(value) {
  return `R${Math.round(value).toLocaleString()}`;
}

// Every investment account this person has opened, across every risk
// profile they've ever completed — not scoped to one profile, since
// redoing a profile creates a new one but past accounts stay real.
export default function AccountsPage({ authToken, onBack }) {
  const [accounts, setAccounts] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!authToken) return;
    fetch(`${API_BASE}/accounts/mine`, { headers: { Authorization: `Bearer ${authToken}` } })
      .then((r) => {
        if (!r.ok) throw new Error("Couldn't load your accounts");
        return r.json();
      })
      .then(setAccounts)
      .catch((e) => setError(e.message));
  }, [authToken]);

  return (
    <div className="history-shell">
      <div className="history-card card">
        <div className="history-card__header">
          <h2>My accounts</h2>
          <button className="btn btn-ghost" onClick={onBack}>
            Back
          </button>
        </div>

        {error && <p className="field-error">{error}</p>}

        {accounts === null && !error && <p className="step-subtitle">Loading…</p>}

        {accounts && accounts.length === 0 && (
          <p className="step-subtitle">
            No accounts yet — complete a risk profile and use Invest Now to open your first one.
          </p>
        )}

        {accounts && accounts.length > 0 && (
          <div className="history-list">
            {accounts.map((acc) => (
              <div key={acc.account_id} className="history-row accounts-page__row">
                <span className={`pill pill--${acc.status}`}>
                  {acc.status === "pending" ? "Pending review" : acc.status}
                </span>
                <div className="history-row__main">
                  <strong>{acc.product_name}</strong>
                  <span className="history-row__meta">
                    {acc.tax_wrapper.replace(/_/g, " ")} · {acc.portfolio_name}
                  </span>
                  {acc.beneficiary_name && (
                    <span className="history-row__goals">Beneficiary: {acc.beneficiary_name}</span>
                  )}
                </div>
                <div className="accounts-page__amounts mono">
                  {acc.initial_amount > 0 && <span>{formatRand(acc.initial_amount)} lump sum</span>}
                  {acc.monthly_amount > 0 && <span>{formatRand(acc.monthly_amount)}/month</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
