"""DynamoDB data layer.

Replaces the earlier SQLite file with DynamoDB tables — the same
shapes, mapped as directly as possible onto DynamoDB's item model:

- Users            PK: email
- ChatSessions     PK: session_id
- ChatMessages     PK: session_id, SK: created_at (ordered retrieval for free)
- Clients          PK: client_id, GSI "by-user" PK: user_id, SK: created_at
- Portfolios       PK: portfolio_id (product_ids stored as a list attribute —
                   replaces the old separate mapping table; the relationship
                   rarely changes and is read constantly, a good fit for
                   denormalizing rather than a second table + query)
- Products         PK: product_id
- PortfolioReturns PK: portfolio_id, SK: horizon_years (a Query on
                   portfolio_id returns the whole curve already sorted by
                   tenor — no client-side sort needed)
- Accounts         PK: account_id, GSI "by-client" PK: client_id — an
                   actually-opened investment account/policy, stemming
                   from a risk profile (see the Invest Now flow)
- Counters         PK: counter_name — atomic ADD gives auto-increment-like
                   integer ids (session_id, client_id, portfolio_id,
                   product_id, account_id) without changing any existing
                   int-typed field in the API or frontend.

JSON-blob fields (known_context, extracted_profile, finalized_result,
saved_profile, a chat message's content, an account's application/
beneficiary details) stay JSON-encoded strings, exactly as they were
as SQLite TEXT columns — this sidesteps DynamoDB's Decimal-for-numbers
requirement entirely for those fields, since from DynamoDB's point of
view they're just opaque strings.

Note: the old `recommendations` / `product_recommendations` audit
tables are dropped in this migration — nothing in the app ever read
them back, they were pure write-only audit trails. Say the word if you
want that audit trail restored as DynamoDB tables too.
"""

from __future__ import annotations

import os
from decimal import Decimal

import boto3

TABLE_PREFIX = "RiskProfiler"
_REGION = os.environ.get("AWS_REGION")  # falls back to boto3's own resolution if unset

_dynamo_kwargs = {"region_name": _REGION} if _REGION else {}
_resource = boto3.resource("dynamodb", **_dynamo_kwargs)
_client = boto3.client("dynamodb", **_dynamo_kwargs)


def _table(name: str):
    return _resource.Table(f"{TABLE_PREFIX}{name}")


USERS = _table("Users")
CHAT_SESSIONS = _table("ChatSessions")
CHAT_MESSAGES = _table("ChatMessages")
CLIENTS = _table("Clients")
PORTFOLIOS = _table("Portfolios")
PRODUCTS = _table("Products")
PORTFOLIO_RETURNS = _table("PortfolioReturns")
ACCOUNTS = _table("Accounts")
COUNTERS = _table("Counters")


# ---------------------------------------------------------------------
# Numeric helpers — DynamoDB's Python SDK requires Decimal for numbers
# on write (rejects native float with a TypeError) and returns Decimal
# on read. Pydantic auto-coerces Decimal -> int/float on model
# construction, so most call sites never need `num()` at all — reach
# for it only where raw arithmetic happens directly on a DynamoDB item
# before any Pydantic model sees it (e.g. combining a fee from two
# items, or feeding rates into projections.py's plain-float math).
# ---------------------------------------------------------------------
def dec(value) -> Decimal:
    """Python float/int -> DynamoDB-safe Decimal. Goes via str() to
    avoid binary float artifacts (Decimal(0.1) != Decimal("0.1"))."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def num(value) -> float:
    """DynamoDB Decimal (or already a plain number) -> plain float,
    for raw arithmetic outside of Pydantic."""
    return float(value)


def next_id(counter_name: str) -> int:
    """Atomically increments and returns a counter — DynamoDB's
    equivalent of an auto-increment integer id. Works even if the
    counter doesn't exist yet: ADD on a missing item creates it."""
    resp = COUNTERS.update_item(
        Key={"counter_name": counter_name},
        UpdateExpression="ADD #v :incr",
        ExpressionAttributeNames={"#v": "value"},
        ExpressionAttributeValues={":incr": 1},
        ReturnValues="UPDATED_NEW",
    )
    return int(resp["Attributes"]["value"])


