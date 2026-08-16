"""
Tests for the five narration validators.

The point of this file is the FAILURE cases. A test suite that only feeds a
validator well-formed input proves nothing — node 4 exists for the bad drafts,
so every check has a fixture that must trip it, and one that must not.
"""
from __future__ import annotations

import pytest

from src.decision import Catalog
from src.kb_retrieval import select
from src.narration_client import BAD_DRAFTS, GOOD_DRAFT, Draft, FakeClient
from src.validators import (CAUSAL_ALLOWLIST, ValidationContext, check_causal,
                            check_citations, check_money, check_offer,
                            check_schema, feedback, load_registry_ids, validate)

CATALOG = Catalog.load()
OFFERS = {o.offer_id: o for o in CATALOG.offers}
CHOSEN = OFFERS["OFF-BUNDLE-ALL"]
LEVERS = ["NO_TECH_SUPPORT", "NO_ONLINE_SECURITY", "MONTH_TO_MONTH"]


@pytest.fixture(scope="module")
def ctx() -> ValidationContext:
    ev = select(LEVERS, CHOSEN.offer_id)
    return ValidationContext(
        offer_id=CHOSEN.offer_id, offer_name=CHOSEN.name, cost=120.51,
        p_churn=0.99, cltv=5962.0, expected_value=705.82,
        delta_prior=0.14, delta_ci=(0.05, 0.24),
        monthly_charges=95.45, tenure_months=1,
        allowed_evidence_ids=tuple(ev.ids), evidence_text=ev.text,
        other_offer_ids=tuple(o for o in OFFERS if o != CHOSEN.offer_id),
        other_offer_names=tuple(o.name for oid, o in OFFERS.items()
                                if oid != CHOSEN.offer_id))


def draft(**over) -> Draft:
    return Draft.model_validate({**GOOD_DRAFT, **over})


# ------------------------------------------------------------ the fixtures --
def test_good_draft_passes_every_check(ctx):
    assert validate(draft(), ctx) == []


@pytest.mark.parametrize("fixture,expected", [
    ("invented_discount", "V-MONEY"),
    ("wrong_offer", "V-OFFER"),
    ("fake_citation", "V-CITE"),
    ("causal_claim", "V-CAUSAL"),
])
def test_each_bad_fixture_is_caught_by_its_own_check(fixture, expected, ctx):
    d = Draft.model_validate(BAD_DRAFTS[fixture])
    codes = {v.code for v in validate(d, ctx)}
    assert expected in codes, f"{fixture} was not caught by {expected}: {codes}"


def test_schema_invalid_fixtures_never_reach_the_content_checks():
    """These two fail the provider schema, which is the cheaper gate."""
    with pytest.raises(Exception):
        Draft.model_validate(BAD_DRAFTS["missing_field"])
    assert BAD_DRAFTS["garbage"] is None       # not even JSON


# ---------------------------------------------------------------- V-MONEY --
def test_invented_discount_is_rejected(ctx):
    d = draft(talk_track="Good news, I can take 25% off your bill today for you.")
    v = check_money(" ".join([d.summary, d.why, d.talk_track]), ctx)
    assert [x.code for x in v] == ["V-MONEY"]
    assert "25%" in v[0].detail


def test_figures_quoted_from_the_evidence_are_allowed(ctx):
    """LEVER-060 reports 41.64% / 11.85%; a note may round them."""
    text = "accounts without tech support left at 41.6% against 11.9%"
    assert check_money(text, ctx) == []


def test_rounding_tolerance_is_half_a_unit_in_the_last_place(ctx):
    # 41.64 -> 41.6 is a correct rounding; 41.0 is not.
    assert ctx.permits(41.6, 1)
    assert not ctx.permits(41.0, 1)
    # Python rounds half to even, so 11.85 -> round(...,1) is 11.8. The correct
    # human rounding 11.9 must still pass. This is the regression this guards.
    assert ctx.permits(11.9, 1)


def test_the_customers_own_cost_is_allowed(ctx):
    assert check_money("The bundle costs us $120.51 over the year.", ctx) == []


def test_a_price_from_a_different_customer_is_rejected(ctx):
    assert [v.code for v in check_money("It comes to $180.27.", ctx)] == ["V-MONEY"]


def test_discount_with_the_sign_dropped_is_still_caught(ctx):
    v = check_money("I can take 30 off your monthly bill.", ctx)
    assert [x.code for x in v] == ["V-MONEY"]


def test_a_figure_is_reported_once_not_per_occurrence(ctx):
    v = check_money("25% today and 25% next month.", ctx)
    assert len(v) == 1


