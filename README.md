# Risk Profiler — worked example

A deterministic, band-based risk profiling backend (FastAPI + SQLite)
with an AI-assisted conversational intake, and a banking-app-styled
React frontend.

## Flow

1. **Quick questions** (`QuickQuestions.jsx`) — a short structured form:
   age, dependents, income/expenses, horizon, goal, a 5-question risk
   attitude questionnaire, investable amounts. Fast and deterministic —
   the record that suitability decisions can be traced back to.
2. **AI conversation** (`ChatPanel.jsx`) — a chat, backed by the
   Anthropic API, that fills in what the form can't easily capture:
   goals in the client's own words, dependents detail, tax bracket,
   and income/expenses if not already known. The quick-form answers
   are sent as `known_context` when the session starts — the opening
   message and every subsequent turn's system prompt are built to
   explicitly list what's already known, so the model doesn't re-ask
   for a client's income or dependents just because it's having a
   conversation. The client can also upload a bank statement PDF; its
   extracted text is handed to the model, which estimates
   income/expenses and asks the client to confirm before recording
   anything.
3. **Confirm & edit** (`ConfirmModal.jsx`) — after the client says
   they're done chatting, a modal shows what was picked up (goals,
   dependents, income, expenses, tax bracket) as editable fields. The
   client can correct anything before it's used — confirming saves the
   edits back to the chat session (`PUT
   /chat/sessions/{id}/extracted`) and moves straight to results.
4. **Results** (`ResultsPanel.jsx`) — the quick-form values and the
   (possibly edited) chat-extracted values are merged and run through
   the same deterministic scoring/matching pipeline as before,
   producing the risk matrix: governed band, matched portfolios, and
   matched products, each with an **Invest Now** button (a UI
   placeholder in this POC — wire it to your actual application flow).

Quick questions come first deliberately: it seeds a clean numeric
record on file, and gives the chat model context so it doesn't re-ask
what's already known.

## Backend

- `schema.sql` — clients, chat_sessions, chat_messages, portfolios,
  products, recommendations, product_recommendations
- `seed_data.py` — 8 example portfolios, 15 example products
- `scoring.py` — client inputs → bands, governed by
  `min(tolerance, capacity, horizon)`
- `matching.py` — portfolio filter-then-rank, then product
  filter-then-rank within each matched portfolio (with an optional
  tax-efficiency ranking nudge for high-tax-bracket clients)
- `ai_chat.py` — the conversational intake: a standard Anthropic
  tool-use loop. `build_system_prompt(known_context)` and
  `build_opening_message(known_context)` turn the quick form's answers
  into an explicit "already known, don't ask again" list, so the
  opening line and every turn's instructions are personalized rather
  than generic. The model calls `record_client_info` whenever it
  learns a concrete fact; the backend merges those fields into the
  session's `extracted_profile`. The visible chat reply and the
  structured extraction are two outputs of the same turn.
- `pdf_extract.py` — pulls raw text out of an uploaded PDF (via
  `pypdf`) and hands it to the chat model to summarize; does no
  financial parsing itself.
- `main.py` — FastAPI app:
  - `POST /clients/profile` — quick-form submit; if `chat_session_id`
    is included, also merges that session's extracted fields
  - `GET /portfolios`
  - `POST /chat/sessions` — start a session, get the opening question
  - `POST /chat/sessions/{id}/messages` — send a message, get a reply
    + updated extracted fields
  - `POST /chat/sessions/{id}/upload-statement` — upload a PDF,
    extracted text is fed to the model as a turn

### Chat requires an API key

Set `ANTHROPIC_API_KEY` in the backend's environment before using the
chat endpoints:

```bash
# macOS / Linux
export ANTHROPIC_API_KEY=sk-ant-...
```

