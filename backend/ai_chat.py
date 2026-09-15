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
    "I'm comfortable with a 20%+ drawdown for better long-run returns.",
    "I prefer simplicity over complexity, even if it caps some upside.",
    "A downturn would push me to de-risk immediately.",
    "My horizon is genuinely long — no near-term liquidity need.",
    "I'm willing to lean into risk for the right opportunity.",
]

_GOAL_LABELS = {
    "retirement": "retirement",
    "house_deposit": "a house deposit",
    "general_growth": "general growth",
}

# ---------------------------------------------------------------------
# Language support — the AI's own replies are made multilingual by
# simply instructing it to converse in the chosen language (Claude is
# genuinely fluent in all of these; there's no translation-string
# system for dynamic AI output, it just speaks the language natively).
# What DOES need real translated strings are the fixed pieces the
# backend composes itself, deterministically, outside any model call:
# the risk questionnaire text and the opening greeting templates.
#
# Confidence note: Portuguese and Swahili translations below are
# reasonably solid. isiZulu and Igbo are a genuine best-effort first
# draft, not verified by a native/professional speaker — given this is
# financial content where precision matters, get these reviewed before
# any real client-facing use.
# ---------------------------------------------------------------------
LANGUAGE_NAMES = {
    "en": "English",
    "zu": "isiZulu",
    "sw": "Swahili",
    "ig": "Igbo",
    "pt": "Portuguese",
}


def _language_directive(language: str) -> str:
    """Appended to a system prompt to make the model's own replies
    multilingual — no per-string translation table needed for this
    part, Claude just converses in the requested language directly."""
    if language == "en" or language not in LANGUAGE_NAMES:
        return ""
    name = LANGUAGE_NAMES[language]
    return (
        f"\n\nLANGUAGE: conduct this entire conversation in {name}. Every reply you write "
        f"to the client — greetings, questions, explanations, everything — must be in "
        f"{name}. Tool calls themselves (field names, and structured values like numbers "
        f"or the fixed goal codes) stay exactly as specified in their schema regardless of "
        f"language; only the natural-language text you write to the client needs to be in "
        f"{name}."
    )


# Non-English languages use one consistent, clear wording rather than
# the separate novice/expert tiers English has — that tiering was a
# phrasing nicety, not core functionality, and doubling five
# translation sets for a wording variant wasn't worth the trade-off.
TOL_QUESTIONS_TRANSLATED = {
    "pt": [
        "Eu me sentiria confortável vendo meu investimento cair 20% num ano ruim, se isso significasse um crescimento melhor no longo prazo.",
        "Prefiro investir em coisas que entendo bem do que buscar algo complexo com maior potencial.",
        "Se os mercados sofressem uma queda repentina, eu iria querer mover meu dinheiro para o caixa imediatamente.",
        "Tenho confiança de que não vou precisar mexer neste dinheiro por vários anos.",
        "Estou disposto(a) a assumir algum risco para aproveitar uma boa oportunidade financeira.",
    ],
    "sw": [
        "Ningekuwa vizuri kuona uwekezaji wangu ukishuka kwa asilimia 20 katika mwaka mbaya, ikiwa hilo lingemaanisha ukuaji bora kwa muda mrefu.",
        "Ningependelea kuwekeza katika vitu ninavyovielewa vizuri kuliko kufuatilia kitu chenye utata na uwezo mkubwa zaidi.",
        "Kama masoko yangeporomoka ghafla, ningetaka kuhamisha pesa zangu kwenye fedha taslimu mara moja.",
        "Nina uhakika sitohitaji kutumia pesa hizi kwa miaka kadhaa.",
        "Niko tayari kuchukua hatari fulani ili kufuatilia fursa nzuri ya kifedha.",
    ],
    "zu": [
        "Ngingakhululeka ukubona ukutshalwa kwemali kwami kwehla ngo-20% onyakeni omubi, uma lokho kusho ukukhula okungcono esikhathini eside.",
        "Ngingathanda ukutshala emalini ezintweni engizizwa kahle kunokulandela into eyinkimbinkimbi enamathuba amakhulu.",
        "Uma izimakethe zehla ngokuzumayo, ngingathanda ukususa imali yami ngiyifake emalini ekhona ngokushesha.",
        "Nginesiqiniseko sokuthi angisoze ngayidinga le mali eminyakeni embalwa ezayo.",
        "Ngizimisele ukuthatha ubungozi obuthile ukuze ngithole ithuba elihle lezimali.",
    ],
    "ig": [
        "Aga m enwe obi udo ị̥hụ ka ego m tinyere na-adaba 20% n'afọ ọjọọ, ma ọ bụrụ na nke ahụ pụtara uto ka mma n'ogologo oge.",
        "Ọ ga-akara m mma itinye ego n'ihe m ghọtara nke ọma karịa ịchụso ihe mgbagwoju anya nwere ohere ka ukwuu.",
        "Ọ bụrụ na ahịa dara na mberede, m ga-achọ ibugharị ego m gaa n'ego nkịtị ozugbo.",
        "Enwere m ntụkwasị obi na agaghị m achọ ego a ruo ọtụtụ afọ.",
        "Adị m njịke re iwere ihe ize ndụ ụfọdụ iji chụso ohere ezigbo ego.",
    ],
}

