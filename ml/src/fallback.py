"""
The deterministic note. No model, no network, no chance of a wrong number.

WHY IT EXISTS
    Two independent reasons, and the second is the one people forget:

    1. If the model fails validation twice, the queue must not stall. An agent with
       a blank screen at 9am is worse than an agent with a plain sentence.
    2. `no_action_needed` covers 649 of 1,409 customers. Paying a model to write
       "nothing to do here" 649 times is waste, and worse -- a model asked that
       question repeatedly will eventually produce something warmer and more
       confident than "risk 5.8%, below average" actually supports.

WHY IT STILL GOES THROUGH THE VALIDATORS
    It is generated from f-strings, so in principle it cannot invent a figure. But
    the validators are the contract, and a template that has drifted (a renamed
    field, a changed unit) should fail loudly rather than reach an agent because it
    happened to come from trusted code. Every path through this file is tested
    against `validate()`.
"""
from __future__ import annotations

from typing import Any

from .narration_client import Draft


def _money(x: float) -> str:
    return f"${x:,.2f}"


def _pct(x: float, d: int = 1) -> str:
    return f"{x * 100:.{d}f}%"


def _months(n: int) -> str:
    return "1 month" if n == 1 else f"{n} months"


def build(state: dict[str, Any], base_rate: float = 0.2654) -> Draft:
    """One deterministic Draft for whichever outcome this customer landed in."""
    status = state.get("status", "recommended")
    if status == "recommended":
        return _recommended(state)
    if status == "review_no_profitable_offer":
        return _no_profit(state)
    if status == "review_no_applicable_offer":
        return _no_offer_fits(state)
    return _no_action(state, base_rate)


# --------------------------------------------------------------------------- #
def _ev_ids(state: dict[str, Any], n: int = 2) -> list[str]:
    ids = list(state.get("evidence_ids") or [])
    # Policy documents are always retrieved, so this can never come back empty for
    # a customer who went through retrieval.
    return ids[:n] or ["POLICY-001"]


def _account_line(s: dict[str, Any]) -> str:
    """The reference an agent wants first, in one clause, always the same shape."""
    return (f"{_months(s['tenure_months'])} with us at "
            f"{_money(s['monthly_charges'])} a month, churn risk "
            f"{_pct(s['p_churn'])}, lifetime value {_money(s['cltv'])}")


def _recommended(s: dict[str, Any]) -> Draft:
    return Draft(
        summary=(f"{s['customer_id']}: {_account_line(s)}. "
                 f"{(s.get('lever_labels') or 'no gaps recorded').split(';')[0].strip()}."),
        why=(f"The recommended action is {s['offer_name']} ({s['offer_id']}). What is "
             f"observable on this account: {s.get('lever_labels') or 'none recorded'}. "
             f"Those attributes are associated with higher churn in past data. Nothing "
             f"here is a measured effect of the offer, and nothing states why this "
             f"customer might leave — that is not knowable for someone who has not left."),
        talk_track=(f"Offer {s['offer_name']}. Confirm the customer understands what is "
                    f"included and for how long. Do not quote any figure that is not on "
                    f"this screen. This note was produced by a template, not by the "
                    f"assistant, so read the account details yourself before calling."),
        evidence_ids=_ev_ids(s))


def _no_profit(s: dict[str, Any]) -> Draft:
    """
    TWO SUB-CASES SINCE v5.1, and saying the wrong one would be a lie.
    Before the minimum expected value existed this could only mean "every offer loses
    money". It can now also mean "the best offer is worth $4.10, and an action has to
    be worth $20.00 to be worth an agent's time".
    """
    considered = s.get("considered") or []
    floor = float(s.get("min_ev_floor") or 0.0)
    best = max(considered, key=lambda c: c["ev"]) if considered else None
    if best is None:
        headline, detail = "no offer covers its own cost", "No priced candidate was recorded."
        reason = (f"Nothing was priced, so there is no figure to compare against their "
                  f"lifetime value of {_money(s['cltv'])}.")
    elif best["ev"] > 0:
        headline = "no offer is worth acting on"
        detail = (f"The best was {best['offer_id']}, worth {_money(best['ev'])} to us "
                  f"against a minimum of {_money(floor)}, short by "
                  f"{_money(floor - best['ev'])}.")
        # NOT "it loses money" -- it does not. Saying so would be false.
        reason = (f"It does clear its own cost, by {_money(best['ev'])}, and that is "
                  f"less than the call would take to make. The margin is too thin to "
                  f"act on, against a lifetime value of {_money(s['cltv'])}.")
    else:
        headline = "no offer covers its own cost"
        detail = (f"The closest was {best['offer_id']} at {_money(best['cost'])}, short by "
                  f"{_money(abs(best['ev']))}.")
        reason = (f"What we would protect — their risk against their lifetime value of "
                  f"{_money(s['cltv'])} — is smaller than what the offer costs.")
    return Draft(
        summary=(f"{s['customer_id']}: {_account_line(s)} — above average risk, but "
                 f"{headline}."),
        why=(f"{len(considered)} offer(s) applied to this account and none of them "
             f"cleared the bar. {detail} {reason} This is arithmetic, not a judgement "
             f"about the customer."),
        talk_track=("Internal note — do not call this customer and do not raise any of "
                    "this with them. No offer is worth its price here at current "
                    "pricing. If you believe the account justifies an exception, take "
                    "the shortfall above to a supervisor. Offer nothing from the list."),
        evidence_ids=_ev_ids(s))


