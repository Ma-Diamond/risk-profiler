-- Risk profiling schema
-- Deliberately loose: few CHECK constraints, no rigid enums enforced at
-- the DB layer. This structure is expected to change as the product
-- catalog evolves — favour adding/renaming columns over redesigning
-- around a schema that resists change.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- CHAT SESSIONS
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    known_context       TEXT NOT NULL DEFAULT '{}',
    extracted_profile   TEXT NOT NULL DEFAULT '{}',
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     INTEGER NOT NULL REFERENCES chat_sessions(id),
    role           TEXT NOT NULL,
    content        TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------
-- CLIENTS
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clients (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name                  TEXT NOT NULL,
    age                        INTEGER NOT NULL,
    dependents                 INTEGER NOT NULL DEFAULT 0,
    gross_monthly_income       REAL NOT NULL,
    monthly_expenses           REAL NOT NULL,
    emergency_fund_months      REAL NOT NULL,
    investment_horizon_years   REAL NOT NULL,
    investment_goal            TEXT NOT NULL,
    available_lump_sum         REAL NOT NULL DEFAULT 0,
    monthly_contribution       REAL NOT NULL DEFAULT 0,
    goals_detail               TEXT,
    tax_bracket                TEXT,
    chat_session_id            INTEGER REFERENCES chat_sessions(id),
    tolerance_questionnaire    TEXT NOT NULL,
    knowledge_score            INTEGER NOT NULL,
    tolerance_band              INTEGER,
    capacity_band                INTEGER,
    horizon_band                 INTEGER,
    governed_risk_band          INTEGER,
    created_at                  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------
-- PORTFOLIOS
-- An investment strategy/mandate. Carries its own risk characteristics
-- AND its own underlying fee (TER) — the cost of running that
-- strategy, independent of which wrapper/product it's sold through.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portfolios (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    name                     TEXT NOT NULL,
    provider                TEXT,
    risk_band                INTEGER NOT NULL,
    max_equity_pct           REAL NOT NULL,
    min_horizon_years        REAL NOT NULL,
    liquidity_days           INTEGER NOT NULL,
    reg28_compliant          INTEGER NOT NULL DEFAULT 0,
    min_knowledge_band       INTEGER NOT NULL DEFAULT 1,
    requires_emergency_fund  INTEGER NOT NULL DEFAULT 0,
    underlying_fee_pct       REAL NOT NULL DEFAULT 0,
    description               TEXT
);

-- ---------------------------------------------------------------------
-- PRODUCTS
-- A wrapper a client can invest through (RA, TFSA, endowment, unit
-- trust account, ...). Carries platform-level fees, minimums, tax
-- treatment, and lock-in — NOT tied to a single portfolio. Which
-- portfolios are actually selectable under a given product lives in
-- product_portfolio_mapping below, so one product can offer many
-- portfolios (a realistic RA menu, for example) and one portfolio can
-- be sold through many products.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    name                         TEXT NOT NULL,
    provider                    TEXT,
    tax_wrapper                 TEXT NOT NULL,
    min_initial_investment      REAL NOT NULL DEFAULT 0,
    min_monthly_investment      REAL NOT NULL DEFAULT 0,
    annual_platform_fee_pct     REAL NOT NULL DEFAULT 0,
    advice_fee_pct              REAL NOT NULL DEFAULT 0,
    min_term_years              REAL NOT NULL DEFAULT 0,
    description                 TEXT,
    spec_notes                  TEXT   -- free text for the AI help-chat to draw on later
);

CREATE TABLE IF NOT EXISTS product_portfolio_mapping (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id     INTEGER NOT NULL REFERENCES products(id),
    portfolio_id   INTEGER NOT NULL REFERENCES portfolios(id)
);

-- ---------------------------------------------------------------------
-- PORTFOLIO RETURNS
-- Expected annual return + a rough confidence interval per portfolio,
-- produced by a separate research/actuarial process (NOT this app).
-- Values here are illustrative placeholders — see seed_data.py.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portfolio_returns (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id          INTEGER NOT NULL REFERENCES portfolios(id),
    expected_return_pct   REAL NOT NULL,
    lower_return_pct      REAL NOT NULL,
    upper_return_pct      REAL NOT NULL,
    methodology           TEXT,
    updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------
-- RECOMMENDATIONS (audit trail)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recommendations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id      INTEGER NOT NULL REFERENCES clients(id),
    portfolio_id   INTEGER NOT NULL REFERENCES portfolios(id),
    rank           INTEGER NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS product_recommendations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id      INTEGER NOT NULL REFERENCES clients(id),
    product_id     INTEGER NOT NULL REFERENCES products(id),
    portfolio_id   INTEGER NOT NULL REFERENCES portfolios(id),
    rank           INTEGER NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
