import { useState } from "react";
import "./quick-flow.css";

const GOALS = [
  { value: "retirement", label: "Retirement" },
  { value: "house_deposit", label: "House deposit" },
  { value: "general_growth", label: "General growth" },
];

// Same 5 risk-attitude dimensions, in the same order, always asked —
// suitability assessment doesn't get skipped just because someone
// says they're experienced. Only the wording adapts, so a novice gets
// context and an experienced client isn't slowed down by it.
const TOL_QUESTIONS_NOVICE = [
  "I'd be comfortable seeing my investment drop 20% in a bad year, if it meant better growth over the long run.",
  "I'd rather invest in things I understand well than chase something complex with higher potential.",
  "If markets took a sudden downturn, I'd want to move my money to cash right away.",
  "I'm confident I won't need to touch this money for several years.",
  "I'm willing to take on some risk to pursue a good financial opportunity.",
];

const TOL_QUESTIONS_EXPERT = [
  "OK with a 20%+ drawdown for better long-run returns?",
  "Prefer simplicity over complexity, even capping upside?",
  "Would a downturn push you to de-risk immediately?",
  "Genuinely long horizon — no near-term liquidity need?",
  "Willing to lean into risk for the right opportunity?",
];

/** Number input that selects its contents on focus (see earlier fix)
 * and allows a genuinely empty field mid-edit. */
function NumberField({ value, onChange, onEnter, ...props }) {
  const [text, setText] = useState(String(value ?? ""));
  return (
    <input
      {...props}
      type="number"
      className="text-input mono qf-answer-input"
      value={text}
      autoFocus
      onFocus={(e) => e.target.select()}
      onChange={(e) => {
        const raw = e.target.value;
        setText(raw);
        onChange(raw === "" ? 0 : Number(raw));
      }}
      onBlur={() => {
        if (text === "") setText("0");
      }}
      onKeyDown={(e) => e.key === "Enter" && onEnter?.()}
    />
  );
}

// Fixed traversal order. Visibility of a few steps is conditional —
// see `isVisible` below — everything else always shows.
const STEP_ORDER = [
  "full_name",
  "knowledge_score",
  "age",
  "has_dependents",
  "dependents",
  "investment_goal",
  "investment_horizon_years",
  "gross_monthly_income",
  "monthly_expenses",
  "has_emergency_fund",
  "emergency_fund_months",
  "has_lump_sum",
  "available_lump_sum",
  "wants_monthly",
  "monthly_contribution",
  "tol_0",
  "tol_1",
  "tol_2",
  "tol_3",
  "tol_4",
];

function isVisible(id, gates) {
  switch (id) {
    case "dependents":
      return gates.hasDependents === true;
    case "emergency_fund_months":
      return gates.hasEmergencyFund === true;
    case "available_lump_sum":
      return gates.hasLumpSum === true;
    case "monthly_contribution":
      return gates.wantsMonthly === true;
    default:
      return true;
  }
}

