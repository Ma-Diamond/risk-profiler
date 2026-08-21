"""AI-driven conversational intake.

The assistant's job is narrow: have a natural conversation that fills
in the gaps a structured form can't easily capture — goals in the
client's own words, dependents detail, income/expenses — and,
whenever it learns something concrete, call `record_client_info` to
persist it. The visible chat reply and the structured extraction are
two separate outputs of the same turn, produced via Anthropic's
standard tool-use loop: the model calls the tool, we execute it
(here, "executing" just means merging fields into the session's
extracted-profile dict), send the result back, and the model then
produces its next visible message.

This keeps extraction auditable: every field in `extracted_profile`
was explicitly recorded by a named tool call, not silently inferred
by parsing free text after the fact.
"""

from __future__ import annotations

import os

import anthropic

MODEL = "claude-sonnet-5"

BASE_INSTRUCTIONS = """You are a financial intake assistant for a bank's investment \
risk-profiling tool. The client has already completed a short structured \
questionnaire — you are told exactly what it captured below. Do NOT ask about \
anything already listed there; treat it as known and move straight past it. \
Your job is to fill in what that form can't easily capture:

- their investment goal(s) in their own words (the form may only have a \
category like "retirement" — get the actual story)
- confirm/refine number of dependents and their financial responsibility for them
- gross monthly income and monthly expenses, ONLY if these are not already \
listed as known below — if they are known, do not ask about them again unless \
the client brings them up themselves
- anything else materially relevant to suitability (debt, upcoming large \
expenses, job stability)

Do NOT ask the client what tax bracket they're in — most people don't know \
this off-hand, and it's estimated automatically from their income instead. \
Only record a tax_bracket if the client volunteers it unprompted (e.g. "I'm \
in the 45% bracket").

Ask ONE question at a time, in plain conversational language — never a wall of \
questions, and never a question about something already known. Whenever the \
client gives you a concrete fact, call record_client_info immediately with \
just the fields you learned (don't re-send fields you haven't just learned, \
and don't re-send fields already listed as known below unless the client \
corrected them). Keep replies short — two or three sentences. If the client \
uploads a bank statement, use the transaction summary you're given to \
estimate income and expenses, state your estimate back to them in plain \
terms, and ask them to confirm or correct it before recording it.

When you believe you have goals detail, dependents, income, and expenses \
(whether from the known context below or from this conversation), tell the \
client they're done and can move on to their results — do not keep asking \
more questions after that point."""

_GOAL_LABELS = {
    "retirement": "retirement",
    "house_deposit": "a house deposit",
    "general_growth": "general growth",
}

_KNOWN_CONTEXT_LABELS = [
    ("investment_goal", "goal category", lambda v: _GOAL_LABELS.get(v, v)),
    ("age", "age", str),
    ("dependents", "dependents", str),
    ("gross_monthly_income", "gross monthly income", lambda v: f"R{v:,.0f}"),
    ("monthly_expenses", "monthly expenses", lambda v: f"R{v:,.0f}"),
    ("investment_horizon_years", "investment horizon", lambda v: f"{v} years"),
    ("emergency_fund_months", "emergency fund", lambda v: f"{v} months of expenses"),
]


def build_system_prompt(known_context: dict) -> str:
    """Fold the quick-form answers into the system prompt as an explicit
    'already known, do not re-ask' list."""
    if not known_context:
        return BASE_INSTRUCTIONS + "\n\nThe client has not filled in any structured form yet — ask everything."

    lines = []
    for key, label, fmt in _KNOWN_CONTEXT_LABELS:
        if known_context.get(key) not in (None, "", 0) or (
            key in ("dependents", "age") and known_context.get(key) == 0
        ):
            value = known_context.get(key)
            if value in (None, ""):
                continue
            lines.append(f"- {label}: {fmt(value)}")

    known_block = "\n".join(lines) if lines else "(nothing usable was filled in)"
    return (
        BASE_INSTRUCTIONS
        + "\n\nAlready known from the structured form (do not ask about these again):\n"
        + known_block
    )


