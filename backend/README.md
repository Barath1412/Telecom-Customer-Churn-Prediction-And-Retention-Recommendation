# Retention console API

FastAPI service. Five endpoints serve the generated API contract; one runs the real
LangGraph pipeline live, on demand, for a single customer.

---

## Repository structure this expects

```
Telecom-Customer-Churn-Prediction-And-Retention-Recommendation/
├── ml/                                       the LangGraph project — NOT modified
│   ├── .env                                  YOUR GEMINI KEY (gitignored)
│   ├── .env.example
│   ├── requirements.txt
│   ├── artifacts/
│   │   ├── churn_model_v1.joblib
│   │   ├── churn_model_v1_attribution.joblib
│   │   ├── evidence_ids.json
│   │   ├── model_registry.json
│   │   ├── queue_audit.json
│   │   ├── queue_full.csv
│   │   └── queue_top40.csv
│   ├── data/
│   │   ├── Telco_customer_churn.xlsx         7,043 customers — the narrate source
│   │   ├── offers.yaml                       catalog v3, 6 offers
│   │   └── kb/knowledge_base.md
│   ├── samples/                              34 sample customers + customers_200.jsonl
│   ├── src/                                  26 modules incl. graph.py, decision.py
│   └── tests/                                285 tests
│
├── backend/                                  THIS SERVICE
│   ├── README.md                             this file
│   ├── requirements.txt
│   ├── run.sh
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                           app, CORS, error handlers, warm-up
│   │   ├── routes.py                         the 7 endpoints
│   │   ├── narrate.py                        live graph.invoke() + timeout
│   │   ├── population.py                     spreadsheet -> customer records
│   │   ├── fixtures.py                       loads api-contract/*.json
│   │   ├── errors.py                         the error envelope
│   │   └── settings.py                       paths and provider, all overridable
│   └── tests/
│       ├── __init__.py
│       └── test_api.py                       25 tests
│
└── retention-console-frontend/
    ├── api-contract/                         9 JSON files — THE CONTRACT
    │   ├── GET_queue.json
    │   ├── GET_customer_detail.json
    │   ├── GET_customer_no_offer.json
    │   ├── GET_summary.json
    │   ├── GET_catalog.json
    │   ├── POST_action.json
    │   ├── POST_score.json
    │   ├── ERROR_validation.json
    │   └── ERROR_leakage.json
    └── frontend/                             React + TS + Vite, 129 tests
        └── src/
            ├── components/NarrationPanel.tsx     CHANGED — hosts the button
            ├── components/RegenerateNote.tsx     NEW — the live call
            ├── components/RegenerateNote.test.tsx NEW — 4 tests
            ├── features/customer/CustomerPage.tsx CHANGED — one line
            ├── lib/api.ts                        CHANGED — api.narrate()
            ├── mocks/handlers.ts                 CHANGED — mock narrate handler
            └── types/api.ts                      CHANGED — NarrateResponse
```

---

## Run it

```bash
# 1. dependencies — both sets. The live endpoint imports src.graph, which needs
#    xgboost, scikit-learn, shap and langgraph.
pip install -r ml/requirements.txt
pip install -r backend/requirements.txt

# 2. the key. narration_client.py reads ml/.env at import.
cp ml/.env.example ml/.env      # then paste GEMINI_API_KEY into it

# 3. the API
cd backend
./run.sh                        # or: uvicorn app.main:app --port 8000

# 4. the frontend, in a second terminal
cd retention-console-frontend/frontend
echo "VITE_USE_MSW=false" > .env.development
npm run dev                     # http://localhost:5173
```

### On Windows

`run.sh` is bash. Use `run.bat` from PowerShell instead:

```powershell
# 1. dependencies
python -m pip install -r ml\requirements.txt
python -m pip install -r backend\requirements.txt

# 2. the key
copy ml\.env.example ml\.env     # then paste GEMINI_API_KEY into it

# 3. the API  (from the repo root, or from backend\)
cd backend
.\run.bat                         # provider from NARRATION_PROVIDER, default gemini
.\run.bat fake                    # stub client — no key, no network, no cost
.\run.bat fake 8001               # provider and port

# 4. the frontend, in a second PowerShell terminal
cd retention-console-frontend\frontend
"VITE_USE_MSW=false" | Out-File .env.development -Encoding ascii
npm run dev                       # http://localhost:5173
```

`run.bat` checks that `ml\src`, `ml\artifacts\churn_model_v1.joblib`, and
`retention-console-frontend\api-contract` exist before starting; it prints a clear
error and exits non-zero if any are missing.

Startup takes about 5 seconds — the model, the SHAP explainer, the catalog and the
7,043-row spreadsheet are all loaded before the first request, so nobody waits for
them mid-demo. You will see:

```
────────────────────────────────────────────────────────────────────────
  retention console API
  ml root         .../ml
  api contract    .../retention-console-frontend/api-contract
  provider        gemini
  narrate timeout 30s
  contract        9 files loaded
  population      7,043 customers
  graph           compiled and warm in 5.0s
  ready in 5.0s   →  http://localhost:8000/api/health
────────────────────────────────────────────────────────────────────────
```

If `provider` says `gemini` and there is no key, it warns loudly at startup rather
than failing silently on the first click.

---

## Endpoints

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | status, resolved paths, customer count, graph readiness |
| GET | `/api/queue?page=1&page_size=40` | `GET_queue.json` unchanged — 40 rows, 688 eligible |
| GET | `/api/summary` | `GET_summary.json` unchanged |
| GET | `/api/catalog` | `GET_catalog.json` unchanged — 6 offers, policy block |
| GET | `/api/customers/{id}` | detail fixture; `5461-QKNTN` gets the no-offer fixture |
| POST | `/api/customers/{id}/action` | records approve / edit / reject |
| POST | `/api/customers/{id}/narrate` | **runs the real pipeline live** |

