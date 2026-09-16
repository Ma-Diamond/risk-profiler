import { useEffect, useState } from "react";
import { t } from "./i18n";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

function formatRand(value) {
  const abs = Math.abs(Math.round(value));
  return `${value < 0 ? "-" : ""}R${abs.toLocaleString()}`;
}

const LINKED_ACCOUNT_ICONS = {
  debit: "💳",
  credit: "🪪",
  home_loan: "🏠",
  vehicle_finance: "🚗",
};

// Every investment account this person has opened, across every risk
// profile they've ever completed — not scoped to one profile, since
// redoing a profile creates a new one but past accounts stay real.
// Also shows their other linked banking relationships (demo values)
// so the app has something concrete to reference in conversation.
export default function AccountsPage({ authToken, onBack, language }) {
  const [accounts, setAccounts] = useState(null);
  const [linked, setLinked] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!authToken) return;
    const headers = { Authorization: `Bearer ${authToken}` };
    fetch(`${API_BASE}/accounts/mine`, { headers })
      .then((r) => {
        if (!r.ok) throw new Error("Couldn't load your accounts");
        return r.json();
      })
      .then(setAccounts)
      .catch((e) => setError(e.message));
    fetch(`${API_BASE}/accounts/linked`, { headers })
      .then((r) => (r.ok ? r.json() : []))
      .then(setLinked)
      .catch(() => setLinked([]));
  }, [authToken]);

  return (
    <div className="history-shell">
      <div className="history-card card accounts-page-card">
        <div className="history-card__header">
          <h2>{t(language, "accounts.title")}</h2>
          <button className="btn btn-ghost" onClick={onBack}>
            {t(language, "accounts.back")}
          </button>
        </div>

        {error && <p className="field-error">{error}</p>}

        {linked && linked.length > 0 && (
          <>
            <p className="form-section__title">{t(language, "accounts.linkedAccounts")}</p>
            <div className="linked-accounts-grid">
              {linked.map((acc) => (
                <div key={acc.account_type} className="linked-account-card">
                  <span className="linked-account-card__icon">{LINKED_ACCOUNT_ICONS[acc.account_type] || "🏦"}</span>
                  <span className="linked-account-card__name">{acc.name}</span>
                  <span className={`linked-account-card__balance mono ${acc.balance < 0 ? "linked-account-card__balance--negative" : ""}`}>
                    {formatRand(acc.balance)}
                  </span>
                  {acc.limit != null && (
                    <span className="linked-account-card__limit">Limit: {formatRand(acc.limit)}</span>
                  )}
                </div>
              ))}
            </div>
          </>
        )}

        <p className="form-section__title">{t(language, "accounts.investmentAccounts")}</p>

        {accounts === null && !error && <p className="step-subtitle">{t(language, "common.loading")}</p>}

        {accounts && accounts.length === 0 && (
          <p className="step-subtitle">{t(language, "accounts.noInvestmentAccounts")}</p>
        )}

        {accounts && accounts.length > 0 && (
          <div className="history-list">
            {accounts.map((acc) => (
              <div key={acc.account_id} className="history-row accounts-page__row">
                <span className={`pill pill--${acc.status}`}>
                  {acc.status === "pending" ? t(language, "accounts.pending") : acc.status}
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
