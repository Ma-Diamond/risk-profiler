from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone

import ai_chat
import auth
import boto3
import db
import pdf_extract
import product_specs
import projections
import tax_estimate
from boto3.dynamodb.conditions import Key
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from matching import (
    Portfolio,
    Product,
    build_product_reasons,
    combined_fee_pct,
    match_products_with_allocations,
    pick_top_product,
    product_weighted_fee,
)
from pydantic import BaseModel, Field, model_validator
from scoring import BAND_EXPLANATIONS, BAND_LABELS, BandResult, ClientInput, compute_bands, horizon_band as compute_horizon_band

app = FastAPI(title="Risk Profiling API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_optional_user_id(authorization: str | None = Header(default=None)) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    return auth.decode_token(token)


def require_user_id(user_id: str | None = Depends(get_optional_user_id)) -> str:
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def _check_session_access(session_owner_id: str | None, requester_user_id: str | None) -> None:
    if session_owner_id is not None and session_owner_id != requester_user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this chat session")


# ---------------------------------------------------------------------
# Shared models
# ---------------------------------------------------------------------
class ClientProfileIn(BaseModel):
    full_name: str
    age: int = Field(ge=18, le=100)
    dependents: int = Field(ge=0)
    gross_monthly_income: float = Field(gt=0)
    monthly_expenses: float = Field(ge=0)
    emergency_fund_months: float = Field(ge=0)
    investment_horizon_years: float = Field(ge=0)
    investment_goal: str
    tolerance_questionnaire: list[int]
    knowledge_score: int = Field(ge=1, le=5)
    available_lump_sum: float = Field(ge=0, default=0)
    monthly_contribution: float = Field(ge=0, default=0)
    chat_session_id: int | None = None


class ProjectionOut(BaseModel):
    expected_value: float
    lower_value: float
    upper_value: float
    net_expected_return_pct: float


class RecommendedPortfolioOut(BaseModel):
    """One portfolio recommended within a product's split — a client
    doesn't just pick a product, they hold a mix of portfolios inside
    it. allocation_pct is our starting recommendation (weighted toward
    the best-fit portfolio); the client can ask for a different split
    in the chat."""

    portfolio_id: int
    portfolio_name: str
    provider: str | None
    risk_band: int
    allocation_pct: float
    split_initial_amount: float
    split_monthly_amount: float
    fee_pct: float
    projection: ProjectionOut | None = None


class ProductOut(BaseModel):
    id: int
    name: str
    provider: str | None
    tax_wrapper: str
    min_initial_investment: float
    min_monthly_investment: float
    min_term_years: float
    description: str | None
    reasons: list[str] = []
    is_top_pick: bool = False
    top_pick_reason: str | None = None
    total_fee_pct: float  # weighted-average fee across the recommended portfolio split
    total_expected_value: float | None = None
    total_lower_value: float | None = None
    total_upper_value: float | None = None
    recommended_portfolios: list[RecommendedPortfolioOut] = []


class PortfolioCatalogOut(BaseModel):
    """Plain catalog listing (GET /portfolios) — unrelated to a
    client's own matched results, kept separate from ProductOut/
    RecommendedPortfolioOut which are specific to a profile."""

    id: int
    name: str
    provider: str | None
    risk_band: int
    max_equity_pct: float
    min_horizon_years: float
    liquidity_days: int
    reg28_compliant: bool
    description: str | None


class ProfileResult(BaseModel):
    client_id: int
    tolerance_band: int
    capacity_band: int
    horizon_band: int
    knowledge_band: int
    governed_risk_band: int
    governed_risk_band_label: str
    governed_risk_band_explanation: str
    goals_detail: str | None
    tax_bracket: str | None
    tax_bracket_estimated: bool
    gross_monthly_income: float
    monthly_expenses: float
    monthly_contribution: float
    # Both added alongside the product-centric restructure — needed to
    # re-run matching for a hypothetical "what if" question in chat
    # without re-asking the client everything. Optional because a
    # profile finalized before this existed won't have them; recalculate
    # degrades gracefully (falls back to "can't re-match, sorry") rather
    # than crashing for those older records.
    investment_goal: str | None = None
    emergency_fund_months: float | None = None
    matched_products: list[ProductOut]

    @model_validator(mode="before")
    @classmethod
    def _backfill_band_framing(cls, data):
        """Profiles finalized before governed_risk_band_label/
        _explanation existed have stored JSON without them — without
        this, loading one of those old records would hard-crash with a
        validation error. Derives them from governed_risk_band, which
        every record has always had."""
        if isinstance(data, dict) and "governed_risk_band" in data:
            band = data["governed_risk_band"]
            if not data.get("governed_risk_band_label"):
                data["governed_risk_band_label"] = BAND_LABELS.get(band, f"Band {band}")
            if not data.get("governed_risk_band_explanation"):
                data["governed_risk_band_explanation"] = BAND_EXPLANATIONS.get(band, "")
        return data


class ChatStartIn(BaseModel):
    known_context: dict = Field(default_factory=dict)
    language: str = "en"


class ChatStartOut(BaseModel):
    session_id: int
    reply: str


class ChatMessageIn(BaseModel):
    message: str


class ChatTurnOut(BaseModel):
    reply: str
    extracted: dict = {}
    ready_to_finalize: bool = False
    missing_fields: list[str] = []
    finalized_result: ProfileResult | None = None
    # The full, possibly-different recommended product set for a
    # hypothetical "what if" question — a genuine re-match, not just
    # updated numbers on the same fixed product list. None when this
    # turn didn't involve a recalculation. Never persisted — this is a
    # preview only, shown in the results view until the client starts
    # a new conversation or explicitly asks to update their profile.
    recalculated_products: list[ProductOut] | None = None
    recalculated_note: str | None = None
    risk_widget: dict | None = None
    profile_summary: dict | None = None
    nudge: dict | None = None
    intake_progress: dict | None = None


class TaxEstimateOut(BaseModel):
    label: str
    rate: int


class TTSIn(BaseModel):
    text: str


class RiskRatingsIn(BaseModel):
    ratings: list[int]


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=8)
    full_name: str | None = None


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str | None


class AuthOut(BaseModel):
    token: str
    user: UserOut


class ChatMessageOut(BaseModel):
    role: str
    text: str


class ProfileSummaryOut(BaseModel):
    client_id: int
    chat_session_id: int | None
    created_at: str
    governed_risk_band: int
    investment_goal: str
    goals_detail: str | None


class BeneficiaryIn(BaseModel):
    full_name: str
    id_number: str
    relationship: str


class AccountApplicationIn(BaseModel):
    client_id: int
    product_id: int
    portfolio_id: int
    initial_amount: float = Field(ge=0, default=0)
    monthly_amount: float = Field(ge=0, default=0)
    full_name: str
    id_number: str
    date_of_birth: str
    address: str
    contact_number: str
    email: str
    bank_name: str
    bank_account_number: str
    branch_code: str
    beneficiary: BeneficiaryIn | None = None


