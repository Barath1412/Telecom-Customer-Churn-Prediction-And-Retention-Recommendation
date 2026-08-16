"""
Tests for serve-time evidence retrieval.

The two weaknesses these exist to close:

  (a) Four levers used to map to no evidence at all. No customer happened to end
      up empty-handed, but that was luck. `test_every_lever_has_evidence` now
      fails loudly the moment a lever is added without a document.

  (b) Cohort documents keyed on `Churn Reason` could reach a live prompt, where
      they invite the model to guess a motive. `test_no_reason_keyed_document_is_
      ever_retrieved` proves it cannot happen -- exhaustively, over all 512
      possible lever combinations, for every offer in the catalog.
"""
from __future__ import annotations

from itertools import combinations

import pytest

from src.decision import Catalog
from src.kb_retrieval import (SERVE_TIME, Evidence, assert_lever_coverage,
                              lever_document_map, registry, render_for_prompt,
                              select)
from src.levers import LEVERS

ALL_LEVERS = sorted(LEVERS)
OFFER_IDS = [o.offer_id for o in Catalog.load().offers]


def all_lever_subsets():
    for k in range(len(ALL_LEVERS) + 1):
        for combo in combinations(ALL_LEVERS, k):
            yield list(combo)


# --------------------------------------------------------------- coverage --
def test_every_lever_has_evidence():
    """Weakness (a). This assertion did not exist before KB v4 and would have failed."""
    assert_lever_coverage()
    have = lever_document_map()
    missing = [c for c in LEVERS if c not in have]
    assert missing == [], f"levers with no evidence document: {missing}"


def test_lever_documents_are_one_to_one():
    have = lever_document_map()
    assert len(have) == len(set(have.values())) == len(LEVERS)


def test_no_customer_can_end_up_with_an_unmapped_lever():
    for levers in all_lever_subsets():
        assert select(levers, OFFER_IDS[0]).unmapped_levers == []


# ------------------------------------------------- no motive leaks (b) --
def test_no_reason_keyed_document_is_ever_retrieved():
    """Weakness (b), proved exhaustively: 512 lever sets x every offer."""
    docs = registry()["documents"]
    for offer in OFFER_IDS + [None]:
        for levers in all_lever_subsets():
            for did in select(levers, offer).ids:
                assert docs[did]["applies_to"] == SERVE_TIME, (
                    f"{did} is {docs[did]['applies_to']} and reached a live prompt")
                assert not did.startswith(("ASSOC", "HIST")), f"{did} is reason-keyed"


def test_registry_marks_reason_keyed_documents():
    docs = registry()["documents"]
    reason_keyed = [d for d in docs if d.startswith(("ASSOC", "HIST"))]
    assert len(reason_keyed) >= 39
    assert all(docs[d]["applies_to"] != SERVE_TIME for d in reason_keyed)


def test_serve_time_set_is_only_policy_delta_lever_outcome():
    docs = registry()["documents"]
    serve = {d for d, m in docs.items() if m["applies_to"] == SERVE_TIME}
    assert all(d.startswith(("POLICY", "DELTA", "LEVER", "OUTCOME")) for d in serve)


# ------------------------------------------------------------ selection --
def test_policy_documents_are_always_present():
    for levers in ([], ALL_LEVERS, ["MANUAL_PAYMENT"]):
        ids = select(levers, None).ids
        assert sum(1 for d in ids if d.startswith("POLICY")) == 3


def test_manual_payment_alone_now_yields_evidence():
    """The exact case that used to produce zero thematic evidence."""
    ev = select(["MANUAL_PAYMENT"], "OFF-AUTOPAY")
    assert any(d.startswith("LEVER") for d in ev.ids)
    assert any(d.startswith("DELTA") for d in ev.ids)
    # v5.3: the evidence is rendered for a human reader, so the lever appears as
    # its LABEL and not as the code. The code still exists -- in levers.py, in the
    # decision record and in the CSV -- it is simply not what the model is shown.
    from src.levers import LEVERS
    assert LEVERS["MANUAL_PAYMENT"].label in ev.text
    assert "MANUAL_PAYMENT" not in ev.text, (
        "a lever CODE reached the prompt; that is what the model then quotes")


def test_offer_delta_document_is_included():
    docs = registry()["documents"]
    for offer in OFFER_IDS:
        ids = select(["MONTH_TO_MONTH"], offer).ids
        deltas = [d for d in ids if d.startswith("DELTA")]
        assert len(deltas) == 1
        assert docs[deltas[0]]["offer"] == offer


def test_unknown_offer_is_survivable():
    ev = select(["MONTH_TO_MONTH"], "OFF-DOES-NOT-EXIST")
    assert not any(d.startswith("DELTA") for d in ev.ids)
    assert len(ev.ids) >= 4          # policies + the lever document


def test_no_offer_still_returns_policy_and_levers():
    ev = select(["NO_TECH_SUPPORT"], None)
    assert len(ev.ids) == 4          # 3 policy + 1 lever


