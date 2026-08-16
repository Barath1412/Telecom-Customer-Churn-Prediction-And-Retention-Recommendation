"""
The decision layer: probability -> offer.

This is the component neither reviewed approach had, and it is where the system
stops describing and starts deciding.

    EV(offer | customer) = P_churn_calibrated x CLTV x delta_retention - cost

Order matters and is enforced here:
    generate candidates -> rank by EV -> POLICY VETO -> capacity cut
The policy engine runs AFTER ranking and can only remove, never add. An LLM (not
in this module) writes the rationale afterwards and cannot change any of it.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "data" / "offers.yaml"

# --------------------------------------------------------------------------- #
#  OUTCOMES. Four, and every customer lands in exactly one.
#
#  Until v4 there were three, and one of them ("no_eligible_offer") was a flat
#  label covering three genuinely different situations with no explanation aimed
#  at a human. Splitting it is the whole point: "we have nothing worth selling
#  them" and "we have nothing to sell them at all" are different problems for
#  different people.
# --------------------------------------------------------------------------- #
STATUSES = (
    "recommended",                 # an offer clears the minimum and passes policy
    "review_no_profitable_offer",  # riskier than average, offers applied, none clears
                                   # the minimum expected value (may be negative EV,
                                   # or positive but too small to be worth a call)
    "review_no_applicable_offer",  # riskier than average, no offer's conditions match
    "no_action_needed",            # risk below the portfolio base rate
)

# The portfolio churn rate, 1,869 of 7,043. It is the line between "this customer
# is riskier than average, put it in front of a human" and "this customer is not
# a concern". Asserted against the dataset in tests/test_policy.py so it cannot
# drift if the data is ever reloaded.
BASE_RATE = 0.2654


def risk_band(p_churn: float) -> str:
    """
    Where this customer sits against the portfolio average. DISPLAY ONLY -- nothing
    routes on it. Rounded to 4dp first so it agrees with the p_churn actually stored.
    """
    p = round(float(p_churn), 4)
    if p > BASE_RATE:
        return "above"
    return "at" if p == BASE_RATE else "below"


@dataclass
class Offer:
    offer_id: str
    name: str
    category: str
    requires_levers: list
    excludes_levers: list
    min_tenure_months: int
    cost_type: str
    discount_pct: float
    unit_cost: float | None
    delta_prior: float
    delta_ci: list
    delta_source: str
    note: str = ""

    def cost_for(self, monthly_charges: float) -> float:
        if self.cost_type == "pct_of_annual":
            return round(monthly_charges * 12 * self.discount_pct, 2)
        return float(self.unit_cost or 0.0)


@dataclass
class Catalog:
    version: int
    currency: str
    policy: dict
    offers: list

    @classmethod
    def load(cls, path=CATALOG_PATH):
        raw = yaml.safe_load(Path(path).read_text())
        return cls(
            version=raw["catalog_version"],
            currency=raw["currency"],
            policy=raw["policy"],
            offers=[Offer(**{k: o.get(k) for k in Offer.__dataclass_fields__}
                          | {"note": (o.get("note") or "").strip()})
                    for o in raw["offers"]],
        )

    def by_id(self, oid): return next(o for o in self.offers if o.offer_id == oid)


# --------------------------------------------------------------------------- #
#  Policy rules. Deterministic, versioned, VETO-ONLY.
#  Every evaluation is recorded, pass or fail, so any recommendation can be
#  explained to a regulator or a finance lead.
# --------------------------------------------------------------------------- #
@dataclass
class RuleOutcome:
    """
    Three states, not two. `passed=True` must mean "we checked and it was fine".

    A rule that cannot be checked because the required data does not exist is
    NOT a pass -- recording it as one makes an audit log read as though every
    control was verified. R4_COOLDOWN and R5_ONE_PER_WINDOW both need an offer
    history this project has never had, so they now report `not_evaluable` and
    say why.
    """
    rule_id: str
    passed: bool                      # False only when the rule genuinely VETOES
    detail: str
    evaluable: bool = True            # False -> could not be checked at all
    unmet_requirement: str = ""       # what data is missing, when evaluable=False

    @property
    def state(self) -> str:
        if not self.evaluable:
            return "not_evaluable"
        return "pass" if self.passed else "veto"


def evaluate_policy(offer: Offer, *, levers, tenure, monthly_charges, cltv,
                    ev, catalog, recent_offer_ids=None) -> list:
    """
    recent_offer_ids : None  -> no offer-history source is connected. R4 and R5
                               report `not_evaluable` instead of silently passing.
                       tuple -> real history; R4/R5 are checked.

    R6_INVOLUNTARY WAS REMOVED IN v4, AND THAT IS THE HONEST CHANGE.
    It asked "is this customer leaving for a reason no offer can fix (moved,
    deceased)?" We had been answering it from `Churn Reason` -- a quarantined
    post-outcome column that only exists for people who have ALREADY left. For a
    live customer that flag simply does not exist in this dataset, so the rule
    was checking a field we are not allowed to use, on people we would never be
    scoring. Rule ids are NOT renumbered: R7 stays R7 so that stored decisions
    and the frontend keep referring to the same rule.
    """
    p = catalog.policy
    history_known = recent_offer_ids is not None
    recent = tuple(recent_offer_ids or ())
    cost = offer.cost_for(monthly_charges)
    annual_revenue = monthly_charges * 12
    out = []

    out.append(RuleOutcome(
        "R1_ELIGIBILITY",
        set(offer.requires_levers).issubset(set(levers))
        and not (set(offer.excludes_levers) & set(levers)),
        f"requires {offer.requires_levers or '-'}, excludes {offer.excludes_levers or '-'}"))

    # Money is compared in INTEGER CENTS. Comparing floats here silently broke
    # every OFF-CONTRACT-2Y offer: its 15% discount exactly equals the 15% margin
    # floor, so the two sides differ only by float representation noise
    # (184.05 vs 184.04999999999998) and the veto fired at random.
    cap_cents = round(p["margin_floor_pct"] * annual_revenue * 100)
    cost_cents = round(cost * 100)
    out.append(RuleOutcome(
        "R2_MARGIN_FLOOR", cost_cents <= cap_cents,
        f"cost {cost:.2f} <= {p['margin_floor_pct']:.0%} x annual {annual_revenue:.2f}"
        f" = {cap_cents/100:.2f}"))

    # R3 IS A WORTHWHILENESS TEST, NOT JUST A TRIPWIRE.  (changed in v5.1)
    # It read `ev > 0`, so an expected value of $0.18 passed and that customer got a
    # queue slot, a model call and an agent's attention. Losing money and being worth
    # doing are two different questions; `min_expected_value_usd` supplies the second
    # number. Absent from an older catalog it defaults to 0.0, which is exactly the
    # previous behaviour -- so a v3 catalog still replays identically.
    floor = float(p.get("min_expected_value_usd", 0.0) or 0.0)
    out.append(RuleOutcome(
        "R3_POSITIVE_EV",
        (ev >= floor) if floor > 0 else (ev > 0),
        # Reads correctly whether it passed or vetoed. "EV 0.18 >= minimum 20.00"
        # would state a falsehood on the line where the rule fired.
        f"EV {ev:.2f} (minimum {floor:.2f})" if floor > 0 else f"EV {ev:.2f} > 0"))

    if history_known:
        repeat = offer.offer_id in recent
        out.append(RuleOutcome(
            "R4_COOLDOWN", not repeat,
            f"ALREADY offered within {p['cooldown_days']}d" if repeat
            else f"not offered in last {p['cooldown_days']}d"))
        n_active = len(recent)
        cap = p["max_offers_per_quarter"]
        out.append(RuleOutcome(
            "R5_ONE_PER_WINDOW", n_active < cap,
            f"{n_active} active offer(s) >= cap {cap}" if n_active >= cap
            else f"{n_active} active < cap {cap}"))
    else:
        out.append(RuleOutcome(
            "R4_COOLDOWN", True, "NOT CHECKED - no offer history available",
            evaluable=False,
            unmet_requirement="act.recommendation history (offer_id, created_at) "
                              "per customer for the last {}d".format(p["cooldown_days"])))
        out.append(RuleOutcome(
            "R5_ONE_PER_WINDOW", True, "NOT CHECKED - no offer history available",
            evaluable=False,
            unmet_requirement="act.recommendation history for the current quarter"))

    # A guardrail nothing currently trips is doing its job, but the audit log
    # should not imply it was a close call.
    out.append(RuleOutcome(
        "R7_DISCOUNT_CAP", offer.discount_pct <= p["max_discount_pct"],
        f"discount {offer.discount_pct:.0%} <= cap {p['max_discount_pct']:.0%}"
        + ("  (tripwire - no catalog offer approaches this)" if offer.discount_pct == 0
           else "")))

    return out


@dataclass
class Recommendation:
    customer_id: str
    p_churn: float
    cltv: float
    monthly_charges: float
    tenure_months: int
    levers: list
    offer_id: str | None
    offer_name: str | None
    cost: float
    delta_prior: float
    delta_ci: list
    ev: float
    considered: list = field(default_factory=list)   # every candidate, ranked
    vetoed: list = field(default_factory=list)       # offer_id -> failing rule
    policy_trace: list = field(default_factory=list)
    status: str = "recommended"   # see STATUSES below
    catalog_version: int = 0
    rules_not_evaluable: list = field(default_factory=list)  # controls we COULD NOT check
    # ---- v5.1 -------------------------------------------------------------- #
    min_ev_floor: float = 0.0     # the R3 minimum this decision was judged against
    risk_vs_base: str = ""        # "below" | "at" | "above" the portfolio base rate
    #  risk_vs_base IS DISPLAY ONLY. It changes no route and no ranking.
    #  It exists because low RISK and low VALUE are different things and the queue
    #  was hiding the difference: a customer at 0.20 risk with $8,000 lifetime value
    #  and a $60 offer is worth +$164 and should be called. The agent should see that
    #  they are below-average risk and judge; the system should not quietly drop them.

    def to_row(self):
        d = asdict(self)
        d["levers"] = "|".join(self.levers)
        d["considered"] = "|".join(f"{c['offer_id']}:{c['ev']:.0f}" for c in self.considered)
        d["vetoed"] = "|".join(f"{v['offer_id']}:{v['rule_id']}" for v in self.vetoed)
        d["rules_not_evaluable"] = "|".join(self.rules_not_evaluable)
        d.pop("policy_trace")
        return d


def decide(*, customer_id, p_churn, cltv, row, catalog,
           recent_offer_ids=None) -> Recommendation:
    """One customer -> one auditable decision."""
    from .levers import extract

    # ONE CANONICAL PRECISION, ROUNDED ONCE, HERE.
    # Until v5 this function reported round(p, 4) while computing the expected value
    # from the full-precision float. The two differed by fractions of a cent -- which
    # was invisible until the graph re-scored a customer and node 9's "the decision
    # did not change" assertion fired on a $0.03 discrepancy. It was right to fire:
    # if the same customer can produce two different expected values, neither is
    # reproducible. Round first, then use the rounded value everywhere.
    p_churn = round(float(p_churn), 4)
    levers = extract(row)
    monthly = float(row["Monthly Charges"])
    tenure = int(row["Tenure Months"])

    floor = float(catalog.policy.get("min_expected_value_usd", 0.0) or 0.0)
    base = dict(customer_id=customer_id, p_churn=p_churn,
                cltv=float(cltv), monthly_charges=monthly, tenure_months=tenure,
                levers=levers, catalog_version=catalog.version,
                min_ev_floor=floor, risk_vs_base=risk_band(p_churn))

    # ---- candidates, scored by EV, ranked ---------------------------------
    scored = []
    for o in catalog.offers:
        if not set(o.requires_levers).issubset(set(levers)):
            continue
        if set(o.excludes_levers) & set(levers):
            continue
        if tenure < o.min_tenure_months:
            continue
        cost = o.cost_for(monthly)
        ev = p_churn * cltv * o.delta_prior - cost
        scored.append({"offer_id": o.offer_id, "name": o.name, "cost": round(cost, 2),
                       "delta": o.delta_prior, "ev": round(ev, 2), "_o": o})
    scored.sort(key=lambda c: -c["ev"])

    # ---- policy veto, in EV order; first survivor wins ---------------------
    vetoed, trace = [], []
    for cand in scored:
        outcomes = evaluate_policy(
            cand["_o"], levers=levers, tenure=tenure, monthly_charges=monthly,
            cltv=cltv, ev=cand["ev"], catalog=catalog,
            recent_offer_ids=recent_offer_ids)
        trace.append({"offer_id": cand["offer_id"],
                      "rules": [asdict(r) for r in outcomes]})
        unchecked = sorted({r.rule_id for r in outcomes if not r.evaluable})
        failed = [r for r in outcomes if r.evaluable and not r.passed]
        if failed:
            vetoed.append({"offer_id": cand["offer_id"], "rule_id": failed[0].rule_id,
                           "detail": failed[0].detail})
            continue
        o = cand["_o"]
        return Recommendation(
            **base, rules_not_evaluable=unchecked,
            offer_id=o.offer_id, offer_name=o.name, cost=cand["cost"],
            delta_prior=o.delta_prior, delta_ci=list(o.delta_ci), ev=cand["ev"],
            considered=[{k: c[k] for k in ("offer_id", "cost", "delta", "ev")}
                        for c in scored],
            vetoed=vetoed, policy_trace=trace, status="recommended")

    # ---- no offer survived. WHICH KIND of no? -----------------------------
    # The distinction is not cosmetic. "Offers existed but none is worth its price"
    # is an economics answer a supervisor may want to override. "No offer applies at
    # all" is a CATALOG GAP -- a product problem, and one that a money-losing
    # filler offer would hide rather than fix. Below the base rate it is neither:
    # the customer is simply not going anywhere.
    #
    # ORDER MATTERS AND IS DELIBERATE. The base-rate test is LAST, reached only when
    # nothing survived. A below-base-rate customer with a genuinely valuable offer is
    # still `recommended`, because low risk is not the same as low value: 0.20 risk x
    # $8,000 lifetime value x 14% = $224 against a $60 offer is +$164 of real
    # expected value. Gating on risk BEFORE pricing would throw that away and would
    # reintroduce exactly the thresholding we refused when we rejected predict()=0/1.
    if p_churn < BASE_RATE:
        status = "no_action_needed"
    elif scored:
        status = "review_no_profitable_offer"
    else:
        status = "review_no_applicable_offer"

    return Recommendation(
        **base, offer_id=None, offer_name=None, cost=0.0, delta_prior=0.0,
        delta_ci=[0, 0], ev=0.0,
        considered=[{k: c[k] for k in ("offer_id", "cost", "delta", "ev")} for c in scored],
        vetoed=vetoed, policy_trace=trace, status=status)
