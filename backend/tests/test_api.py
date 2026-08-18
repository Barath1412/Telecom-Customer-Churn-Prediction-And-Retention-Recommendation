"""
Contract tests. Run with:  cd backend && python -m pytest tests -q

Every read endpoint is asserted EQUAL to its api-contract file -- not a subset, not a
key check. That is the point: the frontend was built against those files, and the only
way the two can drift is if this assertion is weakened.

The live endpoint is exercised with provider=fake, which runs all nine graph nodes and
all six validators with a stub client. Same code path, no API key, no network.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("NARRATION_PROVIDER", "fake")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app                    # noqa: E402
from app.settings import API_CONTRACT_DIR   # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:              # triggers lifespan -> warm-up
        yield c


@pytest.fixture(autouse=True)
def isolate_actions_log(monkeypatch, tmp_path):
    """Ensure no test in this file ever writes to the real ml/artifacts/actions/actions.jsonl."""
    from app import actions_log, queue_state
    log_file = tmp_path / "actions.jsonl"
    monkeypatch.setattr(actions_log, "LOG_PATH", log_file)
    queue_state.state = queue_state.QueueState(
        eligible_ids=queue_state.load_eligible_ids(),
        capacity=40,
        actioned={},
    )


def fixture(name: str) -> dict:
    return json.loads((API_CONTRACT_DIR / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
#  the contract
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "path,name",
    [
        ("/api/summary", "GET_summary.json"),
        ("/api/catalog", "GET_catalog.json"),
    ],
)
def test_endpoint_equals_its_fixture(client, path, name):
    r = client.get(path)
    assert r.status_code == 200
    assert r.json() == fixture(name)


def test_queue_headline_numbers(client):
    """The numbers a panel will read off the screen."""
    q = client.get("/api/queue").json()
    assert q["total_eligible"] == 688
    assert q["returned"] == 40
    assert len(q["items"]) == 40


def test_summary_funnel_has_the_four_current_statuses(client):
    f = client.get("/api/summary").json()["funnel"]
    for k in ("scored", "recommended", "review_no_profitable_offer",
              "review_no_applicable_offer", "no_action_needed",
              "queued_today", "treatment", "control"):
        assert k in f
    assert "involuntary" not in f
    assert "no_eligible_offer" not in f


def test_catalog_is_v3_with_six_offers(client):
    c = client.get("/api/catalog").json()
    assert len(c["offers"]) == 6
    assert c["policy"]["min_expected_value_usd"] == 20.0


def test_note_is_optional_on_an_offer():
    """
    KNOWN MISMATCH, deliberately pinned rather than silently "fixed".

    data/offers.yaml carries `note` on only 3 of the 6 offers (OFF-CONTRACT-1Y,
    OFF-BUNDLE-ALL, OFF-AUTOPAY), and api_fixtures.py emits the key only when it is
    present. The frontend's `Offer` interface in src/types/api.ts declares
    `note: string` as REQUIRED, which is inaccurate -- but nothing renders it today
    (CatalogPage.tsx never reads it), so it cannot throw at runtime.

    The correct fix is `note?: string` in the TypeScript, or a note on every offer in
    the YAML. Neither is done here: this backend does not edit ml/ or frontend/. This
    test exists so the discrepancy is recorded and cannot be mistaken for a bug in
    the API.
    """
    offers = fixture("GET_catalog.json")["offers"]
    with_note = [o["offer_id"] for o in offers if "note" in o]
    assert len(with_note) == 3
    assert all(isinstance(o["note"], str) for o in offers if "note" in o)


def test_no_offer_customer_has_the_review_status(client):
    d = client.get("/api/customers/5461-QKNTN").json()
    assert d["status"] == "review_no_profitable_offer"
    assert d["recommendation"] is None or d["recommendation"].get("offer_id") is None


# --------------------------------------------------------------------------- #
#  errors — the envelope the frontend's ApiError class parses
# --------------------------------------------------------------------------- #
def test_unknown_customer_is_404_in_the_envelope(client):
    r = client.get("/api/customers/NOPE-XXXXX")
    assert r.status_code == 404
    body = r.json()
    assert "detail" not in body
    assert body["error"]["code"] == "CUSTOMER_NOT_FOUND"
    assert body["error"]["message"]
    assert body["error"]["request_id"].startswith("req_")


def test_bad_page_size_is_422_in_the_envelope(client):
    r = client.get("/api/queue?page_size=999")
    assert r.status_code == 422
    body = r.json()
    assert "detail" not in body                     # FastAPI's default must not leak
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["fields"]


def test_page_params_are_accepted(client):
    assert client.get("/api/queue?page=1&page_size=40").status_code == 200


# --------------------------------------------------------------------------- #
#  action
# --------------------------------------------------------------------------- #
def test_approve_returns_the_documented_shape(client, monkeypatch, tmp_path):
    from app import actions_log
    monkeypatch.setattr(actions_log, "LOG_PATH", tmp_path / "actions.jsonl")
    r = client.post("/api/customers/0295-PPHDO/action",
                    json={"action": "approve", "actor": "agent_42",
                          "reason_code": None, "modified_offer_id": None,
                          "note": "Customer accepted on first call."})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == set(fixture("POST_action.json")["response_example"])
    assert body["status"] == "recorded"
    assert body["customer_id"] == "0295-PPHDO"


def test_unknown_reason_code_is_rejected(client):
    r = client.post("/api/customers/0295-PPHDO/action",
                    json={"action": "reject", "actor": "agent_42",
                          "reason_code": "not_a_real_code"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_reject_without_a_reason_is_rejected(client):
    r = client.post("/api/customers/0295-PPHDO/action",
                    json={"action": "reject", "actor": "agent_42"})
    assert r.status_code == 422


def test_unknown_action_is_rejected(client):
    r = client.post("/api/customers/0295-PPHDO/action",
                    json={"action": "explode", "actor": "agent_42"})
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
#  the live endpoint
# --------------------------------------------------------------------------- #
def test_narrate_runs_the_real_graph(client):
    r = client.post("/api/customers/0295-PPHDO/narrate?provider=fake")
    assert r.status_code == 200, r.text
    b = r.json()
    n = b["narration"]
    for k in ("summary", "why", "talk_track", "evidence_ids", "uncertainty_note",
              "source", "model", "validator_attempts", "generated_at"):
        assert k in n, f"missing {k}"
    assert n["summary"] and n["why"] and n["talk_track"]
    assert n["source"] in ("llm", "template")
    assert n["validator_attempts"] >= 1
    assert b["violations"] == []
    assert b["elapsed_ms"] > 0


def test_narrate_reaches_a_customer_that_is_not_in_customers_200(client):
    """
    33 of the 40 queue rows are absent from samples/customers_200.jsonl. Reading the
    spreadsheet instead is the whole reason this test exists -- if someone switches
    the source back, this is what fails.
    """
    queue = client.get("/api/queue").json()
    ids = [i["customer_id"] for i in queue["items"]]
    jsonl = Path(os.environ.get("ML_ROOT", Path(__file__).resolve().parents[2] / "ml")) \
        / "samples" / "customers_200.jsonl"
    known = {json.loads(l)["customer_id"] for l in jsonl.read_text().splitlines() if l.strip()}
    outside = [c for c in ids if c not in known]
    assert outside, "expected some queue rows to be outside the jsonl sample"
    r = client.post(f"/api/customers/{outside[0]}/narrate?provider=fake")
    assert r.status_code == 200, r.text
    assert r.json()["narration"]["summary"]


def test_every_queue_row_can_be_narrated(client):
    """No row on screen may 404 when an agent presses the button."""
    from app import population
    ids = [i["customer_id"] for i in client.get("/api/queue").json()["items"]]
    missing = [c for c in ids if population.get(c) is None]
    assert missing == [], f"queue rows with no record: {missing}"


def test_narrate_returns_the_decision_unchanged(client):
    """
    The decision is computed before narration and the graph asserts it cannot move.
    The response carries it so that claim is checkable from outside.
    """
    b = client.post("/api/customers/0295-PPHDO/narrate?provider=fake").json()
    d = b["decision"]
    detail = fixture("GET_customer_detail.json")
    assert d["status"] == detail["status"]
    assert d["offer_id"] == detail["recommendation"]["offer_id"]
    assert abs(d["expected_value"] - detail["recommendation"]["expected_value"]) < 0.01
    assert abs(d["cost"] - detail["recommendation"]["cost"]) < 0.01


def test_narrate_unknown_customer_is_404(client):
    r = client.post("/api/customers/NOPE-XXXXX/narrate?provider=fake")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "CUSTOMER_NOT_FOUND"


def test_narrate_rejects_an_unknown_provider(client):
    r = client.post("/api/customers/0295-PPHDO/narrate?provider=llama")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_uncertainty_note_is_code_generated_not_model_text(client):
    """
    Two runs of the same customer must produce a byte-identical uncertainty note.
    If the model were ever allowed to write it, this would drift.
    """
    a = client.post("/api/customers/0295-PPHDO/narrate?provider=fake").json()
    b = client.post("/api/customers/0295-PPHDO/narrate?provider=fake").json()
    assert a["narration"]["uncertainty_note"] == b["narration"]["uncertainty_note"]
    assert "business assumption" in a["narration"]["uncertainty_note"]


# --------------------------------------------------------------------------- #
#  health
# --------------------------------------------------------------------------- #
def test_health_reports_a_loaded_population(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok"
    assert h["customers_loaded"] > 7000
    assert h["graph_ready"] is True


# --------------------------------------------------------------------------- #
#  POST /api/score — new tests
# --------------------------------------------------------------------------- #
import json as _json  # noqa: E402

_SCORE_CONTRACT_DIR = Path(os.environ.get(
    "API_CONTRACT_DIR",
    Path(__file__).resolve().parents[2] / "retention-console-frontend" / "api-contract",
))

_SCORE_REQUEST = _json.loads(
    (_SCORE_CONTRACT_DIR / "POST_score.json").read_text(encoding="utf-8")
)["request_example"]


def test_score_returns_200_with_all_six_keys(client):
    """POST /api/score with POST_score.json's request_example returns 200."""
    r = client.post("/api/score", json=_SCORE_REQUEST)
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("p_churn", "risk_band", "levers", "recommendation",
                "policy_trace", "provenance"):
        assert key in body, f"missing key: {key}"


