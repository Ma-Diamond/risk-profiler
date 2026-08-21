import { useState } from "react";
import RiskLadder from "./RiskLadder";
import QuickQuestions from "./QuickQuestions";
import ChatPanel from "./ChatPanel";
import ConfirmModal from "./ConfirmModal";
import ResultsPanel from "./ResultsPanel";
import "./tokens.css";
import "./global.css";
import "./layout.css";
import "./animations.css";

const API_BASE = "http://localhost:8000";

const INITIAL_PROFILE = {
  full_name: "",
  age: 30,
  dependents: 0,
  gross_monthly_income: 0,
  monthly_expenses: 0,
  emergency_fund_months: 3,
  investment_horizon_years: 5,
  investment_goal: "general_growth",
  tolerance_questionnaire: [3, 3, 3, 3, 3],
  knowledge_score: 3,
  available_lump_sum: 0,
  monthly_contribution: 500,
};

const STEPS = ["Profile", "Conversation", "Your matrix"];

export default function App() {
  const [step, setStep] = useState(0);
  const [quickProfile, setQuickProfile] = useState(INITIAL_PROFILE);
  const [sessionId, setSessionId] = useState(null);
  const [extracted, setExtracted] = useState({});
  const [showConfirm, setShowConfirm] = useState(false);

  // Rough live estimate of tolerance band, purely for the ladder
  // preview before the backend has computed anything server-side.
  const previewTolerance = Math.min(
    5,
    Math.max(
      1,
      Math.ceil(
        (quickProfile.tolerance_questionnaire.reduce((a, b) => a + b, 0) / 25) * 5
      )
    )
  );

  const handleConfirm = async (editedFields) => {
    try {
      await fetch(`${API_BASE}/chat/sessions/${sessionId}/extracted`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ extracted: { ...extracted, ...editedFields } }),
      });
    } catch {
      // If the save fails, we still move forward — /clients/profile will
      // just fall back to whatever the session already had persisted.
    }
    setExtracted((e) => ({ ...e, ...editedFields }));
    setShowConfirm(false);
    setStep(2);
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header__brand">
          <span className="app-header__mark" aria-hidden="true" />
          <span className="app-header__name">Nedcore Bank</span>
        </div>
        <span className="app-header__product">Risk Profile &amp; Portfolio Match</span>
      </header>

      <div className="app-body">
        <aside className="app-rail">
          <div className="app-rail__ladder-wrap card">
            <span className="field-label">Your risk profile</span>
            <RiskLadder activeBand={step === 0 ? 0 : previewTolerance} />
          </div>
          <ol className="app-rail__steps">
            {STEPS.map((label, i) => (
              <li
                key={label}
                className={`app-rail__step ${i === step ? "is-active" : ""} ${i < step ? "is-done" : ""}`}
              >
                <span className="app-rail__step-index mono">{i + 1}</span>
                {label}
              </li>
            ))}
          </ol>
        </aside>

        <main className="app-main">
          <div className="app-mobile-ladder">
            <RiskLadder
              activeBand={step === 0 ? 0 : previewTolerance}
              orientation="horizontal"
            />
          </div>

          {step === 0 && (
            <QuickQuestions
              value={quickProfile}
              onChange={setQuickProfile}
              onContinue={() => setStep(1)}
            />
          )}
          {step === 1 && (
            <ChatPanel
              quickProfile={quickProfile}
              sessionId={sessionId}
              setSessionId={setSessionId}
              extracted={extracted}
              setExtracted={setExtracted}
              onContinue={() => setShowConfirm(true)}
            />
          )}
          {step === 2 && <ResultsPanel quickProfile={quickProfile} sessionId={sessionId} />}
        </main>
      </div>

      {showConfirm && (
        <ConfirmModal
          quickProfile={quickProfile}
          extracted={extracted}
          onConfirm={handleConfirm}
          onClose={() => setShowConfirm(false)}
        />
      )}
    </div>
  );
}
