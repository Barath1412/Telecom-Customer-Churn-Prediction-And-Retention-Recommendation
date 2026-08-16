"""
POST /api/score — ad-hoc scoring for the Score page.

Accepts a flat customer payload (19 attributes + cltv), runs the full graph with
provider="fake" (scoring is a deterministic model+policy question; no LLM needed),
and returns the six fields the contract specifies.

LEAKAGE GUARD
    The 14 quarantined fields come from src.contracts.BANNED.  They are matched
    case-sensitively, so "CLTV" (uppercase, banned) is rejected while "cltv"
    (lowercase, the legitimate input) is accepted.

POLICY TRACE SHAPE CONVERSION
    The graph returns a nested per-offer structure:
        [{"offer_id": "OFF-...", "rules": [{"rule_id", "passed", "evaluable",
                                            "detail", "unmet_requirement"}, ...]}]

    The contract wants a flat list:
        [{"rule_id", "state", "detail"}]  or  + "unmet_requirement"

    Conversion:
        evaluable is False          -> state "not_evaluable"  (carry unmet_requirement)
        evaluable and passed        -> state "pass"
        evaluable and not passed    -> state "veto"

    We flatten the rules for the chosen offer_id, falling back to the first entry
    if no offer was chosen, or [] if policy_trace is empty.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi.responses import JSONResponse

from .errors import ApiError, request_id
from .settings import ML_ROOT

# ---- leakage quarantine ---------------------------------------------------- #
# The list comes from src.contracts.BANNED (14 keys).  We match case-sensitively:
# "CLTV" is banned, "cltv" is the valid input field.
_QUARANTINED: list[str] = [
    "CLTV",
    "Churn Label",
    "Churn Reason",
    "Churn Score",
    "Churn Value",
    "City",
    "Count",
    "Country",
    "CustomerID",
    "Lat Long",
    "Latitude",
    "Longitude",
    "State",
    "Zip Code",
]

# ---- the 19 customer attributes the model was trained on ------------------- #
# Exactly the keys population.py reads from the spreadsheet.
_CUSTOMER_FIELDS = [
    "Gender",
    "Senior Citizen",
    "Partner",
    "Dependents",
    "Phone Service",
    "Multiple Lines",
    "Internet Service",
    "Online Security",
    "Online Backup",
    "Device Protection",
    "Tech Support",
    "Streaming TV",
    "Streaming Movies",
    "Paperless Billing",
    "Payment Method",
    "Contract",
    "Tenure Months",
    "Monthly Charges",
    "Total Charges",
]


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _provenance() -> dict:
    """
    Read model_registry.json + catalog version + kb version — the same block
    api_fixtures.py builds (around line 226 of src/api_fixtures.py).
    """
    import yaml  # noqa: PLC0415

    reg = json.loads((ML_ROOT / "artifacts" / "model_registry.json").read_text())
    sel = next(m for m in reg["models"] if m["selected"])
    cat_raw = yaml.safe_load((ML_ROOT / "data" / "offers.yaml").read_text())
    kb_version = json.loads(
        (ML_ROOT / "artifacts" / "evidence_ids.json").read_text()
    )["kb_version"]
    return {
        "model_name": sel["model_name"],
        "model_version": sel["version"],
        "model_roc_auc": round(sel["metrics"]["roc_auc"], 6),
        "catalog_version": cat_raw["catalog_version"],
        "kb_version": kb_version,
        "scored_at": _iso_now(),
    }


def _approval_threshold() -> float:
    import yaml  # noqa: PLC0415

    cat_raw = yaml.safe_load((ML_ROOT / "data" / "offers.yaml").read_text())
    return float(cat_raw["policy"]["approval_required_above_cost"])


def _flatten_policy_trace(policy_trace: list, offer_id: str | None) -> list:
    """
    Convert the graph's nested per-offer structure to the flat contract shape.

    Graph input:  [{"offer_id": ..., "rules": [{"rule_id", "passed", "evaluable",
                                                "detail", "unmet_requirement"}, ...]}, ...]
    Contract out: [{"rule_id", "state", "detail"} | + "unmet_requirement"]
    """
    if not policy_trace:
        return []

    # Pick the entry for the chosen offer; fall back to the first entry.
    entry = next(
        (e for e in policy_trace if e.get("offer_id") == offer_id),
        policy_trace[0],
    )
    rules = entry.get("rules", [])

    result = []
    for r in rules:
        evaluable = r.get("evaluable", True)
        passed = r.get("passed", False)

        if not evaluable:
            state = "not_evaluable"
        elif passed:
            state = "pass"
        else:
            state = "veto"

        item: dict[str, Any] = {
            "rule_id": r["rule_id"],
            "state": state,
            "detail": r.get("detail", ""),
        }
        if state == "not_evaluable":
            item["unmet_requirement"] = r.get("unmet_requirement", "")
        result.append(item)
    return result


async def score(raw_body: dict) -> dict | JSONResponse:
    """
    Run the graph and build the six-key response.

    Called from routes.py with the already-parsed request body dict.  The 422
    path for missing/invalid fields is handled by FastAPI before we get here
    (the ScoreRequest pydantic model in routes.py).  We only handle leakage
    rejection (400) and the happy path here.
    """
    # ---- 1. leakage guard ------------------------------------------------- #
    found = [k for k in raw_body if k in _QUARANTINED]
    if found:
        rid = request_id()
        fields = [
            {"field": f, "message": "quarantined: model-output leak"}
            for f in found
        ]
        err: dict = {
            "code": "LEAKAGE_REJECTED",
            "message": (
                "Payload contained a quarantined field. "
                "The upstream system must not expose it."
            ),
            "fields": fields,
            "quarantined_fields": _QUARANTINED,
            "request_id": rid,
        }
        return JSONResponse(status_code=400, content={"error": err})

    # ---- 2. extract the 19 customer fields -------------------------------- #
    missing_fields = [f for f in _CUSTOMER_FIELDS if f not in raw_body]
    if missing_fields:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Request failed field validation",
            [{"field": f, "message": "field required"} for f in missing_fields],
        )
    if "cltv" not in raw_body:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Request failed field validation",
            [{"field": "cltv", "message": "field required"}],
        )

    customer = {f: raw_body[f] for f in _CUSTOMER_FIELDS}
    cltv = float(raw_body["cltv"])

    # ---- 3. run the graph (always provider="fake") ------------------------ #
    from . import narrate as narrate_mod  # noqa: PLC0415

    if narrate_mod._graph is None:
        narrate_mod.warm()

    from src.api_fixtures import _levers, band  # noqa: PLC0415

    state = narrate_mod._graph.invoke(
        {
            "customer_id": "SCORE-ADHOC",
            "customer": customer,
            "cltv": cltv,
        },
        {"configurable": {"auto_approve": True, "provider": "fake"}},
    )

    # ---- 4. build the response -------------------------------------------- #
    offer_id = state.get("offer_id")
    cost = state.get("cost") or 0.0

    if offer_id:
        # delta_source is on the Offer object in the catalog, not in graph state.
        from src.graph import _catalog  # noqa: PLC0415

        try:
            offer = _catalog().by_id(offer_id)
            delta_source = offer.delta_source
        except Exception:
            delta_source = None

        recommendation: dict | None = {
            "offer_id": offer_id,
            "offer_name": state.get("offer_name"),
            "cost": cost,
            "delta_prior": state.get("delta_prior"),
            "delta_ci": state.get("delta_ci"),
            "delta_source": delta_source,
            "expected_value": state.get("ev"),
            "requires_approval": cost > _approval_threshold(),
        }
    else:
        recommendation = None

    return {
        "p_churn": state["p_churn"],
        "risk_band": band(state["p_churn"]),
        "levers": _levers(state.get("levers") or []),
        "recommendation": recommendation,
        "policy_trace": _flatten_policy_trace(
            state.get("policy_trace") or [], offer_id
        ),
        "provenance": _provenance(),
    }