OPENING_MESSAGES = {
    "en": {
        "new": "Hi! I'm here to help figure out the right investment risk profile for you — it's just a conversation, no forms. Let's start simple: what's your name?",
        "name_only": "Hi {name}! I'm here to help figure out the right investment risk profile for you — it's just a conversation, no forms. Let's start with your age — how old are you?",
        "returning": "Welcome back, {name}! Last time you told us you're {recap}. Does that all still look right, or has anything changed?",
    },
    "pt": {
        "new": "Olá! Estou aqui para ajudar a descobrir o perfil de risco de investimento certo para você — é só uma conversa, sem formulários. Vamos começar de forma simples: qual é o seu nome?",
        "name_only": "Olá {name}! Estou aqui para ajudar a descobrir o perfil de risco de investimento certo para você — é só uma conversa, sem formulários. Vamos começar pela sua idade — quantos anos você tem?",
        "returning": "Bem-vindo(a) de volta, {name}! Da última vez você nos disse que {recap}. Ainda está tudo certo, ou algo mudou?",
    },
    "sw": {
        "new": "Habari! Niko hapa kukusaidia kupata wasifu sahihi wa hatari ya uwekezaji kwako — ni mazungumzo tu, hakuna fomu. Tuanze kwa urahisi: jina lako ni nani?",
        "name_only": "Habari {name}! Niko hapa kukusaidia kupata wasifu sahihi wa hatari ya uwekezaji kwako — ni mazungumzo tu, hakuna fomu. Tuanze na umri wako — una miaka mingapi?",
        "returning": "Karibu tena, {name}! Mara ya mwisho ulituambia kuwa {recap}. Je, hayo bado ni sahihi, au kuna kilichobadilika?",
    },
    "zu": {
        "new": "Sawubona! Ngilapha ukukusiza uthole iphrofayili yobungozi bokutshalwa kwemali efanele kuwe — kuwukuxoxa nje, akukho amafomu. Ake siqale ngokulula: ubani igama lakho?",
        "name_only": "Sawubona {name}! Ngilapha ukukusiza uthole iphrofayili yobungozi bokutshalwa kwemali efanele kuwe — kuwukuxoxa nje, akukho amafomu. Ake siqale ngeminyaka yakho — uneminyaka emingaki?",
        "returning": "Siyakwamukela futhi, {name}! Ngesikhathi sokugcina wasitshela ukuthi {recap}. Konke lokho kusesekhona, noma kukhona okushintshile?",
    },
    "ig": {
        "new": "Ndewo! Anọ m ebe a inyere gị aka ịchọpụta profaịlụ ihe ize ndụ itinye ego kwesịrị ekwesị maka gị — ọ bụ naanị mkparịta ụka, ọ nweghị fọm. Ka anyị malite nke dị mfe: gịnị bụ aha gị?",
        "name_only": "Ndewo {name}! Anọ m ebe a inyere gị aka ịchọpụta profaịlụ ihe ize ndụ itinye ego kwesịrị ekwesị maka gị — ọ bụ naanị mkparịta ụka, ọ nweghị fọm. Ka anyị malite site na afọ gị — afọ ole ka ị dị?",
        "returning": "Nnọọ ọzọ, {name}! Oge ikpeazụ ị gwara anyị na {recap}. Ihe niile ka dị mma, ka e nwere ihe gbanwere?",
    },
}

