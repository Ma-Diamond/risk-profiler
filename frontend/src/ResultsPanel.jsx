import { useState } from "react";
import RiskLadder from "./RiskLadder";
import Toast from "./Toast";
import InvestmentApplicationModal from "./InvestmentApplicationModal";
import { t } from "./i18n";

function formatRand(value) {
  return `R${Math.round(value).toLocaleString()}`;
}

const INITIAL_VISIBLE_PRODUCTS = 3;

function ProductCard({ product, isTop, existingAccount, onInvest, style, language }) {
  return (
    <div
      className={`portfolio-card card card--stagger-in ${product.is_top_pick ? "product-card--top-pick" : ""}`}
      style={style}
    >
      <div className="portfolio-card__header">
        <div className="product-card__heading-row">
          {product.is_top_pick && <span className="top-pick-badge">Top pick</span>}
          <strong>{product.name}</strong>
          <span className="product-row__wrapper">{product.tax_wrapper.replace(/_/g, " ")}</span>
        </div>
      </div>

      {product.is_top_pick && product.top_pick_reason && (
        <p className="product-row__top-reason">{product.top_pick_reason}</p>
      )}

      {product.reasons.length > 0 && (
        <div className="product-row__tags">
          {product.reasons.map((reason) => (
            <span key={reason} className="reason-tag">
              {reason}
            </span>
          ))}
        </div>
      )}

      {product.total_expected_value != null && (
        <div className="projection-box mono">
          <span className="projection-box__expected">{formatRand(product.total_expected_value)}</span>
          <span className="projection-box__range">
            {formatRand(product.total_lower_value)} – {formatRand(product.total_upper_value)}
          </span>
        </div>
      )}

      <div className="product-row__stats mono">
        <span>{product.total_fee_pct}% effective fee</span>
        <span>R{product.min_initial_investment.toLocaleString()} min lump sum</span>
        <span>R{product.min_monthly_investment.toLocaleString()} min monthly</span>
        <span>{product.min_term_years > 0 ? `${product.min_term_years}y lock-in` : "no lock-in"}</span>
      </div>

      {/* A client holds several portfolios inside one product, splitting
          contributions between them — this is that recommended split,
          weighted toward the best-fit portfolio with smaller shares for
          diversification. */}
      <div className="portfolio-split">
        <p className="portfolio-split__title">{t(language, "results.recommendedSplit")}</p>
        {product.recommended_portfolios.map((rp) => (
          <div key={rp.portfolio_id} className="portfolio-split__row">
            <div className="portfolio-split__bar-wrap">
              <div className="portfolio-split__bar" style={{ width: `${rp.allocation_pct}%` }} />
            </div>
            <div className="portfolio-split__main">
              <div className="portfolio-split__heading">
                <span className="portfolio-split__name">{rp.portfolio_name}</span>
                <span className="portfolio-split__pct mono">{rp.allocation_pct}%</span>
              </div>
              <span className="portfolio-split__meta mono">
                {rp.split_initial_amount > 0 && `${formatRand(rp.split_initial_amount)} lump · `}
                {rp.split_monthly_amount > 0 && `${formatRand(rp.split_monthly_amount)}/mo · `}
                {rp.fee_pct}% fee
                {rp.projection && ` · projects to ${formatRand(rp.projection.expected_value)}`}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="product-card__footer">
        {existingAccount ? (
          <span className={`pill pill--${existingAccount.status}`}>
            {existingAccount.status === "pending" ? t(language, "accounts.pending") : existingAccount.status}
          </span>
        ) : (
          <button className="btn btn-invest" onClick={onInvest}>
            {t(language, "results.investNow")}
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Mostly a display component — the finalize call happens once, in
 * App.jsx, when the chat confirms the profile.
 *
 * Product-centric: each matched PRODUCT carries its own recommended
 * SPLIT across one or more portfolios (a client holds several
 * portfolios inside one product, not one portfolio per product).
 * Products with no eligible portfolio never reach this component at
 * all — the backend drops them during matching.
 *
 * A "what if" question in chat can return a fully re-matched,
 * possibly different product set (recalculatedProducts) — this is a
 * PREVIEW only, never persisted, so it's shown with a clear banner and
 * a toggle back to the client's actual saved results rather than
 * silently replacing them.
 *
 * Invest Now currently opens an account against the single top-ranked
 * portfolio in a product's recommended split, not the full multi-
 * portfolio split — genuinely splitting one application across
 * several portfolios is a further piece of work beyond this pass.
 */
export default function ResultsPanel({
  result,
  recalculatedProducts,
  recalculatedNote,
  accounts = [],
  authToken,
  savedProfile,
  onAccountOpened,
  language,
}) {
  const [toastMessage, setToastMessage] = useState(null);
  const [applicationTarget, setApplicationTarget] = useState(null);
  const [showAllProducts, setShowAllProducts] = useState(false);
  const [showingPreview, setShowingPreview] = useState(true);

  const isPreview = recalculatedProducts != null;
  const displayedProducts = isPreview && showingPreview ? recalculatedProducts : result.matched_products;

  const visibleProducts = showAllProducts
    ? displayedProducts
    : displayedProducts.slice(0, INITIAL_VISIBLE_PRODUCTS);
  const hiddenCount = displayedProducts.length - visibleProducts.length;

  const markers = {
    tolerance: result.tolerance_band,
    capacity: result.capacity_band,
    horizon: result.horizon_band,
  };

  const accountForProduct = (productId) => accounts.find((a) => a.product_id === productId);

  const investNow = (product) => {
    if (!authToken) {
      setToastMessage("Log in first — opening an account needs to be tied to your account.");
      return;
    }
    const topPortfolio = product.recommended_portfolios[0];
    setApplicationTarget({
      product,
      portfolio: { id: topPortfolio.portfolio_id, name: topPortfolio.portfolio_name },
      initialAmount: topPortfolio.split_initial_amount,
      monthlyAmount: topPortfolio.split_monthly_amount,
    });
  };

  return (
    <div className="step-content step-content--enter">
      <header className="step-header">
        <h2>{t(language, "results.title")}</h2>
        {result.goals_detail && (
          <p className="step-subtitle">
            {t(language, "results.goals")}: {result.goals_detail}
          </p>
        )}
      </header>

      <div className="results-layout">
        <div className={`results-hero card band-bg-${result.governed_risk_band}-wash card--pop-in`}>
          <div className="results-hero__ladder">
            <RiskLadder activeBand={result.governed_risk_band} markers={markers} />
          </div>
          <div className="results-hero__detail">
            <span className={`results-hero__band mono band-color-${result.governed_risk_band}`}>
              {result.governed_risk_band_label}
            </span>
            <p className="results-hero__explanation">{result.governed_risk_band_explanation}</p>
            <div className="results-hero__breakdown">
              <div>
                <span className="field-label">{t(language, "results.overallBand")}</span>
                <span className="mono">{result.governed_risk_band} / 5</span>
              </div>
              <div>
                <span className="field-label">{t(language, "results.tolerance")}</span>
                <span className="mono">{result.tolerance_band}</span>
              </div>
              <div>
                <span className="field-label">{t(language, "results.capacity")}</span>
                <span className="mono">{result.capacity_band}</span>
              </div>
              <div>
                <span className="field-label">{t(language, "results.horizon")}</span>
                <span className="mono">{result.horizon_band}</span>
              </div>
              {result.tax_bracket && (
                <div>
                  <span className="field-label">{t(language, "results.taxBracket")}</span>
                  <span className="mono">
                    {result.tax_bracket}
                    {!result.tax_bracket_estimated && " (as provided)"}
                  </span>
                </div>
              )}
            </div>
            <p className="results-hero__note">
              Governed by the lowest of tolerance (your comfort with risk), capacity (what
              you can financially afford to risk), and horizon (how long until you need this
              money) — the dot on the ladder shows which one is constraining. Ask the chat
              "what if I invest more" to see how the numbers below change.
            </p>
          </div>
        </div>

        {isPreview && (
          <div className="preview-banner card">
            <p className="preview-banner__text">💡 {recalculatedNote}</p>
            <div className="preview-banner__toggle">
              <button
                type="button"
                className={`preview-banner__tab ${showingPreview ? "preview-banner__tab--active" : ""}`}
                onClick={() => setShowingPreview(true)}
              >
                {t(language, "results.preview")}
              </button>
              <button
                type="button"
                className={`preview-banner__tab ${!showingPreview ? "preview-banner__tab--active" : ""}`}
                onClick={() => setShowingPreview(false)}
              >
                {t(language, "results.actualResults")}
              </button>
            </div>
          </div>
        )}

        {accounts.length > 0 && (
          <div className="active-accounts card card--pop-in">
            <h3 className="form-section__title">{t(language, "results.yourAccounts")}</h3>
            {accounts.map((acc) => (
              <div key={acc.account_id} className="active-account-row">
                <div className="active-account-row__main">
                  <strong>{acc.product_name}</strong>
                  <span className="active-account-row__meta">
                    {acc.tax_wrapper.replace(/_/g, " ")} · {acc.portfolio_name}
                  </span>
                  <span className={`pill pill--${acc.status} active-account-row__status`}>
                    {acc.status === "pending" ? t(language, "accounts.pending") : acc.status}
                  </span>
                  {acc.beneficiary_name && (
                    <span className="active-account-row__meta">Beneficiary: {acc.beneficiary_name}</span>
                  )}
                </div>
                <div className="active-account-row__amounts mono">
                  {acc.initial_amount > 0 && <span>{formatRand(acc.initial_amount)} lump sum</span>}
                  {acc.monthly_amount > 0 && <span>{formatRand(acc.monthly_amount)}/month</span>}
                </div>
              </div>
            ))}
          </div>
        )}

        <h3 className="form-section__title">
          {isPreview && showingPreview ? t(language, "results.scenarioProducts") : t(language, "results.matchedProducts")}
        </h3>

        {displayedProducts.length === 0 && <p className="step-subtitle">{t(language, "results.noProducts")}</p>}

        {visibleProducts.map((product, i) => (
          <ProductCard
            key={product.id}
            product={product}
            existingAccount={accountForProduct(product.id)}
            onInvest={() => investNow(product)}
            style={{ animationDelay: `${80 + i * 70}ms` }}
            language={language}
          />
        ))}

        {hiddenCount > 0 && (
          <button type="button" className="btn btn-ghost show-more-btn" onClick={() => setShowAllProducts(true)}>
            {t(language, "results.showMore")} ({hiddenCount})
          </button>
        )}
        {showAllProducts && displayedProducts.length > INITIAL_VISIBLE_PRODUCTS && (
          <button type="button" className="btn btn-ghost show-more-btn" onClick={() => setShowAllProducts(false)}>
            {t(language, "results.showLess")}
          </button>
        )}

        <p className="projection-disclaimer">{t(language, "results.disclaimer")}</p>
      </div>

      {applicationTarget && (
        <InvestmentApplicationModal
          product={applicationTarget.product}
          portfolio={applicationTarget.portfolio}
          clientId={result.client_id}
          defaultInitialAmount={applicationTarget.initialAmount}
          defaultMonthlyAmount={applicationTarget.monthlyAmount}
          savedProfile={savedProfile}
          authToken={authToken}
          onClose={() => setApplicationTarget(null)}
          onOpened={(account) => {
            onAccountOpened?.(account);
            setToastMessage(`${account.product_name} submitted — pending review.`);
          }}
        />
      )}

      {toastMessage && <Toast message={toastMessage} onDismiss={() => setToastMessage(null)} />}
    </div>
  );
}
