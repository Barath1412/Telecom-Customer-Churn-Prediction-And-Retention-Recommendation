"""
Tests for the LangGraph itself.

Every test here runs against `FakeClient` — no API key, no network, no quota. The
point is the CONTROL FLOW: does each of the four outcomes take the right path, does
the retry cycle fire, does the fallback catch a stubborn model, does the human pause
survive a process boundary, and can the language model change a decision (it must
not).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src import fallback
from src.decision import STATUSES
from src.graph import MAX_ATTEMPTS, compile_graph, mermaid
from src.narration_client import FakeClient
from src.validators import validate

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"


def load(name: str) -> dict:
    return json.loads((SAMPLES / name).read_text())


def run(sample: str, script=None, auto=True, cp=None, cfg_extra=None):
    p = load(sample)
    app = compile_graph(cp)
    cfg = {"configurable": {"thread_id": f"t:{sample}:{script}",
                            "auto_approve": auto,
                            "client": FakeClient(script=script),
                            **(cfg_extra or {})}}
    out = app.invoke({"customer_id": p["customer_id"], "customer": p["customer"],
                      "cltv": float(p["cltv"])}, cfg)
    return p, out, app, cfg


ALL_SAMPLES = ["01_recommended_top_value.json",
               "02_review_no_profitable_offer.json",
               "03_review_no_applicable_offer.json",
               "04_no_action_needed.json"]


# ------------------------------------------------------------- the four paths --
@pytest.mark.parametrize("sample", ALL_SAMPLES)
def test_each_sample_reaches_the_status_it_claims(sample):
    p, out, _, _ = run(sample)
    assert out["status"] == p["_expected_status"]
    assert out["status"] in STATUSES


@pytest.mark.parametrize("sample", ALL_SAMPLES)
def test_every_run_ends_with_a_note_and_a_full_trace(sample):
    _, out, _, _ = run(sample)
    assert out["draft"] is not None, "no customer may end without a note"
    assert out["trace"][0] == "score_customer" and out["trace"][-1] == "persist"
    assert out["violations"] == []


def test_recommended_takes_the_evidence_and_narration_path():
    _, out, _, _ = run("01_recommended_top_value.json")
    assert "retrieve_evidence" in out["trace"]
    assert out["mode"] == "recommend" and out["source"] == "llm"
    assert len(out["evidence_ids"]) >= 4


@pytest.mark.parametrize("sample", ["02_review_no_profitable_offer.json",
                                    "03_review_no_applicable_offer.json"])
def test_both_review_outcomes_go_through_narrate_validate_human(sample):
    """The behaviour that was explicitly signed off: same five checks, same screen."""
    _, out, _, _ = run(sample)
    for node in ("explain_no_offer", "validate", "human_review:auto", "persist"):
        assert node in out["trace"], f"{node} missing from {out['trace']}"
    assert out["mode"] == "review" and out["offer_id"] is None


def test_no_action_never_calls_the_model():
    """649 of 1,409 customers land here. A model call for them would be pure waste."""
    _, out, _, _ = run("04_no_action_needed.json")
    assert out["trace"] == ["score_customer", "attribute", "extract_levers", "decide",
                            "no_action", "persist"]
    assert out["source"] == "deterministic"
    assert "narrate" not in " ".join(out["trace"])
    assert out.get("llm_usage", {}) == {}
    assert out["evidence_ids"] == []


def test_no_action_does_not_even_fetch_evidence():
    _, out, _, _ = run("04_no_action_needed.json")
    assert out["evidence_text"] == ""


# ----------------------------------------------------------- the retry cycle --
def test_a_bad_draft_is_rewritten_and_the_second_attempt_is_used():
    _, out, _, _ = run("01_recommended_top_value.json",
                       script=["invented_discount", "ok"])
    assert out["trace"].count("narrate#1") == 1
    assert out["trace"].count("narrate#2") == 1
    assert out["trace"].count("validate") == 2
    assert out["attempts"] == 2
    assert out["source"] == "llm" and out["violations"] == []


def test_the_cycle_stops_at_the_attempt_limit():
    _, out, _, _ = run("01_recommended_top_value.json",
                       script=["invented_discount", "wrong_offer", "ok"])
    assert out["attempts"] == MAX_ATTEMPTS
    assert "narrate#3" not in out["trace"], "the cycle must not run forever"
    assert out["source"] == "fallback_template"


def test_two_failures_fall_back_to_the_template():
    _, out, _, _ = run("01_recommended_top_value.json",
                       script=["invented_discount", "causal_claim"])
    assert "fallback" in out["trace"]
    assert out["source"] == "fallback_template"
    assert out["violations"] == [], "the template itself must pass every check"
    assert out["draft"]["summary"].startswith("0295-PPHDO")


def test_non_json_output_is_a_violation_not_a_crash():
    _, out, _, _ = run("01_recommended_top_value.json", script=["garbage", "ok"])
    assert out["source"] == "llm" and out["attempts"] == 2


def test_the_queue_never_stalls_whatever_the_model_does():
    """Every broken fixture, twice over. A note must still come out."""
    for bad in ("invented_discount", "wrong_offer", "fake_citation", "causal_claim",
                "missing_field", "garbage"):
        _, out, _, _ = run("01_recommended_top_value.json", script=[bad, bad])
        assert out["draft"] is not None, f"{bad} produced no note at all"
        assert out["source"] == "fallback_template"


# ------------------------------------------------------------ the human pause --
def test_interrupt_pauses_before_persist_and_resume_completes_it():
    _, out, app, cfg = run("01_recommended_top_value.json", auto=False,
                           cp=InMemorySaver())
    assert "__interrupt__" in out
    snap = app.get_state(cfg)
    assert snap.next == ("human_review",)
    assert "persist" not in (snap.values.get("trace") or [])

    final = app.invoke(Command(resume={"action": "reject", "actor": "agent_42",
                                       "note": "already contacted"}), cfg)
    assert final["agent_action"] == "reject"
    assert final["agent_actor"] == "agent_42"
    assert final["trace"][-1] == "persist"


def test_the_pause_payload_gives_the_agent_what_they_need_to_decide():
    _, out, _, _ = run("01_recommended_top_value.json", auto=False, cp=InMemorySaver())
    payload = out["__interrupt__"][0].value
    for k in ("customer_id", "status", "offer_id", "cost", "expected_value",
              "note", "options"):
        assert k in payload, f"{k} missing from the interrupt payload"
    assert payload["options"] == ["approve", "edit", "reject"]


def test_a_paused_run_survives_a_new_checkpointer_connection(tmp_path):
    """The reason for SQLite: the agent may approve tomorrow, from another process."""
    from langgraph.checkpoint.sqlite import SqliteSaver
    db = str(tmp_path / "cp.sqlite")
    p = load("01_recommended_top_value.json")
    cfg = {"configurable": {"thread_id": "restart-test", "auto_approve": False,
                           "client": FakeClient()}}
    with SqliteSaver.from_conn_string(db) as cp:
        app = compile_graph(cp)
        app.invoke({"customer_id": p["customer_id"], "customer": p["customer"],
                    "cltv": float(p["cltv"])}, cfg)
        assert app.get_state(cfg).next == ("human_review",)
    # connection closed; open the file fresh, as a later process would
    with SqliteSaver.from_conn_string(db) as cp:
        app = compile_graph(cp)
        assert app.get_state(cfg).next == ("human_review",)
        final = app.invoke(Command(resume={"action": "approve", "actor": "agent_7"}), cfg)
    assert final["agent_action"] == "approve" and final["trace"][-1] == "persist"


# ------------------------------------------- the model cannot change anything --
def test_persist_rejects_a_changed_decision():
    """
    The assertion that makes the whole design checkable. Feed node 9 an expectation
    that disagrees with what decide() produced and it must refuse to persist.
    """
    with pytest.raises(Exception) as e:
        run("01_recommended_top_value.json",
            cfg_extra={"expected_decision": {"offer_id": "OFF-AUTOPAY"}})
    assert "the decision changed during narration" in str(e.value)


def test_persist_accepts_the_decision_it_was_given():
    p = load("01_recommended_top_value.json")
    _, out, _, _ = run("01_recommended_top_value.json", cfg_extra={
        "expected_decision": {"offer_id": p["_expected_offer_id"],
                              "ev": p["_expected_expected_value"]}})
    assert out["trace"][-1] == "persist"


def test_the_score_is_a_probability_not_a_label():
    _, out, _, _ = run("01_recommended_top_value.json")
    assert 0.0 < out["p_churn"] < 1.0
    assert out["p_churn"] not in (0, 1)


def test_narration_is_never_asked_to_choose_an_offer():
    """The prompt states the decision; it never offers the model a choice."""
    from src import prompts
    p, out, _, _ = run("01_recommended_top_value.json")
    block = prompts.user_block(dict(out, customer_id=p["customer_id"],
                                    customer=p["customer"], cltv=p["cltv"]))
    assert "ALREADY MADE, NOT YOURS TO CHANGE" in block
    assert out["offer_id"] in block


# ------------------------------------------------------- structure and shape --
def test_every_state_value_is_json_serialisable():
    """If it is not, the SQLite checkpointer cannot save a paused run."""
    _, out, _, _ = run("01_recommended_top_value.json")
    json.dumps({k: v for k, v in out.items() if k != "__interrupt__"})


def test_the_graph_has_the_nodes_and_branches_we_signed_off():
    m = mermaid()
    for node in ("score_customer", "attribute", "extract_levers", "decide",
                 "retrieve_evidence", "explain_no_offer", "no_action", "narrate",
                 "validate", "fallback", "human_review", "persist"):
        assert node in m, f"{node} is not in the compiled graph"
    assert m.count("decide -.->") == 3, "the router must have exactly three exits"
    assert "validate -.-> narrate" in m, "the retry cycle is missing"
    assert "validate -.-> fallback" in m


def test_narrations_are_appended_to_the_log(tmp_path):
    log = tmp_path / "narrations.jsonl"
    run("01_recommended_top_value.json", cfg_extra={"narrations_path": str(log)})
    run("04_no_action_needed.json", cfg_extra={"narrations_path": str(log)})
    lines = [json.loads(x) for x in log.read_text().splitlines()]
    assert len(lines) == 2
    assert {l["source"] for l in lines} == {"llm", "deterministic"}
    for l in lines:
        for k in ("customer_id", "status", "draft", "attempts", "evidence_ids", "trace"):
            assert k in l


# ---------------------------------------------------- the template in isolation --
@pytest.mark.parametrize("status", STATUSES)
def test_the_deterministic_template_passes_validation_for_every_status(status):
    """
    It comes from f-strings so it cannot invent a figure -- but if it ever drifts
    (a renamed field, a changed unit) it must fail loudly, not be trusted blindly.

    Uses the graph's own context builder, so this also covers the seam that let the
    review-mode template name a rejected offer: the note must be allowed to say
    "the closest was OFF-CONTRACT-1Y, short by $7.50" without tripping V-OFFER.
    """
    from src.graph import _validation_context
    from src.kb_retrieval import select
    ev = select(["NO_TECH_SUPPORT", "NO_ONLINE_SECURITY", "MONTH_TO_MONTH"],
                "OFF-BUNDLE-ALL")
    state = {"customer_id": "TEST-0001", "status": status, "p_churn": 0.43,
             "cltv": 2040.0, "tenure_months": 1, "monthly_charges": 94.30,
             "lever_labels": "Rolling month-to-month contract",
             "offer_id": "OFF-BUNDLE-ALL",
             "offer_name": "Tech Support + Online Security bundle, 12 months",
             "cost": 120.51, "ev": 705.82, "delta_prior": 0.14,
             "delta_ci": [0.05, 0.24], "evidence_ids": ev.ids,
             "evidence_text": ev.text,
             "considered": [{"offer_id": "OFF-CONTRACT-1Y", "cost": 113.16,
                             "delta": 0.12, "ev": -7.5}]}
    assert validate(fallback.build(state), _validation_context(state)) == []


def test_a_review_note_may_name_the_offers_it_rejected():
    """
    The precise property: offers that WERE priced may be named; one that was not
    priced for this customer is still a violation.
    """
    from src.graph import _validation_context
    from src.kb_retrieval import select
    from src.validators import check_offer
    ev = select(["MONTH_TO_MONTH"], None)
    state = {"customer_id": "T", "status": "review_no_profitable_offer",
             "p_churn": 0.43, "cltv": 2040.0, "tenure_months": 43,
             "monthly_charges": 94.30, "offer_id": None, "offer_name": None,
             "cost": 0.0, "ev": 0.0, "delta_prior": 0.0, "delta_ci": [0, 0],
             "evidence_ids": ev.ids, "evidence_text": ev.text,
             "considered": [{"offer_id": "OFF-CONTRACT-1Y", "cost": 113.16,
                             "delta": 0.12, "ev": -7.5}]}
    ctx = _validation_context(state)
    assert check_offer("The closest was OFF-CONTRACT-1Y, short by $7.50.", ctx) == []
    assert check_offer("Try OFF-TECHSUP-12 instead.", ctx), \
        "an offer that was never priced must still be rejected"


# --------------------------------------------------------- the graph seam --
def test_the_graph_hands_the_validator_the_customers_current_contract():
    """
    THIS TEST EXISTS BECAUSE ITS ABSENCE COST A WHOLE MEASUREMENT ROUND. (v5.6)

    v5.5 fixed a V-OFFER false positive: a note saying "this customer is on a
    one-year contract" was being rejected as if it named an offer. The fix needed
    TWO files to agree -- validators.py to read `current_contract`, and graph.py to
    pass it in from the account record.

    The tests shipped with it built a ValidationContext BY HAND, so they passed with
    a stale graph.py. The suite went green, the fix was reported as landed, and the
    next Gemini run failed in exactly the same way, on exactly the same four
    customers. A test that skips the seam does not test the fix.

    This one goes through the graph's own context builder, so a stale graph.py
    fails pytest instead of failing silently twelve requests later.
    """
    from src.graph import _validation_context
    from src.kb_retrieval import select
    ev = select(["NO_TECH_SUPPORT"], "OFF-TECHSUP-12")
    state = {
        "customer_id": "0471-ARVMX",
        "customer": {"Contract": "One year", "Internet Service": "Fiber optic",
                     "Payment Method": "Mailed check", "Tech Support": "No"},
        "status": "recommended", "p_churn": 0.3045, "cltv": 5061.0,
        "tenure_months": 62, "monthly_charges": 104.85,
        "offer_id": "OFF-TECHSUP-12",
        "offer_name": "Tech Support bundled free for 12 months",
        "cost": 60.35, "ev": 62.94, "delta_prior": 0.08, "delta_ci": [0.02, 0.15],
        "evidence_ids": ev.ids, "evidence_text": ev.text, "considered": [],
    }
    ctx = _validation_context(state)
    assert ctx.current_contract == "One year", (
        "graph.py is not passing the account's Contract into the validation "
        "context. src/graph.py is stale — re-copy it.")

    from src.narration_client import Draft
    d = Draft(summary="Fiber customer, 62 months with us at $104.85 a month, "
                      "30.4% churn risk, with no tech support add-on.",
              why="This customer is on a one-year contract and has no tech support "
                  "add-on. Accounts without tech support left at 41.64% in past data.",
              talk_track="We can add Tech Support bundled free for 12 months, at no "
                         "extra cost to you.",
              evidence_ids=[ev.ids[0]])
    assert [v for v in validate(d, ctx) if v.code == "V-OFFER"] == []


def test_a_month_to_month_customer_still_gets_the_strict_check():
    """The seam must not turn the exemption on for everybody."""
    from src.graph import _validation_context
    from src.kb_retrieval import select
    from src.narration_client import Draft
    ev = select(["NO_TECH_SUPPORT"], "OFF-BUNDLE-ALL")
    state = {
        "customer_id": "1400-MMYXY",
        "customer": {"Contract": "Month-to-month", "Tech Support": "No"},
        "status": "recommended", "p_churn": 0.8668, "cltv": 3000.0,
        "tenure_months": 3, "monthly_charges": 105.90,
        "offer_id": "OFF-BUNDLE-ALL",
        "offer_name": "Tech Support + Online Security bundle, 12 months",
        "cost": 120.51, "ev": 208.96, "delta_prior": 0.14, "delta_ci": [0.05, 0.24],
        "evidence_ids": ev.ids, "evidence_text": ev.text, "considered": [],
    }
    ctx = _validation_context(state)
    assert ctx.current_contract == "Month-to-month"
    d = Draft(summary="Fiber customer, 3 months with us at $105.90 a month, "
                      "86.7% churn risk, with no tech support add-on.",
              why="Accounts without tech support left at 41.64% in past data.",
              talk_track="We could look at a one-year contract for you instead.",
              evidence_ids=[ev.ids[0]])
    assert [v for v in validate(d, ctx) if v.code == "V-OFFER"], (
        "the alias check must stay live when the phrase is not the status quo")