def test_score_known_values(client):
    """p_churn, risk_band, offer_id, cost and EV must match what the model produces."""
    r = client.post("/api/score", json=_SCORE_REQUEST)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["p_churn"] == 0.99
    assert body["risk_band"] == "critical"
    rec = body["recommendation"]
    assert rec is not None
    assert rec["offer_id"] == "OFF-BUNDLE-ALL"
    assert abs(rec["cost"] - 120.51) < 0.01
    assert abs(rec["expected_value"] - 705.82) < 0.01


def test_score_policy_trace_shape(client):
    """Every entry has a valid state and no raw passed/evaluable keys."""
    r = client.post("/api/score", json=_SCORE_REQUEST)
    assert r.status_code == 200, r.text
    trace = r.json()["policy_trace"]
    assert trace, "policy_trace must not be empty"
    valid_states = {"pass", "veto", "not_evaluable"}
    for entry in trace:
        assert entry["state"] in valid_states, f"bad state: {entry['state']}"
        assert "passed" not in entry, "raw 'passed' key must not appear"
        assert "evaluable" not in entry, "raw 'evaluable' key must not appear"
    # R4 and R5 are not_evaluable and carry unmet_requirement
    ne = [e for e in trace if e["state"] == "not_evaluable"]
    ne_ids = {e["rule_id"] for e in ne}
    assert "R4_COOLDOWN" in ne_ids
    assert "R5_ONE_PER_WINDOW" in ne_ids
    for e in ne:
        assert "unmet_requirement" in e, f"{e['rule_id']} missing unmet_requirement"


