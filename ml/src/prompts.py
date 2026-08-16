"""
Prompt construction. The only file that decides what the model is told.

TWO MODES, ONE CONTRACT
    "recommend"  an offer was chosen -> write the note the agent reads before calling
    "review"     no offer survived   -> explain WHY to the agent, so they can judge
                                        whether to escalate

    Both produce the same four-field `Draft`, so node 4's validators and the agent's
    screen do not care which mode produced the text.

THREE RULES THAT SHAPE EVERY PROMPT HERE

 1. THE DECISION IS PRESENTED AS SETTLED, NOT AS A QUESTION.
    The model is told which offer was chosen and what it costs. It is never asked
    to pick, price or rank anything. Asking it to choose and then rejecting its
    choice in code would be theatre.

 2. NO NUMBER IS INVITED THAT IS NOT ALREADY ON SCREEN.
    The permitted figures are listed explicitly. V-MONEY enforces it afterwards,
    but a prompt that tempts the model into inventing a discount and then punishes
    it wastes two requests.

 3. THE EVIDENCE FRAME IS STRUCTURAL, NOT POLITE.
    Every retrieved document describes this customer's own observable attributes,
    the offer's derivation, or a system policy. Nothing about motive is retrievable
    at all (see src/kb_retrieval.py), so the frame can state that flatly instead of
    asking the model to be careful.

 4. SUPPLYING A FIGURE IS NOT THE SAME AS REQUIRING IT.  (fixed here)
    A real Gemini run produced: "a new fiber optic subscriber with a high monthly
    charge". Tenure (1 month) and the charge ($95.45) were both supplied AND both on
    the permitted list -- the model simply chose prose over numbers, because nothing
    told it not to. An agent about to speak to a customer needs "one month with us,
    $95.45 a month", not "new" and "high". The summary now has a required shape.

 5. THE PRICE TO THE CUSTOMER WAS NEVER STATED.  (fixed here)
    The same run said "we can add our tech support and online security bundle to your
    plan for the coming year" -- and never that it is FREE. That is the single most
    persuasive fact available, and omitting it risks an agent implying an upsell. The
    talk track must now state what the customer pays and for how long.

    NOTE ON HOW TO SAY "FREE": in words, never as a figure. "$0" would be extracted
    by V-MONEY, 0 is not on the whitelist, and the draft would be rejected. "at no
    extra cost" passes and reads better aloud.

 6. REVIEW MODE WAS ASKING FOR A CONVERSATION THAT MUST NEVER HAPPEN.  (fixed here)
    `talk_track` was a required, customer-facing field in ALL FOUR outcomes. In both
    review outcomes there is no call at all -- so the model, handed a mandatory field
    with no valid content, invented one. Two real Gemini runs produced:
        "Explain the position plainly to the customer. Inform them that no priced
         offer clears its own cost..."
        "Explain to the customer that this is a catalogue gap rather than a decision
         about their account worth..."
    Nobody would ever say that to a customer. This was a SCHEMA design error, not a
    wording error: give a model a required field with no valid content and it will
    fill it with something plausible and wrong. The field is now explicitly
    mode-dependent -- a spoken script in recommend mode, an internal instruction to
    the agent in review and no-action modes -- and both review prompts now open by
    stating that there is no call. The field NAME is unchanged, because renaming it
    would break the API fixtures and the frontend for no functional gain.

    Note also that the validators could never have caught this. Those notes were
    entirely TRUTHFUL; they were just terrible advice. V-* checks truthfulness. The
    fix has to be upstream, in what we ask for.

 7. THE NOTE WAS FULL OF MACHINERY.  (fixed here)
    Real runs emitted "DELTA-052 records an assumed effect of 4%" and the prompt
    listed the expected value as a figure the model MAY use. An agent seconds from
    dialling does not need our internal cost, our expected value, our assumed
    effect, or a SHAP contribution in log-odds -- all four are already on their
    screen, rendered deterministically. Hard rules 10 and 11 now say what belongs in
    a note, `permitted_figures` no longer invites the internal ones, and
    `_attribution` no longer prints the contribution values at all.
"""
from __future__ import annotations

