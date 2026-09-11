"""Estimate a client's marginal tax bracket from income alone.

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
- No primary/secondary/tertiary rebates, medical credits, or other
  deductions are applied — this is a top-marginal-rate estimate, not
  a tax calculation. It should never be shown to a client as their
  actual tax liability.
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
