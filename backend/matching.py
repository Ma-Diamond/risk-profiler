"""Portfolio matching: hard filters first, then rank by risk_band fit.

This is deliberately NOT a similarity/distance score across all fields.
Horizon, liquidity, Reg 28, and knowledge requirements are treated as
non-negotiable eligibility gates — a portfolio either qualifies or it
doesn't. Only within the surviving set does risk_band proximity decide
ordering.
"""

from __future__ import annotations

from dataclasses import dataclass

from scoring import BandResult


@dataclass
class Portfolio:
    id: int
    name: str
    provider: str
    risk_band: int
    max_equity_pct: float
    min_horizon_years: float
    liquidity_days: int
    reg28_compliant: int
    min_knowledge_band: int
    requires_emergency_fund: int
    underlying_fee_pct: float
    description: str


def is_eligible(
    portfolio: Portfolio,
    bands: BandResult,
    investment_horizon_years: float,
    emergency_fund_months: float,
    investment_goal: str,
) -> tuple[bool, list[str]]:
    """Returns (eligible, reasons_excluded). reasons_excluded is empty
    when eligible=True, and otherwise lists every failed constraint —
    useful for showing the adviser/client why a product was excluded."""
    reasons: list[str] = []

    if portfolio.risk_band > bands.governed_risk_band:
        reasons.append(
            f"risk_band {portfolio.risk_band} exceeds governed band {bands.governed_risk_band}"
        )

    if portfolio.min_horizon_years > investment_horizon_years:
        reasons.append(
            f"requires {portfolio.min_horizon_years}y horizon, client has {investment_horizon_years}y"
        )

    if portfolio.requires_emergency_fund and emergency_fund_months < 3:
        reasons.append("requires an emergency fund buffer of 3+ months")

    if portfolio.min_knowledge_band > bands.knowledge_band:
        reasons.append(
            f"requires knowledge band {portfolio.min_knowledge_band}, client is {bands.knowledge_band}"
        )

    if investment_goal == "retirement" and not portfolio.reg28_compliant:
        reasons.append("not Reg 28 compliant, required for retirement-linked goals")

    return (len(reasons) == 0, reasons)


def match_portfolios(
    portfolios: list[Portfolio],
    bands: BandResult,
    investment_horizon_years: float,
    emergency_fund_months: float,
    investment_goal: str,
) -> list[Portfolio]:
    """Returns eligible portfolios ranked closest-risk-band-first.

    Ranking rule: prefer the highest risk_band that still qualifies
    (i.e. the closest match to the client's governed band from below),
    so the client isn't defaulted into an unnecessarily conservative
    option purely because it also happened to pass the filters.
    """
    eligible = [
        p
        for p in portfolios
        if is_eligible(
            p, bands, investment_horizon_years, emergency_fund_months, investment_goal
        )[0]
    ]
    eligible.sort(key=lambda p: (bands.governed_risk_band - p.risk_band, p.name))
    return eligible


# ---------------------------------------------------------------------
# PRODUCT LAYER
#
# Products are generic wrappers, decoupled from any single portfolio —
# which portfolios a product offers is looked up via
# product_portfolio_mapping (resolved to `mapped_product_ids` by the
# caller). The combined fee for a given (product, portfolio) pairing
# is the wrapper's platform+advice fee PLUS that portfolio's own
# underlying fee — fee is a property of the pairing, not of either
# side alone, so it's computed via combined_fee_pct() rather than
# cached on the Product.
# ---------------------------------------------------------------------

GOAL_TO_ALLOWED_WRAPPERS: dict[str, set[str]] = {
    "retirement": {"retirement_annuity", "preservation_fund", "discretionary"},
    "house_deposit": {"discretionary", "tax_free_savings", "investment_policy", "offshore_endowment", "cash_account"},
    "general_growth": {"discretionary", "tax_free_savings", "endowment", "offshore_discretionary", "cash_account"},
}

TAX_ADVANTAGED_WRAPPERS = {"retirement_annuity", "preservation_fund", "tax_free_savings", "endowment"}


@dataclass
class Product:
    id: int
    name: str
    provider: str
    tax_wrapper: str
    min_initial_investment: float
    min_monthly_investment: float
    annual_platform_fee_pct: float
    advice_fee_pct: float
    min_term_years: float
    description: str
    spec_notes: str = ""


def combined_fee_pct(product: Product, portfolio: Portfolio) -> float:
    """The all-in annual fee for investing in this portfolio through
    this specific product: the wrapper's platform+advice fee plus the
    portfolio's own underlying fee (TER)."""
    return product.annual_platform_fee_pct + product.advice_fee_pct + portfolio.underlying_fee_pct


