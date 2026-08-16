"""
Every sample file, through the real graph, asserted.

WHY THIS FILE REPLACED `src/run_samples.py`
    That script ran all the samples, printed one line each, and threw everything
    away: no note was persisted, nothing was asserted beyond a printed tick, and a
    run with `--provider gemini` spent 33 real requests to produce a table of status
    codes. It was doing two jobs badly -- REGRESSION CHECKING, which belongs in the
    test suite where it runs automatically and fails a build; and BATCH EXECUTION,
    which `run_batch` already does properly, with ranking, a run directory and
    `narrations.jsonl`.

    So the assertions moved here, and the execution moved to:

        python -m src.run_batch --input samples/samples_all.jsonl --capacity 10

    `samples/samples_all.jsonl` is generated from the sample files, so the two can
    never drift apart. There is now one runner for one customer (`run_one`) and one
    for many (`run_batch`), and no third thing.

NOTHING HERE NEEDS AN API KEY. FakeClient, no network.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.decision import STATUSES, Catalog, decide
from src.graph import _feature_frame, _model, compile_graph
from src.narration_client import FakeClient

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"

FILES = sorted(f for f in SAMPLES.glob("*.json") if f.name != "MANIFEST.json")
MANIFEST = json.loads((SAMPLES / "MANIFEST.json").read_text())


def _load(f: Path) -> dict:
    """
    Read a sample, and SAY WHAT IS WRONG WITH IT if it will not parse.

    `json.loads("")` raises `JSONDecodeError: Expecting value: line 1 column 1`,
    which names neither the file nor the actual problem. A zero-byte sample --
    a truncated copy, an interrupted unzip, a file an editor blanked -- then
    reads as a JSON syntax error, and you go looking for a bug in the JSON.
    One clean install produced exactly that, on exactly one file.
    """
    raw = f.read_text(encoding="utf-8").strip()
    if not raw:
        raise AssertionError(
            f"{f.name} is EMPTY ({f.stat().st_size} bytes). This is not a JSON "
            f"problem -- the file did not copy. Re-extract it from the release "
            f"zip into samples/ and run again.")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise AssertionError(
            f"{f.name} is not valid JSON ({e}). First 80 characters: "
            f"{raw[:80]!r}") from None


def test_every_sample_file_is_readable():
    """
    Runs first and names the file, so a bad copy is diagnosed in one line instead
    of as five unrelated-looking failures further down.
    """
    empty = [f.name for f in FILES if not f.read_text(encoding="utf-8").strip()]
    assert not empty, f"these sample files are empty and must be re-copied: {empty}"


def test_there_are_samples_and_a_manifest_entry_for_each():
    assert FILES, "no sample files found"
    assert {m["file"] for m in MANIFEST} == {f.name for f in FILES}


def test_every_outcome_is_represented():
    """A sample set that exercises three of four branches is not a sample set."""
    covered = {m["expected_status"] for m in MANIFEST}
    assert covered == set(STATUSES), f"missing coverage for {set(STATUSES) - covered}"


@pytest.mark.parametrize("f", FILES, ids=lambda f: f.stem)
def test_decide_matches_the_status_the_file_claims(f):
    """
    The cheap check: scoring plus the decision layer, no graph, no model call.
    This is the one that fires when a policy threshold changes underneath the
    samples -- as the minimum expected value did to two of them in v5.1.
    """
    j = _load(f)
    pipe, _ = _model()
    p = float(pipe.predict_proba(_feature_frame(j["customer"]))[:, 1][0])
    r = decide(customer_id=j["customer_id"], p_churn=p, cltv=float(j["cltv"]),
               row=pd.Series(j["customer"]), catalog=Catalog.load())
    assert r.status == j["_expected_status"], (
        f"{f.name} claims {j['_expected_status']} but decide() returns {r.status}. "
        f"Either the file is stale or a policy change moved this customer.")
    if j.get("_expected_offer_id") is not None:
        assert r.offer_id == j["_expected_offer_id"]
    if j.get("_expected_expected_value"):
        assert abs(r.ev - j["_expected_expected_value"]) < 0.005


@pytest.mark.parametrize("f", FILES, ids=lambda f: f.stem)
def test_the_whole_graph_runs_and_the_decision_survives_narration(f):
    """
    The full nine nodes with the stub client. `expected_decision` makes node 9 assert
    that the offer, the cost and the expected value are unchanged after narration --
    so this is also the per-sample proof that the model cannot alter a decision.
    """
    j = _load(f)
    expected = {k: v for k, v in (("offer_id", j.get("_expected_offer_id")),
                                  ("ev", j.get("_expected_expected_value")))
                if v is not None}
    out = compile_graph().invoke(
        {"customer_id": j["customer_id"], "customer": j["customer"],
         "cltv": float(j["cltv"])},
        {"configurable": {"thread_id": f"test_samples:{f.stem}", "auto_approve": True,
                          "client": FakeClient(), "expected_decision": expected}})
    assert out["status"] == j["_expected_status"]
    assert out["draft"] is not None, "every outcome must produce a note"
    assert out["source"] in ("llm", "fallback_template", "deterministic")
    assert out["trace"][0] == "score_customer" and out["trace"][-1] == "persist"
    assert out["risk_vs_base"] in ("below", "at", "above")


@pytest.mark.parametrize("m", MANIFEST, ids=lambda m: m["file"])
def test_the_manifest_is_not_stale(m):
    """The manifest is documentation, and documentation that can lie is worse than none."""
    j = _load(SAMPLES / m["file"])
    assert m["customer_id"] == j["customer_id"]
    assert m["expected_status"] == j["_expected_status"]
    assert m["cltv"] == j["cltv"]


def test_the_batch_input_file_matches_the_sample_files():
    """
    samples_all.jsonl is what `run_batch --input` reads. If someone edits a sample
    and forgets to regenerate it, the batch would silently run different customers.
    """
    lines = [json.loads(ln) for ln in
             (SAMPLES / "samples_all.jsonl").read_text().splitlines() if ln.strip()]
    assert {r["customer_id"] for r in lines} == {_load(f)["customer_id"] for f in FILES}
    for r in lines:
        assert set(r) == {"customer_id", "cltv", "customer"}


def test_the_deterministic_note_for_the_below_minimum_case_is_true_and_valid():
    """
    Two properties on the sub-case the minimum created, on a REAL record:

      1. it validates -- it may name the offers it priced, quote their costs, quote
         the minimum, and quote the gap, without tripping V-OFFER or V-MONEY;
      2. it does not say the offer loses money, because it does not. The best offer
         here is worth $19.59. Calling that a loss would be false, and the earlier
         wording did exactly that.
    """
    from src import fallback
    from src.graph import _validation_context
    from src.kb_retrieval import select
    from src.validators import validate

    j = _load(SAMPLES / "34_review_below_minimum_ev.json")
    pipe, _ = _model()
    p = float(pipe.predict_proba(_feature_frame(j["customer"]))[:, 1][0])
    r = decide(customer_id=j["customer_id"], p_churn=p, cltv=float(j["cltv"]),
               row=pd.Series(j["customer"]), catalog=Catalog.load())
    assert r.status == "review_no_profitable_offer"
    best = max(c["ev"] for c in r.considered)
    assert 0 < best < r.min_ev_floor, "this sample must sit between zero and the minimum"

    ev = select(list(r.levers), None)
    state = {"customer_id": r.customer_id, "status": r.status, "p_churn": r.p_churn,
             "cltv": r.cltv, "tenure_months": r.tenure_months,
             "monthly_charges": r.monthly_charges, "lever_labels": "Rolling contract",
             "offer_id": None, "offer_name": None, "cost": 0.0, "ev": 0.0,
             "delta_prior": 0.0, "delta_ci": [0, 0], "considered": r.considered,
             "min_ev_floor": r.min_ev_floor,
             "evidence_ids": ev.ids, "evidence_text": ev.text}
    draft = fallback.build(state)
    assert validate(draft, _validation_context(state)) == []
    text = f"{draft.summary} {draft.why} {draft.talk_track}".lower()
    assert "loses money" not in text and "loss-making" not in text
    assert "do not call" in text


def test_the_minimum_expected_value_branch_has_a_real_record():
    """
    v5.1 split `review_no_profitable_offer` into two sub-cases: every offer loses
    money, and the best offer MAKES money but not enough of it. The second reads
    differently in the prompt and in the template, so it must be exercised by an
    actual customer, not only by a unit test with invented numbers.
    """
    hit = [m for m in MANIFEST
           if m["expected_status"] == "review_no_profitable_offer"
           and m["offers_priced"] and max(c["ev"] for c in m["offers_priced"]) > 0]
    assert hit, ("no sample covers 'positive expected value, below the minimum'. "
                 "That branch would ship untested against real data.")
