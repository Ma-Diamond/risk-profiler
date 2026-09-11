"""AI-driven conversational intake AND post-results "what if" chat.

Two distinct phases share the same tool-use loop machinery
(`run_turn`) but use different tool sets and system prompts:

INTAKE phase (before the client has confirmed):
  - `record_client_info` — the model calls this whenever it learns a
    concrete fact. Fields merge into the session's extracted_profile.
  - `confirm_and_proceed` — the model calls this ONLY after the client
    has explicitly confirmed a recap is accurate. The backend
    double-checks completeness before honouring it (see
    is_profile_complete) — a premature or mistaken call gets a
    "missing_fields" tool_result back instead of silently finalizing
    an incomplete profile.

POST-RESULTS phase (after confirm_and_proceed has succeeded):
  - `recalculate_investment_projection` — "what if I invest more /
    for longer" questions. The model calls this instead of the client
    using a manual duration/amount form; the backend computes the
    numbers and the model explains them conversationally.

Which phase a session is in is a deterministic backend decision (see
main.py: whether chat_sessions.finalized_result is set), not something
the model decides for itself.
"""

from __future__ import annotations

import os

import anthropic

MODEL = "claude-sonnet-5"

# ---------------------------------------------------------------------
# Risk-attitude questions — identical wording/order/scoring to the old
# slider-based form, just asked conversationally now. Preserving these
# verbatim means scoring.py's tolerance_band() needs zero changes.
# ---------------------------------------------------------------------
TOL_QUESTIONS_NOVICE = [
    "I'd be comfortable seeing my investment drop 20% in a bad year, if it meant better growth over the long run.",
    "I'd rather invest in things I understand well than chase something complex with higher potential.",
    "If markets took a sudden downturn, I'd want to move my money to cash right away.",
    "I'm confident I won't need to touch this money for several years.",
    "I'm willing to take on some risk to pursue a good financial opportunity.",
]

TOL_QUESTIONS_EXPERT = [
    "OK with a 20%+ drawdown for better long-run returns?",
    "Prefer simplicity over complexity, even capping upside?",
    "Would a downturn push you to de-risk immediately?",
    "Genuinely long horizon — no near-term liquidity need?",
    "Willing to lean into risk for the right opportunity?",
]

_GOAL_LABELS = {
    "retirement": "retirement",
    "house_deposit": "a house deposit",
    "general_growth": "general growth",
}

# ---------------------------------------------------------------------
# Completeness — deterministic, backend-owned. The model's own sense
# of "I think I'm done" is only ever a suggestion; this is the real
# gate confirm_and_proceed checks before it's allowed to finalize.
# ---------------------------------------------------------------------
REQUIRED_FIELDS = [
    "full_name",
    "age",
    "dependents",
    "gross_monthly_income",
    "monthly_expenses",
    "emergency_fund_months",
    "investment_horizon_years",
    "investment_goal",
    "available_lump_sum",
    "monthly_contribution",
    "knowledge_score",
]


def is_profile_complete(extracted: dict) -> tuple[bool, list[str]]:
    missing = [f for f in REQUIRED_FIELDS if extracted.get(f) in (None, "")]

    tol = extracted.get("tolerance_questionnaire")
    if not (
        isinstance(tol, list)
        and len(tol) == 5
        and all(isinstance(x, (int, float)) and 1 <= x <= 5 for x in tol)
    ):
        missing.append("tolerance_questionnaire (all 5 risk-attitude answers)")

    return (len(missing) == 0, missing)