`?provider=fake` on the narrate endpoint forces the stub client for any single call —
useful for proving the wiring without spending an API request.

### The live endpoint

```bash
curl -X POST localhost:8000/api/customers/0295-PPHDO/narrate
```

```jsonc
{
  "customer_id": "0295-PPHDO",
  "narration": {
    "summary": "...", "why": "...", "talk_track": "...",
    "evidence_ids": ["DELTA-051", "LEVER-060"],
    "uncertainty_note": "...",       // composed in code, never model-written
    "source": "llm",                 // or "fallback_template" if it failed twice
    "model": "gemini-...",
    "validator_attempts": 1,
    "generated_at": "2026-08-17T18:04:11Z"
  },
  "decision": {                      // proof the model changed nothing
    "status": "recommended",
    "offer_id": "OFF-BUNDLE-ALL",
    "cost": 120.51,
    "expected_value": 705.82,
    "p_churn": 0.99,
    "levers": ["NO_TECH_SUPPORT", "..."]
  },
  "violations": [],
  "provider": "gemini",
  "elapsed_ms": 7412
}
```

Errors, all in the envelope the frontend's `ApiError` class parses:

| Status | Code | When |
|---|---|---|
| 404 | `CUSTOMER_NOT_FOUND` | id is not in the spreadsheet |
| 422 | `VALIDATION_ERROR` | bad provider, bad page_size, bad reason_code |
| 502 | `NARRATION_FAILED` | the graph raised, or produced no draft |
| 504 | `NARRATION_TIMEOUT` | no response within `NARRATE_TIMEOUT_S` |

---

## Why the narrate endpoint reads the spreadsheet

`samples/customers_200.jsonl` holds 200 customers. The queue holds 40. **Only 7 of
those 40 are in the jsonl** — so sourcing records from it would 404 on 33 of the 40
rows an agent can click. `data/Telco_customer_churn.xlsx` has all 7,043, so every row
on screen can be narrated. `tests/test_api.py::test_every_queue_row_can_be_narrated`
pins this; if someone switches the source back, that test fails.

Only the 19 model/lever attributes plus CLTV are passed to the graph. Churn Label,
Churn Score and Churn Reason are never read — those are the quarantined columns in
`src/gate.py`, and handing them to the graph would be leakage.

---

## Configuration

Every value is an environment variable with a sensible default. Nothing needs editing
to move the app.

| Variable | Default | Notes |
|---|---|---|
| `ML_ROOT` | `<repo>/ml` | added to `sys.path`; the package is imported as `src.*` |
| `API_CONTRACT_DIR` | `<repo>/retention-console-frontend/api-contract` | |
| `NARRATION_PROVIDER` | `gemini` | `fake` runs everything with a stub, no key needed |
| `NARRATE_TIMEOUT_S` | `30` | a hung request in front of an audience is the worst case |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | comma-separated |

All paths resolve from the file's own location, not the working directory, so
`uvicorn app.main:app` behaves the same from anywhere.

---

## Tests

```bash
cd backend && NARRATION_PROVIDER=fake python -m pytest tests -q     # 25 passed
cd ml && python -m pytest tests -q                                  # 285 passed
cd retention-console-frontend/frontend && npm test                  # 129 passed
```

The backend tests assert every read endpoint is **equal** to its `api-contract` file —
not a subset, not a key check. That is the only thing preventing drift.

---

## Known issues, recorded rather than hidden

**1. `note` is missing on 3 of the 6 offers.** `data/offers.yaml` carries `note` on
`OFF-CONTRACT-1Y`, `OFF-BUNDLE-ALL` and `OFF-AUTOPAY` only, and `api_fixtures.py`
emits the key only when present. `src/types/api.ts` declares `note: string` as
required, which is inaccurate. Nothing renders it (`CatalogPage.tsx` never reads it),
so it cannot throw. Correct fix is `note?: string` in the TypeScript or a note on
every offer in the YAML. Pinned by `test_note_is_optional_on_an_offer`.

**2. `/api/queue` accepts `page`/`page_size` but always returns the same 40 rows.**
The contract fixture is one page; slicing it would report a `returned` count that
disagrees with `items`. Real paging arrives with a real queue source.

**3. `/api/customers/{id}` only knows two ids.** `0295-PPHDO` and `5461-QKNTN` — the
two the contract covers. Anything else is an honest 404 rather than pretending every
customer is `0295-PPHDO`. The **narrate** endpoint, by contrast, works for all 7,043.

**4. The timeout cancels the await, not the thread.** A timed-out graph run keeps
going in the background until it finishes on its own. Fine here — the request is
freed and the client gets a clean 504 — but it would matter under real load.

---

## Demo notes

Keep this terminal visible. Every live call logs one line:

```
POST /api/customers/0295-PPHDO/narrate  200  7412ms  provider=gemini
```

Watching that appear as the note lands on screen is worth more than any slide.

If the network dies mid-demo, the button returns a clean 504 and the previous note
stays on screen — the panel sees an error message, not a broken page. Say: *"That's
the network. The read endpoints are unaffected because they don't call the model."*

The offline demo that cannot fail, and the best thing in the project:

```bash
cd ml
python -m src.run_one samples/01_recommended_top_value.json --script invented_discount,ok
```

The model invents a discount, a validator rejects it, the graph retries, the second
draft passes. No API calls, no network, fully repeatable.