# ---------------------------------------------------------------- V-OFFER --
def test_naming_a_different_offer_id_is_rejected(ctx):
    v = check_offer("Let us move you to OFF-CONTRACT-2Y instead.", ctx)
    assert v and v[0].code == "V-OFFER"


def test_naming_a_different_offer_by_name_is_rejected(ctx):
    v = check_offer("I can do the 2-year contract at 15% off.", ctx)
    assert v and all(x.code == "V-OFFER" for x in v)


def test_the_chosen_offer_may_be_named_freely(ctx):
    assert check_offer(f"I can set up the {CHOSEN.name}.", ctx) == []


def test_alias_table_only_fires_for_other_offers(ctx):
    """'autopay' belongs to OFF-AUTOPAY, which is not the chosen offer here."""
    assert any(v.code == "V-OFFER" for v in check_offer("switch to autopay", ctx))


# ----------------------------------------------------------------- V-CITE --
def test_a_fabricated_document_id_is_rejected(ctx):
    v = check_citations(["HIST-REASON-099"], ctx)
    assert v and v[0].code == "V-CITE" and "not a document" in v[0].detail


def test_a_real_document_that_was_not_shown_is_rejected(ctx):
    """ASSOC-002 exists but is reason-keyed, so it is never retrievable."""
    v = check_citations(["ASSOC-002"], ctx)
    assert v and "was not shown" in v[0].detail


def test_ids_actually_shown_are_accepted(ctx):
    assert check_citations(list(ctx.allowed_evidence_ids[:2]), ctx) == []


def test_registry_is_the_source_of_truth():
    ids = load_registry_ids()
    assert len(ids) >= 70 and "POLICY-001" in ids and "HIST-REASON-099" not in ids


# --------------------------------------------------------------- V-CAUSAL --
@pytest.mark.parametrize("phrase", [
    "Adding Tech Support will reduce their churn risk.",
    "This is proven to keep customers like you with us.",
    "The bundle guarantees they stay another year.",
    "Their churn is caused by the missing support package.",
])
def test_causal_claims_are_rejected(phrase):
    assert [v.code for v in check_causal(phrase)] == ["V-CAUSAL"]


@pytest.mark.parametrize("phrase", CAUSAL_ALLOWLIST)
def test_association_language_is_not_flagged(phrase):
    assert check_causal(f"This pattern is {phrase} in the historical base.") == []


def test_the_good_draft_uses_association_language(ctx):
    assert check_causal(GOOD_DRAFT["why"]) == []


# --------------------------------------------------------------- V-SCHEMA --
def test_empty_field_is_caught_without_pydantic():
    class Loose:
        summary, why, talk_track, evidence_ids = "", "", "", []
    codes = {v.code for v in check_schema(Loose())}
    assert codes == {"V-SCHEMA"}


def test_missing_citation_is_caught():
    class NoCite:
        summary = GOOD_DRAFT["summary"]
        why = GOOD_DRAFT["why"]
        talk_track = GOOD_DRAFT["talk_track"]
        evidence_ids: list[str] = []
    assert any("at least one document" in v.detail for v in check_schema(NoCite()))


def test_overlong_field_is_caught():
    class Long:
        summary = "x" * 400
        why = GOOD_DRAFT["why"]
        talk_track = GOOD_DRAFT["talk_track"]
        evidence_ids = ["LEVER-060"]
    assert any("maximum" in v.detail for v in check_schema(Long()))


def test_validate_short_circuits_on_empty_prose(ctx):
    """Nothing else can be checked meaningfully, so do not bury the real problem."""
    class Empty:
        summary, why, talk_track, evidence_ids = "", "", "", []
    assert {v.code for v in validate(Empty(), ctx)} == {"V-SCHEMA"}


def test_validate_never_raises_on_malformed_input(ctx):
    class Weird:
        summary = None
        why = 12345
        talk_track = ["not", "a", "string"]
        evidence_ids = "not-a-list"
    assert validate(Weird(), ctx)          # violations, not an exception


# -------------------------------------------------------------- feedback --
def test_feedback_is_empty_when_the_draft_is_clean(ctx):
    assert feedback([], ctx) == ""


def test_feedback_names_the_only_permitted_offer(ctx):
    vs = validate(Draft.model_validate(BAD_DRAFTS["wrong_offer"]), ctx)
    msg = feedback(vs, ctx)
    assert CHOSEN.offer_id in msg and "do not suggest an alternative" in msg.lower()


def test_feedback_lists_permitted_figures_when_money_failed(ctx):
    vs = validate(Draft.model_validate(BAD_DRAFTS["invented_discount"]), ctx)
    msg = feedback(vs, ctx)
    assert "Permitted values include" in msg


