"""
Retention console API.

    uvicorn app.main:app --port 8000            from backend/
    ./run.sh                                    same thing, with the checks

Two kinds of endpoint live here, and the difference is the whole design:

  * FIVE READ ENDPOINTS return the files in api-contract/ unchanged. Those files are
    generated from the trained model and the v3 catalog, so the rankings, costs and
    expected values on screen are real -- they are just a snapshot rather than a live
    query.

  * ONE LIVE ENDPOINT, POST /api/customers/{id}/narrate, runs the actual LangGraph
    pipeline for one customer on demand: score, attribute, extract levers, decide,
    retrieve evidence, call the model, validate, retry if a validator bites, fall
    back to a template if it bites twice.

Nothing in ml/ is imported for the read endpoints and nothing in ml/ is modified by
any of this.
"""
from __future__ import annotations

import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import errors, fixtures, narrate as narrate_mod
from .routes import router
from .settings import (
    API_CONTRACT_DIR,
    CORS_ORIGINS,
    ML_ROOT,
    NARRATION_PROVIDER,
    NARRATE_TIMEOUT_S,
)


if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    t0 = time.time()
    try:
        print("─" * 72, flush=True)
    except UnicodeEncodeError:
        print("-" * 72, flush=True)
    print("  retention console API", flush=True)
    print(f"  ml root         {ML_ROOT}", flush=True)
    print(f"  api contract    {API_CONTRACT_DIR}", flush=True)
    print(f"  provider        {NARRATION_PROVIDER}", flush=True)
    print(f"  narrate timeout {NARRATE_TIMEOUT_S:.0f}s", flush=True)

    try:
        n = len(fixtures.load_all())
        print(f"  contract        {n} files loaded", flush=True)
    except Exception as exc:                     # noqa: BLE001
        print(f"\n  FATAL: {exc}\n", flush=True)
        raise

    # Compile the graph and pull the model, catalog and spreadsheet into memory now,
    # so the first press of the button costs only the model call.
    try:
        info = narrate_mod.warm()
        print(f"  population      {info['customers']:,} customers", flush=True)
        print(f"  graph           compiled and warm in {info['warmup_s']}s", flush=True)
    except Exception as exc:                     # noqa: BLE001
        print(f"\n  FATAL during warm-up: {type(exc).__name__}: {exc}", flush=True)
        print(f"  Check that ML_ROOT is right and that `cd {ML_ROOT} && "
              f"python -m src.doctor` passes.\n", flush=True)
        raise

    from . import cache, detail as detail_mod, queue_state  # noqa: PLC0415
    import asyncio  # noqa: PLC0415

    cache.load()
    queue_state.state = queue_state.init_state()

    active_ids = queue_state.state.active_ids()
    detail_mod._init_queue_data()
    control_ids = {
        cid for cid in active_ids
        if detail_mod._queue_full_by_id.get(cid, {}).get("arm") == "control"
    }
    treatment_ids = [cid for cid in active_ids if cid not in control_ids]
    missing = [cid for cid in treatment_ids if cid not in cache.cached]
    if missing and NARRATION_PROVIDER != "fake":
        asyncio.create_task(cache.autowarm(missing))

    try:
        print(f"  ready in {time.time() - t0:.1f}s   →  http://localhost:8000/api/health",
              flush=True)
        print("─" * 72, flush=True)
    except UnicodeEncodeError:
        print(f"  ready in {time.time() - t0:.1f}s   ->  http://localhost:8000/api/health",
              flush=True)
        print("-" * 72, flush=True)
    yield


app = FastAPI(
    title="Retention console API",
    version="1.0.0",
    description="Churn retention decisions, with live LLM narration.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

errors.install(app)
app.include_router(router)


@app.middleware("http")
async def _log_slow_calls(request, call_next):
    """
    One line per narrate call, on stdout. Keep this terminal visible during a demo --
    watching `POST /api/customers/0295-PPHDO/narrate  200  7412ms  provider=gemini`
    appear as the note lands is worth more than any slide.
    """
    if not request.url.path.endswith("/narrate"):
        return await call_next(request)
    t0 = time.time()
    response = await call_next(request)
    ms = (time.time() - t0) * 1000
    print(f"  POST {request.url.path}  {response.status_code}  {ms:.0f}ms  "
          f"provider={request.query_params.get('provider') or NARRATION_PROVIDER}",
          flush=True, file=sys.stdout)
    return response
