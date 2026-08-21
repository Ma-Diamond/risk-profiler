import { useEffect, useState } from "react";

const API_BASE = "http://localhost:8000";

export default function ConfirmModal({ quickProfile, extracted, onConfirm, onClose }) {
  const [fields, setFields] = useState({
    goals: (extracted.goals || []).join(", "),
    dependents: extracted.dependents ?? quickProfile.dependents,
    gross_monthly_income: extracted.gross_monthly_income ?? quickProfile.gross_monthly_income,
    monthly_expenses: extracted.monthly_expenses ?? quickProfile.monthly_expenses,
    tax_bracket: extracted.tax_bracket ?? "",
    notes: extracted.notes ?? "",
  });
  const [taxBracketIsEstimate, setTaxBracketIsEstimate] = useState(!extracted.tax_bracket);

  const set = (field, val) => setFields((f) => ({ ...f, [field]: val }));

  // Most people don't know their marginal tax bracket off-hand, so we
  // estimate it from income rather than asking — but show it here,
  // editable, rather than silently deciding it in the backend.
  useEffect(() => {
    if (extracted.tax_bracket) return; // client already stated one explicitly in chat
    const income = extracted.gross_monthly_income ?? quickProfile.gross_monthly_income;
    if (!income) return;
    fetch(`${API_BASE}/tax-estimate?monthly_income=${income}`)
      .then((r) => r.json())
      .then((data) => set("tax_bracket", data.label))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleConfirm = () => {
    onConfirm({
      goals: fields.goals.split(",").map((g) => g.trim()).filter(Boolean),
      dependents: Number(fields.dependents),
      gross_monthly_income: Number(fields.gross_monthly_income),
      monthly_expenses: Number(fields.monthly_expenses),
      tax_bracket: fields.tax_bracket,
      notes: fields.notes,
    });
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card card" onClick={(e) => e.stopPropagation()}>
        <h3 className="modal-card__title">Does this look right?</h3>
        <p className="step-subtitle">
          Here's what we picked up from the conversation — check it over and fix
          anything before we calculate your risk matrix.
        </p>

        <div className="modal-card__fields">
          <div>
            <label className="field-label">Goals</label>
            <input
              className="text-input"
              value={fields.goals}
              onChange={(e) => set("goals", e.target.value)}
              placeholder="retirement, house deposit"
            />
          </div>
          <div className="modal-card__row">
            <div>
              <label className="field-label">Dependents</label>
              <input
                className="text-input mono"
                type="number"
                value={fields.dependents}
                onFocus={(e) => e.target.select()}
                onChange={(e) => set("dependents", e.target.value)}
              />
            </div>
            <div>
              <label className="field-label">Tax bracket</label>
              <input
                className="text-input"
                value={fields.tax_bracket}
                onChange={(e) => {
                  setTaxBracketIsEstimate(false);
                  set("tax_bracket", e.target.value);
                }}
                placeholder="e.g. 31%"
              />
              {taxBracketIsEstimate && fields.tax_bracket && (
                <span className="modal-card__hint">Estimated from income — edit if you know yours</span>
              )}
            </div>
          </div>
          <div className="modal-card__row">
            <div>
              <label className="field-label">Gross monthly income (R)</label>
              <input
                className="text-input mono"
                type="number"
                value={fields.gross_monthly_income}
                onFocus={(e) => e.target.select()}
                onChange={(e) => set("gross_monthly_income", e.target.value)}
              />
            </div>
            <div>
              <label className="field-label">Monthly expenses (R)</label>
              <input
                className="text-input mono"
                type="number"
                value={fields.monthly_expenses}
                onFocus={(e) => e.target.select()}
                onChange={(e) => set("monthly_expenses", e.target.value)}
              />
            </div>
          </div>
          <div>
            <label className="field-label">Other notes</label>
            <input
              className="text-input"
              value={fields.notes}
              onChange={(e) => set("notes", e.target.value)}
              placeholder="Optional"
            />
          </div>
        </div>

        <div className="modal-card__actions">
          <button className="btn btn-ghost" onClick={onClose}>
            Keep chatting
          </button>
          <button className="btn btn-primary" onClick={handleConfirm}>
            Confirm &amp; see my matrix
          </button>
        </div>
      </div>
    </div>
  );
}
