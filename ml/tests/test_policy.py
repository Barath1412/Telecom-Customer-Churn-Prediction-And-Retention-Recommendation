"""Policy engine + decision layer tests. Every rule has a passing and a veto case."""
from __future__ import annotations
import pandas as pd
import pytest

from src.decision import Catalog, decide, evaluate_policy
from src.levers import extract

BASE = {
    "Gender": "Female", "Senior Citizen": "No", "Partner": "No", "Dependents": "No",
    "Tenure Months": 8, "Phone Service": "Yes", "Multiple Lines": "No",
    "Internet Service": "Fiber optic", "Online Security": "No", "Online Backup": "No",
    "Device Protection": "No", "Tech Support": "No", "Streaming TV": "Yes",
    "Streaming Movies": "Yes", "Contract": "Month-to-month",
    "Paperless Billing": "Yes", "Payment Method": "Electronic check",
    "Monthly Charges": 95.0, "Total Charges": 760.0,
}


@pytest.fixture(scope="module")
def cat():
    return Catalog.load()


# ------------------------------------------------------------------ levers --
def test_levers_are_deterministic():
    assert extract(BASE) == extract(BASE)


def test_levers_detect_the_real_attributes():
    lv = set(extract(BASE))
    assert {"NO_TECH_SUPPORT", "NO_ONLINE_SECURITY", "MONTH_TO_MONTH",
            "MANUAL_PAYMENT", "NEW_CUSTOMER", "FIBER_PREMIUM"} <= lv


def test_loyal_customer_has_few_levers():
    loyal = {**BASE, "Contract": "Two year", "Tech Support": "Yes",
             "Online Security": "Yes", "Device Protection": "Yes",
             "Payment Method": "Credit card (automatic)", "Tenure Months": 60}
    assert set(extract(loyal)) == {"FIBER_PREMIUM"}


# ------------------------------------------------------------------- rules --
def test_R1_eligibility_vetoes_offer_for_a_lever_you_do_not_have(cat):
    o = cat.by_id("OFF-TECHSUP-12")
    r = evaluate_policy(o, levers=["MONTH_TO_MONTH"], tenure=10, monthly_charges=90,
                        cltv=4000, ev=100, catalog=cat)
    assert not next(x for x in r if x.rule_id == "R1_ELIGIBILITY").passed


def test_R2_margin_floor_vetoes_an_offer_too_big_for_the_customer(cat):
    o = cat.by_id("OFF-BUNDLE-ALL")            # 180.00 fixed
    cheap = 20.0                                # annual 240, floor 15% = 36
    r = evaluate_policy(o, levers=["NO_TECH_SUPPORT", "NO_ONLINE_SECURITY"], tenure=10,
                        monthly_charges=cheap, cltv=4000, ev=100, catalog=cat)
    assert not next(x for x in r if x.rule_id == "R2_MARGIN_FLOOR").passed


def test_R3_positive_ev_vetoes_value_destroying_offers(cat):
    o = cat.by_id("OFF-SEC-12")                     # v3: RETENTION-CALL was removed
    r = evaluate_policy(o, levers=["NO_ONLINE_SECURITY"], tenure=10,
                        monthly_charges=90, cltv=100, ev=-12.0, catalog=cat)
    assert not next(x for x in r if x.rule_id == "R3_POSITIVE_EV").passed


def test_R4_cooldown_blocks_a_repeat_offer(cat):
    o = cat.by_id("OFF-AUTOPAY")
    r = evaluate_policy(o, levers=["MANUAL_PAYMENT"], tenure=10, monthly_charges=90,
                        cltv=4000, ev=100, catalog=cat,
                        recent_offer_ids=("OFF-AUTOPAY",))
    assert not next(x for x in r if x.rule_id == "R4_COOLDOWN").passed