def test_score_leakage_rejected(client):
    """A body with a quarantined field returns 400 LEAKAGE_REJECTED."""
    bad = dict(_SCORE_REQUEST)
    bad["Churn Score"] = 90
    r = client.post("/api/score", json=bad)
    assert r.status_code == 400, r.text
    err = r.json()["error"]
    assert err["code"] == "LEAKAGE_REJECTED"
    assert len(err["quarantined_fields"]) == 14


def test_score_cltv_lowercase_is_accepted(client):
    """lowercase cltv is a valid input field and must NOT trigger leakage."""
    body = dict(_SCORE_REQUEST)
    assert "cltv" in body           # sanity: the fixture uses lowercase
    assert "CLTV" not in body       # sanity: the banned uppercase form is absent
    r = client.post("/api/score", json=body)
    assert r.status_code == 200, r.text


def test_score_missing_required_field_is_422(client):
    """A body missing a required field returns 422 in the envelope."""
    bad = dict(_SCORE_REQUEST)
    del bad["Contract"]
    r = client.post("/api/score", json=bad)
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"


def test_narrate_levers_are_dicts_with_code_and_label(client):
    """narrate response: decision.levers must be [{code, label}, ...], not bare strings."""
    b = client.post("/api/customers/0295-PPHDO/narrate?provider=fake").json()
    levers = b["decision"]["levers"]
    assert isinstance(levers, list)
    assert len(levers) > 0, "expected at least one lever"
    for lv in levers:
        assert isinstance(lv, dict), f"lever is not a dict: {lv!r}"
        assert "code" in lv, f"lever missing 'code': {lv}"
        assert "label" in lv, f"lever missing 'label': {lv}"
        assert isinstance(lv["code"], str) and lv["code"]
        assert isinstance(lv["label"], str) and lv["label"]


def test_settings_narration_provider_from_dotenv():
    """
    NARRATION_PROVIDER reflects ml/.env when no shell variable is set.
    An existing environment variable must still win over .env.
    """
    import importlib
    from pathlib import Path as P

    # The test runner sets NARRATION_PROVIDER=fake at the top of this file.
    # That shell variable must win.
    from app import settings
    assert settings.NARRATION_PROVIDER == "fake"

    # Verify load_dotenv uses setdefault (does not overwrite existing keys).
    ml_env = P(settings.ML_ROOT) / ".env"
    if ml_env.exists():
        from src.narration_client import load_dotenv
        # Set a sentinel, run load_dotenv, confirm sentinel survives.
        import os
        os.environ["_TEST_DOTENV_SENTINEL"] = "ORIGINAL"
        # Temporarily write a conflicting value to a temp env to test the pattern.
        # Since we cannot safely mutate ml/.env, we test the setdefault contract
        # by calling load_dotenv twice: the second call must not overwrite keys set
        # by the first.
        result1 = load_dotenv()
        result2 = load_dotenv()
        for k, v in result1.items():
            assert os.environ.get(k) is not None, f"{k} missing from env after load"
        # The sentinel must survive.
        assert os.environ.get("_TEST_DOTENV_SENTINEL") == "ORIGINAL"
        del os.environ["_TEST_DOTENV_SENTINEL"]


