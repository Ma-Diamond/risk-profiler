import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

const RA_DISCLAIMER = [
  "This is a retirement annuity (RA), governed by the Pension Funds Act. You will not be able to withdraw any portion of this investment until you reach age 55 (or later, if you choose to defer retirement) — this money is locked until then, no exceptions.",
  "Because it's locked, this RA can't serve as your accessible emergency or short-term savings — keep that in your everyday or savings account instead, not here.",
  "You must nominate a beneficiary for this policy. If you pass away before retirement, the proceeds go to your nominated beneficiary, not automatically to your estate.",
  "Contributions may qualify for a tax deduction, up to the SARS-permitted limit (27.5% of taxable income, capped at R350,000 per year).",
  "Returns are not guaranteed and depend on the performance of the underlying portfolio. Fees apply as already shown for this product.",
];

const ENDOWMENT_DISCLAIMER = [
  "This is a 5-year endowment policy. South African regulation restricts withdrawals during the first 5 years — at most one partial withdrawal and one policy loan are permitted in that period.",
  "Returns are not guaranteed and depend on the performance of the underlying portfolio. Fees apply as already shown for this product.",
  "This policy falls outside your estate for creditor purposes in most cases, but speak to an advisor if this matters for your specific situation.",
];

const GENERIC_DISCLAIMER = [
  "Returns are not guaranteed and depend on the performance of the underlying portfolio. Fees apply as already shown for this product.",
  "You can typically access this investment without a fixed lock-in, subject to the product's own minimum term shown earlier.",
];

function disclaimerFor(taxWrapper) {
  if (taxWrapper === "retirement_annuity") return RA_DISCLAIMER;
  if (taxWrapper === "endowment") return ENDOWMENT_DISCLAIMER;
  return GENERIC_DISCLAIMER;
}

const emptyForm = {
  full_name: "",
  id_number: "",
  date_of_birth: "",
  address: "",
  contact_number: "",
  email: "",
  bank_name: "",
  bank_account_number: "",
  branch_code: "",
};

const emptyBeneficiary = { full_name: "", id_number: "", relationship: "" };

