const GOAL_LABELS = {
  retirement: "Retirement",
  house_deposit: "House deposit",
  general_growth: "General growth",
};

function Row({ label, value }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="summary-modal__row">
      <span className="summary-modal__label">{label}</span>
      <span className="summary-modal__value">{value}</span>
    </div>
  );
}

export default function SummaryModal({ summary, onConfirm, onClose }) {
  const rand = (v) => (v || v === 0 ? `R${Number(v).toLocaleString()}` : null);
  const goalLine = [
    summary.investment_goal_label || GOAL_LABELS[summary.investment_goal],
    summary.investment_horizon_years ? `~${summary.investment_horizon_years} years away` : null,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card card summary-modal" onClick={(e) => e.stopPropagation()}>
        <h3 className="modal-card__title">Does this look right?</h3>
        <p className="step-subtitle">Here's everything gathered so far — check it over.</p>

        <div className="summary-modal__body">
          <Row label="Name" value={summary.full_name} />
          <Row label="Age" value={summary.age} />
          <Row label="Dependents" value={summary.dependents} />
          <Row label="Goal" value={goalLine || null} />
          {summary.goals && summary.goals.length > 0 && (
            <Row label="In their words" value={summary.goals.join(", ")} />
          )}
          <Row label="Gross monthly income" value={rand(summary.gross_monthly_income)} />
          <Row label="Monthly expenses" value={rand(summary.monthly_expenses)} />
          <Row
            label="Emergency fund"
            value={
              summary.emergency_fund_months || summary.emergency_fund_months === 0
                ? `${summary.emergency_fund_months} months of expenses`
                : null
            }
          />
          <Row label="Lump sum to invest" value={rand(summary.available_lump_sum) || "None"} />
          <Row label="Monthly contribution" value={rand(summary.monthly_contribution) || "None"} />
          <Row
            label="Investing experience"
            value={summary.knowledge_score ? `${summary.knowledge_score}/5` : null}
          />
          {summary.tolerance_questionnaire && (
            <Row label="Risk ratings" value={summary.tolerance_questionnaire.join(", ")} />
          )}
          {summary.tax_bracket && <Row label="Tax bracket" value={summary.tax_bracket} />}
          {summary.notes && <Row label="Notes" value={summary.notes} />}
        </div>

        <div className="modal-card__actions">
          <button className="btn btn-ghost" onClick={onClose}>
            I need to fix something
          </button>
          <button className="btn btn-primary" onClick={onConfirm}>
            Looks good — continue
          </button>
        </div>
      </div>
    </div>
  );
}
