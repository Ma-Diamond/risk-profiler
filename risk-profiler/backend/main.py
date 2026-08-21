from __future__ import annotations

import json
import re

import ai_chat
import pdf_extract
import projections
import tax_estimate
from db import get_connection, init_db
from fastapi import FastAPI, File, HTTPException, UploadFile
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
# Quick profile (Step 1) models
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


# ---------------------------------------------------------------------
# Chat (Step 2) models
# ---------------------------------------------------------------------
class ChatStartIn(BaseModel):
    known_context: dict = Field(default_factory=dict)


class ChatStartOut(BaseModel):
    session_id: int
    reply: str
    extracted: dict


class ChatMessageIn(BaseModel):
    message: str


class ChatTurnOut(BaseModel):
    reply: str
    extracted: dict


class TaxEstimateOut(BaseModel):
    label: str
    rate: int


class ProjectionPairIn(BaseModel):
    product_id: int
    portfolio_id: int


class ProjectionsBatchIn(BaseModel):
    initial_amount: float = Field(ge=0)
    monthly_amount: float = Field(ge=0)
    horizon_years: float = Field(gt=0)
    pairs: list[ProjectionPairIn]


class ProjectionsBatchItemOut(BaseModel):
    product_id: int
    portfolio_id: int
    projection: ProjectionOut


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
    """portfolio_id -> set of product_ids that offer it."""
    rows = conn.execute("SELECT product_id, portfolio_id FROM product_portfolio_mapping").fetchall()
    mapping: dict[int, set[int]] = {}
    for r in rows:
        mapping.setdefault(r["portfolio_id"], set()).add(r["product_id"])
    return mapping