def test_R5_one_offer_per_window(cat):
    o = cat.by_id("OFF-SEC-12")
    r = evaluate_policy(o, levers=["NO_ONLINE_SECURITY"], tenure=10, monthly_charges=90,
                        cltv=4000, ev=100, catalog=cat,
                        recent_offer_ids=("OFF-PROTECT-12",))
    assert not next(x for x in r if x.rule_id == "R5_ONE_PER_WINDOW").passed


def test_R6_involuntary_no_longer_exists(cat):
    """
    Removed in v4. It answered "did this customer move or die?" from
    `Churn Reason` -- a quarantined post-outcome column that exists only for
    people who have ALREADY left. There is no such field for a live customer, so
    the rule was checking something we are not allowed to use, on people we would
    never be scoring. Rule ids are not renumbered; R7 stays R7.
    """
    o = cat.by_id("OFF-SEC-12")
    r = evaluate_policy(o, levers=["NO_ONLINE_SECURITY"], tenure=10,
                        monthly_charges=90, cltv=4000, ev=100, catalog=cat)
    assert not any(x.rule_id == "R6_INVOLUNTARY" for x in r)
    assert {x.rule_id for x in r} == {"R1_ELIGIBILITY", "R2_MARGIN_FLOOR",
                                      "R3_POSITIVE_EV", "R4_COOLDOWN",
                                      "R5_ONE_PER_WINDOW", "R7_DISCOUNT_CAP"}


def test_R7_no_offer_in_catalog_breaches_the_discount_cap(cat):
    cap = cat.policy["max_discount_pct"]
    assert all(o.discount_pct <= cap for o in cat.offers)


# ---------------------------------------------------------------- decisions --
def test_low_risk_customer_is_no_action_needed(cat):
    """Below the base rate and nothing affordable -> not a problem, not a review."""
    rec = decide(customer_id="X", p_churn=0.02, cltv=300,
                 row=pd.Series(BASE), catalog=cat)
    assert rec.offer_id is None and rec.status == "no_action_needed"


def test_risky_customer_with_only_losing_offers_is_flagged_for_review(cat):
    """Offers applied, every one negative -> a human should see the numbers."""
    rec = decide(customer_id="X", p_churn=0.60, cltv=200,
                 row=pd.Series(BASE), catalog=cat)
    assert rec.offer_id is None
    assert rec.status == "review_no_profitable_offer"
    assert rec.considered, "the losing candidates must still be recorded"


def test_risky_customer_with_no_matching_offer_is_a_catalog_gap(cat):
    """
    Nothing in the catalog even applies. This is a PRODUCT problem, not an
    economics one, and it must not be reported as the same thing.
    """
    settled = dict(BASE, **{"Contract": "Two year", "Tech Support": "Yes",
                            "Online Security": "Yes", "Device Protection": "Yes",
                            "Payment Method": "Credit card (automatic)"})
    rec = decide(customer_id="X", p_churn=0.60, cltv=6000,
                 row=pd.Series(settled), catalog=cat)
    assert rec.offer_id is None
    assert rec.status == "review_no_applicable_offer"
    assert rec.considered == []


def test_every_status_is_declared(cat):
    from src.decision import STATUSES
    assert len(STATUSES) == 4 and "involuntary_routed_to_account_ops" not in STATUSES


def test_base_rate_constant_matches_the_dataset():
    """The escalation threshold is a dataset property, not a preference."""
    from src.contracts import load_and_validate
    from src.decision import BASE_RATE
    df, _ = load_and_validate("data/Telco_customer_churn.xlsx")
    assert abs(df["Churn Value"].mean() - BASE_RATE) < 0.0005


def test_economics_change_the_offer_for_identical_levers(cat):
    """
    THE point of the EV layer: same problems, different value -> different offer.
    A rules table alone cannot do this.
    """
    rich = decide(customer_id="RICH", p_churn=0.85, cltv=6000,
                  row=pd.Series(BASE), catalog=cat)
    poor = decide(customer_id="POOR", p_churn=0.85, cltv=400,
                  row=pd.Series(BASE), catalog=cat)
    assert extract(BASE) == extract(BASE)              # identical levers
    assert rich.offer_id != poor.offer_id
    assert rich.cost > poor.cost


