"""Product-centric matching: for each eligible PRODUCT, recommend a
split of the client's contribution across the eligible PORTFOLIOS it
offers.

This reflects how these products actually work in practice — a client
picks one product (e.g. a retirement annuity) and, within it, can hold
several underlying portfolios at once, splitting contributions between
them. It replaced an earlier portfolio-first design (rank portfolios,
then list which products offer each one), which didn't match reality
and — worse — could show the same product repeated once per portfolio
instead of once with its own recommended mix underneath.

Hard filters first, then rank by fit — deliberately NOT a similarity/
distance score across all fields. Horizon, liquidity, Reg 28, and
knowledge requirements are non-negotiable eligibility gates; only
within the surviving set does risk_band proximity decide ordering.
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
    useful for showing the adviser/client why a portfolio was excluded."""
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


# ---------------------------------------------------------------------
# PRODUCT LAYER
#
# Products are generic wrappers, decoupled from any single portfolio —
# which portfolios a product offers is looked up via
# product_portfolio_mapping (resolved by the caller into
# product_id -> [portfolio_id, ...]). The combined fee for a given
# (product, portfolio) pairing is the wrapper's platform+advice fee
# PLUS that portfolio's own underlying fee — fee is a property of the
# pairing, not of either side alone.
# ---------------------------------------------------------------------

