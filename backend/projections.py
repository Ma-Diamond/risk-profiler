"""Investment value projections.

Returns are now stored as a term structure per portfolio — a set of
(horizon_years, expected_pct, lower_pct, upper_pct) points, much like
a bond yield curve. The rate at a given tenor is already the
annualized rate for holding to that horizon (not a single "year N"
return to compound with other years) — resolve_curve_point() finds
the right rate for an arbitrary horizon by linearly interpolating
between the two nearest known tenor points, matching this project's
existing preference for deterministic, auditable math over anything
resembling a black box.

Given a resolved annualized rate and the combined fee of a specific
product+portfolio pairing, projects the investment's value at the end
of a horizon: a lump sum compounding at the net annual rate, plus a
monthly contribution annuity compounding at the same net rate, both
converted to a monthly-compounding basis. This is a projection under
a constant assumed return, not a guarantee or a stochastic simulation
— actual returns vary year to year and the real outcome could fall
outside the stated lower/upper range.
"""

from __future__ import annotations

from dataclasses import dataclass

# A single tenor point: (horizon_years, expected_pct, lower_pct, upper_pct)
CurvePoint = tuple[float, float, float, float]


def resolve_curve_point(curve: list[CurvePoint], horizon_years: float) -> tuple[float, float, float]:
    """Returns the (expected, lower, upper) annualized rates to use for
    a projection over `horizon_years`, resolved from a portfolio's
    return curve.

    - Exact match on a known tenor -> that point, unchanged.
    - Between two known tenors -> linear interpolation of each of
      expected/lower/upper independently.
    - Outside the curve's range (shorter than the shortest tenor, or
      longer than the longest) -> clamped to the nearest end. We were
      only asked for interpolation "for periods in between", so
      extrapolation is deliberately not attempted — clamping is the
      conservative, unsurprising choice for out-of-range horizons.
    - A single-point curve always returns that point regardless of
      horizon, which is the same as today's flat-rate behaviour —
      this is a compatible generalization, not a breaking one.
    """
    if not curve:
        raise ValueError("resolve_curve_point() called with an empty curve")

    points = sorted(curve, key=lambda p: p[0])

    if len(points) == 1 or horizon_years <= points[0][0]:
        _, e, l, u = points[0]
        return e, l, u

    if horizon_years >= points[-1][0]:
        _, e, l, u = points[-1]
        return e, l, u

    for (h0, e0, l0, u0), (h1, e1, l1, u1) in zip(points, points[1:]):
        if h0 <= horizon_years <= h1:
            frac = 0.0 if h1 == h0 else (horizon_years - h0) / (h1 - h0)
            expected = e0 + frac * (e1 - e0)
            lower = l0 + frac * (l1 - l0)
            upper = u0 + frac * (u1 - u0)
            return expected, lower, upper

    # Unreachable given the boundary checks above, but keeps the type
    # checker happy and fails safe rather than returning None.
    _, e, l, u = points[-1]
    return e, l, u


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
    performance, so it applies uniformly across the range).

    Takes already-resolved rates (e.g. from resolve_curve_point) —
    this function itself has no opinion on term structure, just the
    compounding math once a rate has been picked for the horizon."""
    net_expected = net_annual_return_pct(expected_return_pct, fee_pct)
    net_lower = net_annual_return_pct(lower_return_pct, fee_pct)
    net_upper = net_annual_return_pct(upper_return_pct, fee_pct)

    return ProjectionRange(
        expected_value=future_value(initial_amount, monthly_amount, horizon_years, net_expected),
        lower_value=future_value(initial_amount, monthly_amount, horizon_years, net_lower),
        upper_value=future_value(initial_amount, monthly_amount, horizon_years, net_upper),
        net_expected_return_pct=net_expected,
    )