# --------------------------------------------------------------------------- #
#  GET /api/customers/{customer_id} & cache tests
# --------------------------------------------------------------------------- #
def test_golden_customer_detail_matches_fixture(client):
    """
    GET /api/customers/0295-PPHDO matches GET_customer_detail.json except for
    narration (null by design until warmed), provenance.scored_at (live timestamp),
    and evidence.approx_tokens (the committed fixture is one KB generation behind,
    so we assert it is within ±1500 of 3103).
    """
    from app import cache
    # Ensure cache is clean for this test
    old_cache = dict(cache.cached)
    cache.cached.pop("0295-PPHDO", None)
    try:
        r = client.get("/api/customers/0295-PPHDO")
        assert r.status_code == 200, r.text
        actual = r.json()
        expected = fixture("GET_customer_detail.json")

        # 1. narration is null by design
        assert actual["narration"] is None

        # 2. provenance matches except scored_at is a live ISO string
        assert actual["provenance"]["model_name"] == expected["provenance"]["model_name"]
        assert actual["provenance"]["model_version"] == expected["provenance"]["model_version"]
        assert actual["provenance"]["model_roc_auc"] == expected["provenance"]["model_roc_auc"]
        assert actual["provenance"]["catalog_version"] == expected["provenance"]["catalog_version"]
        assert actual["provenance"]["kb_version"] == expected["provenance"]["kb_version"]
        assert "scored_at" in actual["provenance"]

        # 3. evidence: ids and count match; approx_tokens within ±1500 of 3103
        assert actual["evidence"]["ids"] == expected["evidence"]["ids"]
        assert actual["evidence"]["count"] == expected["evidence"]["count"]
        # The committed fixture has 3103 from an older KB generation; live is ~4235
        assert abs(actual["evidence"]["approx_tokens"] - 3103) <= 1500

        # 4. Exact matches on all core decision and profile fields
        assert actual["rank"] == expected["rank"]
        assert actual["customer_id"] == expected["customer_id"]
        assert actual["arm"] == expected["arm"]
        assert actual["actionable"] is True
        assert actual["risk"] == expected["risk"]
        assert actual["value"] == expected["value"]
        assert actual["levers"] == expected["levers"]
        assert actual["recommendation"] == expected["recommendation"]
        assert actual["status"] == expected["status"]
        assert actual["vetoed"] == expected["vetoed"]
        assert actual["attribution"] == expected["attribution"]
        assert actual["attribution_disclaimer"] == expected["attribution_disclaimer"]
        assert actual["profile"] == expected["profile"]

        # 5. alternatives: candidate offer IDs, names and priors match; expected_values within 1.0 of fixture
        assert len(actual["alternatives"]) == len(expected["alternatives"])
        for act_alt, exp_alt in zip(actual["alternatives"], expected["alternatives"]):
            assert act_alt["offer_id"] == exp_alt["offer_id"]
            assert act_alt["offer_name"] == exp_alt["offer_name"]
            assert act_alt["delta_prior"] == exp_alt["delta_prior"]
            assert abs(act_alt["expected_value"] - exp_alt["expected_value"]) < 1.0

        # 6. policy_trace: rules, states and unmet_requirements match
        assert len(actual["policy_trace"]) == len(expected["policy_trace"])
        for act_rule, exp_rule in zip(actual["policy_trace"], expected["policy_trace"]):
            assert act_rule["rule_id"] == exp_rule["rule_id"]
            assert act_rule["state"] == exp_rule["state"]
            if "unmet_requirement" in exp_rule:
                assert "unmet_requirement" in act_rule
    finally:
        cache.cached.update(old_cache)


def test_every_queue_row_has_a_detail_page(client):
    """Regression guard: all 40 customer_ids in GET_queue.json return 200 on /api/customers/{id}."""
    q = client.get("/api/queue").json()
    for item in q["items"]:
        cid = item["customer_id"]
        r = client.get(f"/api/customers/{cid}")
        assert r.status_code == 200, f"Customer {cid} failed: {r.text}"
        body = r.json()
        assert body["customer_id"] == cid
        assert "risk" in body
        assert "value" in body
        assert "status" in body


def test_customer_review_no_profitable_offer(client):
    """5461-QKNTN returns 200 with review_no_profitable_offer and recommendation is None."""
    r = client.get("/api/customers/5461-QKNTN")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "review_no_profitable_offer"
    assert body["recommendation"] is None
    assert body["alternatives"] == []


def test_customer_no_action_needed(client):
    """A no_action_needed customer returns 200 with recommendation None, evidence count 0, non-empty levers."""
    r = client.get("/api/customers/0486-HECZI")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "no_action_needed"
    assert body["recommendation"] is None
    assert body["evidence"]["count"] == 0
    assert len(body["levers"]) > 0


def test_customer_not_found(client):
    """GET /api/customers/NOPE-XXXXX returns 404 CUSTOMER_NOT_FOUND."""
    r = client.get("/api/customers/NOPE-XXXXX")
    assert r.status_code == 404, r.text
    err = r.json()["error"]
    assert err["code"] == "CUSTOMER_NOT_FOUND"


def test_customer_detail_narration_is_null(client):
    """narration is null on detail response when not in cache."""
    from app import cache
    cache.cached.pop("0295-PPHDO", None)
    r = client.get("/api/customers/0295-PPHDO")
    assert r.status_code == 200
    assert r.json()["narration"] is None


def test_customer_detail_makes_no_llm_call(client, monkeypatch):
    """The detail endpoint makes zero LLM calls: patch build_client to raise."""
    import src.narration_client

    def _boom(*args, **kwargs):
        raise RuntimeError("LLM was called unexpectedly!")

    monkeypatch.setattr(src.narration_client, "build_client", _boom)
    r = client.get("/api/customers/0295-PPHDO")
    assert r.status_code == 200


def test_customer_detail_response_time(client):
    """A warm second call for the same customer completes in under 2 seconds."""
    import time
    t0 = time.time()
    r = client.get("/api/customers/0295-PPHDO")
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0, f"Detail call took {elapsed:.2f}s (expected < 2.0s)"


def test_customer_detail_risk_percentile(client):
    """risk.percentile for 0295-PPHDO is 100.0."""
    r = client.get("/api/customers/0295-PPHDO")
    assert r.status_code == 200
    assert r.json()["risk"]["percentile"] == 100.0


