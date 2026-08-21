"""Seed data for portfolios, products, the mapping between them, and
placeholder return assumptions.

Portfolios and products are now independent: a portfolio is an
investment strategy with its own risk profile and underlying fee; a
product is a wrapper (tax treatment, platform fee, minimums, lock-in)
that offers a MENU of portfolios, via PRODUCT_PORTFOLIO_MAPPING. This
mirrors how real platforms work — an RA isn't tied to one fund, it's
tied to a fee structure and a list of funds you can choose from.

PORTFOLIO_RETURNS are placeholder numbers standing in for actual
capital market assumptions, which in a real system would come from an
actuarial/investment research process, not this codebase. Treat every
figure here as a dummy to be replaced.
"""

from __future__ import annotations

PORTFOLIOS: list[dict] = [
    {
        "key": "capital_protector",
        "name": "Capital Protector Money Market",
        "provider": "Example Asset Managers",
        "risk_band": 1,
        "max_equity_pct": 0,
        "min_horizon_years": 0,
        "liquidity_days": 1,
        "reg28_compliant": 1,
        "min_knowledge_band": 1,
        "requires_emergency_fund": 0,
        "underlying_fee_pct": 0.15,
        "description": "Pure money market fund, capital preservation focus.",
    },
    {
        "key": "stable_income",
        "name": "Stable Income Fund",
        "provider": "Example Asset Managers",
        "risk_band": 2,
        "max_equity_pct": 20,
        "min_horizon_years": 1,
        "liquidity_days": 2,
        "reg28_compliant": 1,
        "min_knowledge_band": 1,
        "requires_emergency_fund": 0,
        "underlying_fee_pct": 0.55,
        "description": "Bond and cash heavy, modest equity kicker.",
    },
    {
        "key": "balanced_growth",
        "name": "Balanced Growth Fund",
        "provider": "Example Asset Managers",
        "risk_band": 3,
        "max_equity_pct": 50,
        "min_horizon_years": 3,
        "liquidity_days": 3,
        "reg28_compliant": 1,
        "min_knowledge_band": 2,
        "requires_emergency_fund": 1,
        "underlying_fee_pct": 0.85,
        "description": "Balanced multi-asset fund within Reg 28 limits.",
    },
    {
        "key": "managed_flexible",
        "name": "Managed Flexible Fund",
        "provider": "Example Asset Managers",
        "risk_band": 3,
        "max_equity_pct": 60,
        "min_horizon_years": 4,
        "liquidity_days": 3,
        "reg28_compliant": 0,
        "min_knowledge_band": 2,
        "requires_emergency_fund": 1,
        "underlying_fee_pct": 0.95,
        "description": "Flexible mandate, not Reg 28 bound, slightly higher equity ceiling.",
    },
    {
        "key": "growth_equity",
        "name": "Growth Equity Fund",
        "provider": "Example Asset Managers",
        "risk_band": 4,
        "max_equity_pct": 80,
        "min_horizon_years": 5,
        "liquidity_days": 3,
        "reg28_compliant": 1,
        "min_knowledge_band": 3,
        "requires_emergency_fund": 1,
        "underlying_fee_pct": 1.10,
        "description": "Domestic + offshore equity tilt, retirement-fund eligible.",
    },
    {
        "key": "offshore_growth",
        "name": "Offshore Growth Feeder Fund",
        "provider": "Example Asset Managers",
        "risk_band": 4,
        "max_equity_pct": 90,
        "min_horizon_years": 7,
        "liquidity_days": 5,
        "reg28_compliant": 0,
        "min_knowledge_band": 3,
        "requires_emergency_fund": 1,
        "underlying_fee_pct": 1.35,
        "description": "Rand-denominated feeder into an offshore equity fund; longer horizon needed.",
    },
    {
        "key": "aggressive_equity",
        "name": "Aggressive Equity Fund",
        "provider": "Example Asset Managers",
        "risk_band": 5,
        "max_equity_pct": 100,
        "min_horizon_years": 8,
        "liquidity_days": 3,
        "reg28_compliant": 0,
        "min_knowledge_band": 4,
        "requires_emergency_fund": 1,
        "underlying_fee_pct": 1.50,
        "description": "Concentrated high-conviction equity mandate, high volatility.",
    },
    {
        "key": "thematic_growth",
        "name": "Thematic High Growth Fund",
        "provider": "Example Asset Managers",
        "risk_band": 5,
        "max_equity_pct": 100,
        "min_horizon_years": 10,
        "liquidity_days": 5,
        "reg28_compliant": 0,
        "min_knowledge_band": 4,
        "requires_emergency_fund": 1,
        "underlying_fee_pct": 1.75,
        "description": "Sector/thematic equity exposure, highest volatility in the range.",
    },
]