export default function QuickQuestions({ value, onChange, onContinue }) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [gates, setGates] = useState({
    hasDependents: null,
    hasEmergencyFund: null,
    hasLumpSum: null,
    wantsMonthly: null,
  });
  const [attemptedAdvance, setAttemptedAdvance] = useState(false);

  const set = (field, val) => onChange({ ...value, [field]: val });
  const setQ = (i, val) => {
    const next = [...value.tolerance_questionnaire];
    next[i] = val;
    set("tolerance_questionnaire", next);
  };

  const visibleSteps = STEP_ORDER.filter((id) => isVisible(id, gates));
  const stepId = STEP_ORDER[currentIndex];
  const positionInFlow = visibleSteps.indexOf(stepId) + 1;

  const goNext = () => {
    let i = currentIndex + 1;
    while (i < STEP_ORDER.length && !isVisible(STEP_ORDER[i], gates)) i++;
    setAttemptedAdvance(false);
    if (i >= STEP_ORDER.length) {
      onContinue();
      return;
    }
    setCurrentIndex(i);
  };

  const goBack = () => {
    let i = currentIndex - 1;
    while (i >= 0 && !isVisible(STEP_ORDER[i], gates)) i--;
    if (i < 0) return;
    setAttemptedAdvance(false);
    setCurrentIndex(i);
  };

  const answerGate = (gateKey, answer, resetField) => {
    const nextGates = { ...gates, [gateKey]: answer };
    setGates(nextGates);
    if (answer === false && resetField) set(resetField, 0);

    let i = currentIndex + 1;
    while (i < STEP_ORDER.length && !isVisible(STEP_ORDER[i], nextGates)) i++;
    setAttemptedAdvance(false);
    if (i >= STEP_ORDER.length) onContinue();
    else setCurrentIndex(i);
  };

  const requiredButMissing =
    (stepId === "full_name" && !value.full_name.trim()) ||
    (stepId === "gross_monthly_income" && !value.gross_monthly_income);

  const handleNextClick = () => {
    setAttemptedAdvance(true);
    if (!requiredButMissing) goNext();
  };

  const tolTier = value.knowledge_score >= 4 ? TOL_QUESTIONS_EXPERT : TOL_QUESTIONS_NOVICE;

  const renderQuestion = () => {
    switch (stepId) {
      case "full_name":
        return (
          <>
            <h2 className="qf-question-text">What's your name?</h2>
            <input
              className="text-input qf-answer-input"
              autoFocus
              value={value.full_name}
              onChange={(e) => set("full_name", e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleNextClick()}
              placeholder="Jane Dlamini"
            />
            {attemptedAdvance && requiredButMissing && (
              <span className="field-error">Required</span>
            )}
          </>
        );

      case "knowledge_score":
        return (
          <>
            <h2 className="qf-question-text">How would you describe your investment experience?</h2>
            <div className="qf-option-list">
              {[
                [1, "New to investing"],
                [2, "Some familiarity"],
                [3, "Comfortable"],
                [4, "Experienced"],
                [5, "Expert"],
              ].map(([v, label]) => (
                <button
                  key={v}
                  type="button"
                  className={`qf-option ${value.knowledge_score === v ? "is-active" : ""}`}
                  onClick={() => {
                    set("knowledge_score", v);
                    goNext();
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </>
        );

      case "age":
        return (
          <>
            <h2 className="qf-question-text">How old are you?</h2>
            <NumberField value={value.age} onChange={(v) => set("age", v)} onEnter={handleNextClick} />
          </>
        );

      case "has_dependents":
        return (
          <>
            <h2 className="qf-question-text">Do you have any financial dependents?</h2>
            <div className="qf-yesno">
              <button
                className={`qf-yesno__btn ${gates.hasDependents === true ? "is-active" : ""}`}
                onClick={() => answerGate("hasDependents", true)}
              >
                Yes
              </button>
              <button
                className={`qf-yesno__btn ${gates.hasDependents === false ? "is-active" : ""}`}
                onClick={() => answerGate("hasDependents", false, "dependents")}
              >
                No
              </button>
            </div>
          </>
        );

      case "dependents":
        return (
          <>
            <h2 className="qf-question-text">How many dependents do you have?</h2>
            <NumberField
              value={value.dependents}
              onChange={(v) => set("dependents", v)}
              onEnter={handleNextClick}
            />
          </>
        );

      case "investment_goal":
        return (
          <>
            <h2 className="qf-question-text">What's your main investment goal?</h2>
            <div className="qf-option-list">
              {GOALS.map((g) => (
                <button
                  key={g.value}
                  type="button"
                  className={`qf-option ${value.investment_goal === g.value ? "is-active" : ""}`}
                  onClick={() => {
                    set("investment_goal", g.value);
                    goNext();
                  }}
                >
                  {g.label}
                </button>
              ))}
            </div>
          </>
        );

      case "investment_horizon_years":
        return (
          <>
            <h2 className="qf-question-text">How many years until you might need this money?</h2>
            <NumberField
              value={value.investment_horizon_years}
              onChange={(v) => set("investment_horizon_years", v)}
              onEnter={handleNextClick}
            />
          </>
        );

      case "gross_monthly_income":
        return (
          <>
            <h2 className="qf-question-text">What's your gross monthly income? (R)</h2>
            <NumberField
              value={value.gross_monthly_income}
              onChange={(v) => set("gross_monthly_income", v)}
              onEnter={handleNextClick}
            />
            {attemptedAdvance && requiredButMissing && (
              <span className="field-error">Required</span>
            )}
          </>
        );

      case "monthly_expenses":
        return (
          <>
            <h2 className="qf-question-text">Roughly what are your monthly expenses? (R)</h2>
            <NumberField
              value={value.monthly_expenses}
              onChange={(v) => set("monthly_expenses", v)}
              onEnter={handleNextClick}
            />
          </>
        );

      case "has_emergency_fund":
        return (
          <>
            <h2 className="qf-question-text">Do you have money set aside for emergencies?</h2>
            <div className="qf-yesno">
              <button
                className={`qf-yesno__btn ${gates.hasEmergencyFund === true ? "is-active" : ""}`}
                onClick={() => answerGate("hasEmergencyFund", true)}
              >
                Yes
              </button>
              <button
                className={`qf-yesno__btn ${gates.hasEmergencyFund === false ? "is-active" : ""}`}
                onClick={() => answerGate("hasEmergencyFund", false, "emergency_fund_months")}
              >
                No
              </button>
            </div>
          </>
        );

      case "emergency_fund_months":
        return (
          <>
            <h2 className="qf-question-text">Roughly how many months of expenses does it cover?</h2>
            <NumberField
              value={value.emergency_fund_months}
              onChange={(v) => set("emergency_fund_months", v)}
              onEnter={handleNextClick}
            />
          </>
        );

      case "has_lump_sum":
        return (
          <>
            <h2 className="qf-question-text">Do you have a lump sum ready to invest right now?</h2>
            <div className="qf-yesno">
              <button
                className={`qf-yesno__btn ${gates.hasLumpSum === true ? "is-active" : ""}`}
                onClick={() => answerGate("hasLumpSum", true)}
              >
                Yes
              </button>
              <button
                className={`qf-yesno__btn ${gates.hasLumpSum === false ? "is-active" : ""}`}
                onClick={() => answerGate("hasLumpSum", false, "available_lump_sum")}
              >
                No
              </button>
            </div>
          </>
        );

      case "available_lump_sum":
        return (
          <>
            <h2 className="qf-question-text">How much? (R)</h2>
            <NumberField
              value={value.available_lump_sum}
              onChange={(v) => set("available_lump_sum", v)}
              onEnter={handleNextClick}
            />
          </>
        );

      case "wants_monthly":
        return (
          <>
            <h2 className="qf-question-text">Would you like to also invest a set amount every month?</h2>
            <div className="qf-yesno">
              <button
                className={`qf-yesno__btn ${gates.wantsMonthly === true ? "is-active" : ""}`}
                onClick={() => answerGate("wantsMonthly", true)}
              >
                Yes
              </button>
              <button
                className={`qf-yesno__btn ${gates.wantsMonthly === false ? "is-active" : ""}`}
                onClick={() => answerGate("wantsMonthly", false, "monthly_contribution")}
              >
                No
              </button>
            </div>
          </>
        );

      case "monthly_contribution":
        return (
          <>
            <h2 className="qf-question-text">How much per month? (R)</h2>
            <NumberField
              value={value.monthly_contribution}
              onChange={(v) => set("monthly_contribution", v)}
              onEnter={handleNextClick}
            />
          </>
        );

      default: {
        // tol_0..tol_4
        const i = Number(stepId.split("_")[1]);
        return (
          <>
            <h2 className="qf-question-text">{tolTier[i]}</h2>
            <p className="form-section__hint">1 = disagree, 5 = agree</p>
            <div className="qf-likert">
              <input
                type="range"
                min={1}
                max={5}
                className="range-input"
                value={value.tolerance_questionnaire[i]}
                onChange={(e) => setQ(i, Number(e.target.value))}
              />
              <span className="qf-likert__value mono">{value.tolerance_questionnaire[i]}</span>
            </div>
          </>
        );
      }
    }
  };

  // Types that auto-advance on selection (button-style answers) don't
  // need a visible Next button — yesno, knowledge_score, and
  // investment_goal all call goNext() themselves.
  const showNextButton = !["has_dependents", "has_emergency_fund", "has_lump_sum", "wants_monthly", "knowledge_score", "investment_goal"].includes(stepId);

  return (
    <div className="step-content step-content--enter">
      <header className="step-header">
        <span className="pill">Step 1 of 3</span>
        <h2>Tell us the basics</h2>
        <p className="step-subtitle">
          One question at a time — we'll only ask what's actually relevant to you.
        </p>
      </header>

      <div className="qf-progress">
        <div className="qf-progress__track">
          <div
            className="qf-progress__fill"
            style={{ width: `${(positionInFlow / visibleSteps.length) * 100}%` }}
          />
        </div>
        <span className="qf-progress__label mono">
          {positionInFlow} / {visibleSteps.length}
        </span>
      </div>

      <div key={stepId} className="qf-card card">
        {renderQuestion()}
      </div>

      <div className="step-actions qf-actions">
        <button className="btn btn-ghost" onClick={goBack} disabled={currentIndex === 0}>
          Back
        </button>
        {showNextButton && (
          <button className="btn btn-primary" onClick={handleNextClick}>
            Next
          </button>
        )}
      </div>
    </div>
  );
}