# --------------------------------------------------------- determinism --
def test_selection_is_deterministic_and_order_independent():
    a = select(["MONTH_TO_MONTH", "NO_TECH_SUPPORT"], "OFF-TECHSUP-12")
    b = select(["NO_TECH_SUPPORT", "MONTH_TO_MONTH"], "OFF-TECHSUP-12")
    assert a.ids == b.ids == sorted(a.ids)
    assert a.text == b.text


def test_duplicate_levers_do_not_duplicate_documents():
    a = select(["NO_TECH_SUPPORT"], None)
    b = select(["NO_TECH_SUPPORT", "NO_TECH_SUPPORT"], None)
    assert a.ids == b.ids


# ------------------------------------------------------------- payload --
def test_every_returned_id_exists_and_has_text():
    docs = registry()["documents"]
    ev = select(ALL_LEVERS, OFFER_IDS[0])
    for did in ev.ids:
        assert did in docs
        # v5.3: the id moved out of the heading and into an explicit filing
        # reference line. It is still present for every document -- that is the
        # property this test is about -- it is just no longer the title.
        assert f"**Filing reference:** {did}" in ev.text


def test_worst_case_payload_stays_small():
    """Largest possible retrieval must not blow the prompt budget."""
    ev = select(ALL_LEVERS, OFFER_IDS[0])
    assert len(ev.ids) <= 20
    assert ev.approx_tokens < 6000, ev.approx_tokens


def test_state_payload_shape():
    st = select(["MONTH_TO_MONTH"], "OFF-CONTRACT-1Y").as_state()
    assert st["evidence_ids"] == st["allowed_ids"]
    assert st["evidence_tokens"] > 0


def test_prompt_frame_is_present():
    ev = select(["MONTH_TO_MONTH"], "OFF-CONTRACT-1Y")
    rendered = render_for_prompt(ev)
    assert "Do not infer a motive" in rendered
    assert ev.text in rendered


def test_evidence_is_immutable():
    ev = select(["MONTH_TO_MONTH"], None)
    with pytest.raises(Exception):
        ev.ids = []                                    # type: ignore[misc]
    assert isinstance(ev, Evidence)


# ------------------------------------------- v5.7: what the model is shown --
def test_every_lever_document_carries_a_ready_written_sentence():
    """
    Roughly one note in twelve inverted a comparison -- "those WITH device
    protection have a churn rate of 39.13%", when that is the rate for accounts
    WITHOUT it. Every such note passed all six validators: the figure was real,
    cited and correctly rounded, and no check looks at DIRECTION.

    So the sentence is written out for the model instead of left to be assembled.
    This test asserts the parse still works for all nine -- if the knowledge base
    changes shape the hint is silently dropped at runtime, which is safe, but the
    suite must say so rather than let the inversions quietly return.
    """
    from src.kb_retrieval import _load, _ready_made_sentence
    reg, bodies = _load()
    docs = reg["documents"]
    levers = [d for d, m in docs.items() if m["type"] == "LEVER"]
    assert len(levers) == 9
    for did in levers:
        line = _ready_made_sentence(docs[did], bodies[did])
        assert line, f"{did} produced no ready-written sentence"
        assert "applies left at" in line and "does not left at" in line
        assert "26.54%" in line, "the base rate must be in the same sentence"


def test_the_rendering_drops_exactly_the_figures_it_means_to():
    """
    Every figure in the evidence lands on V-MONEY's whitelist, so removing one
    makes it unquotable. v5.7 removes the DELTA derivation line ON PURPOSE -- that
    is what turns "never quote the churn rate of the group the offer would move
    them into" from a request into a rule the money check enforces for free.

    An ACCIDENTAL removal would silently start rejecting true notes, so the exact
    set is pinned here. 2.8 and 11.3 are the two-year and one-year churn rates:
    the ones real notes were quoting next to a contract offer.
    """
    from src.kb_retrieval import _load, _humanise, figures_dropped
    reg, bodies = _load()
    docs = reg["documents"]
    before = "\n".join(b for d, b in bodies.items() if d in docs)
    after = "\n".join(_humanise(d, b, docs[d]) for d, b in bodies.items() if d in docs)
    dropped = set(figures_dropped(before, after))
    assert {"2.8", "11.3"} <= dropped, "the target-state contract rates must go"
    assert {"14.6", "15.2"} <= dropped, "the target-state add-on rates must go"
    # The customer's OWN group rates survive at full precision in the lever
    # documents, so the 1-dp forms stay quotable through V-MONEY's tolerance.
    assert "41.64" not in dropped and "42.71" not in dropped


def test_no_lever_code_and_no_delta_field_name_reaches_the_prompt():
    """The rendering is the first line of defence; V-PLAIN is the second."""
    from src.kb_retrieval import select
    from src.levers import LEVERS
    text = select(list(LEVERS), "OFF-CONTRACT-2Y").text
    for code in LEVERS:
        assert code not in text, f"lever code {code} reached the prompt"
    for field in ("delta_prior", "delta_ci", "delta_source", "business_judgment_v1"):
        assert field not in text, f"{field} reached the prompt"
