"""
Serve-time evidence retrieval — deterministic, auditable, no embeddings.

WHAT THIS REPLACES
    Up to KB v3 the plan was: customer -> levers -> reason THEME -> theme-keyed
    documents. Measured over all 1,869 churners, the lever->theme lift is noise
    (max 1.13, min 0.84 across 63 pairs; none above 1.15 with adequate support).
    That bridge was my judgment and the dataset does not support it. Retrieving a
    document about "why competitor-pressure churners left" for a live customer,
    on the strength of a 1.0x lift, is exactly the motive-guessing this whole
    project exists to prevent.

WHAT IT DOES INSTEAD
    Three sources, all keyed on things we actually know about THIS customer:

        POLICY-*   always            the guardrails (3 documents)
        DELTA-*    the chosen offer  how that offer's effect estimate was derived
        LEVER-*    one per lever     observable attribute -> historical churn rate

    Nothing keyed on `Churn Reason` is ever retrieved. The registry marks those
    `historical_cohort` and select() refuses them.

WHY NOT A VECTOR DATABASE
    The retrieval key is STRUCTURED, not semantic: we already hold the customer's
    levers as exact categorical facts. Recovering an exact fact by approximate
    cosine similarity is a downgrade. It is also not reproducible -- "which
    documents did customer 3241 see on 12 Aug" must be answerable byte-for-byte in
    six months, and an embedding index whose model version has moved cannot
    promise that. At 19 serve-time documents an ANN index is theatre.

    A vector DB becomes the right tool when the corpus is thousands of free-text
    documents nobody can enumerate a mapping for -- agent call notes, complaint
    transcripts. That is a real future state. It is not this one.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .decision import BASE_RATE
from .levers import LEVERS

ROOT = Path(__file__).resolve().parent.parent
KB_PATH = ROOT / "data" / "kb" / "knowledge_base.md"
REGISTRY_PATH = ROOT / "artifacts" / "evidence_ids.json"

SERVE_TIME = "this_customer_observable"


@dataclass(frozen=True)
class Evidence:
    """Exactly what node 2 hands to node 3, and what node 4 validates against."""
    ids: list[str]
    text: str
    approx_tokens: int
    unmapped_levers: list[str]      # levers with no document -- must always be []

    def as_state(self) -> dict:
        return {"evidence_ids": list(self.ids), "allowed_ids": list(self.ids),
                "evidence_tokens": self.approx_tokens}


@lru_cache(maxsize=1)
def _load() -> tuple[dict, dict[str, str]]:
    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(
            f"{REGISTRY_PATH} missing -- run `python -m src.kb_build` first")
    reg = json.loads(REGISTRY_PATH.read_text())
    bodies: dict[str, str] = {}
    for chunk in re.split(r"^### ", KB_PATH.read_text(), flags=re.M)[1:]:
        did = chunk.split("\n", 1)[0].strip()
        bodies[did] = "### " + chunk.rstrip() + "\n"
    return reg, bodies


def registry() -> dict:
    return _load()[0]


def lever_document_map() -> dict[str, str]:
    """lever code -> document id. Built from the KB, never hand-maintained."""
    reg = registry()
    return {m["lever"]: did for did, m in reg["documents"].items()
            if m["type"] == "LEVER" and m.get("lever")}


def assert_lever_coverage() -> None:
    """
    THE ASSERTION THAT WAS MISSING.

    Until v4, four levers (NO_DEVICE_PROTECTION, MANUAL_PAYMENT, NEW_CUSTOMER,
    NO_INTERNET) mapped to no evidence at all. No customer happened to end up
    with zero documents, but that was luck, not design -- MANUAL_PAYMENT is the
    electronic-check segment at 45.3% churn and the lever behind OFF-AUTOPAY.
    This now fails loudly instead of degrading quietly.
    """
    have = lever_document_map()
    missing = sorted(c for c in LEVERS if c not in have)
    if missing:
        raise AssertionError(
            f"{len(missing)} lever(s) have no evidence document: {missing}. "
            f"Run `python -m src.kb_build` to regenerate, or remove the lever.")


def select(levers: list[str], offer_id: str | None) -> Evidence:
    """
    Deterministic: same inputs -> same document ids, in sorted order, forever.
    That property is what makes a recommendation replayable in an audit.
    """
    reg, bodies = _load()
    docs = reg["documents"]
    lever_docs = lever_document_map()

    chosen = {d for d, m in docs.items() if m["type"] == "POLICY"}
    if offer_id:
        chosen |= {d for d, m in docs.items() if m.get("offer") == offer_id}
    unmapped = []
    for code in levers:
        did = lever_docs.get(code)
        if did:
            chosen.add(did)
        else:
            unmapped.append(code)

    # Belt and braces: even if a future edit mis-tags a document, a
    # reason-keyed one cannot reach a prompt.
    leaked = sorted(d for d in chosen if docs[d]["applies_to"] != SERVE_TIME)
    if leaked:
        raise AssertionError(f"reason-keyed documents selected for a live "
                             f"customer: {leaked}")

    ids = sorted(chosen)
    text = "\n".join(_humanise(d, bodies[d], docs[d]) for d in ids)
    return Evidence(ids=ids, text=text, approx_tokens=max(1, len(text) // 4),
                    unmapped_levers=unmapped)


# --------------------------------------------------------------------------- #
#  PRESENTATION ONLY — the same documents, with the machinery relabelled. (v5.3)
#
#  A real Gemini run wrote "...48.28% churn, based on LEVER-066 ... as shown in
#  LEVER-063 ... per LEVER-060". Every figure and every citation was correct, so
#  five of the six validators passed it -- and an agent seconds from dialling
#  could do nothing with "LEVER-066".
#
#  V-PLAIN now rejects that, but a validator that fires on every draft is a
#  wasted request, and the reason it kept happening is visible above: the model
#  was handed `### LEVER-060` as a heading and `**Lever:** `NO_TECH_SUPPORT``
#  as a field. It was quoting what we showed it. Removing the temptation is the
#  same fix that worked for the SHAP log-odds values.
#
#  WHAT THIS DOES NOT DO. It does not edit data/kb/knowledge_base.md, does not
#  change which documents are retrieved, and does not touch the ids -- those
#  still go to `evidence_ids`, the registry and the audit log unchanged. It
#  rewrites HEADINGS AND FIELD LABELS on the way into the prompt. No sentence of
#  document body text is altered, and `_assert_no_figure_lost` proves no number
#  moved, because every figure in this text is on the V-MONEY whitelist and
#  losing one would start rejecting true notes.
# --------------------------------------------------------------------------- #
_LABEL = {
    "LEVER": "SOMETHING WE CAN SEE ON THIS ACCOUNT",
    "DELTA": "HOW BIG AN EFFECT WE ASSUME THIS OFFER HAS",
    "POLICY": "A RULE THIS SYSTEM WORKS UNDER",
    "ASSOC": "A PATTERN IN PAST DATA",
    "DOMAIN": "BACKGROUND ON THE INDUSTRY",
    "HIST": "A PATTERN IN PAST DATA",
    "OUTCOME": "A PATTERN IN PAST DATA",
}
_FIELD = {
    "- **delta_prior:**": "- **Assumed effect (a business estimate, not measured):**",
    "- **delta_ci:**": "- **Plausible range for that estimate:**",
    "- **delta_source:** business_judgment_v1": "- **Where the estimate came from:** business judgment",
    "- **Document type:**": "- **What kind of document this is:**",
    "- **Evidence type:**": "- **What kind of evidence this is:**",
    "- **Evidence strength:**": "- **How strong the evidence is:**",
    "- **Sample size:**": "- **How many customers this is based on:**",
    "- **Source IDs:** ['DATASET', 'BUSINESS_JUDGMENT']": "- **Based on:** the dataset, plus business judgment",
    "- **Source IDs:** ['DATASET']": "- **Based on:** the dataset",
}


# The one sentence a LEVER document is actually FOR, pre-written.  (v5.7)
#
# Measured across four Gemini runs, roughly one note in twelve inverted a
# comparison -- "those WITH device protection have a churn rate of 39.13%", when
# 39.13% is the rate for accounts WITHOUT it. Every such note passed all six
# validators: the figure is real, cited and correctly rounded. Only the direction
# was wrong, and no check looks at direction.
#
# The model has to work out that the second figure belongs to the complement group.
# So it is written out instead. There is nothing left to invert.
_BOLD_PCT = re.compile(r"\*\*([0-9]+(?:\.[0-9]+)?)%\*\*")


def _ready_made_sentence(meta: dict, body: str) -> str | None:
    """
    Every generated LEVER document states its two rates as the first two bolded
    percentages: the attribute group, then the complement. Verified across all 9.
    If that shape ever changes the parse returns None and the line is simply
    omitted -- a missing hint is harmless, a wrong one is not. A test asserts all
    nine still parse, so a KB change fails the suite rather than the note.
    """
    from .levers import LEVERS
    lever = meta.get("lever")
    if lever not in LEVERS:
        return None
    hits = _BOLD_PCT.findall(body)
    if len(hits) < 2:
        return None
    label = LEVERS[lever].label
    return (f'- **THE SENTENCE TO USE, ALREADY WRITTEN:** accounts where "{label}" '
            f'applies left at {hits[0]}%; accounts where it does not left at '
            f'{hits[1]}%; across all customers the rate is {BASE_RATE * 100:.2f}%. '
            f'Use these three figures exactly as written above — do not swap which '
            f'group each one belongs to.')


# The derivation line, removed from what the model is shown.  (v5.7)
#
# Every DELTA document opens with "Observed churn rate with `Contract =
# Month-to-month` is 42.7%; with `Contract = Two year` it is 2.8%." That second
# figure is the churn rate of people who ALREADY CHOSE the long contract, and the
# document's own next paragraph says most of that gap is selection, not treatment.
#
# Real notes were quoting it next to the offer: "rolling contracts left at 42.71%,
# compared to 2.8% on a two-year contract ... we can move you to a two-year
# contract." No causal verb, so V-CAUSAL passes it -- and the sentence still
# implies the move causes the drop, which is the one claim this whole project
# refuses to make.
#
# Removing the line removes the temptation AND creates the enforcement: the figure
# is no longer in the evidence, so it is no longer on V-MONEY's whitelist, and a
# note that quotes it is now rejected automatically. Nothing is lost from the
# audit trail -- data/kb/knowledge_base.md still carries the full derivation.
_OBSERVED_RE = re.compile(r"^Observed churn rate with .*$", re.M)
_OBSERVED_REPLACEMENT = (
    "This offer's effect estimate was derived from a raw comparison between "
    "customers who already have this attribute and those who do not. THOSE RAW "
    "FIGURES ARE DELIBERATELY NOT SHOWN HERE. Customers who chose a long contract "
    "or took an add-on were already more likely to stay, so their churn rate is "
    "not what would happen if this customer were moved into that group. Never "
    "describe an offer by quoting the churn rate of the group it would move "
    "someone into.")


def _humanise(doc_id: str, body: str, meta: dict) -> str:
    from .levers import LEVERS
    if meta.get("type") == "DELTA":
        body = _OBSERVED_RE.sub(_OBSERVED_REPLACEMENT, body)
    ready = _ready_made_sentence(meta, body)
    out = []
    for line in body.splitlines():
        if line.startswith("### "):
            lever = meta.get("lever")
            title = (LEVERS[lever].label if lever in LEVERS
                     else _LABEL.get(meta.get("type"), "REFERENCE"))
            out.append(f"### {title}")
            out.append(f"- **Filing reference:** {doc_id}  — this id goes in the "
                       f"`evidence_ids` field ONLY. Never write it in the note "
                       f"itself; it means nothing to an agent.")
            continue
        if line.startswith("- **Lever:**"):
            # The code is now the heading, in words. The document's whole point
            # goes here instead, pre-written so it cannot be inverted.
            if ready:
                out.append(ready)
            continue
        for k, v in _FIELD.items():
            if line.startswith(k):
                line = v + line[len(k):]
                break
        out.append(line)
    return "\n".join(out)


def figures_dropped(before: str, after: str) -> list[str]:
    """
    Which numbers this rendering removes from what the model is shown.

    Every figure in the evidence lands on V-MONEY's whitelist, so dropping one is
    NOT cosmetic -- it makes that figure unquotable, and a note using it is
    rejected. Until v5.7 nothing was dropped and this asserted so. v5.7 drops the
    DELTA derivation line ON PURPOSE, which is what turns "do not quote the churn
    rate of the group the offer would move them into" from a request into a rule
    the existing money check enforces for free.

    So this returns the list instead of asserting it is empty, and the test suite
    asserts the list is exactly what we intended to drop -- an accidental removal
    still fails, a deliberate one is documented.
    """
    num = re.compile(r"[0-9][0-9,]*(?:\.[0-9]+)?")
    return sorted(set(num.findall(before)) - set(num.findall(after)))


def render_for_prompt(ev: Evidence) -> str:
    """
    Structural separation, not a polite request.

    Weakness (b) was that cohort documents describe customers who ALREADY LEFT,
    and a single sentence asking the model not to confuse that with the live
    customer is weak. v4 removes cohort documents from retrieval entirely, so
    this renderer can state one unambiguous frame for everything it prints.
    """
    return (
        "EVIDENCE — every document below describes either this customer's own\n"
        "observable account attributes, the derivation of the offer's effect\n"
        "estimate, or a system policy. NONE of it states why this customer, or\n"
        "any customer, chose to leave. That information does not exist for a\n"
        "customer who has not left. Do not infer a motive from any of it.\n\n"
        + ev.text
    )


if __name__ == "__main__":
    import collections
    import pandas as pd

    assert_lever_coverage()
    reg = registry()
    serve = [d for d, m in reg["documents"].items() if m["applies_to"] == SERVE_TIME]
    print(f"KB v{reg['kb_version']}: {reg['n_documents']} documents, "
          f"{len(serve)} retrievable at serve time")
    print(f"lever coverage: {len(lever_document_map())}/{len(LEVERS)}\n")

    q = pd.read_csv(ROOT / "artifacts" / "queue_full.csv")
    q = q[q.status == "recommended"]
    res = [select([x for x in str(r.levers).split("|") if x], r.offer_id)
           for r in q.itertuples()]
    n = pd.Series([len(e.ids) for e in res])
    t = pd.Series([e.approx_tokens for e in res])
    print(f"MEASURED over {len(q)} recommended customers")
    print(f"  documents  min {n.min()}  p50 {int(n.median())}  "
          f"p90 {int(n.quantile(.9))}  max {n.max()}")
    print(f"  ~tokens    min {t.min()}  p50 {int(t.median())}  "
          f"p90 {int(t.quantile(.9))}  max {t.max()}")
    print(f"  distribution {dict(sorted(collections.Counter(n).items()))}")
    print(f"  customers with an unmapped lever: "
          f"{sum(1 for e in res if e.unmapped_levers)}")