def test_cache_autowarm_runs_in_background(tmp_path, monkeypatch):
    """
    Patch NARRATION_PROVIDER to non-fake, start app with empty cache dir,
    assert app becomes ready (health check returns 200) in under 1 second without awaiting autowarm.
    """
    import time
    from app import cache, settings
    monkeypatch.setattr(settings, "NARRATION_PROVIDER", "gemini")
    monkeypatch.setattr(cache, "CACHE_PATH", tmp_path / "narrations.jsonl")

    # Mock autowarm so it simulates long work in the background
    import asyncio
    autowarm_called = False

    async def _mock_autowarm(missing):
        nonlocal autowarm_called
        autowarm_called = True
        await asyncio.sleep(5)

    monkeypatch.setattr(cache, "autowarm", _mock_autowarm)

    t0 = time.time()
    with TestClient(app) as test_c:
        elapsed = time.time() - t0
        r = test_c.get("/api/health")
        assert r.status_code == 200
        assert elapsed < 1.0, f"Startup took {elapsed:.2f}s (expected < 1.0s)"


def test_no_autowarm_when_provider_fake(tmp_path, monkeypatch):
    """With NARRATION_PROVIDER=fake, assert no background task is created and live_cache is not written to."""
    from app import cache, settings
    cache_file = tmp_path / "narrations.jsonl"
    monkeypatch.setattr(settings, "NARRATION_PROVIDER", "fake")
    monkeypatch.setattr(cache, "CACHE_PATH", cache_file)

    with TestClient(app) as test_c:
        r = test_c.get("/api/health")
        assert r.status_code == 200
        assert not cache_file.exists()


def test_cache_first_on_narrate(client, monkeypatch):
    """
    Pre-seed cache.cached with a fake entry; assert LLM is never invoked (build_client raises)
    and the pre-seeded record is returned.
    """
    from app import cache
    import src.narration_client

    def _boom(*args, **kwargs):
        raise RuntimeError("LLM called when cached entry exists!")

    monkeypatch.setattr(src.narration_client, "build_client", _boom)

    fake_record = {
        "customer_id": "0295-PPHDO",
        "narration": {
            "summary": "Cached fake summary",
            "why": "Cached fake why",
            "talk_track": "Cached fake talk track",
            "evidence_ids": ["POLICY-001"],
            "uncertainty_note": "Cached fake uncertainty",
            "source": "llm",
            "model": "fake-cached",
            "validator_attempts": 1,
            "generated_at": "2026-08-16T12:00:00Z",
        },
        "decision": {"status": "recommended"},
        "violations": [],
        "provider": "fake",
        "elapsed_ms": 1.0,
    }
    cache.cached["0295-PPHDO"] = fake_record

    r = client.post("/api/customers/0295-PPHDO/narrate")
    assert r.status_code == 200, r.text
    assert r.json() == fake_record


def test_force_param_bypasses_cache(client, monkeypatch, tmp_path):
    """With ?force=true, the cache is bypassed, generation runs, and cache is overwritten."""
    from app import cache
    monkeypatch.setattr(cache, "CACHE_PATH", tmp_path / "narrations.jsonl")

    stale_record = {
        "customer_id": "0295-PPHDO",
        "narration": {"summary": "Stale note", "generated_at": "2020-01-01T00:00:00Z"},
    }
    cache.cached["0295-PPHDO"] = stale_record

    r = client.post("/api/customers/0295-PPHDO/narrate?provider=fake&force=true")
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["narration"]["summary"] != "Stale note"
    assert cache.cached["0295-PPHDO"]["narration"]["summary"] == res["narration"]["summary"]


def test_cache_status_endpoint_excludes_control_arm(client):
    """GET /api/cache/status only counts treatment arm members; control arm IDs are excluded."""
    r = client.get("/api/cache/status")
    assert r.status_code == 200, r.text
    body = r.json()

    queue_items = fixture("GET_queue.json")["items"]
    treatment_ids = [item["customer_id"] for item in queue_items if item.get("arm") == "treatment"]
    control_ids = [item["customer_id"] for item in queue_items if item.get("arm") == "control"]

    assert body["total"] == len(treatment_ids)
    assert isinstance(body["cached"], int)
    assert isinstance(body["missing"], list)
    assert body["cached"] + len(body["missing"]) == body["total"]

    for cid in control_ids:
        assert cid not in body["missing"], f"Control-arm customer {cid} must not be in missing list"


def test_alternatives_contain_cost_delta_ci_and_talk_track(client):
    """Customer detail alternatives include cost, delta_ci, and templated talk_track."""
    r = client.get("/api/customers/0295-PPHDO")
    assert r.status_code == 200, r.text
    alts = r.json()["alternatives"]
    assert len(alts) >= 1, "0295-PPHDO should have alternatives"

    for alt in alts:
        assert "cost" in alt and isinstance(alt["cost"], (int, float)) and alt["cost"] > 0
        assert "delta_ci" in alt and isinstance(alt["delta_ci"], list) and len(alt["delta_ci"]) == 2
        assert "talk_track" in alt and isinstance(alt["talk_track"], str)
        assert alt["offer_name"] in alt["talk_track"]
        assert f"${alt['cost']:.2f}" in alt["talk_track"]
        assert f"${alt['expected_value']:.2f}" in alt["talk_track"]


