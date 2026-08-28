"""Seed data loader — reads portfolios, products, the mapping between
them, and return assumptions from CSV files in backend/data/, so
updating the product catalog, fees, or return assumptions never
requires touching Python code.

Expected files (all in backend/data/, headers required — see the
project notes for exact column layouts):

  portfolios.csv
  products.csv
  product_portfolio_mapping.csv
  portfolio_returns.csv

`key` / `product_key` / `portfolio_key` are your own stable
identifiers (not DB ids) — used only to wire the mapping and returns
files to the right row when seeding. They can stay the same even if
you rename a product or portfolio's display name.
"""

from __future__ import annotations

import csv
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

DEFAULT_METHODOLOGY = (
    "PLACEHOLDER — dummy figures for development only. Replace with "
    "output from an actual capital market assumptions / actuarial "
    "process before this is used for anything beyond a POC."
)


def _read_csv(filename: str) -> list[dict]:
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Expected seed data file not found: {path}\n"
            f"Create it under backend/data/ — see seed_data.py's module "
            f"docstring for the expected columns."
        )
    # Windows editors (Excel, Notepad) often save CSVs as cp1252/ANSI
    # rather than UTF-8 — try UTF-8 first, fall back if that fails.
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            with open(path, newline="", encoding=encoding) as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(
        "utf-8/cp1252", b"", 0, 1,
        f"Could not decode {path} as UTF-8 or cp1252 — check the file's encoding."
    )


def _to_int_bool(value: str) -> int:
    """Accepts '1'/'0', 'true'/'false', 'yes'/'no' (case-insensitive)."""
    return 1 if str(value).strip().lower() in ("1", "true", "yes") else 0


def _blank_to_none(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _load_portfolios() -> list[dict]:
    rows = _read_csv("portfolios.csv")
    portfolios = []
    for i, r in enumerate(rows, start=2):  # row 1 is the header
        try:
            portfolios.append({
                "key": r["key"].strip(),
                "name": r["name"].strip(),
                "provider": _blank_to_none(r.get("provider")),
                "risk_band": int(r["risk_band"]),
                "max_equity_pct": float(r["max_equity_pct"]),
                "min_horizon_years": float(r["min_horizon_years"]),
                "liquidity_days": int(r["liquidity_days"]),
                "reg28_compliant": _to_int_bool(r["reg28_compliant"]),
                "min_knowledge_band": int(r["min_knowledge_band"]),
                "requires_emergency_fund": _to_int_bool(r["requires_emergency_fund"]),
                "underlying_fee_pct": float(r["underlying_fee_pct"]),
                "description": _blank_to_none(r.get("description")),
            })
        except (KeyError, ValueError) as e:
            raise ValueError(f"portfolios.csv row {i}: {e}") from e
    return portfolios


def _load_products() -> list[dict]:
    rows = _read_csv("products.csv")
    products = []
    for i, r in enumerate(rows, start=2):
        try:
            products.append({
                "key": r["key"].strip(),
                "name": r["name"].strip(),
                "provider": _blank_to_none(r.get("provider")),
                "tax_wrapper": r["tax_wrapper"].strip(),
                "min_initial_investment": float(r["min_initial_investment"]),
                "min_monthly_investment": float(r["min_monthly_investment"]),
                "annual_platform_fee_pct": float(r["annual_platform_fee_pct"]),
                "advice_fee_pct": float(r["advice_fee_pct"]),
                "min_term_years": float(r["min_term_years"]),
                "description": _blank_to_none(r.get("description")),
                "spec_notes": _blank_to_none(r.get("spec_notes")),
            })
        except (KeyError, ValueError) as e:
            raise ValueError(f"products.csv row {i}: {e}") from e
    return products


def _load_mapping() -> list[tuple[str, str]]:
    rows = _read_csv("product_portfolio_mapping.csv")
    mapping = []
    for i, r in enumerate(rows, start=2):
        try:
            mapping.append((r["product_key"].strip(), r["portfolio_key"].strip()))
        except KeyError as e:
            raise ValueError(f"product_portfolio_mapping.csv row {i}: {e}") from e
    return mapping


def _load_returns() -> tuple[dict[str, tuple[float, float, float]], dict[str, str]]:
    rows = _read_csv("portfolio_returns.csv")
    returns: dict[str, tuple[float, float, float]] = {}
    methodology_by_key: dict[str, str] = {}
    for i, r in enumerate(rows, start=2):
        try:
            key = r["portfolio_key"].strip()
            returns[key] = (
                float(r["expected_return_pct"]),
                float(r["lower_return_pct"]),
                float(r["upper_return_pct"]),
            )
            methodology_by_key[key] = _blank_to_none(r.get("methodology")) or DEFAULT_METHODOLOGY
        except (KeyError, ValueError) as e:
            raise ValueError(f"portfolio_returns.csv row {i}: {e}") from e
    return returns, methodology_by_key


PORTFOLIOS: list[dict] = _load_portfolios()
PRODUCTS: list[dict] = _load_products()
PRODUCT_PORTFOLIO_MAPPING: list[tuple[str, str]] = _load_mapping()
PORTFOLIO_RETURNS, PORTFOLIO_RETURNS_METHODOLOGY_BY_KEY = _load_returns()
PORTFOLIO_RETURNS_METHODOLOGY = DEFAULT_METHODOLOGY  # fallback default