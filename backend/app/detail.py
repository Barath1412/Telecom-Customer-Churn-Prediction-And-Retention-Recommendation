"""
GET /api/customers/{customer_id} — live computation for every customer.

Runs the graph with provider="fake" (deterministic model + policy; no LLM needed),
and builds the response matching GET_customer_detail.json's shape.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pandas as pd

from . import cache, population, queue_state
from .errors import ApiError
from .score import _flatten_policy_trace, _provenance
from .settings import ML_ROOT

# Cache for queue_full.csv to avoid reading it on every request
_queue_full_df: pd.DataFrame | None = None
_queue_full_by_id: dict[str, dict[str, Any]] = {}
_recommended_ranks: dict[str, int] = {}


def _init_queue_data() -> None:
    global _queue_full_df, _queue_full_by_id, _recommended_ranks
    if _queue_full_df is not None:
        return
    csv_path = ML_ROOT / "artifacts" / "queue_full.csv"
    if not csv_path.exists():
        _queue_full_df = pd.DataFrame(columns=["customer_id", "arm", "p_churn", "status", "ev"])
        _queue_full_by_id = {}
        _recommended_ranks = {}
        return
    df = pd.read_csv(csv_path)
    _queue_full_df = df
    _queue_full_by_id = {row["customer_id"]: row for row in df.to_dict("records")}
    rec_df = df[df["status"] == "recommended"].sort_values("ev", ascending=False).reset_index(drop=True)
    _recommended_ranks = {cid: idx + 1 for idx, cid in enumerate(rec_df["customer_id"])}


def alternate_talk_track(alt: dict[str, Any]) -> str:
    return (
        f"Alternative: {alt['offer_name']} — costs "
        f"${alt['cost']:.2f}, expected value ${alt['expected_value']:.2f}. "
        "Present this if the customer declines the primary offer."
    )


def _approval_threshold() -> float:
    import yaml  # noqa: PLC0415

    cat_raw = yaml.safe_load((ML_ROOT / "data" / "offers.yaml").read_text())
    return float(cat_raw["policy"]["approval_required_above_cost"])


def get_customer_detail(customer_id: str) -> dict[str, Any]:
    record = population.get(customer_id)
    if record is None:
        _init_queue_data()
        if customer_id in _queue_full_by_id:
            row = _queue_full_by_id[customer_id]
            record = population.synthesize_record_from_queue_row(customer_id, row)
            population.add_customer(customer_id, record["customer"], record["cltv"])
            population.save_customer_records([record])
        else:
            raise ApiError(
                404,
                "CUSTOMER_NOT_FOUND",
                f"No customer {customer_id!r} in the source dataset.",
            )

    from . import narrate as narrate_mod  # noqa: PLC0415

    if narrate_mod._graph is None:
        narrate_mod.warm()

    from src.api_fixtures import _levers, band  # noqa: PLC0415
    from src.graph import _catalog  # noqa: PLC0415

    try:
        state = narrate_mod._graph.invoke(
            {
                "customer_id": record["customer_id"],
                "customer": record["customer"],
                "cltv": record["cltv"],
            },
            {"configurable": {"auto_approve": True, "provider": "fake"}},
        )
    except Exception as exc:
        raise ApiError(502, "DETAIL_FAILED", f"{type(exc).__name__}: {exc}")

    _init_queue_data()

    # rank and arm
    if customer_id in _queue_full_by_id:
        q_row = _queue_full_by_id[customer_id]
        arm = q_row.get("arm")
        rank = _recommended_ranks.get(customer_id)
        p_val = float(state["p_churn"])
        percentile = float(round(100.0 * (_queue_full_df["p_churn"] <= p_val).mean(), 1))
    else:
        arm = None
        rank = None
        percentile = None

    # recommendation
    offer_id = state.get("offer_id")
    cost = state.get("cost") or 0.0
    catalog = _catalog()

    if offer_id:
        try:
            offer = catalog.by_id(offer_id)
            delta_source = offer.delta_source
        except Exception:
            delta_source = None

        recommendation = {
            "offer_id": offer_id,
            "offer_name": state.get("offer_name"),
            "cost": cost,
            "delta_prior": state.get("delta_prior"),
            "delta_ci": state.get("delta_ci"),
            "delta_source": delta_source,
            "expected_value": state.get("ev"),
            "requires_approval": bool(cost > _approval_threshold()),
        }
    else:
        recommendation = None

    # alternatives
    alternatives = []
    if offer_id:
        for c in state.get("considered") or []:
            oid = c["offer_id"]
            if oid == offer_id:
                continue
            try:
                o = catalog.by_id(oid)
                name = o.name
                delta_prior = o.delta_prior
                delta_ci = list(o.delta_ci)
            except Exception:
                name = oid
                delta_prior = c.get("delta") or 0.0
                delta_ci = [0.0, 0.0]
            alt_item = {
                "offer_id": oid,
                "offer_name": name,
                "cost": float(c.get("cost", 0.0)),
                "delta_prior": delta_prior,
                "delta_ci": delta_ci,
                "expected_value": float(c.get("ev", 0.0)),
            }
            alt_item["talk_track"] = alternate_talk_track(alt_item)
            alternatives.append(alt_item)
        alternatives.sort(key=lambda a: a["expected_value"], reverse=True)

    # evidence
    evidence_ids = state.get("evidence_ids") or []
    if evidence_ids:
        evidence_text = state.get("evidence_text") or ""
        approx_tokens = max(1, len(evidence_text) // 4)
        evidence = {
            "ids": evidence_ids,
            "count": len(evidence_ids),
            "approx_tokens": approx_tokens,
        }
    else:
        evidence = {
            "ids": [],
            "count": 0,
            "approx_tokens": 0,
        }

    # narration from cache
    cached_entry = cache.cached.get(customer_id)
    if cached_entry:
        if isinstance(cached_entry, dict) and "narration" in cached_entry:
            narration = cached_entry["narration"]
        else:
            narration = cached_entry
    else:
        narration = None

    # Decision audit record if already acted upon
    decision = None
    if queue_state.state and customer_id in queue_state.state.actioned:
        act = queue_state.state.actioned[customer_id]
        off_oid = act.get("modified_offer_id") or act.get("offer_id")
        off_name = None
        if off_oid:
            try:
                off_name = catalog.by_id(off_oid).name
            except Exception:
                off_name = off_oid
        decision = {
            "action": act.get("action"),
            "actor": act.get("actor", "agent_42"),
            "reason_code": act.get("reason_code"),
            "acted_at": act.get("acted_at", ""),
            "note": act.get("note"),
            "offer_changed": bool(act.get("modified_offer_id") and act.get("modified_offer_id") != act.get("offer_id")),
            "offered_offer_id": off_oid,
            "offered_offer_name": off_name,
        }

    actionable = bool(
        queue_state.state
        and customer_id in queue_state.state.pending_ids()
        and decision is None
        and arm != "control"
        and state.get("status") == "recommended"
    )
    queue_pos = None
    if queue_state.state and customer_id in queue_state.state.pending_ids():
        queue_pos = queue_state.state.pending_ids().index(customer_id) + 1

    return {
        "rank": rank,
        "customer_id": customer_id,
        "arm": arm,
        "queue_position": queue_pos,
        "actionable": actionable,
        "decision": decision,
        "risk": {
            "p_churn": state["p_churn"],
            "risk_band": band(state["p_churn"]),
            "percentile": percentile,
        },
        "value": {
            "cltv": state["cltv"],
            "monthly_charges": state["monthly_charges"],
            "tenure_months": state["tenure_months"],
            "currency": "USD",
        },
        "levers": _levers(state.get("levers") or []),
        "recommendation": recommendation,
        "status": state.get("status"),
        "alternatives": alternatives,
        "vetoed": state.get("vetoed") or [],
        "attribution": state.get("attribution") or [],
        "attribution_disclaimer": state.get(
            "attribution_disclaimer",
            "Model attribution, not customer motive. These values show what drove "
            "the model's prediction. They are not causal and are not the "
            "customer's stated reason for leaving.",
        ),
        "evidence": evidence,
        "policy_trace": _flatten_policy_trace(
            state.get("policy_trace") or [], offer_id
        ),
        "profile": record["customer"],
        "provenance": _provenance(),
        "narration": narration,
    }