from typing import Any

from .validators import CAUSAL_PHRASES

SYSTEM = """You write short internal notes for telecom retention agents.

WHO READS YOUR OUTPUT
A company employee, seconds before they telephone a customer, or before they decide
whether to escalate a case. They are not a data scientist. They need to know what is
going on and what to say.

WHAT IS ALREADY DECIDED BEFORE YOU ARE ASKED ANYTHING
The churn risk, the chosen offer, its price and its expected value were all computed
by a deterministic engine and approved by a policy rulebook. You are told the result.
You do not choose an offer, change a price, or rank anything.

HARD RULES
1. Use ONLY the figures listed as permitted. Never invent a discount, a price, a
   percentage or a saving. If you want to express a quantity you were not given,
   describe it in words instead.
2. Name ONLY the offer you were given. Never mention or suggest a different one.
3. Cite ONLY the evidence ids supplied to you, and only ones you actually used.
   PUT THEM IN THE `evidence_ids` FIELD AND NOWHERE ELSE. A document reference
   such as LEVER-060 or DELTA-051 must NEVER appear inside summary, why or
   talk_track. Quote the FIGURE from the document and drop the reference:
     WRONG  "a 42.71% churn rate, as shown in LEVER-063"
     RIGHT  "accounts on a rolling contract left at 42.71%"
   The agent's screen already lists the documents beside your note. A filing
   reference in the middle of a sentence tells them nothing and costs them the
   half-second they had to read it.
4. Describe patterns as ASSOCIATIONS observed in past data. You must not claim any
   offer causes, guarantees, prevents or reduces anything. No effect in this system
   has ever been measured.
5. Never state or guess WHY a customer is unhappy. That information does not exist
   for a customer who has not left.
6. Plain British-neutral English. No jargon, no marketing language, no emoji.
7. BE SPECIFIC WITH NUMBERS YOU WERE GIVEN. Do not write "new", "long-standing",
   "high charge" or "low value" when you were handed the actual tenure, charge or
   value. Write the figure. Vague words waste the agent's time and lose their trust.
8. STATE WHAT THE CUSTOMER PAYS. Every offer has terms -- free for a period, a
   percentage off, or a monthly credit -- and they are in the offer name you were
   given. Say them. An agent who does not mention the price sounds like they are
   selling something.
9. Say "at no extra cost" or "included at no charge" IN WORDS. Never write it as a
   figure such as "$0" or "0%": those are treated as invented numbers and your note
   will be rejected.
10. WRITE FOR A PERSON, NOT FOR AN ANALYST. An automated check rejects the note if
   any of these appear in summary, why or talk_track:
     - a document reference       LEVER-060, POLICY-001, DELTA-051
     - anything with underscores  MONTH_TO_MONTH, no_action_needed, delta_prior
     - the words "expected value", "delta", "assumed effect", "SHAP", "log-odds"
     - the symbol Δ
   Say "on a rolling month-to-month contract", not "MONTH_TO_MONTH". Say "we think
   it makes a difference of around 14%", not "delta 0.14". The internal figures are
   already on the agent's screen next to your note; repeating them there wastes the
   sentence you had to explain the customer.
11. COMPARE THEM TO THE WHOLE BASE, NEVER TO THE GROUP THE OFFER WOULD MOVE THEM
   INTO. Say "accounts on a rolling contract left at 42.71%, against 26.54% across
   all customers". Do NOT say "42.71%, compared to 2.8% on a two-year contract" and
   then offer a two-year contract: the people already on long contracts were more
   likely to stay in the first place, so their rate is not what happens to someone
   we move. Every lever document below hands you the sentence already written -- use
   its three figures exactly as they appear, and do not swap which group each one
   belongs to.
12. THE FIGURES THAT BELONG IN THE NOTE are the ones about the CUSTOMER: how long
   they have been with us, what they pay a month, their churn risk, what the offer
   gives them and for how long, and historical rates quoted from the evidence. That
   is the reference an agent actually reads before dialling.

OUTPUT
Return JSON with exactly four fields.

  summary       ONE sentence, and it MUST contain all four of these, as figures:
                  - tenure in months            ("1 month with us")
                  - the monthly charge          ("$95.45 a month")
                  - the churn risk              ("99.0% churn risk")
                  - the single most important observable gap, in plain words
                Example shape:
                  "Fibre customer, 1 month with us at $95.45 a month, 99.0% churn
                   risk, on a rolling contract with no support add-ons."

  why           2-4 sentences grounded in the levers and evidence supplied. Say what
                is observable about THIS account and how it compares in past data.
                Use figures from the evidence, not adjectives.

  talk_track    ITS MEANING DEPENDS ON THE MODE, AND THE MODE IS STATED BELOW.

                MODE: recommend — this is what the agent SAYS OUT LOUD to the
                customer. It MUST state:
                  - what the customer gets                (the offer, in plain words)
                  - what it costs THEM                    (in words: "at no extra
                    cost", or the percentage off you were given)
                  - for how long                          ("for the next 12 months")
                Do not describe an offer without its price and its duration.

                MODE: review — THERE IS NO CALL AND THERE IS NO CUSTOMER
                CONVERSATION. This is an INTERNAL instruction to the agent and their
                supervisor. Never address the customer, never draft words to say to
                them, and never suggest telling them anything about why they were or
                were not selected. State: do not call, the reason in one clause, and
                who should pick this up next.

  evidence_ids  the document ids you relied on
"""