def _load_returns(conn) -> dict[int, tuple[float, float, float]]:
    """portfolio_id -> (expected, lower, upper) annual return %."""
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
# Step 1 — quick profile / finalize
# ---------------------------------------------------------------------
@app.post("/clients/profile", response_model=ProfileResult)
def submit_profile(payload: ClientProfileIn) -> ProfileResult:
    conn = get_connection()

    dependents = payload.dependents
    gross_monthly_income = payload.gross_monthly_income
    monthly_expenses = payload.monthly_expenses
    goals_detail: str | None = None
    explicit_tax_bracket: str | None = None

    if payload.chat_session_id is not None:
        session_row = conn.execute(
            "SELECT extracted_profile FROM chat_sessions WHERE id = ?",
            (payload.chat_session_id,),
        ).fetchone()
        if session_row is None:
            conn.close()
            raise HTTPException(status_code=404, detail="chat_session_id not found")
        extracted = json.loads(session_row["extracted_profile"])

        dependents = extracted.get("dependents", dependents)
        gross_monthly_income = extracted.get("gross_monthly_income", gross_monthly_income)
        monthly_expenses = extracted.get("monthly_expenses", monthly_expenses)
        explicit_tax_bracket = extracted.get("tax_bracket")
        if extracted.get("goals"):
            goals_detail = ", ".join(extracted["goals"])
        if extracted.get("notes"):
            goals_detail = f"{goals_detail + ' — ' if goals_detail else ''}{extracted['notes']}"

    tax_bracket_estimated = explicit_tax_bracket is None
    if explicit_tax_bracket:
        tax_bracket = explicit_tax_bracket
    else:
        tax_bracket, _ = tax_estimate.estimate_tax_bracket(gross_monthly_income)
    tax_rate = _parse_tax_rate(tax_bracket)

    try:
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
    except ValueError as e:
        conn.close()
        raise HTTPException(status_code=422, detail=str(e))

    cur = conn.execute(
        """
        INSERT INTO clients (
            full_name, age, dependents, gross_monthly_income, monthly_expenses,
            emergency_fund_months, investment_horizon_years, investment_goal,
            available_lump_sum, monthly_contribution, goals_detail, tax_bracket,
            chat_session_id, tolerance_questionnaire, knowledge_score,
            tolerance_band, capacity_band, horizon_band, governed_risk_band
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
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


@app.post("/projections/batch", response_model=list[ProjectionsBatchItemOut])
def batch_projections(payload: ProjectionsBatchIn) -> list[ProjectionsBatchItemOut]:
    """Recalculate projections for a set of (product, portfolio) pairs
    under a shared duration/amount — used by the results page's
    calculator to let the client try different amounts or horizons."""
    conn = get_connection()
    returns_by_portfolio = _load_returns(conn)

    product_ids = {pair.product_id for pair in payload.pairs}
    portfolio_ids = {pair.portfolio_id for pair in payload.pairs}

    if product_ids:
        placeholders = ",".join("?" * len(product_ids))
        product_rows = conn.execute(
            f"SELECT * FROM products WHERE id IN ({placeholders})", tuple(product_ids)
        ).fetchall()
    else:
        product_rows = []
    products_by_id = {r["id"]: _row_to_product(r) for r in product_rows}

    if portfolio_ids:
        placeholders = ",".join("?" * len(portfolio_ids))
        portfolio_rows = conn.execute(
            f"SELECT * FROM portfolios WHERE id IN ({placeholders})", tuple(portfolio_ids)
        ).fetchall()
    else:
        portfolio_rows = []
    portfolios_by_id = {r["id"]: _row_to_portfolio(r) for r in portfolio_rows}
    conn.close()

    results: list[ProjectionsBatchItemOut] = []
    for pair in payload.pairs:
        product = products_by_id.get(pair.product_id)
        portfolio = portfolios_by_id.get(pair.portfolio_id)
        if product is None or portfolio is None:
            continue
        projection = _project(
            returns_by_portfolio,
            portfolio.id,
            combined_fee_pct(product, portfolio),
            payload.initial_amount,
            payload.monthly_amount,
            payload.horizon_years,
        )
        if projection is None:
            continue
        results.append(
            ProjectionsBatchItemOut(
                product_id=product.id, portfolio_id=portfolio.id, projection=projection
            )
        )
    return results


# ---------------------------------------------------------------------
# Step 2 — AI chat intake
# ---------------------------------------------------------------------
def _load_session(conn, session_id: int) -> tuple[list[dict], dict, dict]:
    row = conn.execute(
        "SELECT extracted_profile, known_context FROM chat_sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    extracted = json.loads(row["extracted_profile"])
    known_context = json.loads(row["known_context"])

    message_rows = conn.execute(
        "SELECT role, content FROM chat_messages WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    history = [
        {"role": r["role"], "content": json.loads(r["content"])} for r in message_rows
    ]
    return history, extracted, known_context


def _save_turn(
    conn, session_id: int, history: list[dict], extracted: dict, prior_len: int
) -> None:
    new_messages = history[prior_len:]
    conn.executemany(
        "INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)",
        [(session_id, m["role"], json.dumps(m["content"])) for m in new_messages],
    )
    conn.execute(
        "UPDATE chat_sessions SET extracted_profile = ?, updated_at = datetime('now') WHERE id = ?",
        (json.dumps(extracted), session_id),
    )
    conn.commit()


class ExtractedUpdateIn(BaseModel):
    extracted: dict


@app.get("/chat/sessions/{session_id}", response_model=ChatTurnOut)
def get_chat_session(session_id: int) -> ChatTurnOut:
    conn = get_connection()
    _, extracted, _ = _load_session(conn, session_id)
    conn.close()
    return ChatTurnOut(reply="", extracted=extracted)


@app.put("/chat/sessions/{session_id}/extracted", response_model=ChatTurnOut)
def update_extracted(session_id: int, payload: ExtractedUpdateIn) -> ChatTurnOut:
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM chat_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="chat session not found")

    conn.execute(
        "UPDATE chat_sessions SET extracted_profile = ?, updated_at = datetime('now') WHERE id = ?",
        (json.dumps(payload.extracted), session_id),
    )
    conn.commit()
    conn.close()
    return ChatTurnOut(reply="", extracted=payload.extracted)


@app.post("/chat/sessions", response_model=ChatStartOut)
def start_chat(payload: ChatStartIn = ChatStartIn()) -> ChatStartOut:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO chat_sessions (extracted_profile, known_context) VALUES ('{}', ?)",
        (json.dumps(payload.known_context),),
    )
    session_id = cur.lastrowid
    conn.commit()

    opening = ai_chat.build_opening_message(payload.known_context)
    conn.execute(
        "INSERT INTO chat_messages (session_id, role, content) VALUES (?, 'assistant', ?)",
        (session_id, json.dumps(opening)),
    )
    conn.commit()
    conn.close()

    return ChatStartOut(session_id=session_id, reply=opening, extracted={})


@app.post("/chat/sessions/{session_id}/messages", response_model=ChatTurnOut)
def send_chat_message(session_id: int, payload: ChatMessageIn) -> ChatTurnOut:
    conn = get_connection()
    history, extracted, known_context = _load_session(conn, session_id)
    prior_len = len(history)

    try:
        reply, extracted, updated_history = ai_chat.run_turn(
            history,
            payload.message,
            extracted,
            system_prompt=ai_chat.build_system_prompt(known_context),
        )
    except RuntimeError as e:
        conn.close()
        raise HTTPException(status_code=503, detail=str(e))

    _save_turn(conn, session_id, updated_history, extracted, prior_len)
    conn.close()
    return ChatTurnOut(reply=reply, extracted=extracted)


@app.post("/chat/sessions/{session_id}/upload-statement", response_model=ChatTurnOut)
async def upload_statement(session_id: int, file: UploadFile = File(...)) -> ChatTurnOut:
    conn = get_connection()
    history, extracted, known_context = _load_session(conn, session_id)
    prior_len = len(history)

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
        reply, extracted, updated_history = ai_chat.run_turn(
            history,
            user_content,
            extracted,
            system_prompt=ai_chat.build_system_prompt(known_context),
        )
    except RuntimeError as e:
        conn.close()
        raise HTTPException(status_code=503, detail=str(e))

    _save_turn(conn, session_id, updated_history, extracted, prior_len)
    conn.close()
    return ChatTurnOut(reply=reply, extracted=extracted)