class AccountOut(BaseModel):
    account_id: int
    client_id: int
    product_id: int
    product_name: str
    portfolio_id: int
    portfolio_name: str
    tax_wrapper: str
    initial_amount: float
    monthly_amount: float
    status: str
    created_at: str
    beneficiary_name: str | None = None


class ProfileDetailOut(BaseModel):
    chat_session_id: int
    profile_result: ProfileResult
    accounts: list[AccountOut] = []


class UserProfileOut(BaseModel):
    """The full saved-profile blob on a user's account — both the
    "stable" fields reused across risk-profiling sessions (age,
    dependents, income, etc.) and the KYC/banking fields normally only
    captured during an Invest Now application. Having these editable
    directly, in one place, means neither flow has to start blank if
    the person already told us this once."""

    full_name: str | None = None
    age: int | None = None
    dependents: int | None = None
    gross_monthly_income: float | None = None
    monthly_expenses: float | None = None
    knowledge_score: int | None = None
    id_number: str | None = None
    date_of_birth: str | None = None
    address: str | None = None
    contact_number: str | None = None
    email: str | None = None
    bank_name: str | None = None
    bank_account_number: str | None = None
    branch_code: str | None = None


class UserProfileUpdateIn(BaseModel):
    """Same shape as UserProfileOut, all optional — a PUT here is a
    partial merge (only fields actually sent are updated), not a full
    overwrite, so editing just your phone number doesn't blank out
    your bank details."""

    full_name: str | None = None
    age: int | None = None
    dependents: int | None = None
    gross_monthly_income: float | None = None
    monthly_expenses: float | None = None
    knowledge_score: int | None = None
    id_number: str | None = None
    date_of_birth: str | None = None
    address: str | None = None
    contact_number: str | None = None
    email: str | None = None
    bank_name: str | None = None
    bank_account_number: str | None = None
    branch_code: str | None = None


class LinkedAccountOut(BaseModel):
    """A demo-purposes-only view of the policyholder's OTHER banking
    relationships (credit card, everyday/debit account, home loan,
    vehicle finance) — not real balances, but stable per-user demo
    numbers so the end-of-month surplus check and "My Accounts" page
    have something real to reference in conversation. balance is
    signed: positive means money the client has, negative means money
    owed — so summing balances gives a genuine net position."""

    account_type: str
    name: str
    balance: float
    limit: float | None = None


# ---------------------------------------------------------------------
# Item -> dataclass helpers
# ---------------------------------------------------------------------
def _item_to_product(item: dict) -> Product:
    return Product(
        id=int(item["product_id"]),
        name=item["name"],
        provider=item["provider"],
        tax_wrapper=item["tax_wrapper"],
        min_initial_investment=db.num(item["min_initial_investment"]),
        min_monthly_investment=db.num(item["min_monthly_investment"]),
        annual_platform_fee_pct=db.num(item["annual_platform_fee_pct"]),
        advice_fee_pct=db.num(item["advice_fee_pct"]),
        min_term_years=db.num(item["min_term_years"]),
        description=item["description"],
        spec_notes=item.get("spec_notes") or "",
        key=item.get("key") or "",
    )


def _item_to_portfolio(item: dict) -> Portfolio:
    return Portfolio(
        id=int(item["portfolio_id"]),
        name=item["name"],
        provider=item["provider"],
        risk_band=int(item["risk_band"]),
        max_equity_pct=db.num(item["max_equity_pct"]),
        min_horizon_years=db.num(item["min_horizon_years"]),
        liquidity_days=int(item["liquidity_days"]),
        reg28_compliant=bool(item["reg28_compliant"]),
        min_knowledge_band=int(item["min_knowledge_band"]),
        requires_emergency_fund=bool(item["requires_emergency_fund"]),
        underlying_fee_pct=db.num(item["underlying_fee_pct"]),
        description=item["description"],
        key=item.get("key") or "",
    )


def _load_all_portfolios() -> list[dict]:
    items: list[dict] = []
    resp = db.PORTFOLIOS.scan()
    items.extend(resp["Items"])
    while "LastEvaluatedKey" in resp:
        resp = db.PORTFOLIOS.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp["Items"])
    return items


def _load_all_products() -> list[dict]:
    items: list[dict] = []
    resp = db.PRODUCTS.scan()
    items.extend(resp["Items"])
    while "LastEvaluatedKey" in resp:
        resp = db.PRODUCTS.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp["Items"])
    return items


def _load_returns() -> dict[int, list[tuple[float, float, float, float]]]:
    items: list[dict] = []
    resp = db.PORTFOLIO_RETURNS.scan()
    items.extend(resp["Items"])
    while "LastEvaluatedKey" in resp:
        resp = db.PORTFOLIO_RETURNS.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp["Items"])

    curves: dict[int, list[tuple[float, float, float, float]]] = {}
    for r in items:
        curves.setdefault(int(r["portfolio_id"]), []).append(
            (db.num(r["horizon_years"]), db.num(r["expected_return_pct"]), db.num(r["lower_return_pct"]), db.num(r["upper_return_pct"]))
        )
    for portfolio_id in curves:
        curves[portfolio_id].sort(key=lambda p: p[0])
    return curves


def _parse_tax_rate(tax_bracket: str | None) -> int | None:
    if not tax_bracket:
        return None
    match = re.search(r"\d+", tax_bracket)
    return int(match.group()) if match else None


def _project(returns_by_portfolio, portfolio_id, fee_pct, initial_amount, monthly_amount, horizon_years) -> ProjectionOut | None:
    curve = returns_by_portfolio.get(portfolio_id)
    if not curve:
        return None
    expected, lower, upper = projections.resolve_curve_point(curve, horizon_years)
    result = projections.project_range(
        initial_amount=initial_amount,
        monthly_amount=monthly_amount,
        horizon_years=horizon_years,
        expected_return_pct=expected,
        lower_return_pct=lower,
        upper_return_pct=upper,
        fee_pct=fee_pct,
    )
    return ProjectionOut(
        expected_value=round(result.expected_value, 2),
        lower_value=round(result.lower_value, 2),
        upper_value=round(result.upper_value, 2),
        net_expected_return_pct=round(result.net_expected_return_pct, 2),
    )


def _build_product_id_to_portfolio_ids(portfolio_items_by_id: dict[int, dict]) -> dict[int, list[int]]:
    """Inverts the existing portfolio -> product_ids denormalization
    into product_id -> [portfolio_id, ...], which is what matching now
    needs (product-first, not portfolio-first). No schema change
    required — the source data (each portfolio's product_ids list)
    already has everything needed."""
    mapping: dict[int, list[int]] = {}
    for portfolio_id, item in portfolio_items_by_id.items():
        for product_id in item.get("product_ids", []):
            mapping.setdefault(int(product_id), []).append(portfolio_id)
    return mapping