# Generic wrappers — no portfolio_id here. Which portfolios each one
# offers is defined in PRODUCT_PORTFOLIO_MAPPING below.
PRODUCTS: list[dict] = [
    {
        "key": "cash_account",
        "name": "Flexible Cash Account",
        "provider": "Example Platform",
        "tax_wrapper": "discretionary",
        "min_initial_investment": 500,
        "min_monthly_investment": 250,
        "annual_platform_fee_pct": 0.25,
        "advice_fee_pct": 0.0,
        "min_term_years": 0,
        "description": "No lock-in, near-instant access, low minimums.",
        "spec_notes": "Single money-market portfolio only. No advice fee. Withdrawals settle same day.",
    },
    {
        "key": "tfsa",
        "name": "Tax-Free Savings Account",
        "provider": "Example Platform",
        "tax_wrapper": "tax_free_savings",
        "min_initial_investment": 0,
        "min_monthly_investment": 500,
        "annual_platform_fee_pct": 0.30,
        "advice_fee_pct": 0.5,
        "min_term_years": 0,
        "description": "All growth and withdrawals are tax-free, subject to annual/lifetime contribution limits.",
        "spec_notes": "2025/26 annual contribution limit R36,000, lifetime limit R500,000. Exceeding the limit triggers a 40% SARS penalty on the excess. No lock-in.",
    },
    {
        "key": "unit_trust",
        "name": "Example Unit Trust Account",
        "provider": "Example Asset Managers",
        "tax_wrapper": "discretionary",
        "min_initial_investment": 10000,
        "min_monthly_investment": 500,
        "annual_platform_fee_pct": 0.35,
        "advice_fee_pct": 0.5,
        "min_term_years": 0,
        "description": "Direct discretionary access to a broad range of unit trust portfolios, no lock-in.",
        "spec_notes": "Capital gains tax applies on withdrawal at the client's marginal inclusion rate. No restriction period; switches between portfolios within the account are free.",
    },
    {
        "key": "retirement_annuity",
        "name": "Example Retirement Annuity",
        "provider": "Example Life",
        "tax_wrapper": "retirement_annuity",
        "min_initial_investment": 0,
        "min_monthly_investment": 750,
        "annual_platform_fee_pct": 0.45,
        "advice_fee_pct": 0.75,
        "min_term_years": 15,
        "description": "Contributions are tax-deductible up to 27.5% of income (capped); proceeds locked in until retirement age.",
        "spec_notes": "Modelled here as a flat 15-year minimum term as a stand-in for 'locked until age 55'. On retirement, up to 1/3 may be taken as a lump sum (taxable per SARS retirement tables), the rest must buy an annuity income.",
    },
    {
        "key": "preservation_fund",
        "name": "Example Preservation Fund",
        "provider": "Example Life",
        "tax_wrapper": "preservation_fund",
        "min_initial_investment": 20000,
        "min_monthly_investment": 0,
        "annual_platform_fee_pct": 0.40,
        "advice_fee_pct": 0.5,
        "min_term_years": 10,
        "description": "For transferred retirement fund proceeds; one full or partial pre-retirement withdrawal is allowed.",
        "spec_notes": "Lump-sum transfers only, no ongoing contributions. The one allowed pre-retirement withdrawal is taxed per SARS withdrawal tables.",
    },
    {
        "key": "endowment",
        "name": "Example Endowment",
        "provider": "Example Life",
        "tax_wrapper": "endowment",
        "min_initial_investment": 50000,
        "min_monthly_investment": 1000,
        "annual_platform_fee_pct": 0.45,
        "advice_fee_pct": 0.6,
        "min_term_years": 5,
        "description": "Tax is paid within the fund at a flat rate — useful for clients on a high marginal tax rate. 5-year restriction period.",
        "spec_notes": "Tax paid inside the policy at the insurer's flat rate (typically close to the top marginal rate), so it mainly benefits clients already in a high bracket. Limited withdrawals allowed before year 5 without breaching the '5x5' rule.",
    },
]

# (product_key, portfolio_key) pairs — which portfolios are selectable
# under each product. A product can map to several portfolios; a
# portfolio can appear under several products.
PRODUCT_PORTFOLIO_MAPPING: list[tuple[str, str]] = [
    ("cash_account", "capital_protector"),
    ("tfsa", "capital_protector"),
    ("tfsa", "balanced_growth"),
    ("unit_trust", "stable_income"),
    ("unit_trust", "balanced_growth"),
    ("unit_trust", "managed_flexible"),
    ("unit_trust", "growth_equity"),
    ("unit_trust", "offshore_growth"),
    ("unit_trust", "aggressive_equity"),
    ("retirement_annuity", "balanced_growth"),
    ("retirement_annuity", "growth_equity"),
    ("preservation_fund", "growth_equity"),
    ("endowment", "managed_flexible"),
    ("endowment", "thematic_growth"),
]

# (expected, lower, upper) annual return %, per portfolio — DUMMY
# placeholders standing in for real capital market assumptions.
PORTFOLIO_RETURNS: dict[str, tuple[float, float, float]] = {
    "capital_protector": (7.5, 6.5, 8.5),
    "stable_income": (8.5, 6.0, 11.0),
    "balanced_growth": (9.5, 5.0, 14.0),
    "managed_flexible": (10.0, 4.0, 16.0),
    "growth_equity": (11.5, 2.5, 20.0),
    "offshore_growth": (12.0, 1.0, 22.0),
    "aggressive_equity": (13.5, -3.0, 27.0),
    "thematic_growth": (14.5, -6.0, 32.0),
}

PORTFOLIO_RETURNS_METHODOLOGY = (
    "PLACEHOLDER — dummy figures for development only. Replace with "
    "output from an actual capital market assumptions / actuarial "
    "process before this is used for anything beyond a POC."
)