def test_feedback_lists_the_allowed_document_ids(ctx):
    vs = validate(Draft.model_validate(BAD_DRAFTS["fake_citation"]), ctx)
    msg = feedback(vs, ctx)
    assert ctx.allowed_evidence_ids[0] in msg


# ----------------------------------------------------- end-to-end wiring --
def test_retry_loop_recovers_on_the_second_attempt(ctx):
    """
    The behaviour the graph depends on: a bad draft is caught, the feedback is
    concrete, and a corrected draft passes. Exercised with the fake client so it
    needs no API key.
    """
    client = FakeClient(script=["invented_discount", "ok"])
    first = client.narrate("SYSTEM", "USER")
    assert first.ok                                   # schema-valid...
    v1 = validate(first.draft, ctx)
    assert any(x.code == "V-MONEY" for x in v1)       # ...but not truthful
    retry_prompt = feedback(v1, ctx)
    assert "V-MONEY" in retry_prompt

    second = client.narrate("SYSTEM", "USER\n\n" + retry_prompt)
    assert validate(second.draft, ctx) == []


def test_two_failures_leave_the_graph_with_no_valid_draft(ctx):
    """The condition that must route to the deterministic fallback template."""
    client = FakeClient(script=["invented_discount", "wrong_offer"])
    fails = 0
    for _ in range(2):
        r = client.narrate("SYSTEM", "USER")
        if not r.ok or validate(r.draft, ctx):
            fails += 1
    assert fails == 2


def test_context_can_be_built_from_a_real_decision():
    """Guards the seam between decision.py / kb_retrieval.py and the validators."""
    import numpy as np
    from src.contracts import load_and_validate, split_features_target
    from src.decision import decide
    from src.validators import context_from_decision

    df, _ = load_and_validate("data/Telco_customer_churn.xlsx")
    X, _, cltv = split_features_target(df)
    i = int(np.where(df["CustomerID"].values == "0295-PPHDO")[0][0])
    rec = decide(customer_id="0295-PPHDO", p_churn=0.99, cltv=float(cltv.iloc[i]),
                 row=X.iloc[i], catalog=CATALOG)
    ev = select(rec.levers, rec.offer_id)
    built = context_from_decision(rec, ev, CATALOG)

    assert built.offer_id == rec.offer_id
    assert rec.offer_id not in built.other_offer_ids
    assert built.allowed_evidence_ids == tuple(ev.ids)
    assert validate(draft(evidence_ids=[ev.ids[0]]), built) == []


# ----------------------------------------------------------------- V-PLAIN --
# The sixth check, added v5.3. The first five ask "is this TRUE?"; this one asks
# "is this READABLE?". The fixture below is the real note a live Gemini run
# produced -- every figure correct, every citation real, and five of six checks
# passed it. That is the whole argument for the check existing.
REAL_NOTE_WITH_DOC_IDS = {
    "summary": "Fiber customer, 1 month with us at $95.45 a month, 99.0% churn "
               "risk, on a rolling month-to-month contract with no add-ons.",
    "why": "Rolling month-to-month contracts are associated with a 42.71% "
           "historical churn rate against 6.76% otherwise, as shown in LEVER-063. "
           "Accounts with no tech support show 41.64% per LEVER-060, and those "
           "with no online security show 41.77% per LEVER-061.",
    "talk_track": "I can add the Tech Support and Online Security bundle for the "
                  "next 12 months, included at no extra cost.",
    "evidence_ids": ["LEVER-060", "LEVER-061", "LEVER-063"],
}


def test_the_real_note_that_prompted_this_check_is_now_rejected(ctx):
    d = Draft.model_validate(REAL_NOTE_WITH_DOC_IDS)
    vs = validate(d, ctx)
    codes = {v.code for v in vs}
    assert codes == {"V-PLAIN"}, (
        f"expected V-PLAIN and nothing else -- the note is TRUE, just unreadable. "
        f"Got {codes}")
    assert len(vs) == 3, "each distinct document reference must be named separately"
    for did in ("LEVER-060", "LEVER-061", "LEVER-063"):
        assert any(did in v.detail for v in vs), f"{did} was not named"


