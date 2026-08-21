"""Deterministic, band-based risk profiling.

Every function here is a pure lookup/threshold mapping — no ML, no
weighting of unlike things into one number. Each dimension produces a
band from 1 (most conservative) to 5 (most aggressive), and the final
"governed" band is the minimum across the three independent dimensions:
tolerance is capped by capacity, and both are capped by horizon.

This keeps the calculation auditable: given a client's stored inputs,
anyone can recompute the same bands and see exactly which dimension
constrained the final recommendation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class ClientInput:
    age: int
    dependents: int
    gross_monthly_income: float
    monthly_expenses: float
    emergency_fund_months: float
    investment_horizon_years: float
    investment_goal: str
    tolerance_questionnaire: list[int]  # 5 answers, each 1-5
    knowledge_score: int  # 1-5


@dataclass
class BandResult:
    tolerance_band: int
    capacity_band: int
    horizon_band: int
    governed_risk_band: int
    knowledge_band: int


def tolerance_band(questionnaire: list[int]) -> int:
    """Map a 5-question, 1-5-per-question risk-attitude questionnaire
    to a 1-5 band using its total score (range 5-25)."""
    if len(questionnaire) != 5 or any(not (1 <= a <= 5) for a in questionnaire):
        raise ValueError("tolerance_questionnaire must be 5 answers, each 1-5")

    total = sum(questionnaire)
    # 5 thresholds spanning the possible 5-25 range
    if total <= 8:
        return 1
    if total <= 12:
        return 2
    if total <= 16:
        return 3
    if total <= 20:
        return 4
    return 5


def capacity_band(
    dependents: int,
    gross_monthly_income: float,
    monthly_expenses: float,
    emergency_fund_months: float,
) -> int:
    """Objective ability to absorb loss, from expense ratio, dependents,
    and cash buffer. Deliberately conservative: any one weak factor
    caps the band, rather than averaging against strong factors."""
    if gross_monthly_income <= 0:
        expense_ratio = 1.0
    else:
        expense_ratio = monthly_expenses / gross_monthly_income

    # Start from expense ratio (lower ratio = more capacity)
    if expense_ratio >= 0.9:
        band = 1
    elif expense_ratio >= 0.7:
        band = 2
    elif expense_ratio >= 0.5:
        band = 3
    elif expense_ratio >= 0.3:
        band = 4
    else:
        band = 5

    # Dependents reduce capacity by at most one band step
    if dependents >= 3:
        band = max(1, band - 2)
    elif dependents >= 1:
        band = max(1, band - 1)

    # No emergency buffer caps capacity hard, regardless of the above
    if emergency_fund_months < 1:
        band = min(band, 2)
    elif emergency_fund_months < 3:
        band = min(band, 3)

    return band


def horizon_band(investment_horizon_years: float) -> int:
    """Time until funds are needed. This is a liquidity constraint,
    not a preference — it caps the other two bands below."""
    if investment_horizon_years < 2:
        return 1
    if investment_horizon_years < 4:
        return 2
    if investment_horizon_years < 6:
        return 3
    if investment_horizon_years < 9:
        return 4
    return 5


def knowledge_band(knowledge_score: int) -> int:
    if not (1 <= knowledge_score <= 5):
        raise ValueError("knowledge_score must be 1-5")
    return knowledge_score


def compute_bands(client: ClientInput) -> BandResult:
    t = tolerance_band(client.tolerance_questionnaire)
    c = capacity_band(
        client.dependents,
        client.gross_monthly_income,
        client.monthly_expenses,
        client.emergency_fund_months,
    )
    h = horizon_band(client.investment_horizon_years)
    k = knowledge_band(client.knowledge_score)

    # The governing rule: the client cannot be recommended a riskier band
    # than their capacity or horizon allow, no matter how high their
    # stated tolerance is.
    governed = min(t, c, h)

    return BandResult(
        tolerance_band=t,
        capacity_band=c,
        horizon_band=h,
        governed_risk_band=governed,
        knowledge_band=k,
    )


def client_input_from_row(row: dict) -> ClientInput:
    """Rebuild a ClientInput from a clients table row (as returned by
    sqlite3.Row -> dict), used when recomputing bands for an existing
    client record."""
    return ClientInput(
        age=row["age"],
        dependents=row["dependents"],
        gross_monthly_income=row["gross_monthly_income"],
        monthly_expenses=row["monthly_expenses"],
        emergency_fund_months=row["emergency_fund_months"],
        investment_horizon_years=row["investment_horizon_years"],
        investment_goal=row["investment_goal"],
        tolerance_questionnaire=json.loads(row["tolerance_questionnaire"]),
        knowledge_score=row["knowledge_score"],
    )
