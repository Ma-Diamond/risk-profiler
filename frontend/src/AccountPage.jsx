import { useEffect, useState } from "react";
import { t } from "./i18n";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

const FIELD_GROUPS = [
  {
    title: "About you",
    fields: [
      { key: "full_name", label: "Full name", type: "text" },
      { key: "age", label: "Age", type: "number" },
      { key: "dependents", label: "Dependents", type: "number" },
      { key: "knowledge_score", label: "Investing experience (1-5)", type: "number", min: 1, max: 5 },
    ],
  },
  {
    title: "Finances",
    fields: [
      { key: "gross_monthly_income", label: "Gross monthly income (R)", type: "number" },
      { key: "monthly_expenses", label: "Monthly expenses (R)", type: "number" },
    ],
  },
  {
    title: "Identity",
    fields: [
      { key: "id_number", label: "SA ID number", type: "text" },
      { key: "date_of_birth", label: "Date of birth", type: "date" },
      { key: "contact_number", label: "Contact number", type: "text" },
      { key: "email", label: "Email", type: "email" },
      { key: "address", label: "Residential address", type: "text", fullRow: true },
    ],
  },
  {
    title: "Banking",
    fields: [
      { key: "bank_name", label: "Bank name", type: "text" },
      { key: "bank_account_number", label: "Account number", type: "text" },
      { key: "branch_code", label: "Branch code", type: "text" },
    ],
  },
];

// These fields feed both the chat intake and the Invest Now form, so
// filling them in here means neither has to start from scratch.
export default function AccountPage({ currentUser, onBack, onLogout, onGoToLogin, language }) {
  const [profile, setProfile] = useState({});
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!currentUser) return;
    const token = localStorage.getItem("risk_profiler_token");
    fetch(`${API_BASE}/auth/me/profile`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.json())
      .then((data) => {
        setProfile(data);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, [currentUser]);

  const updateField = (key, value) => setProfile((p) => ({ ...p, [key]: value }));

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const token = localStorage.getItem("risk_profiler_token");
      const res = await fetch(`${API_BASE}/auth/me/profile`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(profile),
      });
      if (!res.ok) throw new Error("Couldn't save your profile");
      const updated = await res.json();
      setProfile(updated);
      setEditing(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  if (!currentUser) {
    return (
      <div className="history-shell">
        <div className="history-card card">
          <div className="history-card__header">
            <h2>{t(language, "accounts.title")}</h2>
            <button className="btn btn-ghost" onClick={onBack}>
              {t(language, "accounts.back")}
            </button>
          </div>
          <p className="step-subtitle">You're not logged in.</p>
          <button className="btn btn-primary" onClick={onGoToLogin}>
            {t(language, "nav.login")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="history-shell">
      <div className="history-card card profile-card">
        <div className="history-card__header">
          <h2>{t(language, "profile.title")}</h2>
          <button className="btn btn-ghost" onClick={onBack}>
            {t(language, "accounts.back")}
          </button>
        </div>
        <p className="step-subtitle">
          {editing
            ? "These details are used to pre-fill your risk profile chat and any Invest Now applications."
            : "Keep this up to date — it saves you re-entering the same details every time."}
        </p>

        <div className="account-detail-row">
          <span className="field-label">Email</span>
          <span>{currentUser.email}</span>
        </div>

        {loaded &&
          FIELD_GROUPS.map((group) => (
            <div key={group.title} className="profile-group">
              <p className="form-section__title">{group.title}</p>
              <div className="profile-group__grid">
                {group.fields.map((f) => (
                  <div key={f.key} className={f.fullRow ? "application-form__full-row" : undefined}>
                    <label className="field-label">{f.label}</label>
                    {editing ? (
                      <input
                        className="text-input"
                        type={f.type}
                        min={f.min}
                        max={f.max}
                        value={profile[f.key] ?? ""}
                        onChange={(e) =>
                          updateField(f.key, f.type === "number" ? Number(e.target.value) : e.target.value)
                        }
                      />
                    ) : (
                      <p className="profile-value">
                        {profile[f.key] === null || profile[f.key] === undefined || profile[f.key] === ""
                          ? "—"
                          : f.type === "number" && (f.key.includes("income") || f.key.includes("expenses"))
                          ? `R${Number(profile[f.key]).toLocaleString()}`
                          : profile[f.key]}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}

        {error && <p className="field-error">{error}</p>}

        <div className="modal-card__actions">
          {editing ? (
            <>
              <button className="btn btn-ghost" onClick={() => setEditing(false)} disabled={saving}>
                {t(language, "profile.cancel")}
              </button>
              <button className="btn btn-primary" onClick={save} disabled={saving}>
                {saving ? "…" : t(language, "profile.save")}
              </button>
            </>
          ) : (
            <>
              <button className="btn btn-ghost" onClick={onLogout}>
                {t(language, "profile.logout")}
              </button>
              <button className="btn btn-primary" onClick={() => setEditing(true)}>
                {t(language, "profile.edit")}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