def _build_product_outputs(
    products_with_allocations: list[tuple[Product, list[tuple[Portfolio, float]]]],
    returns_by_portfolio: dict[int, list[tuple[float, float, float, float]]],
    initial_amount: float,
    monthly_amount: float,
    horizon_years: float,
    emergency_fund_months: float,
    tax_rate: int | None,
) -> list[ProductOut]:
    """Shared by _finalize() and the chat's what-if recalculation —
    turns (product, [(portfolio, allocation_pct), ...]) pairs into the
    full ProductOut list: per-portfolio split amounts, projections, an
    aggregated total projection per product, reasons, and top pick.
    Sorted top-pick first, then cheapest effective fee."""
    reasons_by_id = build_product_reasons(products_with_allocations, emergency_fund_months, tax_rate)
    top_product, top_reason = pick_top_product(products_with_allocations, emergency_fund_months, tax_rate)

    outputs: list[ProductOut] = []
    for product, allocations in products_with_allocations:
        recommended_portfolios: list[RecommendedPortfolioOut] = []
        total_expected = total_lower = total_upper = 0.0
        has_projection = False

        for portfolio, alloc_pct in allocations:
            split_initial = round(initial_amount * alloc_pct / 100, 2)
            split_monthly = round(monthly_amount * alloc_pct / 100, 2)
            fee = combined_fee_pct(product, portfolio)
            projection = _project(returns_by_portfolio, portfolio.id, fee, split_initial, split_monthly, horizon_years)
            if projection is not None:
                total_expected += projection.expected_value
                total_lower += projection.lower_value
                total_upper += projection.upper_value
                has_projection = True
            recommended_portfolios.append(
                RecommendedPortfolioOut(
                    portfolio_id=portfolio.id,
                    portfolio_name=portfolio.name,
                    provider=portfolio.provider,
                    risk_band=portfolio.risk_band,
                    allocation_pct=alloc_pct,
                    split_initial_amount=split_initial,
                    split_monthly_amount=split_monthly,
                    fee_pct=round(fee, 2),
                    projection=projection,
                )
            )

        is_top = top_product is not None and product.id == top_product.id
        outputs.append(
            ProductOut(
                id=product.id,
                name=product.name,
                provider=product.provider,
                tax_wrapper=product.tax_wrapper,
                min_initial_investment=product.min_initial_investment,
                min_monthly_investment=product.min_monthly_investment,
                min_term_years=product.min_term_years,
                description=product.description,
                reasons=reasons_by_id.get(product.id, []),
                is_top_pick=is_top,
                top_pick_reason=top_reason if is_top else None,
                total_fee_pct=round(product_weighted_fee(product, allocations), 2),
                total_expected_value=round(total_expected, 2) if has_projection else None,
                total_lower_value=round(total_lower, 2) if has_projection else None,
                total_upper_value=round(total_upper, 2) if has_projection else None,
                recommended_portfolios=recommended_portfolios,
            )
        )

    outputs.sort(key=lambda p: (0 if p.is_top_pick else 1, p.total_fee_pct))
    return outputs


_seed_status = {"state": "not_started"}


def _run_seeding() -> None:
    _seed_status["state"] = "running"
    try:
        db.seed_catalog()
        _seed_status["state"] = "done"
    except Exception as e:
        _seed_status["state"] = "failed"
        _seed_status["error"] = str(e)
        print(f"Background seeding failed: {e}")


@app.on_event("startup")
def startup() -> None:
    db.ensure_tables_exist()
    threading.Thread(target=_run_seeding, daemon=True).start()


@app.get("/admin/seed-status")
def seed_status() -> dict:
    portfolios_have_items = bool(db.PORTFOLIOS.scan(Limit=1).get("Items"))
    products_have_items = bool(db.PRODUCTS.scan(Limit=1).get("Items"))
    returns_have_items = bool(db.PORTFOLIO_RETURNS.scan(Limit=1).get("Items"))
    return {
        "background_task_state": _seed_status["state"],
        "error": _seed_status.get("error"),
        "portfolios_seeded": portfolios_have_items,
        "products_seeded": products_have_items,
        "portfolio_returns_seeded": returns_have_items,
    }


# ---------------------------------------------------------------------
# Core finalize logic
# ---------------------------------------------------------------------
def _finalize(payload: ClientProfileIn, extracted_extra: dict, user_id: str | None = None) -> ProfileResult:
    dependents = payload.dependents
    gross_monthly_income = payload.gross_monthly_income
    monthly_expenses = payload.monthly_expenses
    goals_detail: str | None = None
    explicit_tax_bracket: str | None = extracted_extra.get("tax_bracket")

    dependents = extracted_extra.get("dependents", dependents)
    gross_monthly_income = extracted_extra.get("gross_monthly_income", gross_monthly_income)
    monthly_expenses = extracted_extra.get("monthly_expenses", monthly_expenses)
    if extracted_extra.get("goals"):
        goals_detail = ", ".join(extracted_extra["goals"])
    if extracted_extra.get("notes"):
        goals_detail = f"{goals_detail + ' — ' if goals_detail else ''}{extracted_extra['notes']}"

    tax_bracket_estimated = explicit_tax_bracket is None
    if explicit_tax_bracket:
        tax_bracket = explicit_tax_bracket
    else:
        tax_bracket, _ = tax_estimate.estimate_tax_bracket(gross_monthly_income)
    tax_rate = _parse_tax_rate(tax_bracket)

    client_input = ClientInput(
        age=payload.age,
        dependents=dependents,
        gross_monthly_income=gross_monthly_income,
        monthly_expenses=monthly_expenses,
        emergency_fund_months=payload.emergency_fund_months,
        investment_horizon_years=payload.investment_horizon_years,
        investment_goal=payload.investment_goal,
        tolerance_questionnaire=payload.tolerance_questionnaire,
        knowledge_score=payload.knowledge_score,
    )
    bands = compute_bands(client_input)

    client_id = db.next_id("client_id")
    client_item = {
        "client_id": client_id,
        "full_name": payload.full_name,
        "age": payload.age,
        "dependents": dependents,
        "gross_monthly_income": db.dec(gross_monthly_income),
        "monthly_expenses": db.dec(monthly_expenses),
        "emergency_fund_months": db.dec(payload.emergency_fund_months),
        "investment_horizon_years": db.dec(payload.investment_horizon_years),
        "investment_goal": payload.investment_goal,
        "available_lump_sum": db.dec(payload.available_lump_sum),
        "monthly_contribution": db.dec(payload.monthly_contribution),
        "goals_detail": goals_detail,
        "tax_bracket": tax_bracket,
        "tolerance_questionnaire": payload.tolerance_questionnaire,
        "knowledge_score": payload.knowledge_score,
        "tolerance_band": bands.tolerance_band,
        "capacity_band": bands.capacity_band,
        "horizon_band": bands.horizon_band,
        "governed_risk_band": bands.governed_risk_band,
        "created_at": _now_iso(),
    }
    if payload.chat_session_id is not None:
        client_item["chat_session_id"] = payload.chat_session_id
    if user_id is not None:
        client_item["user_id"] = user_id
    db.CLIENTS.put_item(Item=client_item)

    if user_id is not None:
        stable_fields = {
            "full_name": payload.full_name,
            "age": payload.age,
            "dependents": dependents,
            "gross_monthly_income": gross_monthly_income,
            "monthly_expenses": monthly_expenses,
            "knowledge_score": payload.knowledge_score,
        }
        _merge_into_saved_profile(user_id, stable_fields)

    portfolio_items_by_id = {int(item["portfolio_id"]): item for item in _load_all_portfolios()}
    portfolios_by_id = {pid: _item_to_portfolio(item) for pid, item in portfolio_items_by_id.items()}
    product_id_to_portfolio_ids = _build_product_id_to_portfolio_ids(portfolio_items_by_id)

    all_products = [_item_to_product(item) for item in _load_all_products()]
    returns_by_portfolio = _load_returns()

    products_with_allocations = match_products_with_allocations(
        products=all_products,
        product_id_to_portfolio_ids=product_id_to_portfolio_ids,
        portfolios_by_id=portfolios_by_id,
        bands=bands,
        investment_horizon_years=payload.investment_horizon_years,
        emergency_fund_months=payload.emergency_fund_months,
        investment_goal=payload.investment_goal,
        available_lump_sum=payload.available_lump_sum,
        monthly_contribution=payload.monthly_contribution,
    )

    product_outputs = _build_product_outputs(
        products_with_allocations,
        returns_by_portfolio,
        payload.available_lump_sum,
        payload.monthly_contribution,
        payload.investment_horizon_years,
        payload.emergency_fund_months,
        tax_rate,
    )

    return ProfileResult(
        client_id=client_id,
        tolerance_band=bands.tolerance_band,
        capacity_band=bands.capacity_band,
        horizon_band=bands.horizon_band,
        knowledge_band=bands.knowledge_band,
        governed_risk_band=bands.governed_risk_band,
        governed_risk_band_label=BAND_LABELS[bands.governed_risk_band],
        governed_risk_band_explanation=BAND_EXPLANATIONS[bands.governed_risk_band],
        goals_detail=goals_detail,
        tax_bracket=tax_bracket,
        tax_bracket_estimated=tax_bracket_estimated,
        gross_monthly_income=gross_monthly_income,
        monthly_expenses=monthly_expenses,
        monthly_contribution=payload.monthly_contribution,
        investment_goal=payload.investment_goal,
        emergency_fund_months=payload.emergency_fund_months,
        matched_products=product_outputs,
    )