def is_product_eligible(
    product: Product,
    investment_goal: str,
    investment_horizon_years: float,
    available_lump_sum: float,
    monthly_contribution: float,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    allowed_wrappers = GOAL_TO_ALLOWED_WRAPPERS.get(investment_goal, {"discretionary"})
    if product.tax_wrapper not in allowed_wrappers:
        reasons.append(
            f"tax wrapper '{product.tax_wrapper}' does not suit goal '{investment_goal}'"
        )

    meets_lump_sum = available_lump_sum >= product.min_initial_investment
    meets_monthly = monthly_contribution >= product.min_monthly_investment
    if not (meets_lump_sum or meets_monthly):
        reasons.append(
            f"below minimums (needs R{product.min_initial_investment:,.0f} lump sum "
            f"or R{product.min_monthly_investment:,.0f}/month)"
        )

    if product.min_term_years > investment_horizon_years:
        reasons.append(
            f"has a {product.min_term_years:.0f}-year lock-in, "
            f"client horizon is {investment_horizon_years:.0f} years"
        )

    return (len(reasons) == 0, reasons)


def match_products(
    products: list[Product],
    portfolio: Portfolio,
    mapped_product_ids: set[int],
    investment_goal: str,
    investment_horizon_years: float,
    available_lump_sum: float,
    monthly_contribution: float,
    prioritize_tax_efficient: bool = False,
) -> list[Product]:
    """Returns eligible products offering this portfolio, ranked.

    `mapped_product_ids` narrows candidates to products that actually
    offer this portfolio (from product_portfolio_mapping) before the
    usual goal/minimums/lock-in filters apply.

    Default ranking is cheapest combined fee first. When
    prioritize_tax_efficient=True, tax-advantaged wrappers rank ahead
    of discretionary ones; fee still breaks ties within each group.
    """
    candidates = [p for p in products if p.id in mapped_product_ids]
    eligible = [
        p
        for p in candidates
        if is_product_eligible(
            p,
            investment_goal,
            investment_horizon_years,
            available_lump_sum,
            monthly_contribution,
        )[0]
    ]

    def fee(p: Product) -> float:
        return combined_fee_pct(p, portfolio)

    if prioritize_tax_efficient:
        eligible.sort(
            key=lambda p: (
                0 if p.tax_wrapper in TAX_ADVANTAGED_WRAPPERS else 1,
                fee(p),
                p.min_initial_investment,
            )
        )
    else:
        eligible.sort(key=lambda p: (fee(p), p.min_initial_investment))

    return eligible


# ---------------------------------------------------------------------
# PRODUCT REASONING & TOP PICK
#
# Deterministic, rule-based explanations for why each product is worth
# considering for this portfolio, plus a single "top pick" chosen by a
# fixed priority order tailored to the client's own situation. Every
# reason maps to a specific, inspectable rule — nothing here is
# LLM-generated.
# ---------------------------------------------------------------------


def build_product_reasons(
    products: list[Product],
    portfolio: Portfolio,
    emergency_fund_months: float,
    tax_rate: int | None,
) -> dict[int, list[str]]:
    reasons: dict[int, list[str]] = {p.id: [] for p in products}
    if not products:
        return reasons

    fee = lambda p: combined_fee_pct(p, portfolio)

    cheapest = min(products, key=fee)
    reasons[cheapest.id].append("Lowest fee among your eligible options here")

    if tax_rate is not None and tax_rate >= 39:
        for p in products:
            if p.tax_wrapper in TAX_ADVANTAGED_WRAPPERS:
                reasons[p.id].append(
                    f"Tax-efficient wrapper — suits your {tax_rate}% estimated bracket"
                )

    if emergency_fund_months < 3:
        for p in products:
            if p.min_term_years == 0:
                reasons[p.id].append(
                    "No lock-in — stays accessible given your limited emergency fund"
                )

    cheapest_entry = min(products, key=lambda p: p.min_initial_investment)
    if cheapest_entry.id != cheapest.id:
        reasons[cheapest_entry.id].append("Lowest minimum to get started")

    return reasons


def pick_top_product(
    products: list[Product],
    portfolio: Portfolio,
    emergency_fund_months: float,
    tax_rate: int | None,
) -> tuple[Product | None, str]:
    """Priority order: (1) liquidity if emergency fund is thin,
    (2) tax efficiency if bracket is high, (3) lowest fee. Ties broken
    by lowest fee."""
    if not products:
        return None, ""

    fee = lambda p: combined_fee_pct(p, portfolio)

    if emergency_fund_months < 3:
        liquid = [p for p in products if p.min_term_years == 0]
        if liquid:
            top = min(liquid, key=fee)
            return top, "No lock-in — matters most given your limited emergency fund"

    if tax_rate is not None and tax_rate >= 39:
        tax_efficient = [p for p in products if p.tax_wrapper in TAX_ADVANTAGED_WRAPPERS]
        if tax_efficient:
            top = min(tax_efficient, key=fee)
            return top, f"Tax-efficient wrapper suits your {tax_rate}% estimated bracket"

    top = min(products, key=fee)
    return top, "Lowest fee among your eligible options"