def test_low_value_customer_is_not_overspent_on(cat):
    rec = decide(customer_id="TINY", p_churn=0.30, cltv=200,
                 row=pd.Series({**BASE, "Monthly Charges": 25.0}), catalog=cat)
    assert rec.ev >= 0
    if rec.offer_id:
        assert rec.cost <= 0.15 * 25.0 * 12


def test_every_recommendation_is_auditable(cat):
    rec = decide(customer_id="AUD", p_churn=0.9, cltv=5000,
                 row=pd.Series(BASE), catalog=cat)
    assert rec.catalog_version >= 1
    assert rec.delta_prior > 0 and len(rec.delta_ci) == 2   # belief is recorded
    assert rec.considered                                    # alternatives kept
    for entry in rec.policy_trace:                           # every rule logged
        assert {r["rule_id"] for r in entry["rules"]} >= {
            "R1_ELIGIBILITY", "R2_MARGIN_FLOOR", "R3_POSITIVE_EV",
            "R4_COOLDOWN", "R5_ONE_PER_WINDOW", "R7_DISCOUNT_CAP"}


def test_selected_offer_beats_every_alternative_on_ev(cat):
    rec = decide(customer_id="RANK", p_churn=0.9, cltv=5000,
                 row=pd.Series(BASE), catalog=cat)
    vetoed = {v["offer_id"] for v in rec.vetoed}
    surviving = [c for c in rec.considered if c["offer_id"] not in vetoed]
    assert surviving[0]["offer_id"] == rec.offer_id


def test_delta_priors_carry_a_source_and_an_interval(cat):
    """They are hypotheses, not measurements. The schema must say so."""
    for o in cat.offers:
        assert o.delta_source, o.offer_id
        assert len(o.delta_ci) == 2 and o.delta_ci[0] <= o.delta_prior <= o.delta_ci[1]


def test_sleeping_dog_risk_stays_documented():
    """
    v1-v2 encoded the sleeping-dog risk as a NEGATIVE delta_ci lower bound on
    OFF-RETENTION-CALL. v3 removed that offer -- not because the risk went away, but
    because "phone them" maps to no dataset field, so nothing could evaluate it.
    The risk is real for ANY intervention and must remain written down.
    """
    from pathlib import Path
    y = (Path(__file__).resolve().parent.parent / "data/offers.yaml").read_text()
    assert "sleeping-dog" in y.lower() or "sleeping dog" in y.lower(), (
        "offers.yaml must document that an intervention can INCREASE churn: "
        "reminding a quiet customer about their contract can prompt them to shop around")


def test_every_delta_ci_brackets_its_prior(cat):
    for o in cat.offers:
        assert o.delta_ci[0] <= o.delta_prior <= o.delta_ci[1], o.offer_id


# --------------------------------------------------- regression: float edges --
def test_margin_floor_is_exact_at_the_boundary(cat):
    """
    REGRESSION. OFF-CONTRACT-2Y costs 15% of annual revenue; the margin floor was
    also 15%, so cost == cap exactly and float noise (184.05 vs 184.04999999998)
    made the veto fire at random. Two fixes: compare integer cents, and keep the
    floor strictly above the largest discount. Both are asserted here.
    """
    o = cat.by_id("OFF-CONTRACT-2Y")
    for monthly in [102.25, 95.25, 70.35, 118.75, 18.25, 84.80, 99.25]:
        r = evaluate_policy(o, levers=["MONTH_TO_MONTH"], tenure=24,
                            monthly_charges=monthly, cltv=5000, ev=100, catalog=cat)
        margin = next(x for x in r if x.rule_id == "R2_MARGIN_FLOOR")
        assert margin.passed, f"margin floor wrongly vetoed at monthly={monthly}: {margin.detail}"


