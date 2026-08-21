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
            )

            portfolio_key_to_id: dict[str, int] = {}
            for p in PORTFOLIOS:
                cur = conn.execute(
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
                portfolio_key_to_id[p["key"]] = cur.lastrowid
            conn.commit()

            product_key_to_id: dict[str, int] = {}
            for p in PRODUCTS:
                cur = conn.execute(
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
                product_key_to_id[p["key"]] = cur.lastrowid
            conn.commit()

            mapping_rows = [
                (product_key_to_id[product_key], portfolio_key_to_id[portfolio_key])
                for product_key, portfolio_key in PRODUCT_PORTFOLIO_MAPPING
            ]
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
                    PORTFOLIO_RETURNS_METHODOLOGY,
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
