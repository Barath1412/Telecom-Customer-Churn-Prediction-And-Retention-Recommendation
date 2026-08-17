"""
The live endpoint's engine: run the real graph for one customer, right now.

WHAT THIS DOES NOT DO
    It does not score, choose an offer, price it, build a prompt, retrieve evidence,
    or validate anything. All nine nodes of that already exist in ml/src/graph.py and
    are covered by 285 tests. This module calls `graph.invoke` and reshapes the final
    state into a response. If you find yourself writing a prompt string or a rule in
    here, something has gone wrong.

WHY auto_approve=True
    Node 8 (human_review) calls `interrupt()` and waits for a person. That is correct
    for a production queue and useless for an HTTP request, which has to return. With
    auto_approve the node records an automatic approval and the run completes. The
    graph is compiled without a checkpointer, so no pause is even possible -- see the
    docstring on compile_graph().

WHY A THREADPOOL
    `graph.invoke` is synchronous and CPU-bound in places (SHAP attribution) and
    network-bound in others (the Gemini call). Running it directly in the event loop
    would block every other request, including /api/health, for the whole 5-15
    seconds. run_in_threadpool keeps the server responsive.

ON THE TIMEOUT
    asyncio.wait_for cancels the *await*, not the thread -- the graph keeps running in
    the background until it finishes on its own. That is acceptable here: it frees the
    request, the client gets a clean 504, and the orphaned thread exits within a few
    seconds. It is noted rather than hidden because it would matter under real load.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from fastapi.concurrency import run_in_threadpool

from . import population
from .errors import ApiError
from .settings import NARRATE_TIMEOUT_S, NARRATION_PROVIDER

_graph = None


def _levers_helper(codes: list) -> list:
    """
    Convert raw lever codes to {code, label} dicts using the same helper
    api_fixtures.py uses.  Imported lazily so settings (and sys.path) are
    set up before the first call — which happens after warm().
    """
    from src.api_fixtures import _levers  # noqa: PLC0415

    return _levers(codes)


def warm() -> dict:
    """
    Compile the graph and force the model, catalog and spreadsheet into memory.

    Called once at startup. Without it the first person to press the button pays
    ~4 seconds of joblib load and pandas parsing on top of the model call, which
    looks like a hang.
    """
    global _graph
    t0 = time.time()
    from src.graph import _catalog, _model, compile_graph  # noqa: E402

    _graph = compile_graph()          # no checkpointer -> no interrupt possible
    _model()                          # lru_cache: 3.7 MB joblib + SHAP explainer
    _catalog()                        # lru_cache: offers.yaml
    n = population.load()             # 7,043 rows from the spreadsheet
    return {"customers": n, "warmup_s": round(time.time() - t0, 2)}


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _uncertainty(state: dict) -> str | None:
    """
    Composed in code from delta_prior/delta_ci, never by the model -- the same
    function api_fixtures.py uses, imported rather than copied so the wording on
    screen cannot drift from the wording in the contract.

    Returns None when there is no offer. Without that guard a
    review_no_profitable_offer customer gets "the retention effect used to rank this
    offer is a business assumption of 0.00 (range 0.00-0.00)", which is a sentence
    about an offer that does not exist. Caught by running the endpoint against
    5461-QKNTN, whose whole purpose is to be the customer with nothing to sell.
    """
    if not state.get("offer_id"):
        return None
    prior, ci = state.get("delta_prior"), state.get("delta_ci")
    if prior is None or not ci:
        return None
    from src.api_fixtures import _uncertainty_note  # noqa: E402

    return _uncertainty_note(float(prior), list(ci))


def _invoke(customer_id: str, customer: dict, cltv: float, provider: str) -> tuple[dict, float]:
    if _graph is None:
        warm()
    t0 = time.time()
    state = _graph.invoke(
        {
            "customer_id": customer_id,
            "customer": customer,
            "cltv": cltv,
        },
        {"configurable": {"auto_approve": True, "provider": provider}},
    )
    return state, (time.time() - t0) * 1000.0


async def _narrate_core(customer_id: str, customer: dict, cltv: float, provider: str | None = None) -> dict:
    provider = (provider or NARRATION_PROVIDER).lower()
    try:
        state, elapsed_ms = await asyncio.wait_for(
            run_in_threadpool(_invoke, customer_id, customer, cltv, provider),
            timeout=NARRATE_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        raise ApiError(
            504,
            "NARRATION_TIMEOUT",
            f"The model did not respond within {NARRATE_TIMEOUT_S:.0f}s. "
            f"This is a network or provider problem, not a data problem — retry.",
        )
    except ApiError:
        raise
    except Exception as exc:                     # noqa: BLE001 - surfaced deliberately
        raise ApiError(
            502,
            "NARRATION_FAILED",
            f"{type(exc).__name__}: {exc}",
        )

    draft = state.get("draft") or {}
    if not draft:
        # Two validator failures ship the template instead; a truly empty draft means
        # the provider never returned anything usable. Never return half a note.
        raise ApiError(
            502,
            "NARRATION_FAILED",
            "The graph completed but produced no draft. "
            f"Violations: {state.get('violations') or 'none reported'}",
        )

    return {
        "customer_id": customer_id,
        "narration": {
            "summary": draft.get("summary"),
            "why": draft.get("why"),
            "talk_track": draft.get("talk_track"),
            "evidence_ids": draft.get("evidence_ids") or [],
            "uncertainty_note": _uncertainty(state),
            # "llm" = the model wrote it. "template" = it failed twice and the
            # deterministic fallback shipped instead. The UI shows the difference.
            "source": state.get("source"),
            "model": state.get("llm_model"),
            "validator_attempts": int(state.get("attempts") or 0),
            "generated_at": _iso_now(),
        },
        # Proof, on every response, that narration did not move the decision. The
        # graph asserts this internally in persist(); returning it lets anyone check.
        "decision": {
            "status": state.get("status"),
            "offer_id": state.get("offer_id"),
            "offer_name": state.get("offer_name"),
            "cost": state.get("cost"),
            "expected_value": state.get("ev"),
            "p_churn": state.get("p_churn"),
            "levers": _levers_helper(state.get("levers") or []),
        },
        "violations": state.get("violations") or [],
        "provider": provider,
        "elapsed_ms": round(elapsed_ms, 1),
    }


async def narrate(customer_id: str, provider: str | None = None) -> dict:
    record = population.get(customer_id)
    if record is None:
        raise ApiError(
            404,
            "CUSTOMER_NOT_FOUND",
            f"No customer {customer_id!r} in the source dataset.",
        )
    return await _narrate_core(
        customer_id=record["customer_id"],
        customer=record["customer"],
        cltv=record["cltv"],
        provider=provider,
    )
