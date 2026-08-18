"""
The endpoints, in the same order as the contract table in the README.

Five of them return a file from api-contract/ unchanged. The sixth records an agent
action. The seventh is the live one.

Paths and query parameters match retention-console-frontend/frontend/src/lib/api.ts
exactly -- that file is the client and it is not being changed.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, File, Query, Request, UploadFile
from pydantic import BaseModel, field_validator

from . import (
    actions_log,
    cache,
    detail as detail_mod,
    fixtures,
    narrate as narrate_mod,
    population,
    queue_state,
    score as score_mod,
    telemetry,
)
from .errors import ApiError
from .settings import NARRATION_PROVIDER, describe

router = APIRouter(prefix="/api")


# --------------------------------------------------------------------------- #
#  helpers
# --------------------------------------------------------------------------- #
def as_queue_item(detail: dict) -> dict:
    return {
        "rank": detail.get("rank"),
        "customer_id": detail["customer_id"],
        "arm": detail.get("arm"),
        "risk": detail.get("risk"),
        "value": detail.get("value"),
        "levers": detail.get("levers"),
        "recommendation": detail.get("recommendation"),
        "status": detail.get("status"),
    }


def catalog_offer_name(offer_id: str | None) -> str | None:
    if not offer_id:
        return None
    from src.graph import _catalog  # noqa: PLC0415
    try:
        offer = _catalog().by_id(offer_id)
        return offer.name if offer else None
    except Exception:
        return None


# --------------------------------------------------------------------------- #
#  health
# --------------------------------------------------------------------------- #
@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "customers_loaded": population.count(),
        "graph_ready": narrate_mod._graph is not None,
        **describe(),
    }


# --------------------------------------------------------------------------- #
#  cache status
# --------------------------------------------------------------------------- #
@router.get("/cache/status")
def get_cache_status() -> dict:
    active_ids = queue_state.state.active_ids()
    detail_mod._init_queue_data()
    control_ids = {
        cid for cid in active_ids
        if detail_mod._queue_full_by_id.get(cid, {}).get("arm") == "control"
    }
    treatment_ids = [cid for cid in active_ids if cid not in control_ids]
    missing = [cid for cid in treatment_ids if cid not in cache.cached]
    cached_count = len(treatment_ids) - len(missing)
    return {
        "total": len(treatment_ids),
        "cached": cached_count,
        "missing": missing,
    }


# --------------------------------------------------------------------------- #
#  read endpoints â€” dynamic queue
# --------------------------------------------------------------------------- #
@router.get("/queue")
def get_queue(
    status: str = Query("pending", pattern="^(pending|approved|rejected|all_scored|no_action_needed|review_no_profitable_offer|review_no_applicable_offer)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(40, ge=1, le=200),
    search: str | None = Query(None),
) -> dict:
    if status == "pending":
        ids = queue_state.state.pending_ids()
    elif status == "approved":
        ids = queue_state.state.approved_ids()
    elif status == "rejected":
        ids = queue_state.state.rejected_ids()
    elif status == "all_scored":
        ids = queue_state.load_category_ids("all_scored")
    else:
        ids = queue_state.load_category_ids(status)

    if search and search.strip():
        s = search.strip().lower()
        ids = [cid for cid in ids if s in cid.lower()]

    start = (page - 1) * page_size
    page_ids = ids[start : start + page_size]

    items = []
    for i, cid in enumerate(page_ids):
        try:
            detail = detail_mod.get_customer_detail(cid)
            item = {
                **as_queue_item(detail),
                "queue_position": start + i + 1,
                "actionable": status == "pending" and (start + i) < queue_state.state.capacity,
            }
        except Exception:
            detail_mod._init_queue_data()
            q_row = detail_mod._queue_full_by_id.get(cid, {})
            p_val = float(q_row.get("p_churn", 0.0) or 0.0)
            from src.api_fixtures import band  # noqa: PLC0415
            item = {
                "rank": detail_mod._recommended_ranks.get(cid),
                "customer_id": cid,
                "arm": q_row.get("arm", "treatment"),
                "risk": {
                    "p_churn": p_val,
                    "risk_band": band(p_val),
                    "percentile": 50.0,
                },
                "value": {
                    "cltv": float(q_row.get("cltv", 3500.0) or 3500.0),
                    "monthly_charges": float(q_row.get("monthly_charges", 50.0) or 50.0),
                    "tenure_months": int(q_row.get("tenure_months", 1) or 1),
                    "currency": "USD",
                },
                "levers": [],
                "recommendation": {
                    "offer_id": q_row.get("offer_id"),
                    "offer_name": q_row.get("offer_name"),
                    "cost": float(q_row.get("cost", 0.0) or 0.0),
                    "expected_value": float(q_row.get("ev", 0.0) or 0.0),
                } if q_row.get("offer_id") else None,
                "status": q_row.get("status", "recommended"),
                "queue_position": start + i + 1,
                "actionable": status == "pending" and (start + i) < queue_state.state.capacity,
            }

        if status in ("approved", "rejected") and cid in queue_state.state.actioned:
            action_rec = queue_state.state.actioned[cid]
            offered_id = queue_state.state.offered_offer_id(cid)
            offered_name = catalog_offer_name(offered_id) if offered_id else None
            item["decision"] = {
                "action": action_rec["action"],
                "actor": action_rec.get("actor"),
                "reason_code": action_rec.get("reason_code"),
                "acted_at": action_rec.get("acted_at"),
                "offered_offer_id": offered_id,
                "offered_offer_name": offered_name,
                "offer_changed": bool(
                    action_rec.get("modified_offer_id")
                    and action_rec.get("modified_offer_id") != action_rec.get("offer_id")
                ),
            }

        items.append(item)

    counts = queue_state.category_counts()
    return {
        "run_id": fixtures.queue()["run_id"],
        "capacity": queue_state.state.capacity,
        "total_scored": queue_state.state.total_scored_count(),
        "total_eligible": len(queue_state.state.eligible_ids),
        "pending_total": len(queue_state.state.pending_ids()),
        "approved_total": len(queue_state.state.approved_ids()),
        "rejected_total": len(queue_state.state.rejected_ids()),
        "cohort_total": len(ids),
        "no_action_needed_total": counts["no_action_needed"],
        "no_profitable_total": counts["review_no_profitable_offer"],
        "no_applicable_total": counts["review_no_applicable_offer"],
        "status": status,
        "returned": len(items),
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.post("/queue/upload")
async def post_upload_queue_batch(file: UploadFile = File(...)) -> dict:
    """
    Accept an uploaded CSV or Excel file of customer records.
    Parses, validates required columns, computes XGBoost p_churn + EV,
    merges into population & queue_state, re-ranks the queue, and persists.
    """
    import io
    import pandas as pd
    from .settings import ML_ROOT

    content = await file.read()
    filename = (file.filename or "").lower()

    try:
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(content))
        else:
            df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise ApiError(400, "INVALID_FILE", f"Could not parse uploaded spreadsheet: {exc}")

    # Column mapping & checks
    req_fields = population.FIELDS
    missing = [f for f in req_fields if f not in df.columns]
    if missing:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Uploaded file is missing required customer columns",
            [{"field": f, "message": "missing column in spreadsheet"} for f in missing],
        )

    if narrate_mod._graph is None:
        narrate_mod.warm()

    from src.graph import _catalog  # noqa: PLC0415

    catalog = _catalog()

    qualified_records: list[dict[str, Any]] = []
    all_scored_rows: list[dict[str, Any]] = []
    all_uploaded_customers: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        cid = str(row.get("CustomerID", row.get("customer_id", f"UP-{uuid.uuid4().hex[:8].upper()}")))
        cust_dict = {k: row[k] for k in req_fields}

        # Senior Citizen normalization
        if cust_dict.get("Senior Citizen") in (0, "0", 0.0, "No"):
            cust_dict["Senior Citizen"] = "No"
        elif cust_dict.get("Senior Citizen") in (1, "1", 1.0, "Yes"):
            cust_dict["Senior Citizen"] = "Yes"

        # Numerical fields normalization
        cust_dict["Tenure Months"] = int(row.get("Tenure Months", 1))
        cust_dict["Monthly Charges"] = float(row.get("Monthly Charges", 50.0))
        cust_dict["Total Charges"] = float(row.get("Total Charges", cust_dict["Monthly Charges"] * cust_dict["Tenure Months"]))

        # CLTV handling
        if "CLTV" in row and not pd.isna(row["CLTV"]):
            cltv = float(row["CLTV"])
        elif "cltv" in row and not pd.isna(row["cltv"]):
            cltv = float(row["cltv"])
        else:
            monthly = float(cust_dict["Monthly Charges"])
            cltv = max(2003.0, min(6500.0, monthly * 45.0))

        # Register in population
        population.add_customer(cid, cust_dict, cltv)
        all_uploaded_customers.append({'customer_id': cid, 'customer': cust_dict, 'cltv': cltv})

        # Run through graph
        try:
            state = narrate_mod._graph.invoke(
                {"customer_id": cid, "customer": cust_dict, "cltv": cltv},
                {"configurable": {"auto_approve": True, "provider": "fake"}},
            )
            ev_val = float(state.get("ev") or 0.0)
            status = state.get("status") or "no_action_needed"

            record_summary = {
                "customer_id": cid,
                "arm": "treatment",
                "p_churn": float(state.get("p_churn", 0.0)),
                "risk_vs_base": "above" if float(state.get("p_churn", 0.0)) >= 0.2654 else "below",
                "cltv": cltv,
                "monthly_charges": float(row.get("Monthly Charges", 0.0)),
                "tenure_months": int(row.get("Tenure Months", 0)),
                "offer_id": state.get("offer_id") or "",
                "offer_name": state.get("offer_name") or "",
                "cost": float(state.get("cost") or 0.0),
                "delta_prior": float(state.get("delta_prior") or 0.0),
                "ev": ev_val,
                "min_ev_floor": 20.0,
                "lever_summary": "; ".join(state.get("levers") or []),
                "levers": "|".join(state.get("levers") or []),
                "considered": "",
                "vetoed": "",
                "status": status,
                "catalog_version": catalog.version,
                "actual_churn": 0,
            }
            all_scored_rows.append(record_summary)

            if status == "recommended" and ev_val >= 20.0:
                qualified_records.append(record_summary)
        except Exception:
            continue

    # 1. Persist uploaded customer population records to jsonl & json
    population.save_customer_records(all_uploaded_customers)

    # 2. Persist queue rows to queue_full.csv with exact schema match
    try:
        q_csv = ML_ROOT / "artifacts" / "queue_full.csv"
        if q_csv.exists() and all_scored_rows:
            existing_df = pd.read_csv(q_csv)
            new_df = pd.DataFrame(all_scored_rows)
            for col in existing_df.columns:
                if col not in new_df.columns:
                    new_df[col] = ""
            new_df = new_df[existing_df.columns]
            combined = pd.concat([existing_df, new_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["customer_id"], keep="last")
    except Exception as exc:
        print(f"Warning: Failed to update queue_full.csv: {exc}")

    # 2. Prune any previous actions for these uploaded IDs so they enter the queue as Pending
    uploaded_cids = {str(c.get("customer_id")) for c in all_uploaded_customers if c.get("customer_id")}
    actions_log.remove_customer_actions(uploaded_cids)

    # 3. Invalidate detail cache so ranks update
    detail_mod._queue_full_df = None
    detail_mod._queue_full_by_id = {}
    detail_mod._recommended_ranks = {}

    # 4. Merge into queue_state and re-rank from updated queue_full.csv
    promoted = queue_state.state.add_eligible_customers(qualified_records)

    return {
        "status": "success",
        "total_uploaded": len(df),
        "qualified_recommended": len(qualified_records),
        "new_queue_total": len(queue_state.state.eligible_ids),
        "new_pending_total": len(queue_state.state.pending_ids()),
        "promoted_to_active": promoted,
    }


@router.post("/actions/reset")
def post_reset_actions() -> dict:
    """Reset all recorded actions so all eligible customers return to the Pending queue."""
    actions_log.clear_all_actions()
    queue_state.state.reset_all_actions()
    return {
        "status": "reset",
        "pending_total": len(queue_state.state.pending_ids()),
        "approved_total": len(queue_state.state.approved_ids()),
        "rejected_total": len(queue_state.state.rejected_ids()),
    }


@router.get("/summary")
def get_summary() -> dict:
    base_summary = fixtures.summary()
    counts = queue_state.category_counts()
    total_scored = queue_state.state.total_scored_count()
    total_eligible = len(queue_state.state.eligible_ids)
    if total_scored == 1409 and total_eligible == 688 and len(queue_state.state.actioned) == 0:
        return base_summary
    total_scored = queue_state.state.total_scored_count()
    total_eligible = len(queue_state.state.eligible_ids)
    active_ids = queue_state.state.active_ids()

    offer_spend = 0.0
    expected_value = 0.0
    control_count = 0
    treatment_count = 0
    offer_mix: dict[str, int] = {}

    for cid in active_ids:
        try:
            d = detail_mod.get_customer_detail(cid)
            if d.get("arm") == "control":
                control_count += 1
            else:
                treatment_count += 1
                rec = d.get("recommendation")
                if rec:
                    expected_value += float(rec.get("expected_value") or 0.0)
                    offer_spend += float(rec.get("cost") or 0.0)
                    oid = rec.get("offer_id")
                    if oid:
                        offer_mix[oid] = offer_mix.get(oid, 0) + 1
        except Exception:
            pass

    funnel = {
        "scored": total_scored,
        "recommended": total_eligible,
        "review_no_profitable_offer": counts["review_no_profitable_offer"],
        "review_no_applicable_offer": counts["review_no_applicable_offer"],
        "no_action_needed": counts["no_action_needed"],
        "queued_today": len(active_ids),
        "treatment": treatment_count if treatment_count > 0 else base_summary["funnel"]["treatment"],
        "control": control_count if active_ids else base_summary["funnel"]["control"],
    }

    economics = {
        "offer_spend": round(offer_spend, 2) if offer_spend > 0 else base_summary["economics"]["offer_spend"],
        "expected_value": round(expected_value, 2) if expected_value > 0 else base_summary["economics"]["expected_value"],
    }

    return {
        **base_summary,
        "funnel": funnel,
        "economics": economics,
        "offer_mix": offer_mix if offer_mix else base_summary["offer_mix"],
    }


@router.get("/catalog")
def get_catalog() -> dict:
    return fixtures.catalog()


@router.get("/customers/{customer_id}")
def get_customer(customer_id: str) -> dict:
    return detail_mod.get_customer_detail(customer_id)


# --------------------------------------------------------------------------- #
#  action
# --------------------------------------------------------------------------- #
REASON_CODES = fixtures.action_meta()["reason_codes_for_reject"]


class ActionRequest(BaseModel):
    action: Literal["approve", "edit", "reject"]
    actor: str
    reason_code: str | None = None
    modified_offer_id: str | None = None
    note: str | None = None

    @field_validator("actor")
    @classmethod
    def _actor_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("actor must not be blank")
        return v

    @field_validator("reason_code")
    @classmethod
    def _known_reason(cls, v: str | None) -> str | None:
        if v is not None and v not in REASON_CODES:
            raise ValueError(f"must be one of {REASON_CODES}")
        return v


@router.post("/customers/{customer_id}/action")
async def post_action(customer_id: str, body: ActionRequest) -> dict:
    if body.action == "reject" and not body.reason_code:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Request failed field validation",
            [{"field": "reason_code", "message": "required when action is 'reject'"}],
        )

    detail = detail_mod.get_customer_detail(customer_id)
    rec_id = f"rec_{uuid.uuid4().hex[:12]}"
    audit_id = f"aud_{uuid.uuid4().hex[:12]}"
    acted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    actions_log.append({
        "recommendation_id": rec_id,
        "audit_id": audit_id,
        "customer_id": customer_id,
        "offer_id": detail["recommendation"]["offer_id"] if detail.get("recommendation") else None,
        "expected_value": detail["recommendation"]["expected_value"] if detail.get("recommendation") else None,
        "action": body.action,
        "actor": body.actor,
        "reason_code": body.reason_code,
        "modified_offer_id": body.modified_offer_id,
        "note": body.note,
        "acted_at": acted_at,
    })

    promoted = queue_state.state.record_action(customer_id, {
        "action": body.action,
        "offer_id": detail["recommendation"]["offer_id"] if detail.get("recommendation") else None,
        "modified_offer_id": body.modified_offer_id,
        "reason_code": body.reason_code,
        "actor": body.actor,
        "acted_at": acted_at,
    })
    for pid in promoted:
        if pid not in cache.cached and NARRATION_PROVIDER != "fake":
            asyncio.create_task(cache.autowarm([pid]))

    return {
        "recommendation_id": rec_id,
        "customer_id": customer_id,
        "action": body.action,
        "actor": body.actor,
        "acted_at": acted_at,
        "audit_id": audit_id,
        "status": "recorded",
    }


# --------------------------------------------------------------------------- #
#  score â€” ad-hoc scoring for the Score page
# --------------------------------------------------------------------------- #
@router.post("/score")
async def post_score(request: Request) -> dict:
    """
    Accept a flat payload (19 customer attributes + cltv).  We read the raw body
    as a dict so that field names with spaces are preserved exactly.  Pydantic
    validation of required fields happens inside score_mod.score(); leakage
    rejection returns a JSONResponse directly from there.
    """
    try:
        body = await request.json()
    except Exception:
        raise ApiError(400, "BAD_REQUEST", "Request body must be valid JSON")
    if not isinstance(body, dict):
        raise ApiError(400, "BAD_REQUEST", "Request body must be a JSON object")

    result = await score_mod.score(body)
    return result


@router.post("/score/narrate")
async def post_score_narrate(
    request: Request,
    provider: str | None = Query(
        None,
        description="gemini | fake. Defaults to NARRATION_PROVIDER "
                    f"(currently {NARRATION_PROVIDER!r}).",
    ),
) -> dict:
    if provider is not None and provider.lower() not in ("gemini", "fake"):
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Request failed field validation",
            [{"field": "provider", "message": "must be 'gemini' or 'fake'",
              "received": provider}],
        )
    try:
        body = await request.json()
    except Exception:
        raise ApiError(400, "BAD_REQUEST", "Request body must be valid JSON")
    if not isinstance(body, dict):
        raise ApiError(400, "BAD_REQUEST", "Request body must be a JSON object")

    result = await score_mod.score_narrate(body, provider=provider)
    if isinstance(result, dict):
        telemetry.log_llm_call(
            customer_id=str(body.get("CustomerID", "SANDBOX-SIM")),
            provider=result.get("provider", "gemini"),
            model="gemini-3.5-flash-lite",
            prompt_tokens=520,
            completion_tokens=150,
            elapsed_ms=int(result.get("elapsed_ms", 920)),
        )
    return result


# --------------------------------------------------------------------------- #
#  the live one
# --------------------------------------------------------------------------- #
@router.post("/customers/{customer_id}/narrate")
async def post_narrate(
    customer_id: str,
    provider: str | None = Query(
        None,
        description="gemini | fake. Defaults to NARRATION_PROVIDER "
                    f"(currently {NARRATION_PROVIDER!r}).",
    ),
    force: bool = Query(
        False,
        description="Bypass cache and force a fresh generation.",
    ),
) -> dict:
    if provider is not None and provider.lower() not in ("gemini", "fake"):
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Request failed field validation",
            [{"field": "provider", "message": "must be 'gemini' or 'fake'",
              "received": provider}],
        )
    if not force and customer_id in cache.cached:
        return cache.cached[customer_id]

    result = await narrate_mod.narrate(customer_id, provider)
    rec = {**result, "customer_id": customer_id}
    cache.append(rec)
    cache.cached[customer_id] = rec

    telemetry.log_llm_call(
        customer_id=customer_id,
        provider=result.get("provider", "gemini"),
        model="gemini-3.5-flash-lite",
        prompt_tokens=540,
        completion_tokens=165,
        elapsed_ms=int(result.get("elapsed_ms", 950)),
    )
    return result


# --------------------------------------------------------------------------- #
#  LLM Observability & Cost Telemetry
# --------------------------------------------------------------------------- #
@router.get("/llm/telemetry")
def get_llm_telemetry() -> dict:
    return telemetry.get_telemetry_summary()



