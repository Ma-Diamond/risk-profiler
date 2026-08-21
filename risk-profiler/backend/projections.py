"""Investment value projections.

Given a portfolio's expected/lower/upper annual return assumptions
(from `portfolio_returns` — produced by a separate research process;
this module has no opinion on where those numbers come from) and the
combined fee of a specific product+portfolio pairing, projects the
investment's value at the end of a horizon.

Math: a lump sum compounding at the net annual rate, plus a monthly
contribution annuity compounding at the same net rate, both converted
to a monthly-compounding basis. This is a projection under a constant
assumed return, not a guarantee or a stochastic simulation — actual
returns vary year to year and the real outcome could fall outside the
stated lower/upper range.
"""

from __future__ import annotations

from dataclasses import dataclass


def net_annual_return_pct(gross_annual_return_pct: float, fee_pct: float) -> float:
    """Simple fee drag: subtract the combined product+portfolio fee
    from the assumed gross return."""
    return gross_annual_return_pct - fee_pct


def future_value(
    initial_amount: float,
    monthly_amount: float,
    horizon_years: float,
    annual_return_pct: float,
) -> float:
    """Future value of a lump sum plus a level monthly contribution,
    compounded monthly at the given annual rate."""
    months = max(round(horizon_years * 12), 0)
    if months == 0:
        return initial_amount

    monthly_rate = (1 + annual_return_pct / 100) ** (1 / 12) - 1

    fv_lump = initial_amount * (1 + monthly_rate) ** months

    if abs(monthly_rate) < 1e-12:
        fv_contributions = monthly_amount * months
    else:
        fv_contributions = monthly_amount * (((1 + monthly_rate) ** months - 1) / monthly_rate)

    return fv_lump + fv_contributions


@dataclass
class ProjectionRange:
    expected_value: float
    lower_value: float
    upper_value: float
    net_expected_return_pct: float


def project_range(
    initial_amount: float,
    monthly_amount: float,
    horizon_years: float,
    expected_return_pct: float,
    lower_return_pct: float,
    upper_return_pct: float,
    fee_pct: float,
) -> ProjectionRange:
    """Projects the expected/lower/upper investment value, each net of
    the same combined fee (the fee doesn't change with market
    performance, so it applies uniformly across the range)."""
    net_expected = net_annual_return_pct(expected_return_pct, fee_pct)
    net_lower = net_annual_return_pct(lower_return_pct, fee_pct)
    net_upper = net_annual_return_pct(upper_return_pct, fee_pct)

    return ProjectionRange(
        expected_value=future_value(initial_amount, monthly_amount, horizon_years, net_expected),
        lower_value=future_value(initial_amount, monthly_amount, horizon_years, net_lower),
        upper_value=future_value(initial_amount, monthly_amount, horizon_years, net_upper),
        net_expected_return_pct=net_expected,
    )