EVIDENCE_FRAME = (
    "EVIDENCE — each document below carries a FILING REFERENCE such as LEVER-060.\n"
    "That reference belongs in the `evidence_ids` field and must never appear in a\n"
    "sentence you write. Use the FIGURES; leave the reference behind.\n"
    "Every document below describes either this customer's own observable\n"
    "account attributes, the derivation of the offer's effect estimate, or a system\n"
    "policy. NONE of it states why this customer, or any customer, chose to leave.\n"
    "That information does not exist for a customer who has not left. Do not infer a\n"
    "motive from any of it.\n"
)


def _customer_terms(state: dict[str, Any]) -> str:
    """
    What the CUSTOMER pays, in the words the agent should use.

    This exists because `cost` is what the offer costs US -- $120.51 for the bundle --
    and quoting that to a customer would be nonsense: the bundle is free to them. The
    offer name already carries the real terms, so this reads them back explicitly so
    the model cannot skip them.

    "at no extra cost" is deliberately words, not "$0": V-MONEY would extract 0, find
    it is not on the whitelist, and reject the draft.
    """
    import re
    oid = state.get("offer_id") or ""
    name = state.get("offer_name") or ""
    if "contract" in oid.lower():
        # The percentage is read out of the offer name rather than taken from state,
        # because `discount_pct` is not one of the fields decide() puts in the graph
        # state -- and the name is the customer-facing wording anyway.
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", name)
        pct = f"{m.group(1)}% off" if m else "the discount named in the offer"
        return (f'"{name}" — the customer moves to that contract term and gets {pct} '
                f'their bill for its duration. Quote both the term and the {pct}.')
    if "autopay" in oid.lower():
        return (f'"{name}" — the customer switches to automatic payment and receives '
                f'the monthly credit named in the offer, for 12 months. Quote the '
                f'credit and the duration.')
    return (f'"{name}" — the customer pays NOTHING EXTRA for this. It is included at '
            f'no charge for 12 months. Say so in words ("at no extra cost", "included '
            f'at no charge"), never as "$0".')


def _facts(state: dict[str, Any]) -> str:
    c = state.get("customer", {})
    keep = ["Contract", "Internet Service", "Payment Method", "Tech Support",
            "Online Security", "Device Protection", "Paperless Billing",
            "Senior Citizen", "Partner", "Dependents"]
    lines = [f"  tenure                {state.get('tenure_months')} months",
             f"  monthly charges       ${state.get('monthly_charges'):.2f}",
             f"  lifetime value        ${state.get('cltv'):,.0f}",
             f"  churn risk (model)    {state.get('p_churn', 0) * 100:.1f}%"]
    lines += [f"  {k:<21} {c[k]}" for k in keep if k in c]
    return "\n".join(lines)


