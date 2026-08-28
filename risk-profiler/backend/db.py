from __future__ import annotations
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "risk_profiler.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def _insert_and_get_id(conn: sqlite3.Connection, sql: str, params: dict) -> int:
    """Runs an INSERT and returns its new rowid as a plain int.

    cursor.lastrowid is typed as int | None (it's None if the cursor
    never executed an INSERT) — this asserts the case that can't
    actually happen here, so callers get a clean int instead of
    threading an Optional through every id-mapping dict.
    """
    cur = conn.execute(sql, params)
    assert cur.lastrowid is not None, "INSERT did not produce a rowid"
    return cur.lastrowid

def init_db(seed: bool = True) -> None:
    conn = get_connection()
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()

    if seed:
        cur = conn.execute("SELECT COUNT(*) FROM portfolios")
        if cur.fetchone()[0] == 0:
            from seed_data import (
                PORTFOLIOS,
                PRODUCTS,
                PRODUCT_PORTFOLIO_MAPPING,
                PORTFOLIO_RETURNS,
                PORTFOLIO_RETURNS_METHODOLOGY,
                PORTFOLIO_RETURNS_METHODOLOGY_BY_KEY, 
            )

            portfolio_key_to_id: dict[str, int] = {}
            for p in PORTFOLIOS:
                portfolio_key_to_id[p["key"]] = _insert_and_get_id(
                    conn,
                    """INSERT INTO portfolios (
                        name, provider, risk_band, max_equity_pct, min_horizon_years,
                        liquidity_days, reg28_compliant, min_knowledge_band,
                        requires_emergency_fund, underlying_fee_pct, description
                    ) VALUES (
                        :name, :provider, :risk_band, :max_equity_pct, :min_horizon_years,
                        :liquidity_days, :reg28_compliant, :min_knowledge_band,
                        :requires_emergency_fund, :underlying_fee_pct, :description
                    )""",
                    p,
                )
            conn.commit()

            product_key_to_id: dict[str, int] = {}
            for p in PRODUCTS:
                product_key_to_id[p["key"]] = _insert_and_get_id(
                    conn,
                    """INSERT INTO products (
                        name, provider, tax_wrapper, min_initial_investment,
                        min_monthly_investment, annual_platform_fee_pct, advice_fee_pct,
                        min_term_years, description, spec_notes
                    ) VALUES (
                        :name, :provider, :tax_wrapper, :min_initial_investment,
                        :min_monthly_investment, :annual_platform_fee_pct, :advice_fee_pct,
                        :min_term_years, :description, :spec_notes
                    )""",
                    p,
                )
            conn.commit()

            mapping_rows = []
            for product_key, portfolio_key in PRODUCT_PORTFOLIO_MAPPING:
                if product_key not in product_key_to_id:
                    raise ValueError(f"product_portfolio_mapping.csv references unknown product_key '{product_key}'")
                if portfolio_key not in portfolio_key_to_id:
                    raise ValueError(f"product_portfolio_mapping.csv references unknown portfolio_key '{portfolio_key}'")
                mapping_rows.append((product_key_to_id[product_key], portfolio_key_to_id[portfolio_key]))
            conn.executemany(
                "INSERT INTO product_portfolio_mapping (product_id, portfolio_id) VALUES (?, ?)",
                mapping_rows,
            )

            returns_rows = [
                (
                    portfolio_key_to_id[key],
                    expected,
                    lower,
                    upper,
                    PORTFOLIO_RETURNS_METHODOLOGY_BY_KEY.get(key, PORTFOLIO_RETURNS_METHODOLOGY),
                )
                for key, (expected, lower, upper) in PORTFOLIO_RETURNS.items()
            ]
            conn.executemany(
                """INSERT INTO portfolio_returns
                   (portfolio_id, expected_return_pct, lower_return_pct, upper_return_pct, methodology)
                   VALUES (?, ?, ?, ?, ?)""",
                returns_rows,
            )
            conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print(f"Initialized {DB_PATH}")
