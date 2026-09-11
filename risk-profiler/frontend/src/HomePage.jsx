import { useEffect, useState } from "react";
import { MOCK_ACCOUNTS } from "./mockAccounts";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

const GOAL_LABELS = {
  retirement: "Retirement",
  house_deposit: "House deposit",
  general_growth: "General growth",
};

function formatDate(isoLike) {
  try {
    return new Date(isoLike.replace(" ", "T") + "Z").toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return isoLike;
  }
}

function formatRand(value) {
  const sign = value < 0 ? "-" : "";
  return `${sign}R${Math.abs(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export default function HomePage({
  currentUser,
  authToken,
  onStartNew,
  onContinueProfile,
  onSeeAllProfiles,
  onGoToLogin,
}) {
  const [profiles, setProfiles] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!currentUser) return;
    setLoading(true);
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/profiles`, {
          headers: { Authorization: `Bearer ${authToken}` },
        });
        if (res.ok) setProfiles(await res.json());
      } finally {
        setLoading(false);
      }
    })();
  }, [currentUser, authToken]);

  const firstName = currentUser?.full_name?.split(" ")[0];

  return (
    <div className="home-shell">
      <div className="home-content">
        <header className="home-greeting">
          <h1>{currentUser ? `Welcome back${firstName ? `, ${firstName}` : ""}` : "Welcome to Nedcore"}</h1>
          <p className="step-subtitle">
            {currentUser
              ? "Here's where things stand today."
              : "Log in to see your accounts and investments, or jump straight into a risk profile as a guest."}
          </p>
        </header>

        {currentUser ? (
          <>
            <section className="home-section">
              <div className="home-section__header">
                <h3>Accounts with Nedcore</h3>
              </div>
              <div className="account-grid">
                {MOCK_ACCOUNTS.map((a) => (
                  <div key={a.id} className="account-card card">
                    <span className="account-card__type">{a.type}</span>
                    <strong className="account-card__name">{a.name}</strong>
                    <span
                      className={`account-card__balance mono ${
                        a.balance < 0 ? "account-card__balance--negative" : ""
                      }`}
                    >
                      {formatRand(a.balance)}
                    </span>
                    <span className="account-card__number mono">{a.accountNumber}</span>
                  </div>
                ))}
              </div>
            </section>

            <section className="home-section">
              <div className="home-section__header">
                <h3>Active investments</h3>
                {profiles.length > 3 && (
                  <button className="home-section__link" onClick={onSeeAllProfiles}>
                    See all
                  </button>
                )}
              </div>

              {loading && <p className="step-subtitle">Loading…</p>}

              {!loading && profiles.length === 0 && (
                <div className="home-empty card">
                  <p className="step-subtitle">You haven't completed a risk profile yet.</p>
                  <button className="btn btn-primary" onClick={onStartNew}>
                    Start a risk profile
                  </button>
                </div>
              )}

              {!loading && profiles.length > 0 && (
                <div className="investment-grid">
                  {profiles.slice(0, 3).map((p) => (
                    <div key={p.client_id} className="investment-card card">
                      <div className={`investment-card__band-dot band-bg-${p.governed_risk_band}`} />
                      <div className="investment-card__main">
                        <strong>{GOAL_LABELS[p.investment_goal] || p.investment_goal}</strong>
                        <span className="investment-card__meta">
                          Band {p.governed_risk_band}/5 · {formatDate(p.created_at)}
                        </span>
                      </div>
                      <button
                        className="btn btn-ghost"
                        onClick={() => onContinueProfile(p.client_id)}
                        disabled={!p.chat_session_id}
                      >
                        Continue
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="home-cta-row">
              <button className="btn btn-primary" onClick={onStartNew}>
                Start a new risk profile
              </button>
              <button className="btn btn-ghost" disabled title="Coming soon">
                Talk to an advisor
              </button>
            </section>
          </>
        ) : (
          <section className="home-cta-row">
            <button className="btn btn-primary" onClick={onStartNew}>
              Start a risk profile as a guest
            </button>
            <button className="btn btn-ghost" onClick={onGoToLogin}>
              Log in
            </button>
          </section>
        )}
      </div>
    </div>
  );
}