def _levers(state: dict[str, Any]) -> str:
    labels = state.get("lever_labels") or ""
    return "\n".join(f"  - {x.strip()}" for x in labels.split(";") if x.strip()) or "  - none"


def _attribution(state: dict[str, Any]) -> str:
    """
    SHAP, in words. The contribution VALUES are deliberately not shown. (v5.1)

    They are log-odds -- "+0.815" -- and three things are true about them at once:
    they are meaningless to a retention agent, no validator covers them (V-MONEY
    matches money and percentages, and a bare 0.815 is neither), and a model handed
    a number tends to quote it. Removing the figure removes the failure mode
    outright, which is better than a rule telling the model not to use it.

    The ORDER is the whole signal, and the order is preserved.
    """
    rows = state.get("attribution") or []
    if not rows:
        return "  (not available)"
    out = [f"  {i}. {r['feature']:<34} "
           f"{'pushes the score UP' if r['direction'] == 'increases_risk' else 'pulls the score DOWN'}"
           for i, r in enumerate(rows, 1)]
    out.append("  " + (state.get("attribution_disclaimer") or ""))
    out.append("  Describe these in ordinary words if you use them. They are ranked "
               "most important first.")
    return "\n".join(out)


def permitted_figures(state: dict[str, Any]) -> str:
    """
    Spelled out so the model is never guessing at what it may write.
    Mirrors the whitelist ValidationContext builds, minus the evidence figures --
    those are visible in the evidence text itself.
    """
    out = [f"  ${state['monthly_charges']:.2f} (monthly charges)",
           f"  ${state['monthly_charges'] * 12:,.2f} (annual charges)",
           f"  ${state['cltv']:,.0f} (lifetime value)",
           f"  {state['p_churn'] * 100:.1f}% (churn risk)",
           f"  {state['tenure_months']} (months of tenure)"]
    # THE INTERNAL FIGURES ARE DELIBERATELY NOT LISTED HERE.  (v5.1)
    # Our cost, the expected value and the assumed effect are all still permitted by
    # the validator -- removing them from the whitelist would reject a note that
    # quoted a number we ourselves put on screen. They are simply not INVITED, because
    # "expected value $705.82" and "an assumed effect of 4%" are decision machinery,
    # not something an agent repeats to a customer. Hard rule 10 says the same thing;
    # this list stops tempting the model in the first place.
    if (state.get("status") or "").startswith("review_"):
        for c in state.get("considered", []):
            out.append(f"  ${c['cost']:.2f} (cost of {c['offer_id']}, which was priced "
                       f"and rejected)")
        floor = float(state.get("min_ev_floor") or 0)
        if floor > 0:
            out.append(f"  ${floor:.2f} (the minimum value an action must be worth)")
    out.append("  any figure that appears verbatim in the evidence documents below")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
def user_block(state: dict[str, Any]) -> str:
    return (_recommend_block(state) if state.get("mode") == "recommend"
            else _review_block(state))


