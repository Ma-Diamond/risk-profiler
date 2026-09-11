"""Writes expected-return assumptions into the PortfolioReturns table.

Returns are stored as a TERM STRUCTURE per portfolio (a yield curve),
not one flat rate — each item is one (portfolio, horizon_years) tenor
point, and a portfolio normally has several. Horizons in between
stored tenors are linearly interpolated at query time by the backend
(see projections.resolve_curve_point) — this script only needs to
write the known curve points, not every possible horizon.

Now that everything lives in DynamoDB, this script can run from
anywhere with the right IAM permissions (an EC2/EB instance role, your
own AWS credentials, a Lambda) — it's no longer tied to running on the
same box as the backend or opening a local file. It just needs:
  dynamodb:UpdateItem, dynamodb:PutItem, dynamodb:GetItem, dynamodb:Scan
on the RiskProfilerPortfolioReturns and RiskProfilerPortfolios tables.

Safe to re-run: each run replaces a (portfolio, horizon) point's
existing item rather than adding a new one.

USAGE — if you already have a DataFrame of computed returns (one row
per portfolio per horizon point, i.e. your yield curve already in
long/tidy format):

    from scripts.update_portfolio_returns import upsert_returns_from_dataframe
    import db

    count = upsert_returns_from_dataframe(my_returns_df)
    print(f"Updated {count} rows")

That's it — no loop to write yourself, just pass the DataFrame in.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import db  # noqa: E402


def fetch_portfolios() -> list[dict]:
    """Same table GET /portfolios reads from — useful if your
    calculation needs portfolio attributes (risk_band, fees, etc.) as
    an input, not just an id to write back to."""
    items: list[dict] = []
    resp = db.PORTFOLIOS.scan()
    items.extend(resp["Items"])
    while "LastEvaluatedKey" in resp:
        resp = db.PORTFOLIOS.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp["Items"])
    return items


def upsert_portfolio_returns(
    portfolio_id: int, horizon_years: float, expected: float, lower: float, upper: float, methodology: str
) -> None:
    """Writes (or replaces) one (portfolio, horizon) tenor point."""
    db.PORTFOLIO_RETURNS.put_item(
        Item={
            "portfolio_id": portfolio_id,
            "horizon_years": db.dec(horizon_years),
            "expected_return_pct": db.dec(expected),
            "lower_return_pct": db.dec(lower),
            "upper_return_pct": db.dec(upper),
            "methodology": methodology,
        }
    )


def upsert_returns_from_dataframe(
    df,
    *,
    portfolio_id_col: str = "portfolio_id",
    portfolio_name_col: str = "portfolio_name",
    horizon_col: str = "horizon_years",
    expected_col: str = "expected_return_pct",
    lower_col: str = "lower_return_pct",
    upper_col: str = "upper_return_pct",
    methodology_col: str | None = None,
    methodology: str = "Computed by external returns script",
) -> int:
    """Writes every row of a returns DataFrame into PortfolioReturns.
    The loop happens in here — you just hand over the DataFrame.

    Expects one row PER (portfolio, horizon) tenor point — i.e. your
    yield curve already in long/tidy format, with several rows per
    portfolio (one per horizon you've computed a rate for), not one
    row per portfolio. Accepts anything with a `.to_dict("records")`
    method (a pandas DataFrame is the expected case; a plain list[dict]
    also works since it's used the same way).

    Each row identifies its portfolio either by `portfolio_id_col`
    (this database's own id, if your script already knows it) or by
    `portfolio_name_col` (matched against a portfolio's name — handy
    if your script only knows portfolios by name, not by our internal
    id). If a row has both, portfolio_id_col wins. Column names are
    all overridable if your DataFrame uses different ones.

    Returns the number of rows written.
    """
    records = df.to_dict("records")
    if not records:
        return 0

    has_id_col = portfolio_id_col in records[0]
    name_to_id: dict[str, int] | None = None
    if not has_id_col:
        name_to_id = {p["name"]: int(p["portfolio_id"]) for p in fetch_portfolios()}

    written = 0
    for row in records:
        if has_id_col and row.get(portfolio_id_col) is not None:
            portfolio_id = int(row[portfolio_id_col])
        else:
            name = row[portfolio_name_col]
            if name_to_id is None or name not in name_to_id:
                raise ValueError(
                    f"No portfolio found with name '{name}' — check it matches "
                    f"an existing portfolio's name exactly, or pass portfolio_id instead."
                )
            portfolio_id = name_to_id[name]

        row_methodology = row[methodology_col] if methodology_col else methodology

        upsert_portfolio_returns(
            portfolio_id=portfolio_id,
            horizon_years=float(row[horizon_col]),
            expected=float(row[expected_col]),
            lower=float(row[lower_col]),
            upper=float(row[upper_col]),
            methodology=row_methodology,
        )
        written += 1

    return written


def build_returns_dataframe():
    """PLACEHOLDER — replace this with wherever your script's
    DataFrame already comes from. It should have one row per
    (portfolio, horizon_years) tenor point — your yield curve in
    long/tidy format."""
    raise NotImplementedError("plug in your existing calculation/DataFrame here")


def main() -> None:
    returns_df = build_returns_dataframe()
    count = upsert_returns_from_dataframe(returns_df)
    print(f"Updated {count} portfolio return curve points.")


if __name__ == "__main__":
    main()