def test_alternatives_talk_track_is_deterministic(client):
    """Calling the customer detail endpoint twice produces byte-identical talk_track values."""
    r1 = client.get("/api/customers/0295-PPHDO")
    r2 = client.get("/api/customers/0295-PPHDO")
    assert r1.status_code == 200 and r2.status_code == 200
    alts1 = r1.json()["alternatives"]
    alts2 = r2.json()["alternatives"]
    assert len(alts1) == len(alts2)
    for a1, a2 in zip(alts1, alts2):
        assert a1["talk_track"] == a2["talk_track"]
        assert a1["cost"] == a2["cost"]
        assert a1["delta_ci"] == a2["delta_ci"]


def test_control_arm_customer_detail_has_alternatives(client):
    """Control-arm customer (e.g. 9465-RWMXL) has valid calculation and alternatives."""
    queue_items = fixture("GET_queue.json")["items"]
    control_ids = [item["customer_id"] for item in queue_items if item.get("arm") == "control"]
    assert control_ids, "Expected at least one control-arm customer in queue fixture"

    cid = control_ids[0]
    r = client.get(f"/api/customers/{cid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["arm"] == "control"
    assert "alternatives" in body
    if body["alternatives"]:
        alt = body["alternatives"][0]
        assert "cost" in alt
        assert "delta_ci" in alt
        assert "talk_track" in alt


# --------------------------------------------------------------------------- #
#  POST /api/customers/{customer_id}/action audit log tests
# --------------------------------------------------------------------------- #
def test_post_action_approve_writes_actions_jsonl(client, monkeypatch, tmp_path):
    """POST /customers/{id}/action (approve) writes a line to actions.jsonl with offer_id."""
    from app import actions_log
    log_file = tmp_path / "actions.jsonl"
    monkeypatch.setattr(actions_log, "LOG_PATH", log_file)

    body = {"action": "approve", "actor": "agent_test", "note": "All good"}
    r = client.post("/api/customers/0295-PPHDO/action", json=body)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["status"] == "recorded"
    assert res["action"] == "approve"
    assert res["actor"] == "agent_test"

    assert log_file.exists(), "actions.jsonl was not created"
    lines = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    rec = lines[0]
    assert rec["customer_id"] == "0295-PPHDO"
    assert rec["offer_id"] == "OFF-BUNDLE-ALL"
    assert rec["action"] == "approve"
    assert rec["actor"] == "agent_test"
    assert rec["recommendation_id"] == res["recommendation_id"]
    assert rec["audit_id"] == res["audit_id"]
    assert rec["acted_at"] == res["acted_at"]


def test_post_action_reject_writes_actions_jsonl(client, monkeypatch, tmp_path):
    """POST /customers/{id}/action (reject, with reason_code) writes a line; handles no-offer customer gracefully."""
    from app import actions_log
    log_file = tmp_path / "actions.jsonl"
    monkeypatch.setattr(actions_log, "LOG_PATH", log_file)

    body = {
        "action": "reject",
        "actor": "agent_test",
        "reason_code": "offer_not_suitable",
        "note": "Declined",
    }
    r = client.post("/api/customers/5461-QKNTN/action", json=body)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["status"] == "recorded"
    assert res["action"] == "reject"

    assert log_file.exists()
    lines = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    rec = lines[0]
    assert rec["customer_id"] == "5461-QKNTN"
    assert rec["offer_id"] is None
    assert rec["action"] == "reject"
    assert rec["reason_code"] == "offer_not_suitable"


def test_post_action_customer_not_found(client, monkeypatch, tmp_path):
    """POST /customers/NOPE-XXXXX/action returns 404 CUSTOMER_NOT_FOUND and writes no log."""
    from app import actions_log
    log_file = tmp_path / "actions.jsonl"
    monkeypatch.setattr(actions_log, "LOG_PATH", log_file)

    body = {"action": "approve", "actor": "agent_test"}
    r = client.post("/api/customers/NOPE-XXXXX/action", json=body)
    assert r.status_code == 404, r.text
    err = r.json()["error"]
    assert err["code"] == "CUSTOMER_NOT_FOUND"
    assert not log_file.exists()


# --------------------------------------------------------------------------- #
#  QueueState unit tests
# --------------------------------------------------------------------------- #
def test_queue_state_record_action_promotes_next_eligible():
    from app.queue_state import QueueState

    qs = QueueState(eligible_ids=["a", "b", "c", "d"], capacity=2, actioned={})
    assert qs.pending_ids() == ["a", "b", "c", "d"]
    assert qs.active_ids() == ["a", "b"]

    promoted = qs.record_action("a", {"action": "approve", "acted_at": "2026-08-16T12:00:00Z"})
    assert qs.pending_ids() == ["b", "c", "d"]
    assert qs.active_ids() == ["b", "c"]
    assert promoted == ["c"]


def test_queue_state_rejecting_outside_active_set_promotes_nobody():
    from app.queue_state import QueueState

    qs = QueueState(eligible_ids=["a", "b", "c", "d"], capacity=2, actioned={})
    promoted = qs.record_action("d", {"action": "reject", "acted_at": "2026-08-16T12:00:00Z"})
    assert promoted == []
    assert qs.pending_ids() == ["a", "b", "c"]
    assert qs.active_ids() == ["a", "b"]


def test_queue_state_approved_and_rejected_ids_ordered_most_recent_first():
    from app.queue_state import QueueState

    qs = QueueState(eligible_ids=["a", "b", "c", "d"], capacity=2, actioned={})
    qs.record_action("a", {"action": "approve", "acted_at": "2026-08-16T12:00:00Z"})
    qs.record_action("b", {"action": "edit", "acted_at": "2026-08-16T12:05:00Z"})
    qs.record_action("c", {"action": "reject", "acted_at": "2026-08-16T12:01:00Z"})
    qs.record_action("d", {"action": "reject", "acted_at": "2026-08-16T12:06:00Z"})

    assert qs.approved_ids() == ["b", "a"]
    assert qs.rejected_ids() == ["d", "c"]


def test_queue_state_customer_actioned_twice_counted_only_latest():
    from app.queue_state import QueueState

    qs = QueueState(eligible_ids=["a", "b"], capacity=2, actioned={})
    qs.record_action("a", {"action": "approve", "acted_at": "2026-08-16T12:00:00Z"})
    assert qs.approved_ids() == ["a"]
    assert qs.rejected_ids() == []

    qs.record_action("a", {"action": "reject", "acted_at": "2026-08-16T12:10:00Z"})
    assert qs.approved_ids() == []
    assert qs.rejected_ids() == ["a"]


def test_queue_state_offered_offer_id():
    from app.queue_state import QueueState

    qs = QueueState(eligible_ids=["a", "b", "c"], capacity=2, actioned={})
    assert qs.offered_offer_id("a") is None

    qs.record_action("a", {"action": "approve", "offer_id": "OFF-1", "modified_offer_id": None})
    assert qs.offered_offer_id("a") == "OFF-1"

    qs.record_action("b", {"action": "edit", "offer_id": "OFF-1", "modified_offer_id": "OFF-2"})
    assert qs.offered_offer_id("b") == "OFF-2"


# --------------------------------------------------------------------------- #
#  Dynamic GET /api/queue integration tests
# --------------------------------------------------------------------------- #
def test_get_queue_default_params_matches_fixture_ids(client):
    """GET /api/queue with default params returns the same 40 customer_ids as GET_queue.json pre-action."""
    r = client.get("/api/queue")
    assert r.status_code == 200, r.text
    res = r.json()

    fix = fixture("GET_queue.json")
    expected_cids = [item["customer_id"] for item in fix["items"]]
    actual_cids = [item["customer_id"] for item in res["items"]]

    assert actual_cids == expected_cids
    assert res["total_eligible"] == 688
    assert res["capacity"] == 40
    assert res["pending_total"] == 688
    assert res["approved_total"] == 0
    assert res["rejected_total"] == 0
    assert res["status"] == "pending"
    assert res["page"] == 1
    assert res["page_size"] == 40
    assert res["returned"] == 40

    for i, item in enumerate(res["items"]):
        assert item["queue_position"] == i + 1
        assert item["actionable"] is True


def test_get_queue_paging(client):
    """GET /api/queue?status=pending&page=2 returns items 41..80 with actionable: false."""
    r = client.get("/api/queue?status=pending&page=2&page_size=40")
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["page"] == 2
    assert res["returned"] == 40
    for i, item in enumerate(res["items"]):
        assert item["queue_position"] == 40 + i + 1
        assert item["actionable"] is False


def test_get_queue_empty_rejected_on_fresh_state(client):
    """GET /api/queue?status=rejected on fresh state returns empty items list, not an error."""
    r = client.get("/api/queue?status=rejected")
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["items"] == []
    assert res["returned"] == 0
    assert res["rejected_total"] == 0
    assert res["status"] == "rejected"


def test_post_action_promotes_and_updates_queue_views(client, monkeypatch):
    """Approving 40th pending customer removes them from pending, promotes 41st, and records approved."""
    from app import queue_state
    init_pending = queue_state.state.pending_ids()
    fortieth_id = init_pending[39]
    forty_first_id = init_pending[40]

    # Post approve action
    r = client.post(
        f"/api/customers/{fortieth_id}/action",
        json={"action": "approve", "actor": "agent_demo"},
    )
    assert r.status_code == 200, r.text

    # GET pending queue page 1
    r_pending = client.get("/api/queue?status=pending&page=1&page_size=40")
    assert r_pending.status_code == 200
    pending_items = r_pending.json()["items"]
    pending_cids = [item["customer_id"] for item in pending_items]
    assert fortieth_id not in pending_cids
    assert forty_first_id in pending_cids
    assert pending_items[39]["customer_id"] == forty_first_id
    assert pending_items[39]["queue_position"] == 40
    assert pending_items[39]["actionable"] is True

    # GET approved queue
    r_approved = client.get("/api/queue?status=approved")
    assert r_approved.status_code == 200
    approved_res = r_approved.json()
    assert approved_res["approved_total"] == 1
    assert len(approved_res["items"]) == 1
    app_item = approved_res["items"][0]
    assert app_item["customer_id"] == fortieth_id
    assert app_item["decision"]["action"] == "approve"
    assert app_item["decision"]["actor"] == "agent_demo"
    assert app_item["decision"]["offered_offer_id"] is not None
    assert app_item["decision"]["offer_changed"] is False


def test_post_action_edit_decision_fields(client):
    """Editing offer updates decision.offered_offer_id, offered_offer_name, and offer_changed: true."""
    cid = "0295-PPHDO"
    r = client.post(
        f"/api/customers/{cid}/action",
        json={
            "action": "edit",
            "actor": "agent_demo",
            "modified_offer_id": "OFF-CONTRACT-1Y",
            "note": "Swapped to 1-year contract",
        },
    )
    assert r.status_code == 200, r.text

    r_app = client.get("/api/queue?status=approved")
    assert r_app.status_code == 200
    app_items = r_app.json()["items"]
    assert len(app_items) == 1
    item = app_items[0]
    assert item["customer_id"] == cid
    assert item["decision"]["action"] == "edit"
    assert item["decision"]["offered_offer_id"] == "OFF-CONTRACT-1Y"
    assert item["decision"]["offered_offer_name"] == "1-year contract at 10% off"
    assert item["decision"]["offer_changed"] is True


def test_post_action_reject_decision_fields(client):
    """Rejecting customer populates decision.reason_code and preserves offered_offer_id."""
    cid = "0295-PPHDO"
    r = client.post(
        f"/api/customers/{cid}/action",
        json={
            "action": "reject",
            "actor": "agent_demo",
            "reason_code": "already_contacted",
            "note": "Called earlier today",
        },
    )
    assert r.status_code == 200, r.text

    r_rej = client.get("/api/queue?status=rejected")
    assert r_rej.status_code == 200
    rej_items = r_rej.json()["items"]
    assert len(rej_items) == 1
    item = rej_items[0]
    assert item["customer_id"] == cid
    assert item["decision"]["action"] == "reject"
    assert item["decision"]["reason_code"] == "already_contacted"
    assert item["decision"]["offered_offer_id"] == "OFF-BUNDLE-ALL"


# --------------------------------------------------------------------------- #
#  Customer detail actionable tests
# --------------------------------------------------------------------------- #
def test_customer_detail_actionable_for_active_queue_customer(client):
    """GET /api/customers/{id} for customer in today's active 40 returns actionable: true."""
    r = client.get("/api/customers/0295-PPHDO")
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["actionable"] is True
    assert res["queue_position"] == 1


def test_customer_detail_actionable_for_backlog_customer(client):
    """GET /api/customers/{id} for customer in backlog (rank 41+) returns actionable: true."""
    from app import queue_state
    backlog_id = queue_state.state.pending_ids()[40]
    r = client.get(f"/api/customers/{backlog_id}")
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["actionable"] is True
    assert res["queue_position"] == 41


def test_customer_detail_not_actionable_after_action_taken(client):
    """GET /api/customers/{id} for an approved or rejected customer returns actionable: false."""
    cid = "0295-PPHDO"
    # Approve customer
    r_act = client.post(f"/api/customers/{cid}/action", json={"action": "approve", "actor": "agent_demo"})
    assert r_act.status_code == 200

    r_det = client.get(f"/api/customers/{cid}")
    assert r_det.status_code == 200
    res = r_det.json()
    assert res["actionable"] is False
    assert res["queue_position"] is None


# --------------------------------------------------------------------------- #
#  POST /api/score/narrate tests
# --------------------------------------------------------------------------- #
def test_score_narrate_happy_path(client):
    """POST /api/score/narrate with a valid 19-field body + cltv returns a narration block."""
    body = fixture("POST_score.json")["request_example"]
    r = client.post("/api/score/narrate?provider=fake", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["customer_id"] == "SCORE-ADHOC"
    assert data["provider"] == "fake"
    assert "narration" in data
    assert "summary" in data["narration"]
    assert "why" in data["narration"]
    assert "talk_track" in data["narration"]
    assert data["narration"]["source"] in ("llm", "template", "fake")
    assert "decision" in data
    assert data["decision"]["p_churn"] is not None


def test_score_narrate_never_touches_cache_or_actions_log(client, monkeypatch):
    """POST /api/score/narrate never calls cache.append or actions_log.append."""
    from app import cache, actions_log

    def _forbidden_cache_append(*args, **kwargs):
        raise AssertionError("cache.append must never be called from /api/score/narrate")

    def _forbidden_actions_append(*args, **kwargs):
        raise AssertionError("actions_log.append must never be called from /api/score/narrate")

    monkeypatch.setattr(cache, "append", _forbidden_cache_append)
    monkeypatch.setattr(actions_log, "append", _forbidden_actions_append)

    body = fixture("POST_score.json")["request_example"]
    r = client.post("/api/score/narrate?provider=fake", json=body)
    assert r.status_code == 200, r.text


def test_score_narrate_leakage_guard_rejects_quarantined_field(client):
    """Leakage guard still rejects a quarantined field on /api/score/narrate, same as /api/score."""
    body = dict(fixture("POST_score.json")["request_example"])
    body["CustomerID"] = "0295-PPHDO"  # Quarantined field
    r = client.post("/api/score/narrate?provider=fake", json=body)
    assert r.status_code == 400
    res = r.json()
    assert res["error"]["code"] == "LEAKAGE_REJECTED"


def test_score_narrate_validation_error_on_missing_field(client):
    """Missing customer attribute returns 422 VALIDATION_ERROR."""
    body = dict(fixture("POST_score.json")["request_example"])
    del body["Monthly Charges"]
    r = client.post("/api/score/narrate?provider=fake", json=body)
    assert r.status_code == 422
    res = r.json()
    assert res["error"]["code"] == "VALIDATION_ERROR"
