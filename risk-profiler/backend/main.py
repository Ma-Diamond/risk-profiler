from __future__ import annotations

import json
import re

import ai_chat
import auth
import pdf_extract
import projections
import tax_estimate
from db import get_connection, init_db
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
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
from scoring import ClientInput, compute_bands

app = FastAPI(title="Risk Profiling API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------
# Auth dependencies
#
# get_optional_user_id never raises — no header, a malformed header, or
# an expired/invalid token all just mean "anonymous" (returns None).
# Endpoints that must work for guests (starting a chat, sending a
# message) use this. require_user_id builds on it and raises 401 when
# there's no valid identity — used for /auth/me and /profiles.
# ---------------------------------------------------------------------
def get_optional_user_id(authorization: str | None = Header(default=None)) -> int | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    return auth.decode_token(token)


def require_user_id(user_id: int | None = Depends(get_optional_user_id)) -> int:
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def _check_session_access(session_owner_id: int | None, requester_user_id: int | None) -> None:
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
    goals_detail: str | None
    tax_bracket: str | None
    tax_bracket_estimated: bool
    matched_portfolios: list[PortfolioOut]


class ChatStartIn(BaseModel):
    known_context: dict = Field(default_factory=dict)


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


class TaxEstimateOut(BaseModel):
    label: str
    rate: int


class ExtractedUpdateIn(BaseModel):
    extracted: dict


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
    id: int
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


class ProfileDetailOut(BaseModel):
    chat_session_id: int
    profile_result: ProfileResult


# ---------------------------------------------------------------------
# Row -> dataclass helpers
# ---------------------------------------------------------------------
def _row_to_product(row) -> Product:
    return Product(
        id=row["id"],
        name=row["name"],
        provider=row["provider"],
        tax_wrapper=row["tax_wrapper"],
        min_initial_investment=row["min_initial_investment"],
        min_monthly_investment=row["min_monthly_investment"],
        annual_platform_fee_pct=row["annual_platform_fee_pct"],
        advice_fee_pct=row["advice_fee_pct"],
        min_term_years=row["min_term_years"],
        description=row["description"],
        spec_notes=row["spec_notes"] or "",
    )


def _row_to_portfolio(row) -> Portfolio:
    return Portfolio(
        id=row["id"],
        name=row["name"],
        provider=row["provider"],
        risk_band=row["risk_band"],
        max_equity_pct=row["max_equity_pct"],
        min_horizon_years=row["min_horizon_years"],
        liquidity_days=row["liquidity_days"],
        reg28_compliant=row["reg28_compliant"],
        min_knowledge_band=row["min_knowledge_band"],
        requires_emergency_fund=row["requires_emergency_fund"],
        underlying_fee_pct=row["underlying_fee_pct"],
        description=row["description"],
    )


def _load_mapping(conn) -> dict[int, set[int]]:
    rows = conn.execute("SELECT product_id, portfolio_id FROM product_portfolio_mapping").fetchall()
    mapping: dict[int, set[int]] = {}
    for r in rows:
        mapping.setdefault(r["portfolio_id"], set()).add(r["product_id"])
    return mapping


def _load_returns(conn) -> dict[int, tuple[float, float, float]]:
    rows = conn.execute(
        "SELECT portfolio_id, expected_return_pct, lower_return_pct, upper_return_pct FROM portfolio_returns"
    ).fetchall()
    return {
        r["portfolio_id"]: (r["expected_return_pct"], r["lower_return_pct"], r["upper_return_pct"])
        for r in rows
    }


def _parse_tax_rate(tax_bracket: str | None) -> int | None:
    if not tax_bracket:
        return None
    match = re.search(r"\d+", tax_bracket)
    return int(match.group()) if match else None


def _project(returns_by_portfolio, portfolio_id, fee_pct, initial_amount, monthly_amount, horizon_years) -> ProjectionOut | None:
    rates = returns_by_portfolio.get(portfolio_id)
    if rates is None:
        return None
    expected, lower, upper = rates
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


@app.on_event("startup")
def startup() -> None:
    init_db(seed=True)


# ---------------------------------------------------------------------
# Core finalize logic — shared by the plain POST /clients/profile
# endpoint and the chat's confirm_and_proceed tool. `extracted_extra`
# carries goals/notes/tax_bracket overrides gathered outside the
# ClientProfileIn payload itself (from the chat's extracted_profile).
# ---------------------------------------------------------------------
def _finalize(payload: ClientProfileIn, extracted_extra: dict, user_id: int | None = None) -> ProfileResult:
    conn = get_connection()

    dependents = payload.dependents
    gross_monthly_income = payload.gross_monthly_income
    monthly_expenses = payload.monthly_expenses
    goals_detail: str | None = None
    explicit_tax_bracket: str | None = extracted_extra.get("tax_bracket")

    # extracted_extra may carry more precise dependents/income/expenses
    # than the payload if it was refined after the payload was built —
    # only override where extracted_extra actually has a value.
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

    cur = conn.execute(
        """
        INSERT INTO clients (
            user_id, full_name, age, dependents, gross_monthly_income, monthly_expenses,
            emergency_fund_months, investment_horizon_years, investment_goal,
            available_lump_sum, monthly_contribution, goals_detail, tax_bracket,
            chat_session_id, tolerance_questionnaire, knowledge_score,
            tolerance_band, capacity_band, horizon_band, governed_risk_band
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            payload.full_name,
            payload.age,
            dependents,
            gross_monthly_income,
            monthly_expenses,
            payload.emergency_fund_months,
            payload.investment_horizon_years,
            payload.investment_goal,
            payload.available_lump_sum,
            payload.monthly_contribution,
            goals_detail,
            tax_bracket,
            payload.chat_session_id,
            json.dumps(payload.tolerance_questionnaire),
            payload.knowledge_score,
            bands.tolerance_band,
            bands.capacity_band,
            bands.horizon_band,
            bands.governed_risk_band,
        ),
    )
    client_id = cur.lastrowid
    conn.commit()

    portfolio_rows = conn.execute("SELECT * FROM portfolios").fetchall()
    portfolios = [_row_to_portfolio(r) for r in portfolio_rows]

    matched = match_portfolios(
        portfolios,
        bands,
        payload.investment_horizon_years,
        payload.emergency_fund_months,
        payload.investment_goal,
    )

    product_rows = conn.execute("SELECT * FROM products").fetchall()
    all_products = [_row_to_product(r) for r in product_rows]
    mapping = _load_mapping(conn)
    returns_by_portfolio = _load_returns(conn)

    conn.executemany(
        "INSERT INTO recommendations (client_id, portfolio_id, rank) VALUES (?, ?, ?)",
        [(client_id, p.id, i + 1) for i, p in enumerate(matched)],
    )

    prioritize_tax_efficient = tax_rate is not None and tax_rate >= 39
    portfolio_outputs: list[PortfolioOut] = []
    product_recommendation_rows: list[tuple[int, int, int, int]] = []

    for portfolio in matched:
        mapped_product_ids = mapping.get(portfolio.id, set())
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
        product_recommendation_rows.extend(
            (client_id, prod.id, portfolio.id, i + 1) for i, prod in enumerate(matched_products)
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

    if product_recommendation_rows:
        conn.executemany(
            "INSERT INTO product_recommendations (client_id, product_id, portfolio_id, rank) VALUES (?, ?, ?, ?)",
            product_recommendation_rows,
        )
    conn.commit()
    conn.close()

    return ProfileResult(
        client_id=client_id,
        tolerance_band=bands.tolerance_band,
        capacity_band=bands.capacity_band,
        horizon_band=bands.horizon_band,
        knowledge_band=bands.knowledge_band,
        governed_risk_band=bands.governed_risk_band,
        goals_detail=goals_detail,
        tax_bracket=tax_bracket,
        tax_bracket_estimated=tax_bracket_estimated,
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
    payload: ClientProfileIn, user_id: int | None = Depends(get_optional_user_id)
) -> ProfileResult:
    """Direct entry point (not used by the chat flow, kept for testing
    / potential non-chat integrations). Pulls goals/tax_bracket
    overrides from the chat session if one is referenced."""
    extracted_extra: dict = {}
    if payload.chat_session_id is not None:
        conn = get_connection()
        row = conn.execute(
            "SELECT extracted_profile, user_id FROM chat_sessions WHERE id = ?",
            (payload.chat_session_id,),
        ).fetchone()
        conn.close()
        if row is None:
            raise HTTPException(status_code=404, detail="chat_session_id not found")
        _check_session_access(row["user_id"], user_id)
        extracted_extra = json.loads(row["extracted_profile"])
    return _finalize(payload, extracted_extra, user_id=user_id)


@app.get("/portfolios", response_model=list[PortfolioOut])
def list_portfolios() -> list[PortfolioOut]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM portfolios ORDER BY risk_band").fetchall()
    conn.close()
    return [
        PortfolioOut(
            id=r["id"],
            name=r["name"],
            provider=r["provider"],
            risk_band=r["risk_band"],
            max_equity_pct=r["max_equity_pct"],
            min_horizon_years=r["min_horizon_years"],
            liquidity_days=r["liquidity_days"],
            reg28_compliant=bool(r["reg28_compliant"]),
            description=r["description"],
        )
        for r in rows
    ]


@app.get("/tax-estimate", response_model=TaxEstimateOut)
def get_tax_estimate(monthly_income: float) -> TaxEstimateOut:
    label, rate = tax_estimate.estimate_tax_bracket(monthly_income)
    return TaxEstimateOut(label=label, rate=rate)


# ---------------------------------------------------------------------
# Chat — single endpoint, two phases
# ---------------------------------------------------------------------
@app.post("/chat/sessions", response_model=ChatStartOut)
def start_chat(
    payload: ChatStartIn = ChatStartIn(), user_id: int | None = Depends(get_optional_user_id)
) -> ChatStartOut:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO chat_sessions (user_id, extracted_profile, known_context) VALUES (?, '{}', ?)",
        (user_id, json.dumps(payload.known_context)),
    )
    session_id = cur.lastrowid
    conn.commit()

    opening = ai_chat.build_opening_message()
    conn.execute(
        "INSERT INTO chat_messages (session_id, role, content) VALUES (?, 'assistant', ?)",
        (session_id, json.dumps(opening)),
    )
    conn.commit()
    conn.close()

    return ChatStartOut(session_id=session_id, reply=opening)


def _load_history(conn, session_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT role, content FROM chat_messages WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    return [{"role": r["role"], "content": json.loads(r["content"])} for r in rows]


def _handle_intake_turn(
    conn, session_id: int, extracted: dict, user_content, user_id: int | None = None
) -> ChatTurnOut:
    history = _load_history(conn, session_id)
    prior_len = len(history)

    finalized_holder: dict = {"result": None}
    risk_widget_holder: dict = {"data": None}
    summary_holder: dict = {"data": None}

    def executor(tool_name: str, tool_input: dict) -> dict:
        nonlocal extracted
        if tool_name == "record_client_info":
            extracted = ai_chat.merge_extracted(extracted, tool_input)
            return {"status": "recorded"}

        if tool_name == "request_risk_ratings":
            risk_widget_holder["data"] = ai_chat.build_risk_widget(extracted)
            return {"status": "widget_shown"}

        if tool_name == "show_profile_summary":
            summary_holder["data"] = ai_chat.build_profile_summary(extracted)
            return {"status": "summary_shown"}

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

    reply, updated_history = ai_chat.run_turn(
        history, user_content, ai_chat.INTAKE_SYSTEM_PROMPT, ai_chat.INTAKE_TOOLS, executor
    )

    new_messages = updated_history[prior_len:]
    conn.executemany(
        "INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)",
        [(session_id, m["role"], json.dumps(m["content"])) for m in new_messages],
    )
    conn.execute(
        "UPDATE chat_sessions SET extracted_profile = ?, updated_at = datetime('now') WHERE id = ?",
        (json.dumps(extracted), session_id),
    )

    result = finalized_holder["result"]
    if result is not None:
        conn.execute(
            "UPDATE chat_sessions SET finalized_result = ? WHERE id = ?",
            (result.model_dump_json(), session_id),
        )
    conn.commit()

    complete, missing = ai_chat.is_profile_complete(extracted)
    return ChatTurnOut(
        reply=reply,
        extracted=extracted,
        ready_to_finalize=complete,
        missing_fields=missing,
        finalized_result=result,
        risk_widget=risk_widget_holder["data"],
        profile_summary=summary_holder["data"],
    )


def _handle_post_results_turn(conn, session_id: int, stored_result: dict, user_content) -> ChatTurnOut:
    history = _load_history(conn, session_id)
    prior_len = len(history)

    returns_by_portfolio = _load_returns(conn)
    recalculated: list[RecalculatedProjectionOut] = []

    def executor(tool_name: str, tool_input: dict) -> dict:
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

    system_prompt = ai_chat.build_post_results_system_prompt(stored_result)
    reply, updated_history = ai_chat.run_turn(
        history, user_content, system_prompt, ai_chat.POST_RESULTS_TOOLS, executor
    )

    new_messages = updated_history[prior_len:]
    conn.executemany(
        "INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)",
        [(session_id, m["role"], json.dumps(m["content"])) for m in new_messages],
    )
    conn.execute(
        "UPDATE chat_sessions SET updated_at = datetime('now') WHERE id = ?", (session_id,)
    )
    conn.commit()

    return ChatTurnOut(
        reply=reply,
        ready_to_finalize=True,
        recalculated_projections=recalculated,
    )


@app.post("/chat/sessions/{session_id}/messages", response_model=ChatTurnOut)
def send_chat_message(
    session_id: int, payload: ChatMessageIn, user_id: int | None = Depends(get_optional_user_id)
) -> ChatTurnOut:
    conn = get_connection()
    row = conn.execute(
        "SELECT extracted_profile, finalized_result, user_id FROM chat_sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="chat session not found")
    _check_session_access(row["user_id"], user_id)

    try:
        if row["finalized_result"]:
            result = _handle_post_results_turn(
                conn, session_id, json.loads(row["finalized_result"]), payload.message
            )
        else:
            extracted = json.loads(row["extracted_profile"])
            result = _handle_intake_turn(conn, session_id, extracted, payload.message, user_id=user_id)
    except RuntimeError as e:
        conn.close()
        raise HTTPException(status_code=503, detail=str(e))

    conn.close()
    return result


@app.post("/chat/sessions/{session_id}/risk-ratings", response_model=ChatTurnOut)
def submit_risk_ratings(
    session_id: int, payload: RiskRatingsIn, user_id: int | None = Depends(get_optional_user_id)
) -> ChatTurnOut:
    """The risk-ratings widget's submit button hits this directly rather
    than going through the normal chat message endpoint — the 5 numbers
    are recorded deterministically (no NLU ambiguity), then the model
    gets a synthetic turn so it can continue the conversation naturally
    (recap, ask what's still missing, etc.)."""
    if len(payload.ratings) != 5 or not all(1 <= r <= 5 for r in payload.ratings):
        raise HTTPException(status_code=422, detail="ratings must be exactly 5 integers, each 1-5")

    conn = get_connection()
    row = conn.execute(
        "SELECT extracted_profile, finalized_result, user_id FROM chat_sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="chat session not found")
    _check_session_access(row["user_id"], user_id)
    if row["finalized_result"]:
        conn.close()
        raise HTTPException(status_code=400, detail="This session's profile is already finalized.")

    extracted = json.loads(row["extracted_profile"])
    extracted["tolerance_questionnaire"] = payload.ratings
    synthetic_message = f"[The client submitted their risk ratings via the widget: {payload.ratings}]"

    try:
        result = _handle_intake_turn(conn, session_id, extracted, synthetic_message, user_id=user_id)
    except RuntimeError as e:
        conn.close()
        raise HTTPException(status_code=503, detail=str(e))

    conn.close()
    return result


@app.post("/chat/sessions/{session_id}/upload-statement", response_model=ChatTurnOut)
async def upload_statement(
    session_id: int, file: UploadFile = File(...), user_id: int | None = Depends(get_optional_user_id)
) -> ChatTurnOut:
    """Intake-only — used to help estimate income/expenses before a
    profile is finalized."""
    conn = get_connection()
    row = conn.execute(
        "SELECT extracted_profile, finalized_result, user_id FROM chat_sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="chat session not found")
    _check_session_access(row["user_id"], user_id)
    if row["finalized_result"]:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="This session's profile is already finalized — statement upload is only for intake.",
        )

    pdf_bytes = await file.read()
    try:
        statement_text = pdf_extract.extract_text(pdf_bytes)
    except ValueError as e:
        conn.close()
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
        extracted = json.loads(row["extracted_profile"])
        result = _handle_intake_turn(conn, session_id, extracted, user_content, user_id=user_id)
    except RuntimeError as e:
        conn.close()
        raise HTTPException(status_code=503, detail=str(e))

    conn.close()
    return result


@app.get("/chat/sessions/{session_id}/history", response_model=list[ChatMessageOut])
def get_chat_history(
    session_id: int, user_id: int | None = Depends(get_optional_user_id)
) -> list[ChatMessageOut]:
    """Reconstructs a clean, human-readable transcript for reopening a
    session — the raw stored rows include tool_use/tool_result plumbing
    that was never meant to be displayed. Used when continuing a past
    profile: the chat area needs something to show besides a blank
    screen even though the underlying session already has full history."""
    conn = get_connection()
    row = conn.execute("SELECT user_id FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="chat session not found")
    _check_session_access(row["user_id"], user_id)

    raw_rows = conn.execute(
        "SELECT role, content FROM chat_messages WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    conn.close()

    display: list[ChatMessageOut] = []
    for r in raw_rows:
        content = json.loads(r["content"])
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
    conn = get_connection()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (payload.email,)).fetchone()
    if existing is not None:
        conn.close()
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    password_hash = auth.hash_password(payload.password)
    cur = conn.execute(
        "INSERT INTO users (email, password_hash, full_name) VALUES (?, ?, ?)",
        (payload.email, password_hash, payload.full_name),
    )
    user_id = cur.lastrowid
    conn.commit()
    conn.close()

    token = auth.create_token(user_id)
    return AuthOut(
        token=token,
        user=UserOut(id=user_id, email=payload.email, full_name=payload.full_name),
    )


@app.post("/auth/login", response_model=AuthOut)
def login(payload: LoginIn) -> AuthOut:
    conn = get_connection()
    row = conn.execute(
        "SELECT id, email, password_hash, full_name FROM users WHERE email = ?",
        (payload.email,),
    ).fetchone()
    conn.close()

    if row is None or not auth.verify_password(payload.password, row["password_hash"]):
        # Same message for "no such user" and "wrong password" — never
        # reveal which one it was, that's an account-enumeration leak.
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    token = auth.create_token(row["id"])
    return AuthOut(
        token=token,
        user=UserOut(id=row["id"], email=row["email"], full_name=row["full_name"]),
    )


@app.get("/auth/me", response_model=UserOut)
def get_me(user_id: int = Depends(require_user_id)) -> UserOut:
    conn = get_connection()
    row = conn.execute("SELECT id, email, full_name FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return UserOut(id=row["id"], email=row["email"], full_name=row["full_name"])


# ---------------------------------------------------------------------
# Profile history
# ---------------------------------------------------------------------
@app.get("/profiles", response_model=list[ProfileSummaryOut])
def list_profiles(user_id: int = Depends(require_user_id)) -> list[ProfileSummaryOut]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, chat_session_id, created_at, governed_risk_band, investment_goal, goals_detail
           FROM clients WHERE user_id = ? ORDER BY created_at DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [
        ProfileSummaryOut(
            client_id=r["id"],
            chat_session_id=r["chat_session_id"],
            created_at=r["created_at"],
            governed_risk_band=r["governed_risk_band"],
            investment_goal=r["investment_goal"],
            goals_detail=r["goals_detail"],
        )
        for r in rows
    ]


@app.get("/profiles/{client_id}", response_model=ProfileDetailOut)
def get_profile(client_id: int, user_id: int = Depends(require_user_id)) -> ProfileDetailOut:
    conn = get_connection()
    client_row = conn.execute(
        "SELECT user_id, chat_session_id FROM clients WHERE id = ?", (client_id,)
    ).fetchone()
    if client_row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="profile not found")
    if client_row["user_id"] != user_id:
        conn.close()
        raise HTTPException(status_code=403, detail="Not authorized to access this profile")

    chat_session_id = client_row["chat_session_id"]
    session_row = conn.execute(
        "SELECT finalized_result FROM chat_sessions WHERE id = ?", (chat_session_id,)
    ).fetchone()
    conn.close()
    if session_row is None or not session_row["finalized_result"]:
        raise HTTPException(status_code=404, detail="stored result not found for this profile")

    profile_result = ProfileResult.model_validate_json(session_row["finalized_result"])
    return ProfileDetailOut(chat_session_id=chat_session_id, profile_result=profile_result)
