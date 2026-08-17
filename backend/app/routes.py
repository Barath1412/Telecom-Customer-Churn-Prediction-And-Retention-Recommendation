"""
The endpoints, in the same order as the contract table in the README.

Five of them return a file from api-contract/ unchanged. The sixth records an agent
action. The seventh is the live one.

Paths and query parameters match retention-console-frontend/frontend/src/lib/api.ts
exactly -- that file is the client and it is not being changed.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Query, Request
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
#  read endpoints — dynamic queue
# --------------------------------------------------------------------------- #
@router.get("/queue")
def get_queue(
    status: str = Query("pending", pattern="^(pending|approved|rejected)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(40, ge=1, le=200),
) -> dict:
    ids = {
        "pending": queue_state.state.pending_ids(),
        "approved": queue_state.state.approved_ids(),
        "rejected": queue_state.state.rejected_ids(),
    }[status]

    start = (page - 1) * page_size
    page_ids = ids[start : start + page_size]

    items = []
    for i, cid in enumerate(page_ids):
        detail = detail_mod.get_customer_detail(cid)
        item = {
            **as_queue_item(detail),
            "queue_position": start + i + 1,
            "actionable": status == "pending" and (start + i) < queue_state.state.capacity,
        }

        if status in ("approved", "rejected"):
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

    return {
        "run_id": fixtures.queue()["run_id"],
        "capacity": queue_state.state.capacity,
        "total_eligible": len(queue_state.state.eligible_ids),
        "pending_total": len(ids) if status == "pending" else len(queue_state.state.pending_ids()),
        "approved_total": len(queue_state.state.approved_ids()),
        "rejected_total": len(queue_state.state.rejected_ids()),
        "status": status,
        "returned": len(items),
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.get("/summary")
def get_summary() -> dict:
    return fixtures.summary()


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
#  score — ad-hoc scoring for the Score page
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
    return result
