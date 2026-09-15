"""Loads the per-product spec JSON files in data/ (one per product_key,
e.g. data/liberty_retirement_annuity.json) — real, detailed product
documentation (fees, eligibility, FAQs, etc.), far more than any single
UI surface or AI prompt should show whole.

This module curates a SMALL, stable subset from each file — enough for
a "Learn more" panel and for the post-results chat to answer detailed
questions accurately — rather than exposing the raw JSON anywhere.
Fields not in the curated subset (full fee schedules, eligibility
rules, version history, etc.) are deliberately left out; they're
available in the source JSON directly if ever needed for something
more specific.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

_MAX_FEATURES = 5
_MAX_FAQS = 3
_MAX_ABOUT_CHARS = 800  # keeps the AI-context version bounded; the raw file itself may be much longer


def _load_all_specs() -> dict[str, dict]:
    """product_key -> parsed JSON, for every *.json file in data/ whose
    top-level product_id matches its own filename stem (a light sanity
    check against a stray unrelated JSON file ending up in data/)."""
    specs: dict[str, dict] = {}
    if not DATA_DIR.exists():
        return specs
    for path in DATA_DIR.glob("*.json"):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        product_id = data.get("product_id")
        if product_id and product_id == path.stem:
            specs[product_id] = data
    return specs


_SPECS = _load_all_specs()


def learn_more(product_key: str) -> dict | None:
    """Curated fields for a frontend 'Learn more' panel — about,
    a handful of key features, a handful of FAQs. Returns None if no
    spec file exists for this product_key."""
    spec = _SPECS.get(product_key)
    if spec is None:
        return None

    about = spec.get("about")
    features = [
        {"feature": f.get("feature"), "description": f.get("description")}
        for f in spec.get("key_features", [])[:_MAX_FEATURES]
        if f.get("feature") and f.get("description")
    ]
    faqs = [
        {"question": f.get("question"), "answer": f.get("answer")}
        for f in spec.get("faqs", [])[:_MAX_FAQS]
        if f.get("question") and f.get("answer")
    ]

    return {
        "product_name": spec.get("product_name"),
        "about": about,
        "key_features": features,
        "faqs": faqs,
    }


def context_blurb(product_key: str) -> str | None:
    """A short plain-text summary for injecting into the AI's system
    prompt — enough for it to answer detailed questions about this
    product accurately, small enough not to bloat every turn's token
    usage. None if no spec exists."""
    spec = _SPECS.get(product_key)
    if spec is None:
        return None

    about = (spec.get("about") or "").strip()
    if len(about) > _MAX_ABOUT_CHARS:
        about = about[:_MAX_ABOUT_CHARS].rsplit(" ", 1)[0] + "…"

    feature_lines = [
        f"  - {f['feature']}: {f['description']}"
        for f in spec.get("key_features", [])[:_MAX_FEATURES]
        if f.get("feature") and f.get("description")
    ]

    lines = [f"{spec.get('product_name', product_key)}:"]
    if about:
        lines.append(f"  {about}")
    lines.extend(feature_lines)
    return "\n".join(lines)