def _client_profile_from_extracted(extracted: dict, chat_session_id: int) -> ClientProfileIn:
    return ClientProfileIn(
        full_name=extracted["full_name"],
        age=int(extracted["age"]),
        dependents=int(extracted["dependents"]),
        gross_monthly_income=float(extracted["gross_monthly_income"]),
        monthly_expenses=float(extracted["monthly_expenses"]),
        emergency_fund_months=float(extracted["emergency_fund_months"]),
        investment_horizon_years=float(extracted["investment_horizon_years"]),
        investment_goal=extracted["investment_goal"],
        tolerance_questionnaire=[int(x) for x in extracted["tolerance_questionnaire"]],
        knowledge_score=int(extracted["knowledge_score"]),
        available_lump_sum=float(extracted.get("available_lump_sum", 0)),
        monthly_contribution=float(extracted.get("monthly_contribution", 0)),
        chat_session_id=chat_session_id,
    )


@app.post("/clients/profile", response_model=ProfileResult)
def submit_profile(
    payload: ClientProfileIn, user_id: str | None = Depends(get_optional_user_id)
) -> ProfileResult:
    extracted_extra: dict = {}
    if payload.chat_session_id is not None:
        item = db.CHAT_SESSIONS.get_item(Key={"session_id": payload.chat_session_id}).get("Item")
        if item is None:
            raise HTTPException(status_code=404, detail="chat_session_id not found")
        _check_session_access(item.get("user_id"), user_id)
        extracted_extra = json.loads(item["extracted_profile"])
    return _finalize(payload, extracted_extra, user_id=user_id)


@app.get("/portfolios", response_model=list[PortfolioCatalogOut])
def list_portfolios() -> list[PortfolioCatalogOut]:
    items = sorted(_load_all_portfolios(), key=lambda i: int(i["risk_band"]))
    return [
        PortfolioCatalogOut(
            id=int(i["portfolio_id"]),
            name=i["name"],
            provider=i["provider"],
            risk_band=int(i["risk_band"]),
            max_equity_pct=db.num(i["max_equity_pct"]),
            min_horizon_years=db.num(i["min_horizon_years"]),
            liquidity_days=int(i["liquidity_days"]),
            reg28_compliant=bool(i["reg28_compliant"]),
            description=i["description"],
        )
        for i in items
    ]


@app.get("/tax-estimate", response_model=TaxEstimateOut)
def get_tax_estimate(monthly_income: float) -> TaxEstimateOut:
    label, rate = tax_estimate.estimate_tax_bracket(monthly_income)
    return TaxEstimateOut(label=label, rate=rate)


@app.get("/products/{product_id}/learn-more")
def get_product_learn_more(product_id: int) -> dict:
    item = db.PRODUCTS.get_item(Key={"product_id": product_id}).get("Item")
    if item is None or not item.get("key"):
        raise HTTPException(status_code=404, detail="No additional info available for this product")
    details = product_specs.learn_more(item["key"])
    if details is None:
        raise HTTPException(status_code=404, detail="No additional info available for this product")
    return details


_POLLY_MAX_CHARS = 3000
_polly_client = None


def _get_polly():
    global _polly_client
    if _polly_client is None:
        region = os.environ.get("AWS_REGION")
        _polly_client = boto3.client("polly", **({"region_name": region} if region else {}))
    return _polly_client


