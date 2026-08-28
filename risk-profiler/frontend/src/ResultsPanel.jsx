import { useState } from "react";
import RiskLadder from "./RiskLadder";
import Toast from "./Toast";

function formatRand(value) {
  return `R${Math.round(value).toLocaleString()}`;
}

/**
 * Purely a display component now — the finalize call happens once,
 * in App.jsx, when the chat confirms the profile. "What if" questions
 * are answered by the chat itself; when the chat's recalculation tool
 * fires, App.jsx merges the new numbers into `recalculatedProjections`
 * and this component just reflects whichever is freshest per product.
 */
export default function ResultsPanel({ result, recalculatedProjections }) {
  const [toastMessage, setToastMessage] = useState(null);

  const investNow = (productName) => {
    setToastMessage(`Great choice — we've started your application for ${productName}.`);
  };

  const markers = {
    tolerance: result.tolerance_band,
    capacity: result.capacity_band,
    horizon: result.horizon_band,
  };

  const projectionFor = (prod) => {
    const override = recalculatedProjections[`${prod.id}-${prod.portfolio_id}`];
    return override
      ? { ...override, isRecalculated: true }
      : prod.projection
      ? { ...prod.projection, isRecalculated: false }
      : null;
  };

  return (
    <div className="step-content step-content--enter">
      <header className="step-header">
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
              Governed by the lowest of tolerance, capacity, and horizon — the dot on the
              ladder shows which one is constraining. Ask the chat "what if I invest more"
              to see how the numbers below change.
            </p>
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
                          <div className={`projection-box mono ${projection.isRecalculated ? "projection-box--updated" : ""}`}>
                            {projection.isRecalculated && <span className="projection-box__badge">Updated</span>}
                            <span className="projection-box__expected">
                              {formatRand(projection.expected_value)}
                            </span>
                            <span className="projection-box__range">
                              {formatRand(projection.lower_value)} – {formatRand(projection.upper_value)}
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
