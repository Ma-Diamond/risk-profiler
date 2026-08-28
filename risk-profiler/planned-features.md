# Planned features — design sketches

Three features under consideration, sketched here before building. Order
of complexity (and recommended build order): **advisor callback → login/
profiles → bank statement nudges**. Reasoning at the bottom.

---

## 1. Advisor callback / "Invest Now" split

The simplest of the three — a data-driven flag plus a UI branch. No new
infrastructure.

### Data model

`products` table gains one column:

```sql
ALTER TABLE products ADD COLUMN requires_advisor INTEGER NOT NULL DEFAULT 0;
```

(Same pattern as everything else — plain 0/1, driven by `products.csv` if
you're on the CSV seed pipeline: add a `requires_advisor` column there.)

**Suggested seed values:** `retirement_annuity` and `preservation_fund` set
to `1` (these are the more complex, FAIS-advice-typically-required
products in the current catalog); everything else (`cash_account`,
`tfsa`, `unit_trust`, `endowment`) stays `0`. Easy to change later — it's
just data.

New table for the requests themselves:

```sql
CREATE TABLE callback_requests (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id        INTEGER NOT NULL REFERENCES clients(id),
    product_id       INTEGER NOT NULL REFERENCES products(id),
    contact_method   TEXT NOT NULL,   -- 'phone' | 'email', free text is fine
    contact_detail   TEXT,            -- number or email, if different from profile
    preferred_time   TEXT,            -- free text, e.g. "weekday mornings"
    status           TEXT NOT NULL DEFAULT 'pending',
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### Backend

- `ProductOut` gains `requires_advisor: bool`.
- `POST /callback-requests` — body `{client_id, product_id, contact_method,
  contact_detail, preferred_time}` → inserts a row, returns confirmation.
  No real telephony/CRM integration — this persists the request only,
  same as `Invest Now` is currently a UI-only stub. Worth a comment in
  code flagging where a real CRM/ticketing webhook would plug in later.

### Frontend

- In each product row (`ResultsPanel.jsx`): if `prod.requires_advisor`,
  render **"Request a callback"** instead of **"Invest Now"**.
- Clicking it opens a small inline form (reuse the existing modal
  pattern) — contact method, contact detail, preferred time — submits to
  `/callback-requests`, shows a confirmation `Toast` on success ("Thanks
  — an adviser will be in touch").

No auth dependency — works whether or not feature #2 (login) exists,
since `client_id` already comes from the just-finalized profile.

---

## 2. Login & profile history

The biggest architectural step of the three. Not just a feature — it
changes the trust model of the app. Still additive, though: anonymous
use keeps working exactly as it does today (guest checkout style), and
everything below is designed so `user_id` is nullable throughout.

### Data model

```sql
CREATE TABLE users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    email          TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    full_name      TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
```

Add `user_id INTEGER REFERENCES users(id)` (nullable) to both
`chat_sessions` and `clients`. Denormalizing onto `clients` too (rather
than only joining through `chat_session_id`) keeps "list this user's past
profiles" a single indexed query instead of a join every time.

### Auth mechanism

- **Password hashing:** `bcrypt` (or `passlib[bcrypt]`) — never
  hand-rolled, even for a POC.
- **Session:** lightweight bearer token (`pyjwt`), not a cookie-based
  session store — matches the stateless FastAPI style already in use.
  Token holds `user_id` + expiry, signed with a secret pulled from an
  env var (`AUTH_SECRET_KEY`), never hardcoded.
- Frontend sends `Authorization: Bearer <token>` on requests once logged
  in; stored in `localStorage`, checked for expiry on load.

**Security caveats worth stating plainly, not glossing over:**
`localStorage` tokens are XSS-exposed compared to `httpOnly` cookies —
fine for local dev, worth revisiting (short-lived access token + refresh
token in an `httpOnly` cookie) before this goes anywhere near production
traffic. Same for CORS: currently locked to `localhost:5173`, would need
tightening to the real deployed origin.

### New endpoints

- `POST /auth/register` — `{email, password, full_name}` → creates user,
  returns token.
- `POST /auth/login` — `{email, password}` → verifies, returns token.
- `GET /auth/me` — returns current user from token (also doubles as
  "is my token still valid" check on app load).
- Every chat endpoint gains an **optional** `Authorization` header — if
  present and valid, the chat session it creates/touches gets tagged
  with that `user_id`; ownership is checked on access (a user can't open
  someone else's session — 403 otherwise). No header → anonymous session,
  exactly like today.
- `GET /profiles` (authenticated) — lists the user's past finalized
  profiles: id, created_at, governed_risk_band, goals_detail, a short
  summary line. Powers a "My Profiles" list.
- `GET /profiles/{client_id}` — returns the full stored `ProfileResult`
  plus its `chat_session_id`, so "Continue" can reopen that session
  directly in post-results chat mode — this part is nearly free, since
  `chat_sessions.finalized_result` already persists the full snapshot and
  post-results mode already knows how to load and chat over a stored
  result.

### Frontend

- `Login.jsx` / `Signup.jsx` — simple forms, no new routing library
  needed; a `view` state (`'chat' | 'history' | 'login'`) in `App.jsx`
  follows the same pattern already used for `hasResults`.
- Auth state (token + current user) lifted to `App.jsx`, persisted to
  `localStorage`, checked against `/auth/me` on load.
- `ProfileHistory.jsx` — list of past profiles with date, band, goal;
  "Continue" reopens results + docked chat for that session; a plain
  "View" could be a lighter-weight read-only version if wanted later.
- Header gains a "My Profiles" nav item, visible only when logged in;
  otherwise a "Log in" affordance, with guest use remaining the default
  path (no forced signup wall).

---

## 3. Bank-statement-driven surplus nudges (POC)

Worth being upfront about scope here, same as when this came up earlier:
a **real** version of this needs a live account/transaction feed and a
scheduled backend job — not a one-off chat upload. What's sketched below
is a faithful POC stand-in, clearly labeled as such in the UI copy, not
presented as the real thing.

### Design

Reuses the existing `pdf_extract.py` text extraction, but adds a
dedicated deterministic step rather than folding this into the existing
free-form intake conversation. Bank statement formats vary too much for
regex parsing to be reliable across banks — that part genuinely needs the
model's judgement — but the **arithmetic** (income − expenses) stays
deterministic once the model has structured the noisy text into numbers,
same philosophy as the rest of this app.

- New tool (post-results phase only): `record_statement_totals` — the
  model reads the extracted statement text and calls this with
  `{total_income, total_expenses}` for the statement period. No
  line-item detail needed, just the two totals.
- Backend computes `surplus = total_income - total_expenses`
  deterministically, compares against the client's already-committed
  `monthly_contribution` from their finalized profile.
- If `surplus > monthly_contribution` by a meaningful margin, return a
  structured "nudge" payload: `{surplus_amount, message,
  suggested_portfolio_id}` (suggested portfolio would typically be
  whichever matched instant-access/money-market option is on file for
  them, e.g. Capital Protector). Otherwise, a plain "nothing significant
  found" response — no manufactured urgency when there's nothing to
  flag.

### Backend

- `POST /chat/sessions/{id}/analyze-statement` (post-results only,
  parallel to the existing intake-only `/upload-statement`) — accepts a
  PDF, extracts text, runs the `record_statement_totals` tool turn,
  computes the surplus, returns the nudge payload (or a null result).

### Frontend

- Re-enable the 📎 upload button in post-results chat mode (currently
  hidden via `hasResults` in `ChatPanel.jsx`) — repurposed here with
  copy like "Upload a statement to see if you have room to invest more."
- A nudge renders as a distinct, more prominent bubble than the existing
  dashed-border hint (this one should read as actionable, not just
  informative) with a CTA button — tapping it feeds the surplus straight
  into the existing `recalculate_investment_projection` tool as an
  addition to `monthly_amount`, so the client immediately sees what the
  extra amount would do to their projection, reusing machinery that
  already exists rather than building a parallel path.
- UI copy should say plainly that this is based on the statement they
  just uploaded, not a live feed — avoids implying always-on monitoring
  that isn't actually happening yet.

---

## Why this build order

- **Advisor callback** is quick, self-contained, and has zero dependency
  on the other two — no reason not to build it first.
- **Login/profiles** is the largest lift and the most security-sensitive,
  so it deserves its own focused pass rather than being squeezed in
  alongside something else.
- **Statement nudges** benefits from login existing first: a single
  one-off upload can estimate a surplus once, but the more valuable
  version of this feature — "this happens most months" — needs
  persisted history tied to an actual account, which login provides for
  free once it's there.