GOAL_TO_ALLOWED_WRAPPERS: dict[str, set[str]] = {
    "retirement": {"retirement_annuity", "preservation_fund", "discretionary"},
    "house_deposit": {"discretionary", "tax_free_savings", "investment_policy", "offshore_endowment", "cash_account", "endowment"},
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


# ---------------------------------------------------------------------
# ALLOCATION — splitting a product's contribution across its eligible
# portfolios. Weighted toward the best-fit portfolio (closest risk_band
# match, then lowest fee — same ordering as before), with smaller
# shares to the rest for diversification. A client who wants a single
# portfolio at 100% can still say so in the chat; this is the starting
# recommendation, not a locked-in constraint.
#
# How much spread to recommend is goal-dependent: a house deposit has
# a shorter horizon and less room to ride out a badly-timed portfolio,
# so it concentrates more; retirement's long horizon gets more spread.
# ---------------------------------------------------------------------
MAX_PORTFOLIOS_PER_PRODUCT = 3

ALLOCATION_WEIGHTS_BY_GOAL: dict[str, dict[int, list[float]]] = {
    "retirement": {1: [1.0], 2: [0.65, 0.35], 3: [0.5, 0.3, 0.2]},
    "house_deposit": {1: [1.0], 2: [0.8, 0.2], 3: [0.7, 0.2, 0.1]},
    "general_growth": {1: [1.0], 2: [0.7, 0.3], 3: [0.6, 0.25, 0.15]},
}


def _rank_eligible_portfolios(portfolios: list[Portfolio], governed_risk_band: int) -> list[Portfolio]:
    """Closest risk_band fit first (prefers the portfolio nearest the
    client's governed band, from either direction), fee as tiebreaker."""
    return sorted(portfolios, key=lambda p: (abs(governed_risk_band - p.risk_band), p.underlying_fee_pct))


def recommend_portfolio_allocations(
    eligible_portfolios: list[Portfolio], governed_risk_band: int, investment_goal: str
) -> list[tuple[Portfolio, float]]:
    """(portfolio, allocation_pct) pairs for up to MAX_PORTFOLIOS_PER_PRODUCT
    eligible portfolios, weighted toward the best fit."""
    ranked = _rank_eligible_portfolios(eligible_portfolios, governed_risk_band)
    chosen = ranked[:MAX_PORTFOLIOS_PER_PRODUCT]
    weight_table = ALLOCATION_WEIGHTS_BY_GOAL.get(investment_goal, ALLOCATION_WEIGHTS_BY_GOAL["general_growth"])
    weights = weight_table.get(len(chosen), [1.0 / len(chosen)] * len(chosen))
    return [(p, round(w * 100, 1)) for p, w in zip(chosen, weights)]


def product_weighted_fee(product: Product, allocations: list[tuple[Portfolio, float]]) -> float:
    """The product's effective fee across its recommended split —
    each portfolio's combined fee weighted by its allocation share."""
    return sum(combined_fee_pct(product, p) * (w / 100) for p, w in allocations)


def match_products_with_allocations(
    products: list[Product],
    product_id_to_portfolio_ids: dict[int, list[int]],
    portfolios_by_id: dict[int, Portfolio],
    bands: BandResult,
    investment_horizon_years: float,
    emergency_fund_months: float,
    investment_goal: str,
    available_lump_sum: float,
    monthly_contribution: float,
) -> list[tuple[Product, list[tuple[Portfolio, float]]]]:
    """For each product that passes its own eligibility gate AND has at
    least one eligible portfolio mapped to it, returns the product
    paired with its recommended portfolio allocation. A product with
    zero eligible portfolios is dropped entirely — there's no point
    showing a product the client can't actually invest in through any
    of its portfolios."""
    results: list[tuple[Product, list[tuple[Portfolio, float]]]] = []
    for product in products:
        product_ok, _ = is_product_eligible(
            product, investment_goal, investment_horizon_years, available_lump_sum, monthly_contribution
        )
        if not product_ok:
            continue

        mapped_ids = product_id_to_portfolio_ids.get(product.id, [])
        candidates = [portfolios_by_id[pid] for pid in mapped_ids if pid in portfolios_by_id]
        eligible = [
            p
            for p in candidates
            if is_eligible(p, bands, investment_horizon_years, emergency_fund_months, investment_goal)[0]
        ]
        if not eligible:
            continue

        allocations = recommend_portfolio_allocations(eligible, bands.governed_risk_band, investment_goal)
        results.append((product, allocations))

    return results


# ---------------------------------------------------------------------
# PRODUCT REASONING & TOP PICK
#
# Deterministic, rule-based explanations for why each product is worth
# considering, plus a single "top pick" chosen by a fixed priority
# order tailored to the client's own situation. Every reason maps to a
# specific, inspectable rule — nothing here is LLM-generated.
# ---------------------------------------------------------------------
def build_product_reasons(
    products_with_allocations: list[tuple[Product, list[tuple[Portfolio, float]]]],
    emergency_fund_months: float,
    tax_rate: int | None,
) -> dict[int, list[str]]:
    reasons: dict[int, list[str]] = {product.id: [] for product, _ in products_with_allocations}
    if not products_with_allocations:
        return reasons

    fee = lambda pa: product_weighted_fee(pa[0], pa[1])

    cheapest = min(products_with_allocations, key=fee)
    reasons[cheapest[0].id].append("Lowest fee among your eligible options")

    if tax_rate is not None and tax_rate >= 39:
        for product, _ in products_with_allocations:
            if product.tax_wrapper in TAX_ADVANTAGED_WRAPPERS:
                reasons[product.id].append(
                    f"Tax-efficient wrapper — suits your {tax_rate}% estimated bracket"
                )

    if emergency_fund_months < 3:
        for product, _ in products_with_allocations:
            if product.min_term_years == 0:
                reasons[product.id].append(
                    "No lock-in — stays accessible given your limited emergency fund"
                )

    cheapest_entry = min(products_with_allocations, key=lambda pa: pa[0].min_initial_investment)
    if cheapest_entry[0].id != cheapest[0].id:
        reasons[cheapest_entry[0].id].append("Lowest minimum to get started")

    return reasons


def pick_top_product(
    products_with_allocations: list[tuple[Product, list[tuple[Portfolio, float]]]],
    emergency_fund_months: float,
    tax_rate: int | None,
) -> tuple[Product | None, str]:
    """Priority order: (1) liquidity if emergency fund is thin,
    (2) tax efficiency if bracket is high, (3) lowest fee. Ties broken
    by lowest fee."""
    if not products_with_allocations:
        return None, ""

    fee = lambda pa: product_weighted_fee(pa[0], pa[1])

    if emergency_fund_months < 3:
        liquid = [pa for pa in products_with_allocations if pa[0].min_term_years == 0]
        if liquid:
            top = min(liquid, key=fee)
            return top[0], "No lock-in — matters most given your limited emergency fund"

    if tax_rate is not None and tax_rate >= 39:
        tax_efficient = [pa for pa in products_with_allocations if pa[0].tax_wrapper in TAX_ADVANTAGED_WRAPPERS]
        if tax_efficient:
            top = min(tax_efficient, key=fee)
            return top[0], f"Tax-efficient wrapper suits your {tax_rate}% estimated bracket"

    top = min(products_with_allocations, key=fee)
    return top[0], "Lowest fee among your eligible options"