# ---------------------------------------------------------------------
# INTAKE phase
# ---------------------------------------------------------------------
_INTAKE_SYSTEM_PROMPT_BASE = """You are a financial intake assistant for a bank's investment \
risk-profiling tool. There is no structured form anymore — you are the ONLY way the \
client provides their information, so you need to gather everything below through \
natural conversation, one question at a time, never a wall of questions.

WHAT YOU NEED TO COLLECT (call record_client_info the moment you learn each one):
- full_name
- age
- dependents (number of financial dependents)
- investment_goal — one of: "retirement", "house_deposit", "general_growth". Also ask \
what they're investing towards in their own words and record that separately as `goals`.
- investment_horizon_years — how many years until they'd need the money
- gross_monthly_income
- monthly_expenses
- emergency_fund_months — ask "do you have money set aside for emergencies?" first; if \
no, record 0 immediately and move on, don't ask a follow-up number. If yes, ask how many \
months of expenses it covers — if they answer with a Rand amount instead (e.g. "I have \
R100,000 saved"), record that as emergency_fund_amount and the months figure will be \
calculated automatically for you; do NOT do that division yourself.
- available_lump_sum — ask "do you have a lump sum ready to invest right now?" first; if \
no, record 0 and move on. If yes, ask how much.
- monthly_contribution — ask "would you like to also invest a set amount every month?" \
first; if no, record 0 and move on. If yes, ask how much.
- knowledge_score — 1 (new to investing) to 5 (expert), based on how they describe their \
own experience. Ask this before the risk ratings below, since it changes their phrasing.
- tolerance_questionnaire — exactly 5 integers 1-5. DO NOT ask these questions yourself \
in text. Once you have dependents, goal, horizon, income, expenses, emergency fund, lump \
sum, monthly contribution, AND knowledge_score, call request_risk_ratings — this shows \
the client a rating widget instead of five back-and-forth messages. Just say something \
brief like "Last thing — a quick rating scale below" alongside the tool call. The \
client's ratings come back to you afterwards as a system message; record them with \
record_client_info exactly as given, don't re-ask.

OPTIONAL — only record if the client volunteers it unprompted, never ask directly:
- tax_bracket (most people don't know their marginal rate — it's estimated automatically \
from income; if they do mention a rate like "I'm in the 39% bracket", record it)
- notes — debt, job stability, upcoming large expenses, anything else materially relevant

BANK STATEMENTS: if the client uploads one, use the transaction summary you're given to \
estimate income and expenses, state your estimate back to them in plain terms, and get \
their confirmation before recording it via record_client_info.

CONFIRMATION — this is important: once you believe you have everything required \
(including the risk ratings), call show_profile_summary — this shows the client a \
summary card with everything you've gathered, so DO NOT type out the full recap \
yourself in text; just say something brief like "Here's everything I've got — take a \
look!" alongside the tool call. Do NOT call confirm_and_proceed until the client has \
clearly confirmed the summary is correct (e.g. they said yes / looks good / that's \
right after seeing it). If they correct something, update it with record_client_info \
and call show_profile_summary again before asking a second time. If you call \
confirm_and_proceed too early — before all required fields are collected — the tool \
will tell you exactly what's still missing; just ask for those and try again once you \
have everything and the client has confirmed the summary."""


RISK_WIDGET_TOOL = {
    "name": "request_risk_ratings",
    "description": (
        "Shows the client a rating widget for the 5 risk-attitude questions (1-5 each) "
        "instead of you asking them one at a time in text. Call this once dependents, "
        "goal, horizon, income, expenses, emergency fund, lump sum, monthly "
        "contribution, and knowledge_score are all already known — the widget's "
        "wording depends on knowledge_score. Don't type out the 5 questions yourself."
    ),
    "input_schema": {"type": "object", "properties": {}},
}

SUMMARY_TOOL = {
    "name": "show_profile_summary",
    "description": (
        "Shows the client a formatted summary card of everything gathered so far, for "
        "them to review. Call this once you believe the profile is complete, INSTEAD "
        "OF typing out the full recap in text yourself — just say a brief lead-in "
        "sentence alongside the call. Call it again if the client corrects something, "
        "before asking for confirmation a second time."
    ),
    "input_schema": {"type": "object", "properties": {}},
}


