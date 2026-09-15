from __future__ import annotations

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
    match_portfolios,
    match_products,
    pick_top_product,
)
from pydantic import BaseModel, Field
from scoring import BAND_EXPLANATIONS, BAND_LABELS, ClientInput, compute_bands

app = FastAPI(title="Risk Profiling API")

app.add_middleware(
    CORSMiddleware,
    # Frontend (CloudFront) and backend (Elastic Beanstalk) are now on
    # genuinely different domains, so this needs to actually allow
    # cross-origin requests. Wildcard is safe here specifically because
    # auth is a Bearer token in a header, not a cookie — there's no
    # session to hijack via CSRF, which is the usual reason to lock
    # this down tighter.
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------
# Auth dependencies
#
# get_optional_user_id never raises — no header, a malformed header, or
# an expired/invalid token all just mean "anonymous" (returns None).
# Endpoints that must work for guests (starting a chat, sending a
# message) use this. require_user_id builds on it and raises 401 when
# there's no valid identity — used for /auth/me and /profiles.
#
# "user_id" is now the user's email (DynamoDB's Users table is keyed
# by email) — kept the name for minimal churn on everything that reads
# it, the type just changed from int to str.
# ---------------------------------------------------------------------
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
    """A session with no owner (anonymous/guest) is accessible to anyone,
    matching pre-auth behaviour. An owned session is only accessible to
    its owner."""
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


class ProductOut(BaseModel):
    id: int
    portfolio_id: int
    name: str
    provider: str | None
    tax_wrapper: str
    min_initial_investment: float
    min_monthly_investment: float
    total_fee_pct: float
    min_term_years: float
    description: str | None
    reasons: list[str] = []
    is_top_pick: bool = False
    top_pick_reason: str | None = None
    projection: ProjectionOut | None = None


class PortfolioOut(BaseModel):
    id: int
    name: str
    provider: str | None
    risk_band: int
    max_equity_pct: float
    min_horizon_years: float
    liquidity_days: int
    reg28_compliant: bool
    description: str | None
    matched_products: list[ProductOut] = []


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
    matched_portfolios: list[PortfolioOut]


class ChatStartIn(BaseModel):
    known_context: dict = Field(default_factory=dict)
    language: str = "en"


class ChatStartOut(BaseModel):
    session_id: int
    reply: str


class ChatMessageIn(BaseModel):
    message: str


class RecalculatedProjectionOut(BaseModel):
    product_id: int
    portfolio_id: int
    product_name: str
    portfolio_name: str
    expected_value: float
    lower_value: float
    upper_value: float


class ChatTurnOut(BaseModel):
    reply: str
    extracted: dict = {}
    ready_to_finalize: bool = False
    missing_fields: list[str] = []
    finalized_result: ProfileResult | None = None
    recalculated_projections: list[RecalculatedProjectionOut] = []
    risk_widget: dict | None = None
    profile_summary: dict | None = None
    nudge: dict | None = None
    intake_progress: dict | None = None  # {"completed": int, "total": int} during intake; omitted post-results


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
    id: str  # the email — there's no separate numeric user id anymore
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
    """portfolio_id -> its full return curve, sorted by horizon_years.
    Each point is (horizon_years, expected, lower, upper) — see
    projections.resolve_curve_point for how a specific horizon's rate
    gets resolved from this. The catalog is small, so a full scan
    (grouped client-side) is simpler than a query per portfolio."""
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


_seed_status = {"state": "not_started"}  # not_started | running | done | failed


def _run_seeding() -> None:
    _seed_status["state"] = "running"
    try:
        db.seed_catalog()
        _seed_status["state"] = "done"
    except Exception as e:
        # Seeding failing shouldn't take the whole app down — the API
        # still starts and serves what it can (catalog just stays
        # empty until this is retried). /admin/seed-status surfaces the
        # failure directly instead of it being a silent, hard-to-find gap.
        _seed_status["state"] = "failed"
        _seed_status["error"] = str(e)
        print(f"Background seeding failed: {e}")


@app.on_event("startup")
def startup() -> None:
    # Table creation is fast (a handful of DDL calls) — stays
    # synchronous so the app never starts serving before its tables
    # exist. Seeding the real fund catalog is NOT fast (~8,700+
    # DynamoDB writes, can take a couple of minutes on a cold start),
    # so it runs in a background thread instead of blocking here —
    # blocking was putting it at the mercy of gunicorn's worker
    # timeout AND Elastic Beanstalk's health-check grace period,
    # either of which could (and did) kill the process mid-seed.
    db.ensure_tables_exist()
    threading.Thread(target=_run_seeding, daemon=True).start()


@app.get("/admin/seed-status")
def seed_status() -> dict:
    """Check seeding progress directly instead of digging through AWS
    console item counts (which are only periodically updated anyway,
    not real-time) or EB logs. Cheap Scan(Limit=1) checks per table —
    fine to call occasionally, not meant for polling in a loop."""
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
# Core finalize logic — shared by the plain POST /clients/profile
# endpoint and the chat's confirm_and_proceed tool. `extracted_extra`
# carries goals/notes/tax_bracket overrides gathered outside the
# ClientProfileIn payload itself (from the chat's extracted_profile).
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
        db.USERS.update_item(
            Key={"email": user_id},
            UpdateExpression="SET saved_profile = :sp",
            ExpressionAttributeValues={":sp": json.dumps(stable_fields)},
        )

    portfolio_items_by_id = {int(item["portfolio_id"]): item for item in _load_all_portfolios()}
    portfolios = [_item_to_portfolio(item) for item in portfolio_items_by_id.values()]

    matched = match_portfolios(
        portfolios,
        bands,
        payload.investment_horizon_years,
        payload.emergency_fund_months,
        payload.investment_goal,
    )

    all_products = [_item_to_product(item) for item in _load_all_products()]
    returns_by_portfolio = _load_returns()

    prioritize_tax_efficient = tax_rate is not None and tax_rate >= 39
    portfolio_outputs: list[PortfolioOut] = []

    for portfolio in matched:
        mapped_product_ids = set(int(pid) for pid in portfolio_items_by_id[portfolio.id].get("product_ids", []))
        matched_products = match_products(
            all_products,
            portfolio,
            mapped_product_ids,
            payload.investment_goal,
            payload.investment_horizon_years,
            payload.available_lump_sum,
            payload.monthly_contribution,
            prioritize_tax_efficient=prioritize_tax_efficient,
        )

        reasons_by_id = build_product_reasons(
            matched_products, portfolio, payload.emergency_fund_months, tax_rate
        )
        top_product, top_reason = pick_top_product(
            matched_products, portfolio, payload.emergency_fund_months, tax_rate
        )

        portfolio_outputs.append(
            PortfolioOut(
                id=portfolio.id,
                name=portfolio.name,
                provider=portfolio.provider,
                risk_band=portfolio.risk_band,
                max_equity_pct=portfolio.max_equity_pct,
                min_horizon_years=portfolio.min_horizon_years,
                liquidity_days=portfolio.liquidity_days,
                reg28_compliant=bool(portfolio.reg28_compliant),
                description=portfolio.description,
                matched_products=[
                    ProductOut(
                        id=prod.id,
                        portfolio_id=portfolio.id,
                        name=prod.name,
                        provider=prod.provider,
                        tax_wrapper=prod.tax_wrapper,
                        min_initial_investment=prod.min_initial_investment,
                        min_monthly_investment=prod.min_monthly_investment,
                        total_fee_pct=round(combined_fee_pct(prod, portfolio), 2),
                        min_term_years=prod.min_term_years,
                        description=prod.description,
                        reasons=reasons_by_id.get(prod.id, []),
                        is_top_pick=(top_product is not None and prod.id == top_product.id),
                        top_pick_reason=(
                            top_reason if top_product is not None and prod.id == top_product.id else None
                        ),
                        projection=_project(
                            returns_by_portfolio,
                            portfolio.id,
                            combined_fee_pct(prod, portfolio),
                            payload.available_lump_sum,
                            payload.monthly_contribution,
                            payload.investment_horizon_years,
                        ),
                    )
                    for prod in matched_products
                ],
            )
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
        matched_portfolios=portfolio_outputs,
    )


def _client_profile_from_extracted(extracted: dict, chat_session_id: int) -> ClientProfileIn:
    """Builds a validated ClientProfileIn straight from the chat's
    extracted_profile — used by confirm_and_proceed. Pydantic's own
    validation (e.g. gross_monthly_income > 0) surfaces as a ValueError
    the tool executor can hand back to the model as an actionable
    error instead of crashing the request."""
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
    """Direct entry point (not used by the chat flow, kept for testing
    / potential non-chat integrations). Pulls goals/tax_bracket
    overrides from the chat session if one is referenced."""
    extracted_extra: dict = {}
    if payload.chat_session_id is not None:
        item = db.CHAT_SESSIONS.get_item(Key={"session_id": payload.chat_session_id}).get("Item")
        if item is None:
            raise HTTPException(status_code=404, detail="chat_session_id not found")
        _check_session_access(item.get("user_id"), user_id)
        extracted_extra = json.loads(item["extracted_profile"])
    return _finalize(payload, extracted_extra, user_id=user_id)


@app.get("/portfolios", response_model=list[PortfolioOut])
def list_portfolios() -> list[PortfolioOut]:
    items = sorted(_load_all_portfolios(), key=lambda i: int(i["risk_band"]))
    return [
        PortfolioOut(
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
    """Curated highlights (about/key_features/faqs) from that product's
    spec JSON, for the "Learn more" panel on a matched product's card.
    404s cleanly if the product doesn't exist OR if it just doesn't
    have a spec file yet — the frontend treats both the same way
    (hide the "Learn more" affordance)."""
    item = db.PRODUCTS.get_item(Key={"product_id": product_id}).get("Item")
    if item is None or not item.get("key"):
        raise HTTPException(status_code=404, detail="No additional info available for this product")
    details = product_specs.learn_more(item["key"])
    if details is None:
        raise HTTPException(status_code=404, detail="No additional info available for this product")
    return details


_POLLY_MAX_CHARS = 3000  # keeps a single request bounded — hackathon-scale abuse guard, not a real quota system
_polly_client = None


def _get_polly():
    global _polly_client
    if _polly_client is None:
        region = os.environ.get("AWS_REGION")
        _polly_client = boto3.client("polly", **({"region_name": region} if region else {}))
    return _polly_client


@app.post("/tts")
def synthesize_speech(payload: TTSIn) -> Response:
    """Text -> spoken audio via Amazon Polly's Neural engine — used for
    the optional "read replies aloud" toggle. Deliberately not tied to
    a specific chat session or auth: it's a stateless text-to-audio
    utility, no different in sensitivity from any other public route
    here. Neural voices sound meaningfully more natural than the
    browser's built-in speechSynthesis, which is the whole point of
    using Polly instead."""
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


# ---------------------------------------------------------------------
# Chat — single endpoint, two phases
# ---------------------------------------------------------------------
def _load_saved_known_context(user_id: str) -> dict:
    """A returning user's stable fields from their last finalized profile
    (or just their signup name, if they haven't finalized one yet) —
    pre-filled into a new session so those aren't asked from scratch."""
    item = db.USERS.get_item(Key={"email": user_id}).get("Item")
    if item is None:
        return {}
    if item.get("saved_profile"):
        return json.loads(item["saved_profile"])
    if item.get("full_name"):
        return {"full_name": item["full_name"]}
    return {}


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
    """Sort key is timestamp + a short random suffix — gives ordered
    retrieval via Query (no client-side sort needed) and avoids
    same-timestamp collisions."""
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
            except Exception as e:  # validation error, bad value, etc.
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


SURPLUS_NUDGE_THRESHOLD = 200  # Rand — below this, not worth flagging as a meaningful surplus


def _load_product_blurbs(stored_result: dict) -> list[str]:
    """Curated spec-file summaries for every product in this client's
    matched results — feeds the post-results chat's system prompt so
    it can answer detailed questions accurately. Products without a
    spec file (or whose key lookup fails) are just skipped, not an
    error — this is a nice-to-have enrichment, not required data."""
    product_ids = {
        prod["id"]
        for pf in stored_result.get("matched_portfolios", [])
        for prod in pf.get("matched_products", [])
    }
    blurbs = []
    for product_id in product_ids:
        item = db.PRODUCTS.get_item(Key={"product_id": product_id}).get("Item")
        if item is None or not item.get("key"):
            continue
        blurb = product_specs.context_blurb(item["key"])
        if blurb:
            blurbs.append(blurb)
    return blurbs


def _handle_post_results_turn(session_id: int, stored_result: dict, user_content, language: str = "en") -> ChatTurnOut:
    history = _load_history(session_id)

    returns_by_portfolio = _load_returns()
    recalculated: list[RecalculatedProjectionOut] = []
    nudge_holder: dict = {"data": None}

    product_blurbs = _load_product_blurbs(stored_result)

    def executor(tool_name: str, tool_input: dict) -> dict:
        if tool_name == "check_monthly_surplus":
            income = stored_result.get("gross_monthly_income")
            expenses = stored_result.get("monthly_expenses")
            committed = stored_result.get("monthly_contribution", 0) or 0
            if income is None or expenses is None:
                return {"status": "unavailable"}
            surplus = round(income - expenses - committed, 2)
            if surplus <= SURPLUS_NUDGE_THRESHOLD:
                return {"status": "no_meaningful_surplus", "surplus_amount": surplus}
            nudge_holder["data"] = {"surplus_amount": surplus}
            return {"status": "surplus_found", "surplus_amount": surplus}

        if tool_name != "recalculate_investment_projection":
            return {"status": "unknown_tool"}

        name_filter = (tool_input.get("product_name") or "").lower().strip()
        matches = []
        for pf in stored_result.get("matched_portfolios", []):
            for prod in pf.get("matched_products", []):
                if name_filter and name_filter not in prod["name"].lower():
                    continue
                projection = _project(
                    returns_by_portfolio,
                    prod["portfolio_id"],
                    prod["total_fee_pct"],
                    tool_input["initial_amount"],
                    tool_input["monthly_amount"],
                    tool_input["horizon_years"],
                )
                if projection is None:
                    continue
                entry = {
                    "portfolio_name": pf["name"],
                    "product_name": prod["name"],
                    "expected_value": projection.expected_value,
                    "lower_value": projection.lower_value,
                    "upper_value": projection.upper_value,
                }
                matches.append(entry)
                recalculated.append(
                    RecalculatedProjectionOut(
                        product_id=prod["id"],
                        portfolio_id=prod["portfolio_id"],
                        product_name=prod["name"],
                        portfolio_name=pf["name"],
                        expected_value=projection.expected_value,
                        lower_value=projection.lower_value,
                        upper_value=projection.upper_value,
                    )
                )
        if not matches:
            return {"status": "no_matching_products"}
        return {"projections": matches}

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
        recalculated_projections=recalculated,
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
            result = _handle_post_results_turn(session_id, json.loads(item["finalized_result"]), payload.message, language=language)
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
    """The risk-ratings widget's submit button hits this directly rather
    than going through the normal chat message endpoint — the 5 numbers
    are recorded deterministically (no NLU ambiguity), then the model
    gets a synthetic turn so it can continue the conversation naturally
    (recap, ask what's still missing, etc.)."""
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
    """Intake-only — used to help estimate income/expenses before a
    profile is finalized."""
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
    """Reconstructs a clean, human-readable transcript for reopening a
    session — the raw stored rows include tool_use/tool_result plumbing
    that was never meant to be displayed. Used when continuing a past
    profile: the chat area needs something to show besides a blank
    screen even though the underlying session already has full history."""
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
                continue  # internal tool plumbing, never shown
            text_blocks = [b.get("text", "") for b in content if b.get("type") == "text"]
            combined = " ".join(text_blocks).strip()
            if combined.startswith("I've uploaded a bank statement"):
                display.append(ChatMessageOut(role="user", text="📎 Uploaded a bank statement"))
            elif combined:
                display.append(ChatMessageOut(role="user", text=combined))

    return display


# ---------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------
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
        # Same message for "no such user" and "wrong password" — never
        # reveal which one it was, that's an account-enumeration leak.
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


# ---------------------------------------------------------------------
# Profile history
# ---------------------------------------------------------------------
@app.get("/profiles", response_model=list[ProfileSummaryOut])
def list_profiles(user_id: str = Depends(require_user_id)) -> list[ProfileSummaryOut]:
    resp = db.CLIENTS.query(
        IndexName="by-user",
        KeyConditionExpression=Key("user_id").eq(user_id),
        ScanIndexForward=False,  # newest first
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

    profile_result = ProfileResult.model_validate_json(session_item["finalized_result"])
    accounts = _load_accounts_for_client(client_id)

    return ProfileDetailOut(chat_session_id=chat_session_id, profile_result=profile_result, accounts=accounts)


def _load_accounts_for_client(client_id: int) -> list[AccountOut]:
    resp = db.ACCOUNTS.query(
        IndexName="by-client",
        KeyConditionExpression=Key("client_id").eq(client_id),
    )
    accounts = []
    for a in resp["Items"]:
        beneficiary_name = None
        if a.get("beneficiary"):
            beneficiary_name = json.loads(a["beneficiary"])["full_name"]
        accounts.append(
            AccountOut(
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
        )
    return accounts


# ---------------------------------------------------------------------
# Investment accounts — the "Invest Now" flow. A hackathon-realistic
# simulation (form -> disclaimer -> account "opened"), not a real
# policy administration integration. Opening an account requires
# login, unlike the guest-friendly chat/profiling flow, since an
# account is inherently tied to a persistent identity.
# ---------------------------------------------------------------------
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
    # Server-side, not just a frontend form requirement — a retirement
    # annuity legally needs a nominated beneficiary, so we don't trust
    # the client-side form alone to enforce this.
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
        "status": "active",
        "created_at": created_at,
    }
    if payload.beneficiary is not None:
        account_item["beneficiary"] = json.dumps(payload.beneficiary.model_dump())
    db.ACCOUNTS.put_item(Item=account_item)

    # The application form gathers fuller KYC-style detail than the
    # chat intake did — this is the "application form populates the
    # profile" behaviour: enrich the stored client record with it.
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
        status="active",
        created_at=created_at,
        beneficiary_name=payload.beneficiary.full_name if payload.beneficiary else None,
    )