def _recommend_block(state: dict[str, Any]) -> str:
    return f"""MODE: recommend — an offer was chosen. Write the note the agent reads before calling.

CUSTOMER {state['customer_id']}
{_facts(state)}

WHAT THE COMPANY CAN CHANGE (observable, looked up — not inferred)
{_levers(state)}

WHAT MOVED THE MODEL'S SCORE (model behaviour, NOT the customer's motive)
{_attribution(state)}

THE DECISION — ALREADY MADE, NOT YOURS TO CHANGE
  offer            {state['offer_id']} — {state['offer_name']}
  TERMS TO QUOTE   {_customer_terms(state)}

INTERNAL FIGURES — CONTEXT FOR YOU, NOT CONTENT FOR THE NOTE
  These three are already displayed on the agent's screen beside your note. Do not
  write any of them into the note, and never say any of them to a customer.
  cost to us       ${state['cost']:.2f}   (what WE spend, not the customer's price)
  expected value   ${state['ev']:.2f}
  assumed effect   {state['delta_prior'] * 100:.0f}% (a business assumption, not a measurement)

FIGURES YOU MAY USE — NOTHING ELSE
{permitted_figures(state)}

{EVIDENCE_FRAME}
{state.get('evidence_text', '')}

BEFORE YOU RETURN, CHECK YOUR OWN NOTE
  [ ] summary states tenure in months, the monthly charge, and the churn risk, as
      figures - not as "new", "high" or "at risk"
  [ ] talk_track names what the customer gets, what it costs them, and for how long
  [ ] the price to the customer is in WORDS ("at no extra cost") or is a percentage
      you were given - never "$0"
  [ ] no offer other than the one above is mentioned
  [ ] the note contains NO document reference (LEVER-..., DELTA-..., POLICY-...),
      NO word with underscores, NO "expected value", NO "delta", NO "assumed
      effect" and NO model contribution score - plain words only
  [ ] the document ids are in evidence_ids and appear NOWHERE in the sentences
  [ ] every comparison is against the 26.54% base rate, NOT against the group this
      offer would move them into
  [ ] each rate is attached to the right group - re-read the ready-written sentence
  [ ] every figure you wrote appears in the permitted list or the evidence
  [ ] nothing claims the offer will reduce, prevent or guarantee anything

Write the note now. The talk_track is what the agent says out loud."""


def _review_block(state: dict[str, Any]) -> str:
    kind = state["status"]
    if kind == "review_no_profitable_offer":
        considered = state.get("considered", [])
        floor = float(state.get("min_ev_floor") or 0)
        rows = "\n".join(
            f"  {c['offer_id']:<20} costs us ${c['cost']:>8.2f}   worth ${c['ev']:>9.2f} to us"
            for c in considered)
        best = max(considered, key=lambda c: c["ev"]) if considered else None
        # TWO SUB-CASES, ONE WORDING, AND THE DIFFERENCE IS NOT COSMETIC.  (v5.1)
        # Before the minimum existed, this branch could only mean "every offer loses
        # money". It can now also mean "the best one makes $4.10, which is not worth
        # an agent's time". Telling the model the first thing when the second is true
        # would make it write a sentence that is simply false.
        if best and best["ev"] > 0:
            headline = (f"THE SITUATION — offers apply, but none is worth acting on.\n"
                        f"The best of them, {best['offer_id']}, is worth only "
                        f"${best['ev']:.2f} to us, against a minimum of ${floor:.2f} "
                        f"that any action must clear to be worth an agent's time.")
            reason = (f"It is not that the offer loses money — it does not. It clears "
                      f"its own cost by ${best['ev']:.2f}, and that is less than the "
                      f"time it would take to make the call. Do not describe this as a "
                      f"loss-making offer; it is a margin too thin to act on.")
        else:
            headline = ("THE SITUATION — every offer we could price LOSES money on "
                        "this customer.")
            reason = ("The reason is arithmetic, not judgement: the value we would "
                      "protect (their risk, their lifetime value, and how much "
                      "difference we assume the offer makes) is smaller than what the "
                      "offer costs.")
        situation = f"""{headline}
{rows}

{reason} This customer is genuinely at risk, but not worth the spend at current prices.

WHAT HAPPENS NEXT — THIS IS AN INTERNAL INSTRUCTION, NOT A CALL
Do NOT call this customer and do NOT write anything to say to them. Nobody tells a
customer that they were priced and found not worth an offer. Your talk_track must
say, to the AGENT: do not call, name the closest offer and how far short it fell, and
note that a supervisor may still approve an exception. Do not present any of these
offers as available."""
    else:
        situation = """THE SITUATION — no offer in the catalogue APPLIES to this customer at all.

This is not an economics problem. Every offer requires a specific gap to fix, and
this customer has none of them: their contract, payment method and add-ons are
already in the state our offers would move them to. There is nothing to sell them.

WHAT HAPPENS NEXT — THIS IS AN INTERNAL INSTRUCTION, NOT A CALL
Do NOT call this customer and do NOT write anything to say to them. This is a
CATALOGUE GAP, not a decision about this customer's worth: they are riskier than
average and we have no product answer for them. Your talk_track must say, to the
AGENT: do not call, this is a gap in the offer catalogue, and it belongs with
whoever owns that catalogue rather than with a retention call."""

    return f"""MODE: review — no offer survived. Explain the position to the agent.
THERE IS NO CALL. Nothing you write here will be spoken to a customer.

CUSTOMER {state['customer_id']}
{_facts(state)}

WHAT THE COMPANY CAN CHANGE (observable, looked up — not inferred)
{_levers(state)}

{situation}

FIGURES YOU MAY USE — NOTHING ELSE
{permitted_figures(state)}

{EVIDENCE_FRAME}
{state.get('evidence_text', '')}

BEFORE YOU RETURN, CHECK YOUR OWN NOTE
  [ ] summary states tenure in months, the monthly charge, and the churn risk, as
      figures
  [ ] talk_track is addressed to the AGENT and begins by telling them not to call
  [ ] talk_track contains NO words to say to the customer, and never addresses the
      customer as "you"
  [ ] you have not implied any offer is available to this customer
  [ ] the note contains NO document reference (LEVER-..., DELTA-..., POLICY-...),
      NO word with underscores, NO "expected value", NO "delta" and NO model
      contribution score - plain words only
  [ ] the document ids are in evidence_ids and appear NOWHERE in the sentences
  [ ] every figure you wrote appears in the permitted list or the evidence

Write the note now. It is an internal note. There is no call."""