RECORD_TOOL = {
    "name": "record_client_info",
    "description": (
        "Record structured facts just learned about the client. Call this every time "
        "you learn or refine a fact — only include the fields you learned in THIS turn."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "full_name": {"type": "string"},
            "age": {"type": "integer"},
            "dependents": {"type": "integer"},
            "investment_goal": {
                "type": "string",
                "enum": ["retirement", "house_deposit", "general_growth"],
            },
            "goals": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Goals in the client's own words, e.g. ['retirement', 'kids education']",
            },
            "investment_horizon_years": {"type": "number"},
            "gross_monthly_income": {"type": "number", "description": "Rand per month"},
            "monthly_expenses": {"type": "number", "description": "Rand per month"},
            "emergency_fund_months": {
                "type": "number",
                "description": "Months of expenses their emergency fund covers, 0 if none. Only set this directly if the client states months themselves — if they give a Rand amount instead, use emergency_fund_amount and months will be calculated automatically.",
            },
            "emergency_fund_amount": {
                "type": "number",
                "description": "Rand amount they have saved for emergencies, if that's how they answered (e.g. 'I have R100,000 saved') rather than stating months. Months-of-expenses is calculated automatically from this — don't do the division yourself.",
            },
            "available_lump_sum": {
                "type": "number",
                "description": "Lump sum available to invest now, 0 if none",
            },
            "monthly_contribution": {
                "type": "number",
                "description": "Amount they want to invest monthly going forward, 0 if none",
            },
            "knowledge_score": {
                "type": "integer",
                "description": "1 (new to investing) to 5 (expert)",
            },
            "tolerance_questionnaire": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 5,
                "maxItems": 5,
                "description": "Exactly 5 integers 1-5, one per risk-attitude question, in the fixed order given in the system prompt",
            },
            "tax_bracket": {
                "type": "string",
                "description": "Only if the client states it themselves, unprompted, e.g. '39%'",
            },
            "notes": {"type": "string"},
        },
    },
}

CONFIRM_TOOL = {
    "name": "confirm_and_proceed",
    "description": (
        "Call this ONLY after the client has explicitly confirmed that your recap of "
        "their profile is accurate (they said something like 'yes', 'looks good', "
        "'that's correct'). Never call this speculatively or before recapping. If the "
        "profile isn't actually complete yet, this returns exactly what's still missing "
        "so you know what to ask next."
    ),
    "input_schema": {"type": "object", "properties": {}},
}

INTAKE_TOOLS = [RECORD_TOOL, RISK_WIDGET_TOOL, SUMMARY_TOOL, CONFIRM_TOOL]

# Fields considered stable enough to save on the account and reuse across
# profiling sessions, rather than re-asked each time. Deliberately does
# NOT include investment_goal, investment_horizon_years, available_lump_sum,
# monthly_contribution, emergency_fund_months, or tolerance_questionnaire —
# those are specific to each profiling exercise (a client may reasonably
# redo their risk profile for a different goal, amount, or because their
# risk attitude itself has changed), not durable facts about the client.
STABLE_PROFILE_FIELDS = [
    "full_name",
    "age",
    "dependents",
    "gross_monthly_income",
    "monthly_expenses",
    "knowledge_score",
]


def build_risk_widget(extracted: dict) -> dict:
    """Which question wording tier to show, based on the client's own
    self-rated knowledge_score."""
    tier = "expert" if (extracted.get("knowledge_score") or 0) >= 4 else "novice"
    questions = TOL_QUESTIONS_EXPERT if tier == "expert" else TOL_QUESTIONS_NOVICE
    return {"tier": tier, "questions": questions}


def build_profile_summary(extracted: dict) -> dict:
    """A structured snapshot for the frontend's summary card — deliberately
    just passes through what's known rather than composing prose, so the
    card renders real fields instead of parsing the model's markdown."""
    goal = extracted.get("investment_goal")
    return {
        "full_name": extracted.get("full_name"),
        "age": extracted.get("age"),
        "dependents": extracted.get("dependents"),
        "investment_goal": goal,
        "investment_goal_label": _GOAL_LABELS.get(goal, goal),
        "goals": extracted.get("goals", []),
        "investment_horizon_years": extracted.get("investment_horizon_years"),
        "gross_monthly_income": extracted.get("gross_monthly_income"),
        "monthly_expenses": extracted.get("monthly_expenses"),
        "emergency_fund_months": extracted.get("emergency_fund_months"),
        "emergency_fund_amount": extracted.get("emergency_fund_amount"),
        "available_lump_sum": extracted.get("available_lump_sum"),
        "monthly_contribution": extracted.get("monthly_contribution"),
        "knowledge_score": extracted.get("knowledge_score"),
        "tolerance_questionnaire": extracted.get("tolerance_questionnaire"),
        "tax_bracket": extracted.get("tax_bracket"),
        "notes": extracted.get("notes"),
    }