def test_margin_floor_exceeds_largest_discount(cat):
    """Config invariant: no catalog offer may sit exactly on the margin cap."""
    largest = max(o.discount_pct for o in cat.offers)
    assert cat.policy["margin_floor_pct"] > largest, (
        f"margin_floor_pct {cat.policy['margin_floor_pct']} must exceed the largest "
        f"discount {largest}, or that offer lands on a knife edge")


def test_margin_floor_still_blocks_genuinely_unaffordable_offers(cat):
    """The fix must not disable the rule."""
    o = cat.by_id("OFF-BUNDLE-ALL")          # 180.00 fixed
    r = evaluate_policy(o, levers=["NO_TECH_SUPPORT", "NO_ONLINE_SECURITY"], tenure=10,
                        monthly_charges=20.0, cltv=4000, ev=100, catalog=cat)
    assert not next(x for x in r if x.rule_id == "R2_MARGIN_FLOOR").passed


# ------------------------------------------------------- knowledge base v2 --
def test_kb_has_no_empty_documents():
    """
    v1 shipped 20 EXPLORATORY-* documents that stated an analysis was performed and
    reported nothing. This asserts every document carries a body.
    """
    import re
    from pathlib import Path
    t = (Path(__file__).resolve().parent.parent / "data/kb/knowledge_base.md").read_text()
    clean = re.sub(r"```.*?```", "", t, flags=re.S)
    bodies = re.split(r"^### \S+", clean, flags=re.M)[1:]
    empty = [i for i, b in enumerate(bodies) if len(b.strip()) < 240]
    assert not empty, f"{len(empty)} knowledge-base documents are effectively empty"


def test_kb_fits_in_context_budget():
    """Below the documented 25k-token threshold for full-context loading."""
    from pathlib import Path
    t = (Path(__file__).resolve().parent.parent / "data/kb/knowledge_base.md").read_text()
    approx_tokens = len(t) // 4
    assert approx_tokens < 25_000, (
        f"KB is ~{approx_tokens} tokens; past 25k switch to theme filtering "
        "(see POLICY-002)")


def test_every_offer_has_a_delta_derivation_doc(cat):
    """No effect estimate may exist without a written derivation."""
    from pathlib import Path
    t = (Path(__file__).resolve().parent.parent / "data/kb/knowledge_base.md").read_text()
    for o in cat.offers:
        assert o.offer_id in t, f"{o.offer_id} has no DELTA-* derivation document"


# ------------------------------------------- three-state rules (not_evaluable) --
def test_unavailable_data_is_not_evaluable_not_a_pass(cat):
    """
    A rule we CANNOT check must not read as a control that was verified. R4/R5 need
    offer history; with none connected both report `not_evaluable`, and the audit
    log says exactly what data is missing.
    """
    o = cat.by_id("OFF-CONTRACT-2Y")
    r = evaluate_policy(o, levers=["MONTH_TO_MONTH"], tenure=24, monthly_charges=95.0,
                        cltv=5000, ev=200, catalog=cat)   # no history, no status
    by = {x.rule_id: x for x in r}
    for rid in ["R4_COOLDOWN", "R5_ONE_PER_WINDOW"]:
        assert by[rid].state == "not_evaluable", rid
        assert by[rid].unmet_requirement, f"{rid} must say what data it needs"
    for rid in ["R1_ELIGIBILITY", "R2_MARGIN_FLOOR", "R3_POSITIVE_EV", "R7_DISCOUNT_CAP"]:
        assert by[rid].state == "pass", rid


def test_rules_become_checkable_when_data_is_supplied(cat):
    o = cat.by_id("OFF-CONTRACT-2Y")
    r = evaluate_policy(o, levers=["MONTH_TO_MONTH"], tenure=24, monthly_charges=95.0,
                        cltv=5000, ev=200, catalog=cat,
                        recent_offer_ids=("OFF-CONTRACT-2Y",))
    by = {x.rule_id: x for x in r}
    assert by["R4_COOLDOWN"].state == "veto"          # it IS a repeat
    assert "ALREADY offered" in by["R4_COOLDOWN"].detail
    assert by["R5_ONE_PER_WINDOW"].state == "veto"