def retry_block(user: str, feedback_text: str) -> str:
    """
    The rewrite prompt: the original request, then the exact complaint. Keeping the
    original attached matters -- a bare correction with no context invites the model
    to fix the cited sentence and break another.
    """
    return (f"{user}\n\n"
            f"{'=' * 70}\nYOUR PREVIOUS ATTEMPT WAS REJECTED BY AN AUTOMATED CHECK.\n"
            f"{'=' * 70}\n{feedback_text}\n\n"
            f"Rewrite the whole note. Keep everything that was fine.")


BANNED_PHRASE_HINT = (
    "Phrases that will be rejected automatically: "
    + ", ".join(f'"{p}"' for p in CAUSAL_PHRASES[:8]) + ", and similar."
)


def system_prompt() -> str:
    return SYSTEM + "\n" + BANNED_PHRASE_HINT + "\n"


if __name__ == "__main__":
    import json
    from .kb_retrieval import select
    demo = {
        "customer_id": "0295-PPHDO", "mode": "recommend", "status": "recommended",
        "customer": {"Contract": "Month-to-month", "Internet Service": "Fiber optic",
                     "Payment Method": "Electronic check", "Tech Support": "No",
                     "Online Security": "No", "Senior Citizen": "No"},
        "tenure_months": 1, "monthly_charges": 95.45, "cltv": 5962.0, "p_churn": 0.99,
        "lever_labels": "No tech support add-on; No online security add-on; "
                        "Rolling month-to-month contract",
        "attribution": [{"feature": "Tenure Months = 1", "contribution": 0.8149,
                         "direction": "increases_risk"}],
        "attribution_disclaimer": "Model attribution, not customer motive.",
        "offer_id": "OFF-BUNDLE-ALL",
        "offer_name": "Tech Support + Online Security bundle, 12 months",
        "cost": 120.51, "ev": 705.82, "delta_prior": 0.14, "delta_ci": [0.05, 0.24],
    }
    ev = select(["NO_TECH_SUPPORT", "NO_ONLINE_SECURITY", "MONTH_TO_MONTH"],
                "OFF-BUNDLE-ALL")
    demo["evidence_text"] = ev.text
    sys_p, usr = system_prompt(), user_block(demo)
    print(sys_p)
    print("=" * 74)
    print(usr[:2200], "\n...[evidence continues]...")
    print("=" * 74)
    print(f"system ~{len(sys_p) // 4} tokens · user ~{len(usr) // 4} tokens · "
          f"total ~{(len(sys_p) + len(usr)) // 4} tokens")