@pytest.mark.parametrize("text,why", [
    ("Their contract is MONTH_TO_MONTH so risk is elevated in past data.",
     "a lever code"),
    ("This customer was routed to no_action_needed by the engine.",
     "a status code"),
    ("The delta_prior for this offer is on the low side.",
     "an internal field name"),
    ("The expected value of this action is comfortably positive.",
     "the phrase 'expected value'"),
    ("We apply an assumed effect when ranking these offers.",
     "the phrase 'assumed effect'"),
    ("SHAP puts the rolling contract at the top of the list.",
     "a model-internals word"),
    ("The contribution in log-odds was the largest for tenure.",
     "log-odds"),
    ("Their p_churn is above the portfolio average.",
     "a variable name"),
    ("We assume Δ = 0.14 for this offer.", "the delta symbol"),
])
def test_v_plain_rejects_machinery_in_prose(text, why, ctx):
    d = draft(why="Padding so the field clears its minimum length. " + text)
    codes = {v.code for v in validate(d, ctx)}
    assert "V-PLAIN" in codes, f"{why} was not caught: {text!r}"


@pytest.mark.parametrize("text", [
    "Accounts on a rolling month-to-month contract left at 42.71% in past data.",
    "The customer pays nothing extra; it is included at no charge for 12 months.",
    "They have been with us 1 month and pay $95.45 a month against a 26.54% base rate.",
    "Two things are visible on the account: no tech support and no online security.",
])
def test_v_plain_passes_plain_english(text, ctx):
    d = draft(why="Padding so the field clears its minimum length. " + text)
    codes = {v.code for v in validate(d, ctx)}
    assert "V-PLAIN" not in codes, f"false positive on plain English: {text!r}"


def test_v_plain_allows_an_offer_id_because_that_is_V_OFFERs_question(ctx):
    """
    A review note's whole job can be "the closest was OFF-CONTRACT-1Y, short by
    $7.50". Offer ids look exactly like document ids, so this is the line that
    keeps the two checks from fighting: V-PLAIN ignores every catalog offer id
    and lets V-OFFER decide which one may be named.
    """
    from src.validators import check_plain_language
    for oid in OFFERS:
        assert check_plain_language(f"The closest was {oid}.", ctx) == [], oid


def test_v_plain_allows_the_customers_own_id():
    """
    A customer id can look like a document id -- TEST-0001 does. The note is
    allowed to name the customer it is about, so the id has to reach the context.
    """
    from src.validators import ValidationContext, check_plain_language
    c = ValidationContext(
        offer_id=CHOSEN.offer_id, offer_name=CHOSEN.name, cost=120.51,
        p_churn=0.99, cltv=5962.0, expected_value=705.82,
        delta_prior=0.14, delta_ci=(0.05, 0.24),
        monthly_charges=95.45, tenure_months=1, customer_id="TEST-0001")
    assert check_plain_language("TEST-0001 is on a rolling contract.", c) == []
    assert check_plain_language("LEVER-060 says so.", c), (
        "the same context must still reject a real document reference")


def test_the_retry_message_tells_the_model_how_to_fix_a_v_plain_failure(ctx):
    d = Draft.model_validate(REAL_NOTE_WITH_DOC_IDS)
    msg = feedback(validate(d, ctx), ctx)
    assert "evidence_ids" in msg
    assert "document id" in msg.lower()
    # It must show the SHAPE of a correct sentence, not just forbid the wrong one.
    assert "%" in msg and "left at" in msg


def test_the_deterministic_template_is_plain_for_every_status():
    """
    The fallback ships when the model fails twice, so it must satisfy the same
    readability bar. It writes the offer id and the customer id and nothing else
    that looks like machinery -- this is the test that keeps it that way.
    """
    from src import fallback
    from src.graph import _validation_context
    ev = select(LEVERS, CHOSEN.offer_id)
    base = {"customer_id": "TEST-0001", "p_churn": 0.43, "cltv": 2040.0,
            "tenure_months": 43, "monthly_charges": 94.30,
            "lever_labels": "Rolling month-to-month contract",
            "offer_id": CHOSEN.offer_id, "offer_name": CHOSEN.name,
            "cost": 120.51, "ev": 705.82, "delta_prior": 0.14,
            "delta_ci": [0.05, 0.24], "min_ev_floor": 20.0,
            "evidence_ids": ev.ids, "evidence_text": ev.text,
            "considered": [{"offer_id": "OFF-CONTRACT-1Y", "cost": 113.16,
                            "delta": 0.12, "ev": -7.5}]}
    for status in ("recommended", "review_no_profitable_offer",
                   "review_no_applicable_offer", "no_action_needed"):
        state = {**base, "status": status}
        vs = validate(fallback.build(state), _validation_context(state))
        assert [v for v in vs if v.code == "V-PLAIN"] == [], status