def test_not_evaluable_never_silently_vetoes(cat):
    """An unavailable control must not block an otherwise good recommendation."""
    rec = decide(customer_id="NE", p_churn=0.9, cltv=5000,
                 row=pd.Series(BASE), catalog=cat)
    assert rec.offer_id is not None
    assert set(rec.rules_not_evaluable) == {"R4_COOLDOWN", "R5_ONE_PER_WINDOW"}


# ------------------------------------------------- audited threshold constants --
def test_lever_thresholds_are_named_constants_not_magic_numbers():
    """Every invented threshold must be a named constant with documented provenance."""
    from src import levers
    assert levers.HIGH_CHARGE_USD == 80.0
    assert levers.MAX_BUNDLES == 2
    assert levers.NEW_CUSTOMER_MONTHS == 12
    src = (__import__("pathlib").Path(levers.__file__)).read_text()
    assert "THRESHOLD PROVENANCE" in src, "thresholds must carry their audit"


def test_control_fraction_meets_the_power_requirement():
    """10% holdout must reach n_control>=50 per offer within a month at 200/day."""
    from src.queue_build import CONTROL_FRACTION
    per_day = 200 * CONTROL_FRACTION
    days_to_50 = 50 / (per_day / 3)        # 3 offers dominate the mix
    assert days_to_50 <= 31, f"{days_to_50:.0f} days is too slow to learn anything"


# ------------------------------------------------ catalog grounding (v3 gate) --
def test_every_catalog_offer_is_grounded_in_the_dataset():
    """
    HALLUCINATION GATE. An offer whose action cannot be expressed as a change to a
    real dataset column gives a language model nothing to anchor on. v3 removed the
    four offers that failed this. This test stops them coming back.
    """
    from src.validate_catalog import validate
    results, _ = validate()
    bad = [(oid, [c.name for c in checks if not c.passed])
           for oid, o, checks, n, seg, cf in results if not all(c.passed for c in checks)]
    assert not bad, f"ungrounded offers in the catalog: {bad}"


def test_removed_offers_cannot_silently_return(cat):
    """The four deleted offers must not reappear in offers.yaml."""
    gone = {"OFF-PROTECT-12", "OFF-PLANFIT", "OFF-ONBOARD", "OFF-RETENTION-CALL"}
    present = {o.offer_id for o in cat.offers}
    assert not (gone & present), f"removed offers are back: {gone & present}"
    assert len(cat.offers) == 6, f"expected 6 grounded offers, found {len(cat.offers)}"


def test_bundle_excludes_device_protection(cat):
    """v3 finding: the third service added dP 0.0044 for $60.24."""
    b = cat.by_id("OFF-BUNDLE-ALL")
    assert abs(b.unit_cost - 120.51) < 0.01, "bundle should be 2 services, not 3"


# ---------------------------------------------------------------------------
# CATALOG / DERIVATION CONSISTENCY
#
# Added after an audit found src/derive_costs.py still printing the v1/v2
# three-service bundle at $180.75 while catalog v3 carried the correct
# two-service $120.51. The catalog was right and the derivation script was
# stale -- which is the dangerous direction, because that script is what anyone
# would run to CHECK the catalog. This makes the two impossible to separate.
# ---------------------------------------------------------------------------
def test_derived_service_costs_match_the_catalog(cat):
    from src.derive_costs import implied_prices

    p = implied_prices()
    price = dict(zip(p.component, p.usd_per_month))
    expected = {
        "OFF-TECHSUP-12": 12 * price["Tech Support"],
        "OFF-SEC-12": 12 * price["Online Security"],
        "OFF-BUNDLE-ALL": 12 * (price["Tech Support"] + price["Online Security"]),
    }
    for oid, want in expected.items():
        got = cat.by_id(oid).unit_cost
        assert abs(got - want) < 0.01, (
            f"{oid}: catalog says {got}, the dataset's implied price list says "
            f"{want:.2f}. One of them is stale.")