```powershell
# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

```cmd
:: Windows Command Prompt
set ANTHROPIC_API_KEY=sk-ant-...
```

These only apply to the current terminal session — set it again each
time you open a new one, or add it to your OS's persistent environment
variables if you'd rather not repeat it.

Without it, `/clients/profile` and `/portfolios` work fine (they don't
need the API), but the chat endpoints return `503` with a clear
message rather than crashing.

> If you see `TypeError: Client.__init__() got an unexpected keyword
> argument 'proxies'` when calling a chat endpoint, your installed
> `anthropic` package predates the fix for newer `httpx` versions.
> Run `pip install -U anthropic` (requirements.txt now pins
> `anthropic>=0.69.0`, which is unaffected).

## Frontend — design system

Built to read as a banking-app feature, not a generic AI chat demo:

- **Color** — cool off-white base, near-black teal ink, a deep emerald
  accent. The real signature is a 5-step **risk-band ramp** (cool teal
  → warm copper) used consistently for every risk band shown anywhere
  in the app.
- **Type** — Space Grotesk for display, Inter for body/UI, IBM Plex
  Mono for every number that matters (Rand amounts, fees, band
  figures) — see `tokens.css`.
- **Signature element** — the `RiskLadder` component (`RiskLadder.jsx`):
  a persistent 5-segment bar shown throughout all three steps. It
  doubles as progress indicator (Step 1: empty; Steps 2–3: filling in
  with a live preview, then the final governed band) and as the
  literal content of the result — structure and content are the same
  thing here, not decoration on top of it.

Files: `tokens.css` (design tokens), `global.css` (resets + shared
primitives), `layout.css` (page chrome, forms, chat, results),
`animations.css` (step transitions, modal, toast, card entrance,
ladder fill), `RiskLadder.jsx` + `.css`, `QuickQuestions.jsx`,
`ChatPanel.jsx`, `ConfirmModal.jsx`, `Toast.jsx`, `ResultsPanel.jsx`,
`App.jsx` (wizard orchestration).

### Notes on recent polish

- Number inputs (`NumberField` in `QuickQuestions.jsx`) now select
  their contents on focus, so typing replaces the value instead of
  requiring you to delete a leading zero first.
- The chat no longer re-asks what the quick form already collected —
  see `ai_chat.py`'s `build_system_prompt`/`build_opening_message`.
- Invest Now buttons currently just show a confirmation toast — hook
  `investNow()` in `ResultsPanel.jsx` up to your actual application
  flow when ready.

## Run it

```bash
# backend
cd backend
pip install -r requirements.txt

# set the API key (needed for chat only — see below for your OS)
export ANTHROPIC_API_KEY=sk-ant-...        # macOS/Linux
# $env:ANTHROPIC_API_KEY = "sk-ant-..."    # Windows PowerShell
# set ANTHROPIC_API_KEY=sk-ant-...         # Windows cmd

python db.py              # creates and seeds risk_profiler.db
uvicorn main:app --reload

# frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (typically `http://localhost:5173`). The
frontend expects the API at `http://localhost:8000`.

## Scenarios worth trying

1. Skip the chat entirely (click straight through to results) — the
   quick-form values alone drive the matrix, same as before this
   feature was added.
2. In the chat, say your income is far higher than the form's figure
   — the final matrix should reflect the chat's number, not the form's.
3. Upload a bank statement PDF — the model estimates income/expenses
   from the extracted text and asks you to confirm before recording.
4. Mention a top-bracket tax rate (e.g. "I'm in the 45% bracket") —
   compare the product ranking within a matched portfolio against a
   run without that detail; tax-advantaged wrappers should rank first
   when the bracket is high (39%+).

## Extending this

- Swap the threshold constants in `scoring.py` for values calibrated
  to your actual questionnaire and FAIS suitability methodology.
- Add more hard filters to `matching.py` as needed (e.g. FSCA product
  type restrictions, currency exposure limits).
- `ai_chat.py`'s `SYSTEM_PROMPT` and `RECORD_TOOL` schema are the
  place to extend what the conversation gathers (debt, job stability
  detail, etc.) — add fields to the tool's `input_schema` and mention
  them in the prompt.
- The `recommendations` and `product_recommendations` tables already
  log every (client, portfolio/product, rank) triple with a
  timestamp — useful as the audit trail for suitability record-keeping.
