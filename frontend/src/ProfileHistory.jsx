import { useEffect, useState } from "react";

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

export default function ProfileHistory({ authToken, onContinue, onBack }) {
  const [profiles, setProfiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/profiles`, {
          headers: { Authorization: `Bearer ${authToken}` },
        });
        if (!res.ok) throw new Error("Couldn't load your profiles");
        setProfiles(await res.json());
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, [authToken]);

  return (
    <div className="history-shell">
      <div className="history-card card">
        <div className="history-card__header">
          <h2>My profiles</h2>
          <button className="btn btn-ghost" onClick={onBack}>
            Back
          </button>
        </div>

        {loading && <p className="step-subtitle">Loading…</p>}
        {error && <p className="field-error">{error}</p>}

        {!loading && !error && profiles.length === 0 && (
          <p className="step-subtitle">
            No saved profiles yet — finish a conversation and it'll show up here.
          </p>
        )}

        <div className="history-list">
          {profiles.map((p) => (
            <div key={p.client_id} className="history-row">
              <div className={`history-row__band-dot band-bg-${p.governed_risk_band}`} />
              <div className="history-row__main">
                <strong>{GOAL_LABELS[p.investment_goal] || p.investment_goal}</strong>
                <span className="history-row__meta">
                  Band {p.governed_risk_band}/5 · {formatDate(p.created_at)}
                </span>
                {p.goals_detail && <span className="history-row__goals">{p.goals_detail}</span>}
              </div>
              <button
                className="btn btn-primary"
                onClick={() => onContinue(p.client_id)}
                disabled={!p.chat_session_id}
              >
                Continue
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
