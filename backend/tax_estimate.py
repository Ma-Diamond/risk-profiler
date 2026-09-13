"""Estimate a client's marginal tax bracket, and a rough net income
figure, from gross income alone.

Most people don't know their marginal rate off-hand, so rather than
asking the client in the chat, we estimate it deterministically from
gross monthly income. This is intentionally simple: it annualises
gross income and looks up the top marginal bracket it falls into.

CAUTION — illustrative only:
- These are South Africa's individual tax bracket *rates and structure*
  as a representative example; the exact Rand thresholds change most
  tax years (inflation adjustments in the annual Budget) and this
  table is NOT guaranteed to match the current SARS tax year. Update
  `BRACKETS` against the current SARS tax tables before relying on
  this for anything beyond a rough product-ranking nudge.
- The net-income estimate applies the brackets progressively (only the
  income within each bracket is taxed at that bracket's rate) plus a
  single primary rebate — it does NOT account for medical aid tax
  credits, retirement fund contribution deductions, age-based
  secondary/tertiary rebates, or UIF. It's meant to be meaningfully
  better than "just use gross income", not a payslip-accurate figure,
  and should never be shown to a client as their actual tax liability.
"""

from __future__ import annotations

# (annual taxable income ceiling, marginal rate %) — ordered ascending.
# Verify/update against the current SARS tax tables periodically.
BRACKETS: list[tuple[float, int]] = [
    (237_100, 18),
    (370_500, 26),
    (512_800, 31),
    (673_000, 36),
    (857_900, 39),
    (1_817_000, 41),
    (float("inf"), 45),
]

# 2024/2025 SARS primary rebate (under-65) — a flat amount subtracted
# from tax payable, not from income. Update alongside BRACKETS.
PRIMARY_REBATE = 17_235


def estimate_tax_bracket(gross_monthly_income: float) -> tuple[str, int]:
    """Returns (display_label, marginal_rate_pct).

    e.g. estimate_tax_bracket(45000) -> ("~31% (estimated)", 31)
    """
    annual_income = max(gross_monthly_income, 0) * 12
    for ceiling, rate in BRACKETS:
        if annual_income <= ceiling:
            return f"~{rate}% (estimated)", rate
    # Unreachable — last bracket ceiling is inf — but keep a safe fallback.
    return "~45% (estimated)", 45


def calculate_annual_tax(annual_income: float) -> float:
    """Progressive tax payable on `annual_income` — only the portion of
    income that falls within each bracket is taxed at that bracket's
    rate (not the whole income at the top marginal rate, which would
    badly overstate tax and understate net income). Applies the
    primary rebate, floored at 0."""
    annual_income = max(annual_income, 0)
    tax = 0.0
    lower = 0.0
    for ceiling, rate in BRACKETS:
        if annual_income <= lower:
            break
        taxable_in_bracket = min(annual_income, ceiling) - lower
        tax += taxable_in_bracket * (rate / 100)
        lower = ceiling
    return max(tax - PRIMARY_REBATE, 0.0)


def estimate_net_monthly_income(gross_monthly_income: float) -> float:
    """Gross monthly income minus estimated monthly tax (see caveats
    above — this is a reasonable approximation, not a payslip figure).
    Used wherever a recommendation should be based on what the client
    actually has available, not their gross pay before tax."""
    annual_gross = max(gross_monthly_income, 0) * 12
    annual_tax = calculate_annual_tax(annual_gross)
    return (annual_gross - annual_tax) / 12
