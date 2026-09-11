import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export default function AuthForm({ mode, onAuthenticated, onSwitchMode, onCancel }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const isSignup = mode === "signup";

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const path = isSignup ? "/auth/register" : "/auth/login";
      const body = isSignup ? { email, password, full_name: fullName || null } : { email, password };
      const res = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Something went wrong");
      const data = await res.json();
      onAuthenticated(data.token, data.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-shell">
      <form className="auth-card card" onSubmit={submit}>
        <h2>{isSignup ? "Create your account" : "Log in"}</h2>
        <p className="step-subtitle">
          {isSignup
            ? "Save your risk profile and continue it later."
            : "Welcome back — continue where you left off."}
        </p>

        {isSignup && (
          <div>
            <label className="field-label">Full name (optional)</label>
            <input
              className="text-input"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Jane Dlamini"
            />
          </div>
        )}

        <div>
          <label className="field-label">Email</label>
          <input
            className="text-input"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </div>

        <div>
          <label className="field-label">Password</label>
          <input
            className="text-input"
            type="password"
            required
            minLength={isSignup ? 8 : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={isSignup ? "At least 8 characters" : "••••••••"}
          />
        </div>

        {error && <p className="field-error">{error}</p>}

        <div className="auth-card__actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>
            Continue as guest
          </button>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? "Please wait…" : isSignup ? "Sign up" : "Log in"}
          </button>
        </div>

        <p className="auth-card__switch">
          {isSignup ? "Already have an account? " : "Don't have an account? "}
          <button type="button" className="auth-card__switch-link" onClick={onSwitchMode}>
            {isSignup ? "Log in" : "Sign up"}
          </button>
        </p>
      </form>
    </div>
  );
}
