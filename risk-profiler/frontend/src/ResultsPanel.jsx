import { useEffect, useState } from "react";
import RiskLadder from "./RiskLadder";
import Toast from "./Toast";

const API_BASE = "http://localhost:8000";

const DURATION_OPTIONS = [1, 2, 3, 5, 7, 10, 15, 20, 25, 30];

function formatRand(value) {
  return `R${Math.round(value).toLocaleString()}`;
}

export default function ResultsPanel({ quickProfile, sessionId }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [toastMessage, setToastMessage] = useState(null);

  const [calc, setCalc] = useState({
    horizonYears: quickProfile.investment_horizon_years,
    initialAmount: quickProfile.available_lump_sum,
    monthlyAmount: quickProfile.monthly_contribution,
  });
  const [recalculated, setRecalculated] = useState(null); // null = show default projections
  const [recalculating, setRecalculating] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/clients/profile`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...quickProfile, chat_session_id: sessionId }),
        });
        if (!res.ok) throw new Error((await res.json()).detail || "Request failed");
        setResult(await res.json());
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const investNow = (productName) => {
    setToastMessage(`Great choice — we've started your application for ${productName}.`);
  };

  const recalculate = async () => {
    if (!result) return;
    const pairs = result.matched_portfolios.flatMap((pf) =>
      pf.matched_products.map((prod) => ({ product_id: prod.id, portfolio_id: prod.portfolio_id }))
    );
    if (pairs.length === 0) return;

    setRecalculating(true);
    try {
      const res = await fetch(`${API_BASE}/projections/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          initial_amount: calc.initialAmount,
          monthly_amount: calc.monthlyAmount,
          horizon_years: calc.horizonYears,
          pairs,
        }),
      });
      if (!res.ok) throw new Error("Recalculation failed");
      const items = await res.json();
      const byKey = {};
      items.forEach((item) => {
        byKey[`${item.product_id}-${item.portfolio_id}`] = item.projection;
      });
      setRecalculated(byKey);
    } catch {
      // leave existing values in place on failure
    } finally {
      setRecalculating(false);
    }
  };

  const resetCalc = () => {
    setCalc({
      horizonYears: quickProfile.investment_horizon_years,
      initialAmount: quickProfile.available_lump_sum,
      monthlyAmount: quickProfile.monthly_contribution,
    });
    setRecalculated(null);
  };

  const projectionFor = (prod) => {
    if (recalculated) return recalculated[`${prod.id}-${prod.portfolio_id}`] ?? null;
    return prod.projection;
  };

  if (loading) {
    return (
      <div className="step-content">
        <p className="step-subtitle step-subtitle--loading">Calculating your risk matrix…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="step-content">
        <p className="field-error">{error}</p>
      </div>
    );
  }

  const markers = {
    tolerance: result.tolerance_band,
    capacity: result.capacity_band,
    horizon: result.horizon_band,
  };

  const durationOptions = DURATION_OPTIONS.includes(calc.horizonYears)
    ? DURATION_OPTIONS
    : [...DURATION_OPTIONS, calc.horizonYears].sort((a, b) => a - b);

  return (
    <div className="step-content step-content--enter">
      <header className="step-header">
        <span className="pill">Step 3 of 3</span>
        <h2>Your risk matrix</h2>
        {result.goals_detail && <p className="step-subtitle">Goals: {result.goals_detail}</p>}
      </header>

      <div className="results-layout">
        <div className={`results-hero card band-bg-${result.governed_risk_band}-wash card--pop-in`}>
          <div className="results-hero__ladder">
            <RiskLadder activeBand={result.governed_risk_band} markers={markers} />
          </div>
          <div className="results-hero__detail">
            <span className={`results-hero__band mono band-color-${result.governed_risk_band}`}>
              Band {result.governed_risk_band} / 5
            </span>
            <div className="results-hero__breakdown">
              <div>
                <span className="field-label">Tolerance</span>
                <span className="mono">{result.tolerance_band}</span>
              </div>
              <div>
                <span className="field-label">Capacity</span>
                <span className="mono">{result.capacity_band}</span>
              </div>
              <div>
                <span className="field-label">Horizon</span>
                <span className="mono">{result.horizon_band}</span>
              </div>
              {result.tax_bracket && (
                <div>
                  <span className="field-label">Tax bracket</span>
                  <span className="mono">
                    {result.tax_bracket}
                    {!result.tax_bracket_estimated && " (as provided)"}
                  </span>
                </div>
              )}
            </div>
            <p className="results-hero__note">
              Your recommendation is governed by the lowest of tolerance, capacity, and
              horizon — the dot on the ladder shows which one is doing the constraining.
            </p>
          </div>
        </div>

        <div className="calc-panel card">
          <div className="calc-panel__header">
            <h4 className="extracted-panel__title">Projection calculator</h4>
            <p className="step-subtitle">
              Try a different amount or duration — every projection below updates to match.
            </p>
          </div>
          <div className="calc-panel__controls">
            <div>
              <label className="field-label">Duration</label>
              <select
                className="select-input"
                value={calc.horizonYears}
                onChange={(e) => setCalc((c) => ({ ...c, horizonYears: Number(e.target.value) }))}
              >
                {durationOptions.map((y) => (
                  <option key={y} value={y}>
                    {y} year{y !== 1 ? "s" : ""}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="field-label">Initial amount (R)</label>
              <input
                type="number"
                className="text-input mono"
                value={calc.initialAmount}
                onFocus={(e) => e.target.select()}
                onChange={(e) => setCalc((c) => ({ ...c, initialAmount: Number(e.target.value) || 0 }))}
              />
            </div>
            <div>
              <label className="field-label">Monthly amount (R)</label>
              <input
                type="number"
                className="text-input mono"
                value={calc.monthlyAmount}
                onFocus={(e) => e.target.select()}
                onChange={(e) => setCalc((c) => ({ ...c, monthlyAmount: Number(e.target.value) || 0 }))}
              />
            </div>
          </div>
          <div className="calc-panel__actions">
            {recalculated && (
              <button className="btn btn-ghost" onClick={resetCalc}>
                Reset to my numbers
              </button>
            )}
            <button className="btn btn-primary" onClick={recalculate} disabled={recalculating}>
              {recalculating ? "Recalculating…" : "Recalculate"}
            </button>
          </div>
        </div>

        <h3 className="form-section__title">Matched portfolios &amp; products</h3>
        {result.matched_portfolios.map((p, i) => (
          <div
            key={p.id}
            className="portfolio-card card card--stagger-in"
            style={{ animationDelay: `${80 + i * 70}ms` }}
          >
            <div className="portfolio-card__header">
              <span className={`portfolio-card__band-dot band-bg-${p.risk_band}`} />
              <div>
                <strong>{p.name}</strong>
                <p className="portfolio-card__meta">
                  Up to {p.max_equity_pct}% equity · min {p.min_horizon_years}y horizon
                </p>
              </div>
            </div>
            <p className="portfolio-card__description">{p.description}</p>

            {p.matched_products.length > 0 ? (
              <div className="product-list">
                {p.matched_products.map((prod) => {
                  const projection = projectionFor(prod);
                  return (
                    <div
                      key={prod.id}
                      className={`product-row ${prod.is_top_pick ? "product-row--top-pick" : ""}`}
                    >
                      <div className="product-row__main">
                        <div className="product-row__heading">
                          {prod.is_top_pick && <span className="top-pick-badge">Top pick</span>}
                          <strong>{prod.name}</strong>
                          <span className="product-row__wrapper">{prod.tax_wrapper.replace(/_/g, " ")}</span>
                        </div>

                        {prod.is_top_pick && prod.top_pick_reason && (
                          <p className="product-row__top-reason">{prod.top_pick_reason}</p>
                        )}

                        {prod.reasons.length > 0 && (
                          <div className="product-row__tags">
                            {prod.reasons.map((reason) => (
                              <span key={reason} className="reason-tag">
                                {reason}
                              </span>
                            ))}
                          </div>
                        )}

                        {projection && (
                          <div className="projection-box mono">
                            <span className="projection-box__expected">
                              {formatRand(projection.expected_value)}
                            </span>
                            <span className="projection-box__range">
                              {formatRand(projection.lower_value)} – {formatRand(projection.upper_value)}
                            </span>
                            <span className="projection-box__meta">
                              projected after {calc.horizonYears}y · net {projection.net_expected_return_pct}%/yr
                            </span>
                          </div>
                        )}

                        <div className="product-row__stats mono">
                          <span>{prod.total_fee_pct}% fee</span>
                          <span>R{prod.min_initial_investment.toLocaleString()} min lump sum</span>
                          <span>R{prod.min_monthly_investment.toLocaleString()} min monthly</span>
                          <span>{prod.min_term_years > 0 ? `${prod.min_term_years}y lock-in` : "no lock-in"}</span>
                        </div>
                      </div>

                      <button className="btn btn-invest" onClick={() => investNow(prod.name)}>
                        Invest Now
                      </button>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="portfolio-card__no-products">
                Risk-appropriate, but no product here is currently accessible given your
                available amounts or goal.
              </p>
            )}
          </div>
        ))}

        {result.matched_portfolios.length === 0 && (
          <p className="step-subtitle">No portfolios matched — capital protection only.</p>
        )}

        <p className="projection-disclaimer">
          Projections use illustrative return assumptions and are not guaranteed —
          actual investment performance will vary.
        </p>
      </div>

      {toastMessage && <Toast message={toastMessage} onDismiss={() => setToastMessage(null)} />}
    </div>
  );
}
