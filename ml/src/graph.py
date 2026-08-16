"""
The LangGraph. Nine nodes, one three-way router, one retry cycle, one human pause.

    START
      1 score_customer          the trained model reads the raw account row
      2 attribute               SHAP top-5 — model behaviour, not motive
      3 extract_levers          9 deterministic field lookups
      4 decide                  price · rank by EV · 6 policy rules
      |
      +-- route_by_outcome ------------------------------------------------+
      |                          |                                        |
      5a retrieve_evidence       5b explain_no_offer                       5c no_action
         (recommended)              (review_no_profitable_offer,              (no_action_needed)
          |                          review_no_applicable_offer)               |
          +------------+-------------+                                         |
                       6 narrate     <-------------------+                     |
                       7 validate ---- route_after ------+ (rewrite, max 2)    |
                            |               |                                  |
                            |               +--> fallback --+                  |
                            +-- clean ----------------------+                  |
                                            8 human_review  interrupt()        |
                                                   |                           |
                       9 persist  <-----------------+---------------------------+
                          END

WHY THE ML MODEL IS INSIDE THE GRAPH
    Nodes 1-4 wrap code that already existed and is already tested. Putting them in
    the graph makes it self-contained: hand it one customer JSON and watch nine
    nodes run. The batch runner scores everyone first to RANK them -- so node 1
    re-scores, costing ~2ms, and that redundancy is deliberate: if the graph's score
    ever disagrees with the runner's, something is broken and we want to know.

WHAT IS NOT IN THE GRAPH, AND WHY IT CANNOT BE
    The capacity cut. A single customer's node cannot know its own rank -- rank is a
    property of the group. Ranking lives in src/run_batch.py.

STATE IS JSON ONLY
    The checkpointer serialises state to SQLite. Nothing unpicklable goes in: no
    model, no DataFrame, no dataclass. Everything is dict / list / float / str.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from . import fallback, prompts
from .decision import BASE_RATE, Catalog, decide
from .kb_retrieval import select
from .narration_client import Draft, build_client
from .validators import context_from_decision, feedback, validate

ROOT = Path(__file__).resolve().parent.parent
MAX_ATTEMPTS = 2


class GraphState(TypedDict, total=False):
    # ---- input -----------------------------------------------------------
    customer_id: str
    customer: dict                      # the raw account row, as a plain dict
    cltv: float
    # ---- node 1 ----------------------------------------------------------
    p_churn: float
    monthly_charges: float
    tenure_months: int
    # ---- node 2 ----------------------------------------------------------
    attribution: list
    attribution_disclaimer: str
    # ---- node 3 ----------------------------------------------------------
    levers: list
    lever_labels: str
    # ---- node 4 : WRITTEN ONCE, RE-ASSERTED AT NODE 9 --------------------
    status: str
    offer_id: str | None
    offer_name: str | None
    cost: float
    delta_prior: float
    delta_ci: list
    ev: float
    considered: list
    vetoed: list
    policy_trace: list
    rules_not_evaluable: list
    min_ev_floor: float                 # the R3 minimum this decision was judged on
    risk_vs_base: str                   # "below" | "at" | "above" — DISPLAY ONLY
    # ---- node 5 ----------------------------------------------------------
    mode: str                           # "recommend" | "review" | "none"
    evidence_ids: list
    evidence_text: str
    # ---- node 6 ----------------------------------------------------------
    draft: dict | None
    attempts: int
    llm_model: str
    llm_usage: dict
    # ---- node 7 ----------------------------------------------------------
    violations: list                    # the CURRENT attempt's verdict only
    violation_history: list             # every attempt's verdict, appended (v5.4)
    source: str                         # "llm" | "fallback_template" | "deterministic"
    # ---- node 8 ----------------------------------------------------------
    agent_action: str
    agent_note: str
    agent_actor: str
    # ---- node 9 ----------------------------------------------------------
    trace: list                         # every node that ran, in order


# --------------------------------------------------------------------------- #
#  Heavy objects are module-level and cached. They must never enter state.
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _model():
    import joblib
    reg = json.loads((ROOT / "artifacts" / "model_registry.json").read_text())
    sel = next(m for m in reg["models"] if m["selected"])
    return joblib.load(ROOT / sel["artifact_path"]), sel


@lru_cache(maxsize=1)
def _catalog():
    return Catalog.load()


def _feature_frame(customer: dict) -> "Any":
    """One raw account row -> the exact feature frame the pipeline was fitted on."""
    import pandas as pd
    from .contracts import NOMINAL, NUMERIC, ORDINAL
    cols = [*NOMINAL, *ORDINAL, *NUMERIC]
    missing = [c for c in cols if c not in customer]
    if missing:
        raise ValueError(f"customer record is missing required fields: {missing}")
    return pd.DataFrame([{c: customer[c] for c in cols}])


def _step(state: GraphState, name: str) -> list:
    return [*state.get("trace", []), name]


# --------------------------------------------------------------------------- #
#  NODES 1-4 — deterministic. No AI anywhere in here.
# --------------------------------------------------------------------------- #
def score_customer(state: GraphState) -> dict:
    pipe, _ = _model()
    X = _feature_frame(state["customer"])
    p = float(pipe.predict_proba(X)[:, 1][0])
    # predict_proba, never predict. A 0/1 label cannot be ranked and cannot enter
    # an expected-value calculation; see README.
    assert 0.0 < p < 1.0, "the model must never assert certainty"
    return {"p_churn": round(p, 4),
            "monthly_charges": float(state["customer"]["Monthly Charges"]),
            "tenure_months": int(state["customer"]["Tenure Months"]),
            "attempts": 0, "trace": _step(state, "score_customer")}


def attribute(state: GraphState) -> dict:
    from .attribution import DISCLAIMER, attribute as shap_attribute
    try:
        rows = shap_attribute(_feature_frame(state["customer"]), top_k=5)[0]
        contribs = rows.get("model_attribution", [])
    except Exception as e:                                        # pragma: no cover
        # SHAP is the one optional step. The graph continues without it rather than
        # failing a whole run over an explanation -- but say what to do, because the
        # usual cause is a scikit-learn version older than the one the model was
        # pickled with (1.8.0), which also produces InconsistentVersionWarning.
        contribs = []
        import sklearn
        print(f"  [attribute] SHAP unavailable ({type(e).__name__}: {e}). "
              f"Continuing without it.\n"
              f"              You have scikit-learn {sklearn.__version__}; the model "
              f"was pickled with 1.8.0.\n"
              f"              Fix with:  pip install -U \"scikit-learn>=1.8.0\"")
    return {"attribution": contribs, "attribution_disclaimer": DISCLAIMER,
            "trace": _step(state, "attribute")}


def extract_levers(state: GraphState) -> dict:
    from .levers import describe, extract
    codes = extract(state["customer"])
    return {"levers": codes, "lever_labels": describe(codes),
            "trace": _step(state, "extract_levers")}


def decide_node(state: GraphState) -> dict:
    rec = decide(customer_id=state["customer_id"], p_churn=state["p_churn"],
                 cltv=float(state["cltv"]), row=state["customer"],
                 catalog=_catalog())
    d = asdict(rec)
    d.pop("levers", None)                     # already in state from node 3
    d.pop("p_churn", None)
    d.pop("customer_id", None)
    d.pop("cltv", None)
    d["trace"] = _step(state, "decide")
    return d


def route_by_outcome(state: GraphState) -> str:
    """The first conditional edge. Four statuses, three destinations."""
    status = state["status"]
    if status == "recommended":
        return "retrieve_evidence"
    if status.startswith("review_"):
        return "explain_no_offer"
    return "no_action"


# --------------------------------------------------------------------------- #
#  NODES 5a / 5b / 5c — build the context for the note. Still no AI.
# --------------------------------------------------------------------------- #
def retrieve_evidence(state: GraphState) -> dict:
    ev = select(list(state["levers"]), state.get("offer_id"))
    return {"mode": "recommend", "evidence_ids": ev.ids,
            "evidence_text": prompts.EVIDENCE_FRAME and ev.text,
            "trace": _step(state, "retrieve_evidence")}


def explain_no_offer(state: GraphState) -> dict:
    # No offer was chosen, so there is no DELTA document to fetch -- the evidence is
    # the lever documents plus the policies, which is exactly what select() returns
    # when offer_id is None.
    ev = select(list(state["levers"]), None)
    return {"mode": "review", "evidence_ids": ev.ids, "evidence_text": ev.text,
            "trace": _step(state, "explain_no_offer")}


def no_action(state: GraphState) -> dict:
    """
    649 of 1,409 customers end here. No evidence is fetched, no prompt is built and
    no request is sent. The note is one deterministic sentence.
    """
    draft = fallback.build(dict(state), BASE_RATE)
    return {"mode": "none", "evidence_ids": [], "evidence_text": "",
            "draft": draft.model_dump(), "source": "deterministic",
            "violations": [], "trace": _step(state, "no_action")}


# --------------------------------------------------------------------------- #
#  NODE 6 — THE ONLY PLACE A LANGUAGE MODEL RUNS
# --------------------------------------------------------------------------- #
def narrate(state: GraphState, config) -> dict:
    cfg = config.get("configurable", {}) if config else {}
    client = cfg.get("client") or build_client(cfg.get("provider"))
    system = prompts.system_prompt()
    user = prompts.user_block(dict(state))
    if state.get("violations"):
        user = prompts.retry_block(user, "\n".join(state["violations"]))

    result = client.narrate(system, user)
    attempts = int(state.get("attempts", 0)) + 1
    if not result.ok:
        # A provider error or unparsable output is a violation, not an exception.
        return {"draft": None, "attempts": attempts,
                "violations": [result.error or "V-SCHEMA: no draft returned"],
                "llm_model": result.model, "llm_usage": result.usage,
                "trace": _step(state, f"narrate#{attempts}")}
    return {"draft": result.draft.model_dump(), "attempts": attempts, "violations": [],
            "llm_model": result.model, "llm_usage": result.usage, "source": "llm",
            "trace": _step(state, f"narrate#{attempts}")}


# --------------------------------------------------------------------------- #
#  NODE 7 — the five checks
# --------------------------------------------------------------------------- #
def _validation_context(state: GraphState):
    class _Rec:                       # a thin shim: context_from_decision reads attrs
        offer_id = None
    r = _Rec()
    for k in ("offer_id", "offer_name", "cost", "p_churn", "cltv", "ev",
              "delta_prior", "monthly_charges", "tenure_months"):
        setattr(r, k, state.get(k) if state.get(k) is not None else 0)
    r.offer_id = state.get("offer_id") or ""
    r.offer_name = state.get("offer_name") or ""
    r.cltv = float(state["cltv"])
    # V-PLAIN rejects anything that looks like a document reference. The note is
    # allowed to name the customer it is about, so the id has to reach the context.
    r.customer_id = state.get("customer_id") or ""

    class _Ev:
        ids = list(state.get("evidence_ids") or [])
        text = state.get("evidence_text") or ""
    # The account's CURRENT contract term. V-OFFER needs it to tell "this customer
    # is on a one-year contract" (a fact the agent needs) apart from "let me move
    # you to a one-year contract" (naming an offer that was not chosen).
    return context_from_decision(
        r, _Ev(), _catalog(), considered=state.get("considered"),
        current_contract=(state.get("customer") or {}).get("Contract", ""))


def _record(state: GraphState, outcome: str, violations: list) -> list:
    """
    KEEP EVERY ATTEMPT'S VERDICT, NOT JUST THE LAST ONE.  (v5.4)

    `violations` is overwritten on each pass and cleared by the fallback, so after
    a run that failed twice and shipped the template the record read `[]` -- the
    note looked clean and the reason it was rejected was gone. Measured over three
    seeded runs, the retry recovered 0 of 7 times, and neither of us could say why,
    because the only evidence had been discarded.

    This appends instead of replacing, exactly like `trace`. At most two entries
    per customer, so it costs nothing and it survives into narrations.jsonl.
    """
    return [*state.get("violation_history", []), {
        "attempt": int(state.get("attempts", 0)),
        "model": state.get("llm_model"),
        "outcome": outcome,                       # clean | rejected | no_draft
        "codes": sorted({str(v).split(":")[0] for v in violations}),
        "violations": [str(v) for v in violations],
    }]


def validate_node(state: GraphState) -> dict:
    if state.get("draft") is None:
        # The provider never answered, or the output would not parse. `violations`
        # is already set by narrate(); record it here so the trail is complete.
        vs = state.get("violations") or ["V-SCHEMA: no draft returned"]
        return {"violation_history": _record(state, "no_draft", vs),
                "trace": _step(state, "validate")}
    draft = Draft.model_validate(state["draft"])
    vs = validate(draft, _validation_context(state))
    return {"violations": [str(v) for v in vs],
            "violation_history": _record(state, "rejected" if vs else "clean", vs),
            "trace": _step(state, "validate")}


def route_after_validate(state: GraphState) -> str:
    """The retry cycle, the fallback branch, and the way out."""
    if not state.get("violations"):
        return "human_review"
    if int(state.get("attempts", 0)) < MAX_ATTEMPTS:
        return "narrate"
    return "fallback"


def fallback_node(state: GraphState) -> dict:
    """
    Two rewrites failed. Ship the template so the queue never stalls, and record
    that this happened -- a rising fallback rate is a signal, not noise.
    """
    d = fallback.build(dict(state), BASE_RATE)
    vs = validate(d, _validation_context(state))
    if vs:                                                        # pragma: no cover
        # The template itself is broken. Fail loudly rather than send it.
        raise AssertionError(f"the deterministic template failed validation: {vs}")
    return {"draft": d.model_dump(), "source": "fallback_template", "violations": [],
            "trace": _step(state, "fallback")}


# --------------------------------------------------------------------------- #
#  NODE 8 — the human pause
# --------------------------------------------------------------------------- #
def human_review(state: GraphState, config) -> dict:
    """
    `interrupt()` stops the run here. The state is already in the checkpoint, so the
    process can exit, the machine can restart, and the run resumes days later with
    Command(resume={...}).

    auto_approve=True skips the pause. That is for testing and for the demo -- never
    for a real queue, because nothing may reach a customer without a human.
    """
    cfg = config.get("configurable", {}) if config else {}
    if cfg.get("auto_approve"):
        return {"agent_action": "approve", "agent_actor": "auto_approve",
                "agent_note": "", "trace": _step(state, "human_review:auto")}

    answer = interrupt({
        "customer_id": state["customer_id"],
        "status": state["status"],
        "offer_id": state.get("offer_id"),
        "cost": state.get("cost"),
        "expected_value": state.get("ev"),
        "note": state.get("draft"),
        "source": state.get("source"),
        "options": ["approve", "edit", "reject"],
    })
    if isinstance(answer, str):
        answer = {"action": answer}
    return {"agent_action": answer.get("action", "approve"),
            "agent_actor": answer.get("actor", "unknown"),
            "agent_note": answer.get("note", ""),
            "trace": _step(state, "human_review")}


# --------------------------------------------------------------------------- #
#  NODE 9 — persist, and prove the model changed nothing
# --------------------------------------------------------------------------- #
def persist(state: GraphState, config) -> dict:
    cfg = config.get("configurable", {}) if config else {}
    expected = cfg.get("expected_decision")
    if expected:
        # THE ASSERTION THAT MAKES THE WHOLE DESIGN CHECKABLE.
        # The runner passes in the decision it computed before the graph ran. If the
        # offer, the price or the expected value differ by the time we persist, the
        # narration layer has influenced a decision and that is a hard failure.
        for k in ("offer_id", "cost", "ev"):
            if k not in expected:          # the caller may assert only some fields
                continue
            got, want = state.get(k), expected.get(k)
            if isinstance(want, float) or isinstance(got, float):
                same = abs(float(got or 0) - float(want or 0)) < 0.005
            else:
                same = got == want
            if not same:
                raise AssertionError(
                    f"the decision changed during narration: {k} was {want!r}, "
                    f"is now {got!r}. The LLM must not be able to do this.")

    out = {"customer_id": state["customer_id"], "status": state["status"],
           "p_churn": state["p_churn"], "cltv": state["cltv"],
           "offer_id": state.get("offer_id"), "cost": state.get("cost"),
           "expected_value": state.get("ev"),
           "levers": state.get("levers"), "mode": state.get("mode"),
           "draft": state.get("draft"), "source": state.get("source"),
           "attempts": state.get("attempts", 0),
           "violations_final": state.get("violations") or [],
           "violation_history": state.get("violation_history") or [],
           "evidence_ids": state.get("evidence_ids") or [],
           "llm_model": state.get("llm_model"), "llm_usage": state.get("llm_usage") or {},
           "agent_action": state.get("agent_action"),
           "agent_actor": state.get("agent_actor"),
           "agent_note": state.get("agent_note"),
           "rules_not_evaluable": state.get("rules_not_evaluable") or [],
           "min_ev_floor": state.get("min_ev_floor", 0.0),
           "risk_vs_base": state.get("risk_vs_base"),
           "trace": _step(state, "persist")}
    path = cfg.get("narrations_path")
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as fh:
            fh.write(json.dumps(out) + "\n")
    return {"trace": out["trace"]}


# --------------------------------------------------------------------------- #
def build_graph() -> StateGraph:
    g = StateGraph(GraphState)
    for name, fn in [("score_customer", score_customer), ("attribute", attribute),
                     ("extract_levers", extract_levers), ("decide", decide_node),
                     ("retrieve_evidence", retrieve_evidence),
                     ("explain_no_offer", explain_no_offer), ("no_action", no_action),
                     ("narrate", narrate), ("validate", validate_node),
                     ("fallback", fallback_node), ("human_review", human_review),
                     ("persist", persist)]:
        g.add_node(name, fn)

    g.add_edge(START, "score_customer")
    g.add_edge("score_customer", "attribute")
    g.add_edge("attribute", "extract_levers")
    g.add_edge("extract_levers", "decide")
    g.add_conditional_edges("decide", route_by_outcome,
                            {"retrieve_evidence": "retrieve_evidence",
                             "explain_no_offer": "explain_no_offer",
                             "no_action": "no_action"})
    g.add_edge("retrieve_evidence", "narrate")
    g.add_edge("explain_no_offer", "narrate")
    g.add_edge("no_action", "persist")
    g.add_edge("narrate", "validate")
    g.add_conditional_edges("validate", route_after_validate,
                            {"narrate": "narrate", "fallback": "fallback",
                             "human_review": "human_review"})
    g.add_edge("fallback", "human_review")
    g.add_edge("human_review", "persist")
    g.add_edge("persist", END)
    return g


def compile_graph(checkpointer=None):
    """
    checkpointer=None -> no pause is possible; use only with auto_approve.
    Pass a SqliteSaver (or InMemorySaver) to enable interrupt() and resume.
    """
    return build_graph().compile(checkpointer=checkpointer)


def mermaid() -> str:
    """The diagram, drawn by the code. It cannot disagree with what runs."""
    return compile_graph().get_graph().draw_mermaid()


if __name__ == "__main__":
    out = ROOT / "artifacts" / "graph.mermaid"
    out.parent.mkdir(exist_ok=True)
    m = mermaid()
    out.write_text(m)
    print(m)
    print(f"\nwrote {out.relative_to(ROOT)}")