# ---------------------------------------------------------------------
# Table creation + seeding
# ---------------------------------------------------------------------
_TABLE_DEFS = [
    dict(
        TableName=f"{TABLE_PREFIX}Users",
        KeySchema=[{"AttributeName": "email", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "email", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    ),
    dict(
        TableName=f"{TABLE_PREFIX}ChatSessions",
        KeySchema=[{"AttributeName": "session_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "session_id", "AttributeType": "N"}],
        BillingMode="PAY_PER_REQUEST",
    ),
    dict(
        TableName=f"{TABLE_PREFIX}ChatMessages",
        KeySchema=[
            {"AttributeName": "session_id", "KeyType": "HASH"},
            {"AttributeName": "created_at", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "session_id", "AttributeType": "N"},
            {"AttributeName": "created_at", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    ),
    dict(
        TableName=f"{TABLE_PREFIX}Clients",
        KeySchema=[{"AttributeName": "client_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "client_id", "AttributeType": "N"},
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "created_at", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "by-user",
                "KeySchema": [
                    {"AttributeName": "user_id", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    ),
    dict(
        TableName=f"{TABLE_PREFIX}Portfolios",
        KeySchema=[{"AttributeName": "portfolio_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "portfolio_id", "AttributeType": "N"}],
        BillingMode="PAY_PER_REQUEST",
    ),
    dict(
        TableName=f"{TABLE_PREFIX}Products",
        KeySchema=[{"AttributeName": "product_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "product_id", "AttributeType": "N"}],
        BillingMode="PAY_PER_REQUEST",
    ),
    dict(
        TableName=f"{TABLE_PREFIX}PortfolioReturns",
        KeySchema=[
            {"AttributeName": "portfolio_id", "KeyType": "HASH"},
            {"AttributeName": "horizon_years", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "portfolio_id", "AttributeType": "N"},
            {"AttributeName": "horizon_years", "AttributeType": "N"},
        ],
        BillingMode="PAY_PER_REQUEST",
    ),
    dict(
        TableName=f"{TABLE_PREFIX}Accounts",
        KeySchema=[{"AttributeName": "account_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "account_id", "AttributeType": "N"},
            {"AttributeName": "client_id", "AttributeType": "N"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "by-client",
                "KeySchema": [{"AttributeName": "client_id", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    ),
    dict(
        TableName=f"{TABLE_PREFIX}Counters",
        KeySchema=[{"AttributeName": "counter_name", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "counter_name", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    ),
]


def _existing_table_names() -> set[str]:
    names = set()
    paginator = _client.get_paginator("list_tables")
    for page in paginator.paginate():
        names.update(page["TableNames"])
    return names


def _create_missing_tables() -> None:
    existing = _existing_table_names()
    for table_def in _TABLE_DEFS:
        if table_def["TableName"] in existing:
            continue
        _client.create_table(**table_def)
    waiter = _client.get_waiter("table_exists")
    for table_def in _TABLE_DEFS:
        if table_def["TableName"] not in existing:
            waiter.wait(TableName=table_def["TableName"])


def init_db(seed: bool = True) -> None:
    _create_missing_tables()
    if not seed:
        return

    # Only seed once — if Portfolios already has items, assume this
    # environment has already been seeded (matches the old "SELECT
    # COUNT(*)" guard).
    existing = PORTFOLIOS.scan(Limit=1)
    if existing.get("Items"):
        return

    from seed_data import (
        PORTFOLIOS as SEED_PORTFOLIOS,
        PRODUCTS as SEED_PRODUCTS,
        PRODUCT_PORTFOLIO_MAPPING,
        PORTFOLIO_RETURNS as SEED_PORTFOLIO_RETURNS,
        PORTFOLIO_RETURNS_METHODOLOGY,
        PORTFOLIO_RETURNS_METHODOLOGY_BY_KEY,
    )

    portfolio_key_to_id: dict[str, int] = {}
    portfolio_id_to_product_ids: dict[int, list[int]] = {}

    for p in SEED_PORTFOLIOS:
        portfolio_id = next_id("portfolio_id")
        portfolio_key_to_id[p["key"]] = portfolio_id
        portfolio_id_to_product_ids[portfolio_id] = []

    product_key_to_id: dict[str, int] = {}
    for p in SEED_PRODUCTS:
        product_key_to_id[p["key"]] = next_id("product_id")

    for product_key, portfolio_key in PRODUCT_PORTFOLIO_MAPPING:
        portfolio_id_to_product_ids[portfolio_key_to_id[portfolio_key]].append(
            product_key_to_id[product_key]
        )

    for p in SEED_PORTFOLIOS:
        portfolio_id = portfolio_key_to_id[p["key"]]
        PORTFOLIOS.put_item(
            Item={
                "portfolio_id": portfolio_id,
                "name": p["name"],
                "provider": p["provider"],
                "risk_band": p["risk_band"],
                "max_equity_pct": dec(p["max_equity_pct"]),
                "min_horizon_years": dec(p["min_horizon_years"]),
                "liquidity_days": p["liquidity_days"],
                "reg28_compliant": bool(p["reg28_compliant"]),
                "min_knowledge_band": p["min_knowledge_band"],
                "requires_emergency_fund": bool(p["requires_emergency_fund"]),
                "underlying_fee_pct": dec(p["underlying_fee_pct"]),
                "description": p["description"],
                "product_ids": portfolio_id_to_product_ids[portfolio_id],
            }
        )

    for p in SEED_PRODUCTS:
        PRODUCTS.put_item(
            Item={
                "product_id": product_key_to_id[p["key"]],
                "name": p["name"],
                "provider": p["provider"],
                "tax_wrapper": p["tax_wrapper"],
                "min_initial_investment": dec(p["min_initial_investment"]),
                "min_monthly_investment": dec(p["min_monthly_investment"]),
                "annual_platform_fee_pct": dec(p["annual_platform_fee_pct"]),
                "advice_fee_pct": dec(p["advice_fee_pct"]),
                "min_term_years": dec(p["min_term_years"]),
                "description": p["description"],
                "spec_notes": p["spec_notes"],
            }
        )

    for key, points in SEED_PORTFOLIO_RETURNS.items():
        portfolio_id = portfolio_key_to_id[key]
        methodology = PORTFOLIO_RETURNS_METHODOLOGY_BY_KEY.get(key, PORTFOLIO_RETURNS_METHODOLOGY)
        for horizon, expected, lower, upper in points:
            PORTFOLIO_RETURNS.put_item(
                Item={
                    "portfolio_id": portfolio_id,
                    "horizon_years": dec(horizon),
                    "expected_return_pct": dec(expected),
                    "lower_return_pct": dec(lower),
                    "upper_return_pct": dec(upper),
                    "methodology": methodology,
                }
            )
