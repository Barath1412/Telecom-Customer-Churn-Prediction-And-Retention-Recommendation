"""
The nine files in api-contract/ are the contract, and they are returned unchanged.

They are not placeholder data. They were generated from the trained model, the v3
offer catalog and the knowledge base by `python -m src.api_fixtures` -- real rankings,
real expected-value arithmetic, real policy traces. The one part that is NOT model
output is the `narration` block on the customer fixtures, which is a hand-written
example marked `"source": "example_fixture"`. Live narration comes from
POST /api/customers/{id}/narrate, which runs the actual graph.

Loaded once at import. No response model wraps them: a pydantic model would silently
drop a field the contract has and this service does not know about, and the whole
point is that the JSON wins.
"""
from __future__ import annotations

import json
from pathlib import Path

from .settings import API_CONTRACT_DIR

REQUIRED = [
    "GET_queue.json",
    "GET_customer_detail.json",
    "GET_customer_no_offer.json",
    "GET_summary.json",
    "GET_catalog.json",
    "POST_action.json",
    "POST_score.json",
    "ERROR_validation.json",
    "ERROR_leakage.json",
]

_cache: dict[str, dict] = {}


def load_all() -> dict[str, dict]:
    if _cache:
        return _cache
    missing = [f for f in REQUIRED if not (API_CONTRACT_DIR / f).exists()]
    if missing:
        raise FileNotFoundError(
            f"api-contract is incomplete at {API_CONTRACT_DIR}. Missing: {missing}. "
            f"Regenerate with `cd ml && python -m src.api_fixtures`, or set "
            f"API_CONTRACT_DIR."
        )
    for f in REQUIRED:
        _cache[f] = json.loads(Path(API_CONTRACT_DIR / f).read_text(encoding="utf-8"))
    return _cache


def get(name: str) -> dict:
    return load_all()[name]


# ---- convenience accessors, so routes.py reads like the contract table ---- #
def queue() -> dict:
    return get("GET_queue.json")


def summary() -> dict:
    return get("GET_summary.json")


def catalog() -> dict:
    return get("GET_catalog.json")


def customer_detail() -> dict:
    return get("GET_customer_detail.json")


def customer_no_offer() -> dict:
    return get("GET_customer_no_offer.json")


def action_response() -> dict:
    """POST_action.json documents the endpoint; only response_example is the body."""
    return get("POST_action.json")["response_example"]


def action_meta() -> dict:
    d = get("POST_action.json")
    return {"actions": d["actions"], "reason_codes_for_reject": d["reason_codes_for_reject"]}