export default function InvestmentApplicationModal({
  product,
  portfolio,
  clientId,
  defaultInitialAmount,
  defaultMonthlyAmount,
  authToken,
  onClose,
  onOpened,
}) {
  const [step, setStep] = useState("form"); // "form" | "disclaimer" | "success"
  const [form, setForm] = useState({ ...emptyForm });
  const [beneficiary, setBeneficiary] = useState({ ...emptyBeneficiary });
  const [initialAmount, setInitialAmount] = useState(defaultInitialAmount || 0);
  const [monthlyAmount, setMonthlyAmount] = useState(defaultMonthlyAmount || 0);
  const [disclaimerChecked, setDisclaimerChecked] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [openedAccount, setOpenedAccount] = useState(null);

  const isRA = product.tax_wrapper === "retirement_annuity";

  const updateField = (field, value) => setForm((f) => ({ ...f, [field]: value }));
  const updateBeneficiary = (field, value) => setBeneficiary((b) => ({ ...b, [field]: value }));

  const formComplete =
    Object.values(form).every((v) => v.trim() !== "") &&
    (!isRA || Object.values(beneficiary).every((v) => v.trim() !== ""));

  const goToDisclaimer = (e) => {
    e.preventDefault();
    if (!formComplete) return;
    setStep("disclaimer");
  };

  const submitApplication = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/accounts`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${authToken}` },
        body: JSON.stringify({
          client_id: clientId,
          product_id: product.id,
          portfolio_id: portfolio.id,
          initial_amount: Number(initialAmount) || 0,
          monthly_amount: Number(monthlyAmount) || 0,
          ...form,
          beneficiary: isRA ? beneficiary : null,
        }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Couldn't open the account");
      const account = await res.json();
      setOpenedAccount(account);
      setStep("success");
      onOpened?.(account);
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-card card application-modal">
        {step === "form" && (
          <form onSubmit={goToDisclaimer}>
            <h3 className="modal-card__title">Apply for {product.name}</h3>
            <p className="step-subtitle">
              {isRA ? "Retirement annuity" : product.tax_wrapper.replace(/_/g, " ")} · {portfolio.name}
            </p>

            <div className="application-form__amounts">
              <div>
                <label className="field-label">Lump sum now</label>
                <input
                  className="text-input"
                  type="number"
                  min="0"
                  value={initialAmount}
                  onChange={(e) => setInitialAmount(e.target.value)}
                />
              </div>
              <div>
                <label className="field-label">Monthly contribution</label>
                <input
                  className="text-input"
                  type="number"
                  min="0"
                  value={monthlyAmount}
                  onChange={(e) => setMonthlyAmount(e.target.value)}
                />
              </div>
            </div>

            <p className="form-section__title">Your details</p>
            <div className="application-form__grid">
              <div>
                <label className="field-label">Full legal name</label>
                <input className="text-input" value={form.full_name} onChange={(e) => updateField("full_name", e.target.value)} required />
              </div>
              <div>
                <label className="field-label">SA ID number</label>
                <input className="text-input" value={form.id_number} onChange={(e) => updateField("id_number", e.target.value)} required />
              </div>
              <div>
                <label className="field-label">Date of birth</label>
                <input className="text-input" type="date" value={form.date_of_birth} onChange={(e) => updateField("date_of_birth", e.target.value)} required />
              </div>
              <div>
                <label className="field-label">Contact number</label>
                <input className="text-input" value={form.contact_number} onChange={(e) => updateField("contact_number", e.target.value)} required />
              </div>
              <div className="application-form__full-row">
                <label className="field-label">Residential address</label>
                <input className="text-input" value={form.address} onChange={(e) => updateField("address", e.target.value)} required />
              </div>
              <div className="application-form__full-row">
                <label className="field-label">Email</label>
                <input className="text-input" type="email" value={form.email} onChange={(e) => updateField("email", e.target.value)} required />
              </div>
            </div>

            <p className="form-section__title">Debit order banking details</p>
            <div className="application-form__grid">
              <div>
                <label className="field-label">Bank name</label>
                <input className="text-input" value={form.bank_name} onChange={(e) => updateField("bank_name", e.target.value)} required />
              </div>
              <div>
                <label className="field-label">Account number</label>
                <input className="text-input" value={form.bank_account_number} onChange={(e) => updateField("bank_account_number", e.target.value)} required />
              </div>
              <div>
                <label className="field-label">Branch code</label>
                <input className="text-input" value={form.branch_code} onChange={(e) => updateField("branch_code", e.target.value)} required />
              </div>
            </div>

            {isRA && (
              <>
                <p className="form-section__title">Beneficiary (required for a retirement annuity)</p>
                <div className="application-form__grid">
                  <div>
                    <label className="field-label">Beneficiary full name</label>
                    <input className="text-input" value={beneficiary.full_name} onChange={(e) => updateBeneficiary("full_name", e.target.value)} required />
                  </div>
                  <div>
                    <label className="field-label">Beneficiary SA ID number</label>
                    <input className="text-input" value={beneficiary.id_number} onChange={(e) => updateBeneficiary("id_number", e.target.value)} required />
                  </div>
                  <div>
                    <label className="field-label">Relationship to you</label>
                    <input className="text-input" value={beneficiary.relationship} onChange={(e) => updateBeneficiary("relationship", e.target.value)} required />
                  </div>
                </div>
              </>
            )}

            <div className="modal-card__actions">
              <button type="button" className="btn btn-ghost" onClick={onClose}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={!formComplete}>
                Continue
              </button>
            </div>
          </form>
        )}

        {step === "disclaimer" && (
          <>
            <h3 className="modal-card__title">Before you confirm</h3>
            <p className="step-subtitle">Please read this — it matters for how this product works.</p>
            <ul className="disclaimer-list">
              {disclaimerFor(product.tax_wrapper).map((point, i) => (
                <li key={i}>{point}</li>
              ))}
            </ul>
            <label className="disclaimer-checkbox">
              <input
                type="checkbox"
                checked={disclaimerChecked}
                onChange={(e) => setDisclaimerChecked(e.target.checked)}
              />
              I've read and understand this, and want to proceed.
            </label>

            {error && <p className="field-error">{error}</p>}

            <div className="modal-card__actions">
              <button type="button" className="btn btn-ghost" onClick={() => setStep("form")} disabled={submitting}>
                Back
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={submitApplication}
                disabled={!disclaimerChecked || submitting}
              >
                {submitting ? "Opening…" : "Confirm and open account"}
              </button>
            </div>
          </>
        )}

        {step === "success" && openedAccount && (
          <>
            <h3 className="modal-card__title">🎉 Account opened</h3>
            <p className="step-subtitle">
              Your {openedAccount.product_name} is active. It'll show up on your profile page from now on.
            </p>
            <div className="modal-card__actions">
              <button type="button" className="btn btn-primary" onClick={onClose}>
                Done
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
