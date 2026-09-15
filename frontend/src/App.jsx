import { useEffect, useRef, useState } from "react";
import ChatPanel from "./ChatPanel";
import ResultsPanel from "./ResultsPanel";
import SummaryModal from "./SummaryModal";
import AuthForm from "./AuthForm";
import ProfileHistory from "./ProfileHistory";
import LandingPage from "./LandingPage";
import AccountPage from "./AccountPage";
import AccountsPage from "./AccountsPage";
import NavMenu from "./NavMenu";
import ShieldMark from "./ShieldMark";
import AdvisorButton from "./AdvisorButton";
import "./tokens.css";
import "./global.css";
import "./layout.css";
import "./animations.css";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";
const TOKEN_STORAGE_KEY = "risk_profiler_token";

export default function App() {
  const [sessionId, setSessionId] = useState(null);
  const [result, setResult] = useState(null);
  const [recalculatedProducts, setRecalculatedProducts] = useState(null);
  const [recalculatedNote, setRecalculatedNote] = useState(null);
  const [accounts, setAccounts] = useState([]);
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
  const [savedProfile, setSavedProfile] = useState(null);

  const fetchSavedProfile = async (token) => {
    try {
      const res = await fetch(`${API_BASE}/auth/me/profile`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setSavedProfile(await res.json());
    } catch {
      // Prepopulation is a convenience, not a requirement — the forms
      // just fall back to starting blank if this fails.
    }
  };

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
        fetchSavedProfile(stored);
      } catch {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
      } finally {
        setAuthChecked(true);
      }
    })();
  }, []);

  const handleFinalized = (profileResult) => {
    setResult(profileResult);
    setRecalculatedProducts(null);
    setRecalculatedNote(null);
    setAccounts([]);
  };

  const handleRecalculated = (products, note) => {
    setRecalculatedProducts(products);
    setRecalculatedNote(note);
    setSheetExpanded(true);
  };

  const handleAccountOpened = (account) => {
    setAccounts((prev) => [...prev, account]);
    // Opening an account also saves the KYC/banking details the client
    // just typed onto their saved profile server-side — refresh our
    // copy so a second Invest Now (or a visit to the profile page) in
    // this same session is prefilled with it too, not just next login.
    if (authToken) fetchSavedProfile(authToken);
  };

  const handleSummaryConfirm = () => {
    setActiveSummary(null);
    chatRef.current?.sendProgrammaticMessage("Yes, that all looks right — please proceed.");
  };

  const handleAuthenticated = (token, user) => {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
    setAuthToken(token);
    setCurrentUser(user);
    fetchSavedProfile(token);
    setView("home");
    setResult(null);
    setRecalculatedProducts(null);
    setRecalculatedNote(null);
    setAccounts([]);
    chatRef.current?.startFresh();
  };

  const handleLogout = () => {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setAuthToken(null);
    setCurrentUser(null);
    setView("home");
    setResult(null);
    setRecalculatedProducts(null);
    setRecalculatedNote(null);
    setAccounts([]);
    chatRef.current?.startFresh();
  };

  const handleContinueProfile = async (clientId) => {
    try {
      const headers = { Authorization: `Bearer ${authToken}` };
      const profileRes = await fetch(`${API_BASE}/profiles/${clientId}`, { headers });
      if (!profileRes.ok) {
        const detail = await profileRes.json().catch(() => ({}));
        throw new Error(detail.detail || `Couldn't load that profile (${profileRes.status})`);
      }
      const profileData = await profileRes.json();

      const historyRes = await fetch(
        `${API_BASE}/chat/sessions/${profileData.chat_session_id}/history`,
        { headers }
      );
      const history = historyRes.ok ? await historyRes.json() : [];

      chatRef.current?.resumeSession(profileData.chat_session_id, history);
      setResult(profileData.profile_result);
      setRecalculatedProducts(null);
      setRecalculatedNote(null);
      setAccounts(profileData.accounts || []);
      setView("chat");
    } catch (e) {
      // Temporary: surfacing this instead of swallowing it silently so
      // we can see exactly what's failing — replace with a proper
      // toast once we know the real cause.
      console.error("handleContinueProfile failed:", e);
      alert(`Couldn't continue that profile: ${e.message}`);
    }
  };

  // The landing page is now the entry point for starting a fresh
  // conversation — it collects the chosen language and (optionally) an
  // opening message (typed in the search bar, or a suggestion pill)
  // before the chat itself ever starts, so the very first session is
  // created with the right language rather than defaulting to English
  // and switching mid-conversation.
  const handleLandingStart = (text, language) => {
    if (result !== null) {
      setResult(null);
      setRecalculatedProducts(null);
      setRecalculatedNote(null);
      setAccounts([]);
    }
    chatRef.current?.startWithMessage(text, language);
    setView("chat");
  };

  const hasResults = result !== null;

  if (!authChecked) {
    return <div className="app-shell" />;
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <button type="button" className="app-header__brand" onClick={() => setView("home")}>
          <ShieldMark size={26} />
          <span className="app-header__name">Standard Bank</span>
        </button>
        <div className="app-header__right">
          <span className="app-header__product">AI Financial Guide</span>
          <AdvisorButton />
          <NavMenu currentUser={currentUser} onNavigate={setView} onLogout={handleLogout} />
        </div>
      </header>

      <div
        className={`app-body ${hasResults ? "app-body--results" : "app-body--intake"}`}
        style={{ display: view === "chat" ? undefined : "none" }}
      >
        {hasResults && (
          <main className="results-shell__main">
            <ResultsPanel
              result={result}
              recalculatedProducts={recalculatedProducts}
              recalculatedNote={recalculatedNote}
              accounts={accounts}
              authToken={authToken}
              savedProfile={savedProfile}
              onAccountOpened={handleAccountOpened}
            />
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

      {view === "home" && <LandingPage onStart={handleLandingStart} />}

      {view === "account" && (
        <AccountPage
          currentUser={currentUser}
          onBack={() => setView("home")}
          onLogout={handleLogout}
          onGoToLogin={() => setView("login")}
        />
      )}

      {view === "accounts" && (
        <AccountsPage authToken={authToken} onBack={() => setView("home")} />
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