def build_opening_message(known_context: dict) -> str:
    """A deterministic, no-API-call opening line personalized to what's
    already known, so the very first turn never repeats the form."""
    name = known_context.get("full_name", "").split(" ")[0] if known_context.get("full_name") else ""
    greeting = f"Hi {name}!" if name else "Hi!"

    goal = known_context.get("investment_goal")
    dependents = known_context.get("dependents")

    if goal:
        goal_label = _GOAL_LABELS.get(goal, goal)
        goal_line = f"I can see you're investing towards {goal_label}."
    else:
        goal_line = "What are you investing towards — retirement, a house deposit, or general growth?"

    if dependents is not None and dependents > 0:
        ask_line = (
            f"You mentioned {dependents} dependent{'s' if dependents != 1 else ''} — "
            "could you tell me a bit more about your goal in your own words?"
        )
    else:
        ask_line = "Could you tell me a bit more about that goal in your own words?"

    return f"{greeting} {goal_line} {ask_line}"


RECORD_TOOL = {
    "name": "record_client_info",
    "description": (
        "Record structured facts just learned about the client's financial "
        "situation. Call this every time you learn or refine a fact — only "
        "include the fields you learned in THIS turn, omit anything unchanged."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "goals": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Investment goals in the client's own words, e.g. ['retirement', 'kids education']",
            },
            "dependents": {
                "type": "integer",
                "description": "Number of financial dependents",
            },
            "gross_monthly_income": {
                "type": "number",
                "description": "Gross monthly income in Rand",
            },
            "monthly_expenses": {
                "type": "number",
                "description": "Total monthly expenses in Rand",
            },
            "tax_bracket": {
                "type": "string",
                "description": (
                    "Approximate marginal tax bracket, e.g. '18%', '31%', '39%', '45%'. "
                    "Only include this if the client states it themselves, unprompted — "
                    "never ask for it."
                ),
            },
            "notes": {
                "type": "string",
                "description": "Any other materially relevant detail (debt, job stability, upcoming expenses)",
            },
        },
    },
}


def _get_client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Set it in the backend environment "
            "before using the chat endpoints."
        )
    return anthropic.Anthropic()


def _merge_extracted(extracted: dict, new_fields: dict) -> dict:
    """Merge only the fields present in new_fields, list-valued fields
    (goals) are unioned rather than overwritten."""
    merged = dict(extracted)
    for key, value in new_fields.items():
        if value in (None, "", []):
            continue
        if key == "goals" and isinstance(value, list):
            existing = set(merged.get("goals", []))
            merged["goals"] = sorted(existing | set(value))
        else:
            merged[key] = value
    return merged


def run_turn(
    history: list[dict],
    user_content: str | list[dict],
    extracted: dict,
    system_prompt: str,
    client: anthropic.Anthropic | None = None,
) -> tuple[str, dict, list[dict]]:
    """Run one conversational turn.

    `user_content` is either a plain string (a normal chat message) or a
    list of Anthropic content blocks (used for the statement-upload
    turn, where we inject the extracted PDF text as an extra text
    block alongside the client's message).

    `system_prompt` should come from build_system_prompt(known_context)
    so the model knows what the quick form already collected.

    Returns (assistant_reply_text, updated_extracted_profile, updated_history).
    """
    client = client or _get_client()
    messages = list(history)
    messages.append({"role": "user", "content": user_content})

    # Standard tool-use loop: keep calling the model, executing any
    # tool_use blocks, and feeding results back, until it produces a
    # turn with no further tool calls (its visible reply).
    for _ in range(5):  # hard cap so a stuck loop can't run forever
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system_prompt,
            tools=[RECORD_TOOL],
            messages=messages,
        )
        assistant_blocks = [block.model_dump() for block in response.content]
        messages.append({"role": "assistant", "content": assistant_blocks})

        tool_uses = [b for b in assistant_blocks if b["type"] == "tool_use"]
        if not tool_uses:
            reply_text = "".join(
                b["text"] for b in assistant_blocks if b["type"] == "text"
            )
            return reply_text, extracted, messages

        tool_results = []
        for tu in tool_uses:
            if tu["name"] == "record_client_info":
                extracted = _merge_extracted(extracted, tu["input"])
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": "recorded",
                }
            )
        messages.append({"role": "user", "content": tool_results})

    # Fell through the loop cap — return whatever text we can salvage.
    return "Let's continue — could you tell me more about that?", extracted, messages