def _describe_stable_fields(known_context: dict) -> list[str]:
    """Natural-language fragments for whichever stable fields are known —
    used to build the personalized recap in the opening message."""
    parts = []
    if "age" in known_context:
        parts.append(f"{known_context['age']} years old")
    if "dependents" in known_context:
        n = known_context["dependents"]
        parts.append(f"{n} dependent{'s' if n != 1 else ''}")
    if "gross_monthly_income" in known_context:
        parts.append(f"income of about R{known_context['gross_monthly_income']:,.0f}/month")
    if "monthly_expenses" in known_context:
        parts.append(f"expenses of about R{known_context['monthly_expenses']:,.0f}/month")
    if "knowledge_score" in known_context:
        parts.append(f"investing experience rated {known_context['knowledge_score']}/5")
    return parts


def build_opening_message(known_context: dict | None = None) -> str:
    known_context = known_context or {}
    full_name = known_context.get("full_name")

    if not full_name:
        return (
            "Hi! I'm here to help figure out the right investment risk profile for you — "
            "it's just a conversation, no forms. Let's start simple: what's your name?"
        )

    other_fields = _describe_stable_fields(known_context)
    if not other_fields:
        # Signed up with a name but no prior finalized profile yet — skip
        # asking for the name only, everything else is still fresh.
        return (
            f"Hi {full_name}! I'm here to help figure out the right investment risk "
            "profile for you — it's just a conversation, no forms. Let's start with "
            "your age — how old are you?"
        )

    recap = ", ".join(other_fields)
    return (
        f"Welcome back, {full_name}! Last time you told us you're {recap}. "
        "Does that all still look right, or has anything changed?"
    )


def build_intake_system_prompt(known_context: dict | None = None) -> str:
    known_context = known_context or {}
    saved = {k: known_context[k] for k in STABLE_PROFILE_FIELDS if k in known_context}
    if not saved:
        return _INTAKE_SYSTEM_PROMPT_BASE

    known_lines = "\n".join(f"- {k}: {v}" for k, v in saved.items())
    prefix = (
        "IMPORTANT — this client has an account with details saved from a previous "
        "profile, already pre-filled and shown to them in your opening message:\n"
        f"{known_lines}\n\n"
        "Do NOT ask for these again. Your opening message already asked them to "
        "confirm these are still accurate. If their reply confirms everything (e.g. "
        "'yes', 'still correct', 'looks right', 'all good'), move straight on to "
        "what's not yet known — do not repeat the confirmation question. If they say "
        "something has changed, update just that field with record_client_info and "
        "confirm the rest is still accurate before moving on.\n\n"
    )
    return prefix + _INTAKE_SYSTEM_PROMPT_BASE


# ---------------------------------------------------------------------
# POST-RESULTS phase
# ---------------------------------------------------------------------
RECALCULATE_TOOL = {
    "name": "recalculate_investment_projection",
    "description": (
        "Recalculate the projected investment value for the client's matched products "
        "under a different lump sum, monthly contribution, or horizon than originally "
        "used. Call this whenever the client asks a 'what if' question about investing "
        "a different amount or for a different length of time — this replaces any "
        "manual calculator, so always use this tool rather than estimating the answer "
        "yourself."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "initial_amount": {
                "type": "number",
                "description": "Lump sum to project with — use the client's original amount if they aren't changing it",
            },
            "monthly_amount": {
                "type": "number",
                "description": "Monthly contribution to project with — use the original if unchanged",
            },
            "horizon_years": {
                "type": "number",
                "description": "Investment horizon in years to project over — use the original if unchanged",
            },
            "product_name": {
                "type": "string",
                "description": "Which matched product to recalculate for, by name (partial match ok). Omit to recalculate for every matched product.",
            },
        },
        "required": ["initial_amount", "monthly_amount", "horizon_years"],
    },
}

CHECK_SURPLUS_TOOL = {
    "name": "check_monthly_surplus",
    "description": (
        "Checks whether the client has meaningful spare cash this month, based on "
        "their known income, expenses, and already-committed monthly investment — "
        "computed deterministically, don't estimate this yourself. Call this when "
        "the client asks you to check their balance, simulate month-end, or see if "
        "they have room to invest more right now."
    ),
    "input_schema": {"type": "object", "properties": {}},
}

