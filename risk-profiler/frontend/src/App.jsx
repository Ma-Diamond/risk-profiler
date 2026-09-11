import { useEffect, useRef, useState } from "react";
import ChatPanel from "./ChatPanel";
import ResultsPanel from "./ResultsPanel";
import SummaryModal from "./SummaryModal";
import AuthForm from "./AuthForm";
import ProfileHistory from "./ProfileHistory";
import HomePage from "./HomePage";
import AccountPage from "./AccountPage";
import NavMenu from "./NavMenu";
import "./tokens.css";
import "./global.css";
import "./layout.css";
import "./animations.css";

// In production this is set at build time (see .env.production) to the
// deployed backend's real URL, since frontend (CloudFront) and backend
// (Elastic Beanstalk) are separate domains there. Locally it falls back
// to "/api", which vite.config.js's dev-server proxy forwards to your
// local backend on :8000 — npm run dev needs no configuration.
const API_BASE = import.meta.env.VITE_API_BASE || "/api";
const TOKEN_STORAGE_KEY = "risk_profiler_token";

export default function App() {
  const [sessionId, setSessionId] = useState(null);
  const [result, setResult] = useState(null);
  const [recalcMap, setRecalcMap] = useState({});
  const [sheetExpanded, setSheetExpanded] = useState(false);
  const [activeSummary, setActiveSummary] = useState(null);
  const chatRef = useRef(null);

  // "chat" is the normal app body (intake or docked results); the
  // others replace it entirely while still leaving the chat mounted
  // underneath (hidden via CSS, not unmounted) so an in-progress
  // conversation isn't lost by a trip to another view and back.
  const [view, setView] = useState("home"); // "home" | "chat" | "login" | "signup" | "history" | "account"

  const [authToken, setAuthToken] = useState(null);
  const [currentUser, setCurrentUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  // On load, validate any token we already have rather than trusting
  // it blindly — it may have expired since it was stored.
  useEffect(() => {
    const stored = localStorage.getItem(TOKEN_STORAGE_KEY);
    if (!stored) {
      setAuthChecked(true);
      return;
    }
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/auth/me`, {
          headers: { Authorization: `Bearer ${stored}` },
        });
        if (!res.ok) throw new Error("expired");
        const user = await res.json();
        setAuthToken(stored);
        setCurrentUser(user);
      } catch {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
      } finally {
        setAuthChecked(true);
      }
    })();
  }, []);

  const handleFinalized = (profileResult) => {
    setResult(profileResult);
    setRecalcMap({});
  };

  const handleRecalculated = (list) => {
    setRecalcMap((prev) => {
      const next = { ...prev };
      list.forEach((item) => {
        next[`${item.product_id}-${item.portfolio_id}`] = {
          expected_value: item.expected_value,
          lower_value: item.lower_value,
          upper_value: item.upper_value,
        };
      });
      return next;
    });
    setSheetExpanded(true);
  };

  const handleSummaryConfirm = () => {
    setActiveSummary(null);
    chatRef.current?.sendProgrammaticMessage("Yes, that all looks right — please proceed.");
  };

  const handleAuthenticated = (token, user) => {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
    setAuthToken(token);
    setCurrentUser(user);
    setView("home");
    setResult(null);
    setRecalcMap({});
    // Login doesn't retroactively claim whatever anonymous session was
    // active — start clean under the now-authenticated identity so
    // there's never an ambiguous ownership state.
    chatRef.current?.startFresh();
  };

  const handleLogout = () => {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setAuthToken(null);
    setCurrentUser(null);
    setView("home");
    setResult(null);
    setRecalcMap({});
    chatRef.current?.startFresh();
  };

  const handleContinueProfile = async (clientId) => {
    try {
      const headers = { Authorization: `Bearer ${authToken}` };
      const profileRes = await fetch(`${API_BASE}/profiles/${clientId}`, { headers });
      if (!profileRes.ok) throw new Error("Couldn't load that profile");
      const profileData = await profileRes.json();

      const historyRes = await fetch(
        `${API_BASE}/chat/sessions/${profileData.chat_session_id}/history`,
        { headers }
      );
      const history = historyRes.ok ? await historyRes.json() : [];

      chatRef.current?.resumeSession(profileData.chat_session_id, history);
      setResult(profileData.profile_result);
      setRecalcMap({});
      setView("chat");
    } catch {
      // Leave the user where they were, with nothing changed, if this fails.
    }
  };

  const handleStartNew = () => {
    if (result !== null) {
      setResult(null);
      setRecalcMap({});
      chatRef.current?.startFresh();
    }
    setView("chat");
  };

  const hasResults = result !== null;

  if (!authChecked) {
    return <div className="app-shell" />; // avoid a login-state flash while /auth/me resolves
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <button type="button" className="app-header__brand" onClick={() => setView("home")}>
          <span className="app-header__mark" aria-hidden="true" />
          <span className="app-header__name">Nedcore Bank</span>
        </button>
        <div className="app-header__right">
          <span className="app-header__product">Risk Profile &amp; Portfolio Match</span>
          <button
            type="button"
            className="app-header__avatar"
            onClick={() => setView("account")}
            aria-label="Account"
            title="Account"
          >
            {currentUser?.full_name?.[0]?.toUpperCase() || "👤"}
          </button>
          <NavMenu currentUser={currentUser} onNavigate={setView} onLogout={handleLogout} />
        </div>
      </header>

      {/*
        Single persistent chat area — NOT re-mounted between phases or
        when navigating to another view and back. Only its wrapping
        classes (and whether <main> is present as a sibling) change, so
        the ChatPanel instance and its message history survive intake
        -> results, and a trip to another view, intact. Hidden via CSS
        rather than unmounted when another view is active.
      */}
      <div
        className={`app-body ${hasResults ? "app-body--results" : "app-body--intake"}`}
        style={{ display: view === "chat" ? undefined : "none" }}
      >
        {hasResults && (
          <main className="results-shell__main">
            <ResultsPanel result={result} recalculatedProjections={recalcMap} />
          </main>
        )}

        <aside className={`chat-area ${hasResults ? "chat-area--docked" : "chat-area--full"} ${sheetExpanded ? "is-expanded" : ""}`}>
          {hasResults && (
            <button
              type="button"
              className="chat-dock__toggle"
              onClick={() => setSheetExpanded((e) => !e)}
            >
              <span className="chat-dock__toggle-icon">💬</span>
              {sheetExpanded ? "Hide chat" : "Ask about your results"}
            </button>
          )}
          <div className="chat-area__body">
            <ChatPanel
              ref={chatRef}
              sessionId={sessionId}
              setSessionId={setSessionId}
              authToken={authToken}
              onFinalized={handleFinalized}
              onRecalculated={handleRecalculated}
              onSummary={setActiveSummary}
              hasResults={hasResults}
            />
          </div>
        </aside>
      </div>

      {view === "home" && (
        <HomePage
          currentUser={currentUser}
          authToken={authToken}
          onStartNew={handleStartNew}
          onContinueProfile={handleContinueProfile}
          onSeeAllProfiles={() => setView("history")}
          onGoToLogin={() => setView("login")}
        />
      )}

      {view === "account" && (
        <AccountPage
          currentUser={currentUser}
          onBack={() => setView("home")}
          onLogout={handleLogout}
          onGoToLogin={() => setView("login")}
        />
      )}

      {view === "login" && (
        <AuthForm
          mode="login"
          onAuthenticated={handleAuthenticated}
          onSwitchMode={() => setView("signup")}
          onCancel={() => setView("home")}
        />
      )}
      {view === "signup" && (
        <AuthForm
          mode="signup"
          onAuthenticated={handleAuthenticated}
          onSwitchMode={() => setView("login")}
          onCancel={() => setView("home")}
        />
      )}
      {view === "history" && (
        <ProfileHistory
          authToken={authToken}
          onContinue={handleContinueProfile}
          onBack={() => setView("home")}
        />
      )}

      {activeSummary && (
        <SummaryModal
          summary={activeSummary}
          onConfirm={handleSummaryConfirm}
          onClose={() => setActiveSummary(null)}
        />
      )}
    </div>
  );
}