def _no_offer_fits(s: dict[str, Any]) -> Draft:
    return Draft(
        summary=(f"{s['customer_id']}: {_account_line(s)} — above average risk, and no "
                 f"catalogue offer applies at all."),
        why=(f"Every offer requires a specific gap to close. This account has none of "
             f"them: {s.get('lever_labels') or 'no actionable gaps recorded'}. No offer "
             f"was priced, because none was eligible. This is a gap in the offer "
             f"catalogue, not a decision about this customer's value."),
        talk_track=("Internal note — do not call. There is nothing to offer, and none "
                    "of this should be raised with the customer. Pass it to whoever "
                    "owns the offer catalogue: an above-average risk customer with no "
                    "product answer is a gap in the catalogue, not a retention call."),
        evidence_ids=_ev_ids(s))


def _no_action(s: dict[str, Any], base_rate: float) -> Draft:
    """
    The reference note for a customer nobody will phone.

    It exists for the agent who opens this record for some OTHER reason -- a support
    call, a billing query -- and needs to know where the account stands. That is why
    it repeats the account line in full rather than saying "nothing to do".
    """
    return Draft(
        summary=(f"{s['customer_id']}: {_account_line(s)}, below the {_pct(base_rate)} "
                 f"average. No action needed."),
        why=(f"This account scored {_pct(s['p_churn'])} against a portfolio average of "
             f"{_pct(base_rate)}, so it was not put on the call list and no offer was "
             f"priced for it. On the account: "
             f"{s.get('lever_labels') or 'no actionable gaps recorded'}. These figures "
             f"are the model's view of risk, not a statement about anything the "
             f"customer has said or done."),
        talk_track=("Internal note — no call required, and there is no offer to make. "
                    "If you have this record open for another reason, the account line "
                    "above is the current position; treat the risk figure as "
                    "informational only."),
        evidence_ids=["POLICY-001"])


if __name__ == "__main__":
    demo = {"customer_id": "TEST-0001", "p_churn": 0.43, "cltv": 2040.0,
            "tenure_months": 43, "monthly_charges": 94.30,
            "lever_labels": "Rolling month-to-month contract; Manual payment method",
            "offer_id": "OFF-BUNDLE-ALL", "offer_name": "Tech Support + Online Security "
            "bundle, 12 months", "cost": 120.51, "ev": 705.82, "delta_prior": 0.14,
            "delta_ci": [0.05, 0.24], "evidence_ids": ["LEVER-060", "POLICY-001"],
            "considered": [{"offer_id": "OFF-CONTRACT-1Y", "cost": 113.16, "ev": -7.50},
                           {"offer_id": "OFF-AUTOPAY", "cost": 60.0, "ev": -24.78}]}
    cases = [("recommended", {}), ("review_no_profitable_offer", {}),
             ("review_no_applicable_offer", {}), ("no_action_needed", {}),
             # the v5.1 sub-case: offers apply and MAKE money, just not enough of it
             ("review_no_profitable_offer", {
                 "min_ev_floor": 20.0,
                 "considered": [{"offer_id": "OFF-AUTOPAY", "cost": 60.0, "ev": 0.18}]})]
    for st, extra in cases:
        d = build({**demo, "status": st, **extra})
        print(f"\n{'=' * 74}\n{st}"
              + ("   [below the minimum, not negative]" if extra else "")
              + f"\n{'=' * 74}")
        print("SUMMARY   ", d.summary)
        print("WHY       ", d.why)
        print("TALK      ", d.talk_track)
        print("EVIDENCE  ", d.evidence_ids)