POST_RESULTS_TOOLS = [RECALCULATE_TOOL, CHECK_SURPLUS_TOOL]


def build_post_results_system_prompt(finalized_result: dict) -> str:
    lines = []
    for pf in finalized_result.get("matched_portfolios", []):
        for prod in pf.get("matched_products", []):
            lines.append(
                f"- {prod['name']} (under {pf['name']}, {prod['tax_wrapper']} wrapper, "
                f"{prod['total_fee_pct']}% fee)"
            )
    products_block = "\n".join(lines) if lines else "(no matched products)"

    return f"""You are a friendly financial assistant helping a client understand the \
investment risk matrix they've just been shown. Their matched portfolios/products are:

{products_block}

The client can ask "what if" questions about investing a different amount or for a \
different duration — when they do, call recalculate_investment_projection (don't \
estimate the numbers yourself, always use the tool) and then explain the result in \
plain, encouraging language. Keep replies short — two or three sentences plus the key \
numbers. You can also answer general questions about the products, fees, or their risk \
band using the information above. If asked to change something fundamental about their \
profile (income, goal, age, etc.), explain that they'd need to go back and edit their \
details rather than changing it here.

CHECKING FOR SPARE CASH: if the client asks you to check their balance, simulate \
month-end, or see if they have room to invest more, call check_monthly_surplus — this \
is computed deterministically from their actual income, expenses, and committed \
monthly investment, never estimate it yourself. If it finds a meaningful surplus, \
explain it warmly and suggest putting it to work — mention their top pick or a \
no-lock-in product if one exists among their matches, and note they can ask what that \
extra amount would grow into. If there's nothing meaningful this time, say so plainly \
rather than manufacturing urgency where there isn't any."""


# ---------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------
def merge_extracted(extracted: dict, new_fields: dict) -> dict:
    """Merge only the fields present in new_fields; list-valued fields
    (goals) are unioned rather than overwritten.

    Deterministic derivation: if the client gives a Rand amount for
    their emergency fund rather than stating months directly, months
    is computed here from amount / monthly_expenses — we don't trust
    the model to do this division itself. Whenever both figures are
    known, the computed value always wins over anything the model may
    have separately guessed for emergency_fund_months."""
    merged = dict(extracted)
    for key, value in new_fields.items():
        if value in (None, "", []):
            continue
        if key == "goals" and isinstance(value, list):
            existing = set(merged.get("goals", []))
            merged["goals"] = sorted(existing | set(value))
        else:
            merged[key] = value

    if merged.get("emergency_fund_amount") and merged.get("monthly_expenses"):
        months = merged["emergency_fund_amount"] / merged["monthly_expenses"]
        merged["emergency_fund_months"] = round(months, 1)

    return merged


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Set it in the backend environment "
            "before using the chat endpoints."
        )
    return anthropic.Anthropic(api_key=api_key)


def run_turn(
    history: list[dict],
    user_content: str | list[dict],
    system_prompt: str,
    tools: list[dict],
    tool_executor,
    client: anthropic.Anthropic | None = None,
) -> tuple[str, list[dict]]:
    """Run one conversational turn with an arbitrary tool set.

    `tool_executor(tool_name: str, tool_input: dict) -> dict` is called
    for every tool_use block; its return value is JSON-serialized as
    the tool_result content. Side effects (merging extracted fields,
    finalizing a profile, computing projections) belong in the
    executor the caller supplies — this function only drives the loop.

    Returns (assistant_reply_text, updated_history).
    """
    import json as _json

    client = client or _get_client()
    messages = list(history)
    messages.append({"role": "user", "content": user_content})

    for _ in range(6):  # hard cap so a stuck loop can't run forever
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )
        assistant_blocks = [block.model_dump() for block in response.content]
        messages.append({"role": "assistant", "content": assistant_blocks})

        tool_uses = [b for b in assistant_blocks if b["type"] == "tool_use"]
        if not tool_uses:
            reply_text = "".join(
                b["text"] for b in assistant_blocks if b["type"] == "text"
            )
            return reply_text, messages

        tool_results = []
        for tu in tool_uses:
            result = tool_executor(tu["name"], tu["input"])
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": _json.dumps(result),
                }
            )
        messages.append({"role": "user", "content": tool_results})

    return "Let's continue — could you tell me more about that?", messages