# Per-language phrasing for the recap fragments ({age} years old, etc.)
# — kept deliberately simple (no attempt at grammatical number
# agreement across languages with very different pluralization rules)
# so the composed sentence still reads naturally regardless of count.
RECAP_FRAGMENTS = {
    "en": {
        "age": "{age} years old",
        "dependents": "{n} dependents",
        "income": "income of about R{income}/month",
        "expenses": "expenses of about R{expenses}/month",
        "knowledge": "investing experience rated {score}/5",
    },
    "pt": {
        "age": "{age} anos de idade",
        "dependents": "{n} dependentes",
        "income": "renda de cerca de R{income}/mês",
        "expenses": "despesas de cerca de R{expenses}/mês",
        "knowledge": "experiência em investimentos avaliada em {score}/5",
    },
    "sw": {
        "age": "umri wa miaka {age}",
        "dependents": "wategemezi {n}",
        "income": "kipato cha karibu R{income}/mwezi",
        "expenses": "matumizi ya karibu R{expenses}/mwezi",
        "knowledge": "uzoefu wa uwekezaji uliokadiriwa {score}/5",
    },
    "zu": {
        "age": "iminyaka {age}",
        "dependents": "abancike kuwe abangu-{n}",
        "income": "imali engenayo engu-R{income}/ngenyanga",
        "expenses": "izindleko ezingu-R{expenses}/ngenyanga",
        "knowledge": "ulwazi lokutshala imali olulinganiselwa ku-{score}/5",
    },
    "ig": {
        "age": "afọ {age}",
        "dependents": "ndị dabere na gị {n}",
        "income": "ego ọnụego dị ka R{income}/ọnwa",
        "expenses": "mmefu ihe dị ka R{expenses}/ọnwa",
        "knowledge": "ahụmahụ itinye ego akalarị {score}/5",
    },
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


def compute_intake_progress(extracted: dict) -> tuple[int, int]:
    """(completed, total) for a progress bar — the risk-attitude
    questionnaire counts as one combined item (matching how
    is_profile_complete treats it as a single unit), not 5 separate
    ones, so progress moves in intuitive, evenly-sized steps."""
    total = len(REQUIRED_FIELDS) + 1
    completed = sum(1 for f in REQUIRED_FIELDS if extracted.get(f) not in (None, ""))

    tol = extracted.get("tolerance_questionnaire")
    if (
        isinstance(tol, list)
        and len(tol) == 5
        and all(isinstance(x, (int, float)) and 1 <= x <= 5 for x in tol)
    ):
        completed += 1

    return completed, total


# ---------------------------------------------------------------------
# INTAKE phase
# ---------------------------------------------------------------------
_INTAKE_SYSTEM_PROMPT_BASE = """You are a financial intake assistant for a bank's investment \
risk-profiling tool. There is no structured form anymore — you are the ONLY way the \
client provides their information, so you need to gather everything below through \
natural conversation, one question at a time, never a wall of questions.

FORMATTING: write in plain text only. No markdown — no **bold**, no bullet points with \
- or *, no headers, no numbered lists. This is a plain chat bubble that displays your \
text exactly as written, so any formatting symbols would show up literally to the \
client (they'd see the actual asterisks, not bold text).

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
first; if no, record 0 and move on. If yes, ask how much. If the client asks what YOU'D \
recommend instead of naming a figure, call recommend_monthly_contribution — this \
computes their real disposable income (after tax, minus expenses) deterministically; \
do not do this math yourself, and do not just subtract expenses from gross income \
(that overstates what they actually have available, since it ignores tax).
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
                "description": "Amount they want to invest monthly going forward, 0 if none. If the client asks what you'd recommend instead of naming a figure themselves, call recommend_monthly_contribution first to get an accurate number to suggest — don't estimate or compute this yourself.",
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

RECOMMEND_CONTRIBUTION_TOOL = {
    "name": "recommend_monthly_contribution",
    "description": (
        "Call this when the client asks what you'd recommend for a monthly "
        "contribution instead of naming an amount themselves. Computes their actual "
        "disposable income deterministically — net (after-tax) income minus expenses, "
        "not gross income minus expenses, since gross overstates what they actually "
        "have available. Never estimate or calculate this yourself; always use this "
        "tool. Requires gross_monthly_income and monthly_expenses to already be known."
    ),
    "input_schema": {"type": "object", "properties": {}},
}

INTAKE_TOOLS = [RECORD_TOOL, RISK_WIDGET_TOOL, SUMMARY_TOOL, CONFIRM_TOOL, RECOMMEND_CONTRIBUTION_TOOL]

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


def build_risk_widget(extracted: dict, language: str = "en") -> dict:
    """Which question wording tier to show, based on the client's own
    self-rated knowledge_score — for English only; non-English
    languages use one consistent translated wording regardless of
    knowledge_score (see TOL_QUESTIONS_TRANSLATED's docstring note)."""
    if language != "en" and language in TOL_QUESTIONS_TRANSLATED:
        return {"tier": "novice", "questions": TOL_QUESTIONS_TRANSLATED[language]}
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


def _describe_stable_fields(known_context: dict, language: str = "en") -> list[str]:
    """Natural-language fragments for whichever stable fields are known —
    used to build the personalized recap in the opening message."""
    frag = RECAP_FRAGMENTS.get(language, RECAP_FRAGMENTS["en"])
    parts = []
    if "age" in known_context:
        parts.append(frag["age"].format(age=known_context["age"]))
    if "dependents" in known_context:
        parts.append(frag["dependents"].format(n=known_context["dependents"]))
    if "gross_monthly_income" in known_context:
        parts.append(frag["income"].format(income=f"{known_context['gross_monthly_income']:,.0f}"))
    if "monthly_expenses" in known_context:
        parts.append(frag["expenses"].format(expenses=f"{known_context['monthly_expenses']:,.0f}"))
    if "knowledge_score" in known_context:
        parts.append(frag["knowledge"].format(score=known_context["knowledge_score"]))
    return parts


def build_opening_message(known_context: dict | None = None, language: str = "en") -> str:
    known_context = known_context or {}
    full_name = known_context.get("full_name")
    templates = OPENING_MESSAGES.get(language, OPENING_MESSAGES["en"])

    if not full_name:
        return templates["new"]

    other_fields = _describe_stable_fields(known_context, language)
    if not other_fields:
        # Signed up with a name but no prior finalized profile yet — skip
        # asking for the name only, everything else is still fresh.
        return templates["name_only"].format(name=full_name)

    recap = ", ".join(other_fields)
    return templates["returning"].format(name=full_name, recap=recap)


def build_intake_system_prompt(known_context: dict | None = None, language: str = "en") -> str:
    known_context = known_context or {}
    saved = {k: known_context[k] for k in STABLE_PROFILE_FIELDS if k in known_context}
    prompt = _INTAKE_SYSTEM_PROMPT_BASE
    if saved:
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
        prompt = prefix + prompt
    return prompt + _language_directive(language)


# ---------------------------------------------------------------------
# POST-RESULTS phase
# ---------------------------------------------------------------------
RECALCULATE_TOOL = {
    "name": "recalculate_investment_projection",
    "description": (
        "Re-runs the full product match for a hypothetical lump sum, monthly contribution, "
        "horizon, or even a completely different investment goal — NOT just recomputed "
        "numbers on the same products. A different amount can make a product newly eligible "
        "(e.g. a bigger lump sum clearing a minimum) or drop one that no longer qualifies; a "
        "different goal opens up a different set of tax wrappers entirely. Call this whenever "
        "the client asks a 'what if' question about investing a different amount, for a "
        "different length of time, OR about a fundamentally different kind of product/goal "
        "than their actual profile (e.g. their profile is for retirement but they ask about a "
        "house deposit product) — never estimate this yourself. This is a PREVIEW ONLY: "
        "nothing is saved to their actual profile unless they explicitly ask you to update it, "
        "so say so plainly if they seem to think it already saved."
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
            "investment_goal": {
                "type": "string",
                "enum": ["retirement", "house_deposit", "general_growth"],
                "description": "Only include this if the client is asking about a DIFFERENT goal than their actual profile (e.g. asking about a house deposit product when their profile is for retirement). Omit entirely to keep their actual goal.",
            },
        },
        "required": ["initial_amount", "monthly_amount", "horizon_years"],
    },
}

CHECK_SURPLUS_TOOL = {
    "name": "check_monthly_surplus",
    "description": (
        "Checks whether the client has meaningful spare cash right now, based on the NET "
        "of their everyday (debit) account balance and their credit card balance — what they "
        "actually have available after what they owe, computed deterministically, don't "
        "estimate this yourself. Call this when the client asks you to check their balance, "
        "simulate month-end, or see if they have room to invest more right now."
    ),
    "input_schema": {"type": "object", "properties": {}},
}

POST_RESULTS_TOOLS = [RECALCULATE_TOOL, CHECK_SURPLUS_TOOL]


def build_post_results_system_prompt(finalized_result: dict, product_blurbs: list[str] | None = None, language: str = "en") -> str:
    lines = []
    for prod in finalized_result.get("matched_products", []):
        portfolio_bits = ", ".join(
            f"{rp['portfolio_name']} ({rp['allocation_pct']}%)" for rp in prod.get("recommended_portfolios", [])
        )
        lines.append(
            f"- {prod['name']} ({prod['tax_wrapper']} wrapper, {prod['total_fee_pct']}% effective fee) — "
            f"recommended split: {portfolio_bits or '(none)'}"
        )
    products_block = "\n".join(lines) if lines else "(no matched products)"

    details_block = ""
    if product_blurbs:
        details_block = (
            "\n\nMORE DETAIL on these products, from their actual product specifications — use this "
            "to answer specific questions accurately (fees, features, eligibility, etc.) rather than "
            "guessing or relying on general knowledge about similar products:\n\n"
            + "\n\n".join(product_blurbs)
        )

    return f"""You are a friendly financial assistant helping a client understand the \
investment risk matrix they've just been shown. Each matched PRODUCT comes with its own \
recommended SPLIT across one or more portfolios (a client holds several portfolios inside \
one product, not one portfolio per product):

{products_block}
{details_block}

FORMATTING: write in plain text only. No markdown — no **bold**, no bullet points with \
- or *, no headers. This is a plain chat bubble that displays your text exactly as \
written, so formatting symbols would show up literally to the client.

The client can ask "what if" questions about investing a different amount or for a \
different duration — when they do, call recalculate_investment_projection (don't \
estimate the numbers yourself, always use the tool). This is a genuine re-match: the \
SET of recommended products can change (a bigger lump sum might newly qualify for a \
product it didn't before, or a smaller one might drop below a minimum) — don't assume \
the same products are still the right ones. Point out clearly when something changed \
(a product became newly available, or dropped off). This is a PREVIEW ONLY — nothing \
is saved unless the client explicitly asks you to update their actual profile, so make \
that clear rather than implying it's already been changed. Keep replies short — a few \
sentences plus the key numbers. You can also answer general questions about the \
products, portfolio splits, fees, or their risk band using the information above. If \
asked to change something fundamental about their profile (income, goal, age, etc.), \
explain that they'd need to go back and edit their details rather than changing it here.

CHECKING FOR SPARE CASH: if the client asks you to check their balance, simulate \
month-end, or see if they have room to invest more, call check_monthly_surplus — this \
is the NET of their everyday account and credit card balances (what they actually have \
available after what they owe), computed deterministically from their linked accounts, \
never estimate it yourself. If it finds a meaningful surplus, explain it warmly and \
suggest putting it to work — mention their top pick or a no-lock-in product if one \
exists among their matches, and note they can ask what that extra amount would grow \
into. If there's nothing meaningful this time, say so plainly rather than manufacturing \
urgency where there isn't any.{_language_directive(language)}"""


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