# ------------------------------------------------- V-OFFER: the status quo --
# v5.5. Measured over three seeded Gemini runs, EVERY note that failed validation
# failed here, with the same message, and every one of those customers was already
# ON a one-year contract -- twelve for twelve. The prompt shows the model
# `Contract  One year`, so it wrote "this customer is on a one-year contract",
# which is true and is exactly what the agent needs. Substring matching could not
# tell that apart from "let me move you to a one-year contract".
CONTRACT_OFFERS = {o for o in OFFERS if o.startswith("OFF-CONTRACT")}


def _ctx_for(current_contract: str, chosen: str = "OFF-TECHSUP-12") -> ValidationContext:
    """A customer whose contract offers were never priced -- i.e. not month-to-month."""
    ev = select(["NO_TECH_SUPPORT"], chosen)
    o = OFFERS[chosen]
    return ValidationContext(
        offer_id=o.offer_id, offer_name=o.name, cost=60.35,
        p_churn=0.3045, cltv=5061.0, expected_value=62.94,
        delta_prior=0.08, delta_ci=(0.02, 0.15),
        monthly_charges=104.85, tenure_months=62,
        customer_id="0471-ARVMX", current_contract=current_contract,
        allowed_evidence_ids=tuple(ev.ids), evidence_text=ev.text,
        other_offer_ids=tuple(x for x in OFFERS if x != chosen),
        other_offer_names=tuple(v.name for k, v in OFFERS.items() if k != chosen),
        catalog_offer_ids=tuple(OFFERS))


def _draft(why: str, talk: str, ev_id: str = "LEVER-060") -> Draft:
    return Draft(summary="Fiber customer, 62 months with us at $104.85 a month, "
                         "30.4% churn risk, with no tech support add-on.",
                 why=why, talk_track=talk, evidence_ids=[ev_id])


DESCRIBES_STATUS_QUO = _draft(
    "This customer is on a one-year contract and has no tech support add-on. "
    "Accounts without tech support left at 41.64% in past data.",
    "We can add Tech Support bundled free for 12 months, at no extra cost.")


def test_describing_the_customers_own_contract_is_not_naming_an_offer():
    """The exact note that was rejected twice in production. It must pass."""
    assert validate(DESCRIBES_STATUS_QUO, _ctx_for("One year")) == []


def test_the_same_sentence_is_still_caught_when_it_is_not_the_status_quo():
    """
    Identical text, a customer on a two-year contract. Now "one-year contract" is
    NOT a description of where they are, so the check must fire. This is the test
    that stops the fix becoming a blanket exemption.
    """
    codes = {v.code for v in validate(DESCRIBES_STATUS_QUO, _ctx_for("Two year"))}
    assert "V-OFFER" in codes


@pytest.mark.parametrize("talk,why_caught", [
    ("Let me move you to the 1-year contract at 10% off for the next 12 months.",
     "the full offer name"),
    ("I can put you on OFF-CONTRACT-1Y instead, it is better value.",
     "the literal offer id"),
])
def test_actually_pushing_the_other_offer_is_still_rejected(talk, why_caught):
    """
    The two stricter checks are untouched, so a model genuinely recommending the
    wrong offer is still caught even for a customer on that same contract term.
    """
    d = _draft("Accounts without tech support left at 41.64% in past data.", talk)
    codes = {v.code for v in validate(d, _ctx_for("One year"))}
    assert "V-OFFER" in codes, why_caught


def test_the_alias_check_is_not_dead_for_month_to_month_customers():
    """
    A month-to-month customer with under 6 months tenure cannot be offered the
    2-year contract (min_tenure_months: 6), so that alias stays live and a stray
    mention is still a violation. The fix must not disable the check wholesale.
    """
    from src.validators import _aliases
    ctx = _ctx_for("Month-to-month", chosen="OFF-BUNDLE-ALL")
    assert "two-year contract" in _aliases(ctx)
    d = _draft("Accounts without tech support left at 41.64% in past data.",
               "We could look at a two-year contract for you instead.")
    assert "V-OFFER" in {v.code for v in validate(d, ctx)}


def test_the_message_says_something_useful_when_no_offer_was_chosen():
    """In review mode offer_id is empty; the message used to end 'not to the chosen '."""
    ctx = ValidationContext(
        offer_id="", offer_name="", cost=0.0, p_churn=0.35, cltv=2754.0,
        expected_value=0.0, delta_prior=0.0, delta_ci=(0.0, 0.0),
        monthly_charges=69.95, tenure_months=3, current_contract="Two year",
        other_offer_ids=tuple(OFFERS), catalog_offer_ids=tuple(OFFERS))
    from src.validators import check_offer
    vs = check_offer("we could look at a one-year contract", ctx)
    assert vs and "no offer was chosen" in vs[0].detail