@app.post("/tts")
def synthesize_speech(payload: TTSIn) -> Response:
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="text must not be empty")
    text = text[:_POLLY_MAX_CHARS]

    try:
        resp = _get_polly().synthesize_speech(
            Text=text,
            OutputFormat="mp3",
            VoiceId="Joanna",
            Engine="neural",
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Speech synthesis unavailable: {e}")

    audio_bytes = resp["AudioStream"].read()
    return Response(content=audio_bytes, media_type="audio/mpeg")


def _load_saved_known_context(user_id: str) -> dict:
    item = db.USERS.get_item(Key={"email": user_id}).get("Item")
    if item is None:
        return {}
    if item.get("saved_profile"):
        return json.loads(item["saved_profile"])
    if item.get("full_name"):
        return {"full_name": item["full_name"]}
    return {}


def _merge_into_saved_profile(user_id: str, updates: dict) -> dict:
    """Merges `updates` (only keys with a non-None value are applied)
    into the user's saved_profile blob and writes it back. Used
    whenever any flow — finishing a risk profile, opening an account,
    or editing the profile page directly — learns something durable
    about the person; always a merge, never a blind overwrite, so one
    flow's fields never blank out another's."""
    existing_item = db.USERS.get_item(Key={"email": user_id}).get("Item")
    existing = json.loads(existing_item["saved_profile"]) if existing_item and existing_item.get("saved_profile") else {}
    for key, value in updates.items():
        if value is not None:
            existing[key] = value
    db.USERS.update_item(
        Key={"email": user_id},
        UpdateExpression="SET saved_profile = :sp",
        ExpressionAttributeValues={":sp": json.dumps(existing)},
    )
    return existing


def _generate_demo_linked_accounts(user_id: str) -> list[dict]:
    """Deterministic per-user demo numbers — not real bank data, but
    stable across requests for a given user (seeded off their email)
    rather than re-randomizing every time, so referencing them in
    conversation stays consistent."""
    seed = int(hashlib.sha256(user_id.encode()).hexdigest(), 16)

    def pick(low: float, high: float, salt: int) -> float:
        r = (seed >> salt) % 10000 / 10000
        return round(low + r * (high - low), 2)

    return [
        {"account_type": "debit", "name": "Everyday Account", "balance": pick(1500, 26000, 3)},
        {"account_type": "credit", "name": "Credit Card", "balance": -pick(300, 14000, 11), "limit": 25000.0},
        {"account_type": "home_loan", "name": "Home Loan", "balance": -pick(380000, 1450000, 19)},
        {"account_type": "vehicle_finance", "name": "Vehicle Finance", "balance": -pick(75000, 340000, 27)},
    ]


def _load_or_generate_linked_accounts(user_id: str) -> list[dict]:
    """Generated once per user and stored, not regenerated on every
    call — so the numbers a client sees stay the same across a
    session (and across the surplus check vs. the accounts page)."""
    item = db.USERS.get_item(Key={"email": user_id}).get("Item")
    if item and item.get("other_accounts"):
        return json.loads(item["other_accounts"])
    generated = _generate_demo_linked_accounts(user_id)
    db.USERS.update_item(
        Key={"email": user_id},
        UpdateExpression="SET other_accounts = :oa",
        ExpressionAttributeValues={":oa": json.dumps(generated)},
    )
    return generated


@app.post("/chat/sessions", response_model=ChatStartOut)
def start_chat(
    payload: ChatStartIn = ChatStartIn(), user_id: str | None = Depends(get_optional_user_id)
) -> ChatStartOut:
    known_context = dict(payload.known_context)
    if user_id is not None:
        known_context = {**known_context, **_load_saved_known_context(user_id)}

    language = payload.language if payload.language in ai_chat.LANGUAGE_NAMES else "en"

    session_id = db.next_id("session_id")
    session_item = {
        "session_id": session_id,
        "extracted_profile": json.dumps(known_context),
        "known_context": json.dumps(known_context),
        "language": language,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    if user_id is not None:
        session_item["user_id"] = user_id
    db.CHAT_SESSIONS.put_item(Item=session_item)

    opening = ai_chat.build_opening_message(known_context, language=language)
    _put_message(session_id, "assistant", json.dumps(opening))

    return ChatStartOut(session_id=session_id, reply=opening)


def _put_message(session_id: int, role: str, content_json: str) -> None:
    sort_key = f"{_now_iso()}#{uuid.uuid4().hex[:8]}"
    db.CHAT_MESSAGES.put_item(
        Item={"session_id": session_id, "created_at": sort_key, "role": role, "content": content_json}
    )


def _load_history(session_id: int) -> list[dict]:
    resp = db.CHAT_MESSAGES.query(KeyConditionExpression=Key("session_id").eq(session_id))
    items = resp["Items"]
    while "LastEvaluatedKey" in resp:
        resp = db.CHAT_MESSAGES.query(
            KeyConditionExpression=Key("session_id").eq(session_id),
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        items.extend(resp["Items"])
    return [{"role": r["role"], "content": json.loads(r["content"])} for r in items]


def _handle_intake_turn(
    session_id: int, extracted: dict, user_content, user_id: str | None = None, known_context: dict | None = None, language: str = "en"
) -> ChatTurnOut:
    history = _load_history(session_id)

    finalized_holder: dict = {"result": None}
    risk_widget_holder: dict = {"data": None}
    summary_holder: dict = {"data": None}

    def executor(tool_name: str, tool_input: dict) -> dict:
        nonlocal extracted
        if tool_name == "record_client_info":
            extracted = ai_chat.merge_extracted(extracted, tool_input)
            return {"status": "recorded"}

        if tool_name == "request_risk_ratings":
            risk_widget_holder["data"] = ai_chat.build_risk_widget(extracted, language=language)
            return {"status": "widget_shown"}

        if tool_name == "show_profile_summary":
            summary_holder["data"] = ai_chat.build_profile_summary(extracted)
            return {"status": "summary_shown"}

        if tool_name == "recommend_monthly_contribution":
            income = extracted.get("gross_monthly_income")
            expenses = extracted.get("monthly_expenses")
            if income is None or expenses is None:
                return {
                    "status": "unavailable",
                    "detail": "gross_monthly_income and monthly_expenses must both be known first",
                }
            net_income = tax_estimate.estimate_net_monthly_income(income)
            disposable_surplus = round(net_income - expenses, 2)
            return {
                "status": "computed",
                "net_monthly_income": round(net_income, 2),
                "monthly_expenses": expenses,
                "disposable_surplus": disposable_surplus,
            }

        if tool_name == "confirm_and_proceed":
            complete, missing = ai_chat.is_profile_complete(extracted)
            if not complete:
                return {"status": "incomplete", "missing_fields": missing}
            try:
                profile_in = _client_profile_from_extracted(extracted, session_id)
                result = _finalize(profile_in, extracted, user_id=user_id)
            except Exception as e:
                return {"status": "error", "detail": str(e)}
            finalized_holder["result"] = result
            return {"status": "confirmed", "governed_risk_band": result.governed_risk_band}

        return {"status": "unknown_tool"}

    system_prompt = ai_chat.build_intake_system_prompt(known_context, language=language)
    reply, updated_history = ai_chat.run_turn(
        history, user_content, system_prompt, ai_chat.INTAKE_TOOLS, executor
    )

    for m in updated_history[len(history):]:
        _put_message(session_id, m["role"], json.dumps(m["content"]))

    result = finalized_holder["result"]
    update_expr = "SET extracted_profile = :ep, updated_at = :ua"
    expr_values = {":ep": json.dumps(extracted), ":ua": _now_iso()}
    if result is not None:
        update_expr += ", finalized_result = :fr"
        expr_values[":fr"] = result.model_dump_json()
    db.CHAT_SESSIONS.update_item(
        Key={"session_id": session_id},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values,
    )

    complete, missing = ai_chat.is_profile_complete(extracted)
    completed_count, total_count = ai_chat.compute_intake_progress(extracted)
    return ChatTurnOut(
        reply=reply,
        extracted=extracted,
        ready_to_finalize=complete,
        missing_fields=missing,
        finalized_result=result,
        risk_widget=risk_widget_holder["data"],
        profile_summary=summary_holder["data"],
        intake_progress={"completed": completed_count, "total": total_count} if result is None else None,
    )


SURPLUS_NUDGE_THRESHOLD = 200


def _load_product_blurbs(stored_result: dict) -> list[str]:
    product_ids = {prod["id"] for prod in stored_result.get("matched_products", [])}
    blurbs = []
    for product_id in product_ids:
        item = db.PRODUCTS.get_item(Key={"product_id": product_id}).get("Item")
        if item is None or not item.get("key"):
            continue
        blurb = product_specs.context_blurb(item["key"])
        if blurb:
            blurbs.append(blurb)
    return blurbs


def _rematch_for_hypothetical(
    stored_result: dict, initial_amount: float, monthly_amount: float, horizon_years: float, investment_goal_override: str | None = None
) -> list[ProductOut] | None:
    """Genuinely re-runs product matching for a hypothetical "what if"
    question — a different lump sum, contribution, horizon, or even
    GOAL can change which products are even eligible (e.g. a bigger
    lump sum might newly qualify for a product with a high minimum, or
    a different goal opens up a completely different set of tax
    wrappers), not just the projected numbers on the products already
    shown.

    Uses the client's STORED bands/goal/emergency-fund (unchanged —
    this is a preview, not a redo of the whole intake) unless
    investment_goal_override is given, in which case that goal is used
    instead for this preview only. If horizon changed, horizon_band
    (and therefore governed_risk_band) is re-derived accordingly, same
    as a real re-profiling would.

    Returns None if the stored profile predates investment_goal/
    emergency_fund_months being recorded — an older profile can't be
    re-matched without them, so this degrades gracefully rather than
    crashing; the caller falls back to explaining that a fresh profile
    is needed for this feature.
    """
    investment_goal = investment_goal_override or stored_result.get("investment_goal")
    emergency_fund_months = stored_result.get("emergency_fund_months")
    if investment_goal is None or emergency_fund_months is None:
        return None

    new_horizon_band = compute_horizon_band(horizon_years)
    bands = BandResult(
        tolerance_band=stored_result["tolerance_band"],
        capacity_band=stored_result["capacity_band"],
        horizon_band=new_horizon_band,
        governed_risk_band=min(stored_result["tolerance_band"], stored_result["capacity_band"], new_horizon_band),
        knowledge_band=stored_result["knowledge_band"],
    )

    portfolio_items_by_id = {int(item["portfolio_id"]): item for item in _load_all_portfolios()}
    portfolios_by_id = {pid: _item_to_portfolio(item) for pid, item in portfolio_items_by_id.items()}
    product_id_to_portfolio_ids = _build_product_id_to_portfolio_ids(portfolio_items_by_id)

    all_products = [_item_to_product(item) for item in _load_all_products()]
    returns_by_portfolio = _load_returns()

    products_with_allocations = match_products_with_allocations(
        products=all_products,
        product_id_to_portfolio_ids=product_id_to_portfolio_ids,
        portfolios_by_id=portfolios_by_id,
        bands=bands,
        investment_horizon_years=horizon_years,
        emergency_fund_months=emergency_fund_months,
        investment_goal=investment_goal,
        available_lump_sum=initial_amount,
        monthly_contribution=monthly_amount,
    )

    tax_rate = _parse_tax_rate(stored_result.get("tax_bracket"))
    return _build_product_outputs(
        products_with_allocations,
        returns_by_portfolio,
        initial_amount,
        monthly_amount,
        horizon_years,
        emergency_fund_months,
        tax_rate,
    )


def _handle_post_results_turn(session_id: int, stored_result: dict, user_content, language: str = "en", user_id: str | None = None) -> ChatTurnOut:
    history = _load_history(session_id)

    recalculated_holder: dict = {"products": None, "note": None}
    nudge_holder: dict = {"data": None}

    product_blurbs = _load_product_blurbs(stored_result)

    def executor(tool_name: str, tool_input: dict) -> dict:
        if tool_name == "check_monthly_surplus":
            if user_id is None:
                return {"status": "unavailable", "detail": "No linked accounts to check for a guest session."}
            linked = _load_or_generate_linked_accounts(user_id)
            debit = next((a["balance"] for a in linked if a["account_type"] == "debit"), 0.0)
            credit = next((a["balance"] for a in linked if a["account_type"] == "credit"), 0.0)
            net = round(debit + credit, 2)
            if net <= SURPLUS_NUDGE_THRESHOLD:
                return {"status": "no_meaningful_surplus", "surplus_amount": net}
            nudge_holder["data"] = {"surplus_amount": net}
            return {"status": "surplus_found", "surplus_amount": net}

        if tool_name != "recalculate_investment_projection":
            return {"status": "unknown_tool"}

        new_products = _rematch_for_hypothetical(
            stored_result,
            tool_input["initial_amount"],
            tool_input["monthly_amount"],
            tool_input["horizon_years"],
            investment_goal_override=tool_input.get("investment_goal"),
        )
        if new_products is None:
            return {
                "status": "unavailable",
                "detail": "This profile predates re-matching support — the client would need to redo their profile for this.",
            }

        recalculated_holder["products"] = new_products
        recalculated_holder["note"] = (
            "This is a preview only — nothing has been saved. The client's actual saved profile is unchanged "
            "unless they explicitly ask you to update it."
        )

        original_names = {p["name"] for p in stored_result.get("matched_products", [])}
        new_names = {p.name for p in new_products}
        return {
            "status": "recalculated",
            "product_count": len(new_products),
            "newly_eligible_products": sorted(new_names - original_names),
            "no_longer_eligible_products": sorted(original_names - new_names),
            "top_products": [
                {
                    "name": p.name,
                    "total_fee_pct": p.total_fee_pct,
                    "total_expected_value": p.total_expected_value,
                    "portfolios": [
                        {"name": rp.portfolio_name, "allocation_pct": rp.allocation_pct}
                        for rp in p.recommended_portfolios
                    ],
                }
                for p in new_products[:5]
            ],
        }

    system_prompt = ai_chat.build_post_results_system_prompt(stored_result, product_blurbs=product_blurbs, language=language)
    reply, updated_history = ai_chat.run_turn(
        history, user_content, system_prompt, ai_chat.POST_RESULTS_TOOLS, executor
    )

    for m in updated_history[len(history):]:
        _put_message(session_id, m["role"], json.dumps(m["content"]))

    db.CHAT_SESSIONS.update_item(
        Key={"session_id": session_id},
        UpdateExpression="SET updated_at = :ua",
        ExpressionAttributeValues={":ua": _now_iso()},
    )

    return ChatTurnOut(
        reply=reply,
        ready_to_finalize=True,
        recalculated_products=recalculated_holder["products"],
        recalculated_note=recalculated_holder["note"],
        nudge=nudge_holder["data"],
    )


@app.post("/chat/sessions/{session_id}/messages", response_model=ChatTurnOut)
def send_chat_message(
    session_id: int, payload: ChatMessageIn, user_id: str | None = Depends(get_optional_user_id)
) -> ChatTurnOut:
    item = db.CHAT_SESSIONS.get_item(Key={"session_id": session_id}).get("Item")
    if item is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    _check_session_access(item.get("user_id"), user_id)
    language = item.get("language", "en")

    try:
        if item.get("finalized_result"):
            result = _handle_post_results_turn(session_id, json.loads(item["finalized_result"]), payload.message, language=language, user_id=user_id)
        else:
            extracted = json.loads(item["extracted_profile"])
            known_context = json.loads(item["known_context"])
            result = _handle_intake_turn(
                session_id, extracted, payload.message, user_id=user_id, known_context=known_context, language=language
            )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return result


@app.post("/chat/sessions/{session_id}/risk-ratings", response_model=ChatTurnOut)
def submit_risk_ratings(
    session_id: int, payload: RiskRatingsIn, user_id: str | None = Depends(get_optional_user_id)
) -> ChatTurnOut:
    if len(payload.ratings) != 5 or not all(1 <= r <= 5 for r in payload.ratings):
        raise HTTPException(status_code=422, detail="ratings must be exactly 5 integers, each 1-5")

    item = db.CHAT_SESSIONS.get_item(Key={"session_id": session_id}).get("Item")
    if item is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    _check_session_access(item.get("user_id"), user_id)
    if item.get("finalized_result"):
        raise HTTPException(status_code=400, detail="This session's profile is already finalized.")

    extracted = json.loads(item["extracted_profile"])
    extracted["tolerance_questionnaire"] = payload.ratings
    known_context = json.loads(item["known_context"])
    language = item.get("language", "en")
    synthetic_message = f"[The client submitted their risk ratings via the widget: {payload.ratings}]"

    try:
        result = _handle_intake_turn(
            session_id, extracted, synthetic_message, user_id=user_id, known_context=known_context, language=language
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return result


@app.post("/chat/sessions/{session_id}/upload-statement", response_model=ChatTurnOut)
async def upload_statement(
    session_id: int, file: UploadFile = File(...), user_id: str | None = Depends(get_optional_user_id)
) -> ChatTurnOut:
    item = db.CHAT_SESSIONS.get_item(Key={"session_id": session_id}).get("Item")
    if item is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    _check_session_access(item.get("user_id"), user_id)
    if item.get("finalized_result"):
        raise HTTPException(
            status_code=400,
            detail="This session's profile is already finalized — statement upload is only for intake.",
        )

    pdf_bytes = await file.read()
    try:
        statement_text = pdf_extract.extract_text(pdf_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    user_content = [
        {
            "type": "text",
            "text": (
                "I've uploaded a bank statement. Here is the extracted text "
                f"(it may include noise from the PDF layout):\n\n{statement_text}"
            ),
        }
    ]

    try:
        extracted = json.loads(item["extracted_profile"])
        known_context = json.loads(item["known_context"])
        language = item.get("language", "en")
        result = _handle_intake_turn(
            session_id, extracted, user_content, user_id=user_id, known_context=known_context, language=language
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return result


@app.get("/chat/sessions/{session_id}/history", response_model=list[ChatMessageOut])
def get_chat_history(
    session_id: int, user_id: str | None = Depends(get_optional_user_id)
) -> list[ChatMessageOut]:
    item = db.CHAT_SESSIONS.get_item(Key={"session_id": session_id}).get("Item")
    if item is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    _check_session_access(item.get("user_id"), user_id)

    raw_history = _load_history(session_id)

    display: list[ChatMessageOut] = []
    for r in raw_history:
        content = r["content"]
        role = r["role"]

        if isinstance(content, str):
            display.append(ChatMessageOut(role=role, text=content))
            continue

        if not isinstance(content, list):
            continue

        if role == "assistant":
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
            if text:
                display.append(ChatMessageOut(role="assistant", text=text))
        elif role == "user":
            if all(b.get("type") == "tool_result" for b in content):
                continue
            text_blocks = [b.get("text", "") for b in content if b.get("type") == "text"]
            combined = " ".join(text_blocks).strip()
            if combined.startswith("I've uploaded a bank statement"):
                display.append(ChatMessageOut(role="user", text="📎 Uploaded a bank statement"))
            elif combined:
                display.append(ChatMessageOut(role="user", text=combined))

    return display


@app.post("/auth/register", response_model=AuthOut)
def register(payload: RegisterIn) -> AuthOut:
    existing = db.USERS.get_item(Key={"email": payload.email}).get("Item")
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    password_hash = auth.hash_password(payload.password)
    db.USERS.put_item(
        Item={
            "email": payload.email,
            "password_hash": password_hash,
            "full_name": payload.full_name,
            "created_at": _now_iso(),
        }
    )

    token = auth.create_token(payload.email)
    return AuthOut(
        token=token,
        user=UserOut(id=payload.email, email=payload.email, full_name=payload.full_name),
    )


@app.post("/auth/login", response_model=AuthOut)
def login(payload: LoginIn) -> AuthOut:
    item = db.USERS.get_item(Key={"email": payload.email}).get("Item")

    if item is None or not auth.verify_password(payload.password, item["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    token = auth.create_token(item["email"])
    return AuthOut(
        token=token,
        user=UserOut(id=item["email"], email=item["email"], full_name=item.get("full_name")),
    )


@app.get("/auth/me", response_model=UserOut)
def get_me(user_id: str = Depends(require_user_id)) -> UserOut:
    item = db.USERS.get_item(Key={"email": user_id}).get("Item")
    if item is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return UserOut(id=item["email"], email=item["email"], full_name=item.get("full_name"))


@app.get("/auth/me/profile", response_model=UserProfileOut)
def get_my_profile(user_id: str = Depends(require_user_id)) -> UserProfileOut:
    saved = _load_saved_known_context(user_id)
    return UserProfileOut(**saved)


@app.put("/auth/me/profile", response_model=UserProfileOut)
def update_my_profile(payload: UserProfileUpdateIn, user_id: str = Depends(require_user_id)) -> UserProfileOut:
    merged = _merge_into_saved_profile(user_id, payload.model_dump())
    return UserProfileOut(**merged)


@app.get("/accounts/mine", response_model=list[AccountOut])
def list_my_accounts(user_id: str = Depends(require_user_id)) -> list[AccountOut]:
    """Every account this person has opened, across every risk profile
    they've ever completed — not scoped to one client_id, since a
    person may have redone their profile (and so has more than one
    client_id) over time. The Accounts table only has a by-client GSI,
    so this is a full scan filtered client-side; fine at hackathon
    scale, would want a by-user GSI before this saw real traffic."""
    items: list[dict] = []
    resp = db.ACCOUNTS.scan()
    items.extend(resp["Items"])
    while "LastEvaluatedKey" in resp:
        resp = db.ACCOUNTS.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp["Items"])
    mine = [a for a in items if a.get("user_id") == user_id]
    mine.sort(key=lambda a: a["created_at"], reverse=True)
    return [_account_item_to_out(a) for a in mine]


@app.get("/accounts/linked", response_model=list[LinkedAccountOut])
def list_linked_accounts(user_id: str = Depends(require_user_id)) -> list[LinkedAccountOut]:
    """The client's other banking relationships (credit, debit, home
    loan, vehicle finance) — demo values, generated once and stable
    per user. Shown on the accounts page and referenced by the chat's
    end-of-month surplus check."""
    accounts = _load_or_generate_linked_accounts(user_id)
    return [LinkedAccountOut(**a) for a in accounts]


@app.get("/profiles", response_model=list[ProfileSummaryOut])
def list_profiles(user_id: str = Depends(require_user_id)) -> list[ProfileSummaryOut]:
    resp = db.CLIENTS.query(
        IndexName="by-user",
        KeyConditionExpression=Key("user_id").eq(user_id),
        ScanIndexForward=False,
    )
    items = resp["Items"]
    while "LastEvaluatedKey" in resp:
        resp = db.CLIENTS.query(
            IndexName="by-user",
            KeyConditionExpression=Key("user_id").eq(user_id),
            ScanIndexForward=False,
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        items.extend(resp["Items"])

    return [
        ProfileSummaryOut(
            client_id=int(i["client_id"]),
            chat_session_id=int(i["chat_session_id"]) if i.get("chat_session_id") is not None else None,
            created_at=i["created_at"],
            governed_risk_band=int(i["governed_risk_band"]),
            investment_goal=i["investment_goal"],
            goals_detail=i.get("goals_detail"),
        )
        for i in items
    ]


@app.get("/profiles/{client_id}", response_model=ProfileDetailOut)
def get_profile(client_id: int, user_id: str = Depends(require_user_id)) -> ProfileDetailOut:
    client_item = db.CLIENTS.get_item(Key={"client_id": client_id}).get("Item")
    if client_item is None:
        raise HTTPException(status_code=404, detail="profile not found")
    if client_item.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this profile")

    chat_session_id = int(client_item["chat_session_id"])
    session_item = db.CHAT_SESSIONS.get_item(Key={"session_id": chat_session_id}).get("Item")
    if session_item is None or not session_item.get("finalized_result"):
        raise HTTPException(status_code=404, detail="stored result not found for this profile")

    try:
        profile_result = ProfileResult.model_validate_json(session_item["finalized_result"])
    except Exception:
        # This profile predates the product-centric restructure (a
        # structural reshape, not just missing fields) — nothing to
        # meaningfully backfill from, so surface a clear, honest error
        # rather than a raw 500 or silently-wrong data.
        raise HTTPException(
            status_code=409,
            detail="This profile was created before a product-matching update and can't be reopened — please start a new risk profile.",
        )
    accounts = _load_accounts_for_client(client_id)

    return ProfileDetailOut(chat_session_id=chat_session_id, profile_result=profile_result, accounts=accounts)


def _account_item_to_out(a: dict) -> AccountOut:
    beneficiary_name = None
    if a.get("beneficiary"):
        beneficiary_name = json.loads(a["beneficiary"])["full_name"]
    return AccountOut(
        account_id=int(a["account_id"]),
        client_id=int(a["client_id"]),
        product_id=int(a["product_id"]),
        product_name=a["product_name"],
        portfolio_id=int(a["portfolio_id"]),
        portfolio_name=a["portfolio_name"],
        tax_wrapper=a["tax_wrapper"],
        initial_amount=db.num(a["initial_amount"]),
        monthly_amount=db.num(a["monthly_amount"]),
        status=a["status"],
        created_at=a["created_at"],
        beneficiary_name=beneficiary_name,
    )


def _load_accounts_for_client(client_id: int) -> list[AccountOut]:
    resp = db.ACCOUNTS.query(
        IndexName="by-client",
        KeyConditionExpression=Key("client_id").eq(client_id),
    )
    return [_account_item_to_out(a) for a in resp["Items"]]


@app.post("/accounts", response_model=AccountOut)
def open_account(payload: AccountApplicationIn, user_id: str = Depends(require_user_id)) -> AccountOut:
    client_item = db.CLIENTS.get_item(Key={"client_id": payload.client_id}).get("Item")
    if client_item is None:
        raise HTTPException(status_code=404, detail="profile not found")
    if client_item.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to open an account against this profile")

    product_item = db.PRODUCTS.get_item(Key={"product_id": payload.product_id}).get("Item")
    if product_item is None:
        raise HTTPException(status_code=404, detail="product not found")
    portfolio_item = db.PORTFOLIOS.get_item(Key={"portfolio_id": payload.portfolio_id}).get("Item")
    if portfolio_item is None:
        raise HTTPException(status_code=404, detail="portfolio not found")

    tax_wrapper = product_item["tax_wrapper"]
    if tax_wrapper == "retirement_annuity" and payload.beneficiary is None:
        raise HTTPException(
            status_code=422,
            detail="A retirement annuity requires a nominated beneficiary before the account can be opened.",
        )

    account_id = db.next_id("account_id")
    created_at = _now_iso()
    account_item = {
        "account_id": account_id,
        "client_id": payload.client_id,
        "user_id": user_id,
        "product_id": payload.product_id,
        "product_name": product_item["name"],
        "portfolio_id": payload.portfolio_id,
        "portfolio_name": portfolio_item["name"],
        "tax_wrapper": tax_wrapper,
        "initial_amount": db.dec(payload.initial_amount),
        "monthly_amount": db.dec(payload.monthly_amount),
        "application": json.dumps(
            {
                "full_name": payload.full_name,
                "id_number": payload.id_number,
                "date_of_birth": payload.date_of_birth,
                "address": payload.address,
                "contact_number": payload.contact_number,
                "email": payload.email,
                "bank_name": payload.bank_name,
                "bank_account_number": payload.bank_account_number,
                "branch_code": payload.branch_code,
            }
        ),
        "status": "pending",
        "created_at": created_at,
    }
    if payload.beneficiary is not None:
        account_item["beneficiary"] = json.dumps(payload.beneficiary.model_dump())
    db.ACCOUNTS.put_item(Item=account_item)

    db.CLIENTS.update_item(
        Key={"client_id": payload.client_id},
        UpdateExpression=(
            "SET full_name = :fn, id_number = :idn, date_of_birth = :dob, "
            "address = :addr, contact_number = :cn, email = :em, "
            "bank_name = :bn, bank_account_number = :ban, branch_code = :bc"
        ),
        ExpressionAttributeValues={
            ":fn": payload.full_name,
            ":idn": payload.id_number,
            ":dob": payload.date_of_birth,
            ":addr": payload.address,
            ":cn": payload.contact_number,
            ":em": payload.email,
            ":bn": payload.bank_name,
            ":ban": payload.bank_account_number,
            ":bc": payload.branch_code,
        },
    )

    # Also save the KYC/banking details onto the user's own saved
    # profile (not just the client record) — so the next chat intake
    # or Invest Now application doesn't start blank if we already have
    # this from a previous application.
    _merge_into_saved_profile(
        user_id,
        {
            "full_name": payload.full_name,
            "id_number": payload.id_number,
            "date_of_birth": payload.date_of_birth,
            "address": payload.address,
            "contact_number": payload.contact_number,
            "email": payload.email,
            "bank_name": payload.bank_name,
            "bank_account_number": payload.bank_account_number,
            "branch_code": payload.branch_code,
        },
    )

    return AccountOut(
        account_id=account_id,
        client_id=payload.client_id,
        product_id=payload.product_id,
        product_name=product_item["name"],
        portfolio_id=payload.portfolio_id,
        portfolio_name=portfolio_item["name"],
        tax_wrapper=tax_wrapper,
        initial_amount=payload.initial_amount,
        monthly_amount=payload.monthly_amount,
        status="pending",
        created_at=created_at,
        beneficiary_name=payload.beneficiary.full_name if payload.beneficiary else None,
    )
