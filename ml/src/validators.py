"""
Node 4 of the narration graph — the five checks that run on whatever the model wrote.

WHY THIS FILE EXISTS AT ALL
    `response_format` on the Gemini call guarantees the JSON parses and has the
    right shape. Measured against our own fixtures, that catches 2 of the 5
    failure modes. The other three -- an invented 25% discount, the wrong offer
    named, a fabricated document id -- are perfectly well-formed JSON that is
    simply untrue. Schema-valid and truthful are different properties.

THE SIX CHECKS

    V-OFFER    the offer named in the prose must be the one the decision engine
               chose, and no other catalog offer may be named
    V-MONEY    every money or percent figure in the prose must already exist,
               to rounding, in this customer's record or in the evidence shown
    V-CITE     every cited evidence_id must be in the registry AND in the set
               retrieved for THIS customer
    V-CAUSAL   no causal claims -- the effect sizes are assumptions, not results
    V-SCHEMA   required fields present, non-empty, within length caps
    V-PLAIN    no document ids, internal identifiers or machinery words in the
               prose -- the note is read by an agent, not by a developer  (v5.3)

    The first five ask "is this TRUE?". V-PLAIN asks "is this READABLE?", and it
    exists because a note can be perfectly true and still useless: every figure
    and citation in "...48.28% churn, based on LEVER-066" was correct, and the
    other five checks passed it.

DESIGN NOTES WORTH READING BEFORE CHANGING ANYTHING

 1. THE WHITELIST INCLUDES THE EVIDENCE, NOT JUST THE CUSTOMER RECORD.
    A good note says "accounts without tech support left at 41.6% against
    11.9%". Those figures come from LEVER-060, not from the customer's row. If
    the whitelist were only the customer's own numbers, every well-behaved draft
    would fail. So the whitelist is: the decision state + every figure appearing
    in the documents we actually showed the model.

 2. MATCHING IS ROUNDING-AWARE.
    LEVER-060 says 41.64%; a human-readable note says 41.6%. Requiring an exact
    string match would reject correct rounding. A written figure passes if it
    equals the whitelisted value rounded to the same number of decimal places.

 3. V-MONEY SCOPES TO MONEY AND PERCENT TOKENS, NOT ALL NUMBERS.
    The failure mode we are guarding against is an invented price or discount,
    and those always carry a currency symbol, a percent sign, or an "off"/
    "discount" context. Flagging every bare integer would reject "12 months" and
    "three paragraphs" and train people to ignore the validator.

 4. V-OFFER IS A CONTAINMENT CHECK AND CANNOT CATCH EVERY PARAPHRASE.
    It catches another offer's id, its full name, and a small alias list. A
    model that invents a wholly novel offer in fresh words would slip past it --
    which is exactly why the human approval step exists and is not optional.

 5. NO DISCLAIMER SUBSTRING IS REQUIRED IN THE DRAFT.
    The uncertainty sentence a user sees is composed in code by the API from
    delta_prior/delta_ci (see src/api_fixtures.py). Requiring the model to write
    it too would put numbers back in its hands for no gain.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------- #
#  Causal language. These are claims the dataset cannot support: no intervention
#  has ever been recorded, so no offer has a measured effect on anybody.
# --------------------------------------------------------------------------- #
CAUSAL_PHRASES: tuple[str, ...] = (
    "will reduce", "will prevent", "will stop", "will keep them",
    "will retain", "will lower", "will decrease", "will increase retention",
    "guarantees", "guaranteed", "proven to", "proven that", "clinically",
    "causes", "caused by", "because they will", "this will make",
    "ensures they stay", "eliminates the risk", "removes the risk",
    "is known to reduce", "shown to prevent",
)

# Phrases that are fine and must NOT trip the scan, listed so a future edit does
# not accidentally ban them.
CAUSAL_ALLOWLIST: tuple[str, ...] = (
    "associated with", "association", "in past data", "historically",
    "customers like this", "we assume", "assumption", "hypothesis",
)

MONEY_RE = re.compile(r"\$\s?([0-9][0-9,]*(?:\.[0-9]+)?)")
PERCENT_RE = re.compile(r"([0-9][0-9,]*(?:\.[0-9]+)?)\s?(?:%|percent\b)")
# "25 off", "take 30 off your bill" -- a discount with the sign dropped.
BARE_OFF_RE = re.compile(r"\b([0-9][0-9,]*(?:\.[0-9]+)?)\s+off\b", re.I)

MAX_LEN = {"summary": 240, "why": 700, "talk_track": 700}
MIN_LEN = {"summary": 20, "why": 40, "talk_track": 40}


@dataclass(frozen=True)
class Violation:
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass
class ValidationContext:
    """
    Everything the checks are allowed to treat as true.

    Built by node 1 and node 2 from `decide()` and `kb_retrieval.select()`, never
    from anything the model produced.
    """
    offer_id: str
    offer_name: str
    cost: float
    p_churn: float
    cltv: float
    expected_value: float
    delta_prior: float
    delta_ci: tuple[float, float]
    monthly_charges: float
    tenure_months: int
    discount_pct: float = 0.0
    allowed_evidence_ids: tuple[str, ...] = ()
    evidence_text: str = ""
    other_offer_ids: tuple[str, ...] = ()
    other_offer_names: tuple[str, ...] = ()
    # Every offer id in the catalog, permitted or not. V-PLAIN uses it to tell an
    # offer id apart from a document id: both look like ABC-DEF-12, but naming an
    # offer is a question for V-OFFER, and naming a document is always wrong.
    catalog_offer_ids: tuple[str, ...] = ()
    # The note is allowed to name the customer it is about. Real ids in this
    # dataset look like 0295-PPHDO and do not match the document pattern, but a
    # test id like TEST-0001 does -- and whitelisting it explicitly is correct
    # regardless of what a future id format looks like.
    customer_id: str = ""
    # The customer's CURRENT contract term, verbatim from the account record
    # ("Month-to-month" | "One year" | "Two year"). Read only by V-OFFER, to tell
    # a description of the status quo apart from a recommendation. See _aliases().
    current_contract: str = ""
    extra_allowed_figures: tuple[float, ...] = ()
    _whitelist: set[float] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        self._whitelist = self._build_whitelist()

    # -- whitelist -------------------------------------------------------- #
    def _build_whitelist(self) -> set[float]:
        vals: set[float] = set()

        def add(*xs: float) -> None:
            for x in xs:
                vals.add(round(float(x), 4))

        # The customer's own record and the decision made about them, as both
        # absolute values and percentages (a note may say 14% or 0.14).
        add(self.cost, self.cltv, self.expected_value, self.monthly_charges,
            self.monthly_charges * 12, float(self.tenure_months))
        for frac in (self.p_churn, self.delta_prior, self.delta_ci[0],
                     self.delta_ci[1], self.discount_pct):
            add(frac, frac * 100)
        add(*self.extra_allowed_figures)

        # Every figure in the documents we actually showed the model. Quoting the
        # evidence is the behaviour we want; it must not be a violation.
        for m in MONEY_RE.finditer(self.evidence_text):
            add(_num(m.group(1)))
        for m in PERCENT_RE.finditer(self.evidence_text):
            add(_num(m.group(1)))
        return vals

    def permits(self, written: float, decimals: int) -> bool:
        """
        Rounding-aware membership: 41.6 is permitted by a whitelisted 41.64.

        Implemented as a tolerance rather than `round(v, d) == written` because
        Python rounds half to even: round(11.85, 1) is 11.8, so a note that
        correctly writes 11.9 would have been rejected. The tolerance is exactly
        half a unit in the last written place, which IS the definition of "this
        is a rounding of that".
        """
        tol = 0.5 * 10 ** -decimals + 1e-9
        return any(abs(v - written) <= tol for v in self._whitelist)

    @property
    def whitelist(self) -> set[float]:
        return set(self._whitelist)


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def _decimals(s: str) -> int:
    return len(s.split(".")[1]) if "." in s else 0


# --------------------------------------------------------------------------- #
#  The five checks
# --------------------------------------------------------------------------- #
def check_offer(text: str, ctx: ValidationContext) -> list[Violation]:
    """V-OFFER — the prose may name only the offer that was actually chosen."""
    out: list[Violation] = []
    low = text.lower()
    for oid in ctx.other_offer_ids:
        if oid.lower() in low:
            out.append(Violation("V-OFFER",
                                 f"names a different offer_id {oid!r}; the chosen "
                                 f"offer is {ctx.offer_id!r}"))
    for name in ctx.other_offer_names:
        if name and name.lower() in low:
            out.append(Violation("V-OFFER",
                                 f"names a different offer {name!r}; the chosen "
                                 f"offer is {ctx.offer_name!r}"))
    chosen = ctx.offer_id or "no offer was chosen for this customer"
    for alias, owner in _aliases(ctx).items():
        if alias in low and owner != ctx.offer_id:
            out.append(Violation("V-OFFER",
                                 f"refers to {alias!r}, which belongs to {owner}, "
                                 f"not to the chosen {chosen}"))
    return _dedupe(out)


# Which offer each CONTRACT TERM corresponds to. Used only to recognise when a
# phrase is describing where the customer already is.
CONTRACT_TERM_OFFER = {"one year": "OFF-CONTRACT-1Y", "two year": "OFF-CONTRACT-2Y"}


def _aliases(ctx: ValidationContext) -> dict[str, str]:
    """
    Small, explicit paraphrase table. Deliberately narrow: a wrong entry here
    would reject correct drafts, which is worse than missing a paraphrase that
    the human reviewer will catch.

    A PHRASE THAT DESCRIBES THE CUSTOMER'S CURRENT CONTRACT IS NOT A RECOMMENDATION.
    (fixed v5.5, and this was a real false positive costing 7.4% of the queue.)

    Measured over three seeded runs: EVERY note that failed validation failed on
    this check, with this message --

        V-OFFER: refers to 'one-year contract', which belongs to OFF-CONTRACT-1Y,
                 not to the chosen OFF-TECHSUP-12

    -- and every one of those customers was already ON a one-year contract. Twelve
    for twelve: the four failures were the four non-month-to-month customers, and
    the eight clean notes were all month-to-month. The prompt shows the model
    `Contract  One year`, so it wrote "this customer is on a one-year contract",
    which is TRUE, USEFUL and exactly what an agent needs. Substring matching could
    not tell it apart from "let me move you to a one-year contract".

    It also explains why the retry never recovered: the feedback said "do not
    suggest an alternative offer", the model was not suggesting one, so there was
    nothing it could change. It rewrote, described the contract again, and was
    rejected again.

    WHAT IS GIVEN UP, AND WHY IT IS SAFE. Only the loosest of three checks is
    relaxed, only for the single phrase that is factually true of this customer. A
    model genuinely pushing the wrong offer is still caught by the two stricter
    checks above, which are untouched: the literal offer id (OFF-CONTRACT-1Y) and
    the full offer name ("1-year contract at 10% off"). Neither can appear in a
    description of the status quo.
    """
    table = {
        "1-year contract": "OFF-CONTRACT-1Y", "one-year contract": "OFF-CONTRACT-1Y",
        "one year contract": "OFF-CONTRACT-1Y", "12-month contract": "OFF-CONTRACT-1Y",
        "2-year contract": "OFF-CONTRACT-2Y", "two-year contract": "OFF-CONTRACT-2Y",
        "two year contract": "OFF-CONTRACT-2Y", "24-month contract": "OFF-CONTRACT-2Y",
        "autopay": "OFF-AUTOPAY", "auto-pay": "OFF-AUTOPAY",
    }
    known = {ctx.offer_id, *ctx.other_offer_ids}
    describes_status_quo = CONTRACT_TERM_OFFER.get(
        (ctx.current_contract or "").strip().lower())
    return {k: v for k, v in table.items()
            if v in known and v != describes_status_quo}


def check_money(text: str, ctx: ValidationContext) -> list[Violation]:
    """V-MONEY — the guard that catches a hallucinated discount."""
    out: list[Violation] = []
    seen: set[str] = set()
    for regex, kind in ((MONEY_RE, "amount"), (PERCENT_RE, "percentage"),
                        (BARE_OFF_RE, "discount")):
        for m in regex.finditer(text):
            raw = m.group(1)
            if raw in seen:
                continue
            seen.add(raw)
            if not ctx.permits(_num(raw), _decimals(raw)):
                out.append(Violation(
                    "V-MONEY",
                    f"the {kind} {m.group(0).strip()!r} does not appear in this "
                    f"customer's record or in the evidence supplied"))
    return out


def check_citations(evidence_ids: Sequence[str], ctx: ValidationContext,
                    registry_ids: Iterable[str] | None = None) -> list[Violation]:
    """V-CITE — no invented document ids, and no id we did not show."""
    out: list[Violation] = []
    known = set(registry_ids) if registry_ids is not None else load_registry_ids()
    allowed = set(ctx.allowed_evidence_ids)
    for eid in evidence_ids:
        if eid not in known:
            out.append(Violation("V-CITE", f"{eid!r} is not a document in the "
                                           f"knowledge base"))
        elif allowed and eid not in allowed:
            out.append(Violation("V-CITE", f"{eid!r} exists but was not shown for "
                                           f"this customer"))
    return out


def check_causal(text: str) -> list[Violation]:
    """V-CAUSAL — association may not be restated as cause."""
    low = text.lower()
    return [Violation("V-CAUSAL",
                      f"the phrase {p!r} states a causal effect. No offer in this "
                      f"system has a measured effect; describe it as an "
                      f"association observed in past data")
            for p in CAUSAL_PHRASES if p in low]


# --------------------------------------------------------------------------- #
#  V-PLAIN — the note must read like English, not like the system that made it.
#
#  WHY THIS EXISTS. A real Gemini run produced:
#      "...48.28% historical churn rate for customers under 12 months tenure,
#       based on LEVER-066 ... as shown in LEVER-063 ... per LEVER-060."
#  Every figure was true and every citation was real, so V-MONEY and V-CITE both
#  passed it. It was still unreadable: an agent about to telephone a customer
#  cannot do anything with "LEVER-066". Document ids are a FILING REFERENCE, and
#  they already have a field of their own -- `evidence_ids` -- which is where the
#  UI reads them from. Repeating them mid-sentence is machinery leaking into
#  prose.
#
#  Three families are rejected, and the third is the one that catches the future:
#    1. document ids            LEVER-060, POLICY-001, DELTA-051, HIST-002
#    2. internal identifiers    MONTH_TO_MONTH, no_action_needed, delta_prior,
#                               R3_POSITIVE_EV -- anything snake_case
#    3. named machinery         "expected value", "delta", "assumed effect",
#                               "SHAP", "log-odds", "p_churn"
#
#  OFFER IDS ARE DELIBERATELY ALLOWED. "the closest was OFF-CONTRACT-1Y, short by
#  $7.50" is exactly what a review note is for: the id is short, it appears on the
#  agent's screen beside the note, and it is the handle they use to look the offer
#  up. Which offer may be named is V-OFFER's job, not this one -- one check, one
#  question.
# --------------------------------------------------------------------------- #
DOC_ID_RE = re.compile(r"\b[A-Z]{3,}-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")
SNAKE_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b")
JARGON = {
    "expected value": "say what it is worth to us, in plain words",
    "delta": "say 'how much difference we assume it makes'",
    "delta prior": "say 'the assumed effect'",
    "assumed effect": "say 'we assume it makes a difference of about ...'",
    "shap": "describe what the model reacted to, in words",
    "log-odds": "never quote a model contribution value",
    "log odds": "never quote a model contribution value",
    "p_churn": "say 'churn risk'",
    "predict_proba": "say 'the model scored them at ...'",
    "base rate": None,          # allowed: an agent understands "the base rate"
}
_JARGON_BANNED = {k: v for k, v in JARGON.items() if v is not None}


def check_plain_language(text: str, ctx: ValidationContext) -> list[Violation]:
    """V-PLAIN — no document ids, no internal identifiers, no machinery words."""
    out: list[Violation] = []
    allowed_tokens = {t for t in (ctx.offer_id, ctx.customer_id,
                                  *ctx.other_offer_ids,
                                  *ctx.catalog_offer_ids) if t}

    for m in DOC_ID_RE.finditer(text):
        tok = m.group(0)
        if tok in allowed_tokens:
            continue                       # naming an offer is V-OFFER's question
        out.append(Violation(
            "V-PLAIN",
            f"{tok!r} is a document reference and must not appear in the note. "
            f"Put it in evidence_ids and describe what it says in words"))

    for m in SNAKE_RE.finditer(text):
        out.append(Violation(
            "V-PLAIN",
            f"{m.group(0)!r} is an internal identifier, not English. Say what it "
            f"means instead"))

    low = text.lower()
    for phrase, advice in _JARGON_BANNED.items():
        if phrase in low:
            out.append(Violation(
                "V-PLAIN", f"{phrase!r} is internal machinery — {advice}"))

    # The delta symbol, which the evidence documents use and the model copies.
    if "Δ" in text:
        out.append(Violation("V-PLAIN", "'Δ' is a symbol from our internal "
                                        "documents; write it in words"))
    return _dedupe(out)


def check_schema(draft: object) -> list[Violation]:
    """
    V-SCHEMA — re-checked here even though the provider enforces the schema,
    because the deterministic fallback template goes through the same gate and
    is not produced by a provider at all.
    """
    out: list[Violation] = []
    for f in ("summary", "why", "talk_track"):
        v = getattr(draft, f, None)
        if not isinstance(v, str) or not v.strip():
            out.append(Violation("V-SCHEMA", f"{f} is missing or empty"))
            continue
        if len(v) < MIN_LEN[f]:
            out.append(Violation("V-SCHEMA",
                                 f"{f} is {len(v)} characters, minimum {MIN_LEN[f]}"))
        if len(v) > MAX_LEN[f]:
            out.append(Violation("V-SCHEMA",
                                 f"{f} is {len(v)} characters, maximum {MAX_LEN[f]}"))
    ids = getattr(draft, "evidence_ids", None)
    if not isinstance(ids, (list, tuple)) or len(ids) == 0:
        out.append(Violation("V-SCHEMA", "evidence_ids must cite at least one document"))
    return out


# --------------------------------------------------------------------------- #
def validate(draft: object, ctx: ValidationContext,
             registry_ids: Iterable[str] | None = None) -> list[Violation]:
    """
    Run all five. Order matters only for readability of the retry message.

    Returns [] when the draft is acceptable. Never raises on model output --
    a malformed draft is a violation, not an exception.
    """
    schema = check_schema(draft)
    if any(v.detail.endswith("is missing or empty") for v in schema):
        # Nothing else can be checked meaningfully against empty prose.
        return schema
    text = " ".join(str(getattr(draft, f, "") or "")
                    for f in ("summary", "why", "talk_track"))
    return [*schema,
            *check_offer(text, ctx),
            *check_money(text, ctx),
            *check_citations(list(getattr(draft, "evidence_ids", []) or []), ctx,
                             registry_ids),
            *check_causal(text),
            *check_plain_language(text, ctx)]


def feedback(violations: Sequence[Violation], ctx: ValidationContext) -> str:
    """
    The retry prompt. Naming the exact problem and the permitted values is why
    two attempts is enough rather than optimistic -- a bare "try again" invites
    the same mistake.
    """
    if not violations:
        return ""
    lines = ["Your previous draft was rejected. Fix every point below and rewrite.",
             ""]
    lines += [f"- {v}" for v in violations]
    if any(v.code == "V-MONEY" for v in violations):
        permitted = ", ".join(_fmt(v) for v in sorted(ctx.whitelist)[:12])
        lines += ["",
                  "You may only use figures that appear in the customer record or "
                  "the evidence. Permitted values include: " + permitted + "."]
    if any(v.code == "V-OFFER" for v in violations):
        lines += ["", f"The only offer you may name is {ctx.offer_id} "
                      f"({ctx.offer_name}). It has already been chosen; do not "
                      f"suggest an alternative."]
    if any(v.code == "V-CITE" for v in violations):
        lines += ["", "You may cite only these document ids: "
                  + ", ".join(ctx.allowed_evidence_ids) + "."]
    if any(v.code == "V-PLAIN" for v in violations):
        lines += ["",
                  "The note is read by a retention agent seconds before they "
                  "telephone somebody. Keep the FIGURES and drop the references: "
                  "write \"accounts on a rolling contract left at 42.7%, against "
                  "26.5% across the base\" and put the document id in "
                  "evidence_ids, where the screen already shows it. Never write a "
                  "document id, an identifier with underscores, or the words "
                  "\"expected value\", \"delta\" or \"assumed effect\" in the note."]
    return "\n".join(lines)


def _fmt(v: float) -> str:
    return f"{v:g}"


def _dedupe(vs: list[Violation]) -> list[Violation]:
    seen, out = set(), []
    for v in vs:
        key = (v.code, v.detail)
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out


def load_registry_ids() -> set[str]:
    p = ROOT / "artifacts" / "evidence_ids.json"
    if not p.exists():                                        # pragma: no cover
        raise FileNotFoundError(f"{p} missing -- run `python -m src.kb_build`")
    return set(json.loads(p.read_text())["documents"])


# --------------------------------------------------------------------------- #
def context_from_decision(rec, evidence, catalog, considered=None,
                          current_contract=None) -> ValidationContext:
    """
    Build a context from the objects the graph already holds. Keeping this here
    means node 4 never reaches into the catalog itself.

    `considered` MATTERS, AND THE TEST SUITE FOUND OUT WHY.
    In review mode there is no chosen offer, and the note's whole job is to name the
    offers that WERE priced and say what each one loses: "the closest was
    OFF-CONTRACT-1Y at $113.16, short by $7.50". With a naive context every one of
    those names trips V-OFFER and every one of those figures trips V-MONEY -- the
    validator would reject the truth.

    So the offers a note may name are the chosen one PLUS the ones actually
    considered, and their costs and shortfalls join the whitelist. An offer that was
    never priced for this customer is still a violation, which is the property we
    wanted all along.
    """
    offers = {o.offer_id: o for o in catalog.offers}
    chosen = offers.get(rec.offer_id)
    considered = list(considered or [])
    permitted = {rec.offer_id} | {c.get("offer_id") for c in considered}
    permitted.discard(None)

    figures: list[float] = []
    for c in considered:
        for key in ("cost", "ev", "delta"):
            v = c.get(key)
            if isinstance(v, (int, float)):
                figures += [abs(float(v)), abs(float(v)) * 100]

    # THE MINIMUM EXPECTED VALUE IS AN ON-SCREEN FIGURE.  (v5.1)
    # A review-mode note whose whole job is "the best offer returns $4.10 against a
    # $20.00 minimum" must be allowed to write both numbers, and the gap between
    # them. Without this the validator would once again reject the truth -- the same
    # failure mode `considered` was added to fix.
    floor = float(catalog.policy.get("min_expected_value_usd", 0.0) or 0.0)
    if floor > 0:
        figures.append(floor)
        for c in considered:
            v = c.get("ev")
            if isinstance(v, (int, float)):
                figures.append(abs(floor - float(v)))

    return ValidationContext(
        offer_id=rec.offer_id or "",
        offer_name=rec.offer_name or "",
        cost=float(rec.cost),
        p_churn=float(rec.p_churn),
        cltv=float(rec.cltv),
        expected_value=float(rec.ev),
        delta_prior=float(rec.delta_prior),
        delta_ci=tuple(chosen.delta_ci) if chosen else (0.0, 0.0),
        monthly_charges=float(rec.monthly_charges),
        tenure_months=int(rec.tenure_months),
        discount_pct=float(getattr(chosen, "discount_pct", 0.0) or 0.0),
        allowed_evidence_ids=tuple(evidence.ids),
        evidence_text=evidence.text,
        other_offer_ids=tuple(o for o in offers if o not in permitted),
        other_offer_names=tuple(o.name for oid, o in offers.items()
                                if oid not in permitted),
        catalog_offer_ids=tuple(offers),
        customer_id=str(getattr(rec, "customer_id", "") or ""),
        current_contract=str(current_contract
                             if current_contract is not None
                             else getattr(rec, "current_contract", "") or ""),
        extra_allowed_figures=tuple(figures),
    )


if __name__ == "__main__":
    from .decision import Catalog
    from .kb_retrieval import select
    from .narration_client import BAD_DRAFTS, GOOD_DRAFT, Draft

    cat = Catalog.load()
    offers = {o.offer_id: o for o in cat.offers}
    chosen = offers["OFF-BUNDLE-ALL"]
    ev = select(["NO_TECH_SUPPORT", "NO_ONLINE_SECURITY", "MONTH_TO_MONTH"],
                chosen.offer_id)
    ctx = ValidationContext(
        offer_id=chosen.offer_id, offer_name=chosen.name, cost=120.51,
        p_churn=0.99, cltv=5962.0, expected_value=705.82,
        delta_prior=0.14, delta_ci=(0.05, 0.24),
        monthly_charges=95.45, tenure_months=1,
        allowed_evidence_ids=tuple(ev.ids), evidence_text=ev.text,
        other_offer_ids=tuple(o for o in offers if o != chosen.offer_id),
        other_offer_names=tuple(o.name for oid, o in offers.items()
                                if oid != chosen.offer_id))

    print(f"{'fixture':20} {'verdict':8} {'caught by'}")
    print("-" * 74)
    for name, payload in [*BAD_DRAFTS.items(), ("ok", GOOD_DRAFT)]:
        if payload is None:
            print(f"{name:20} {'FAIL':8} V-SCHEMA (not JSON — rejected before this point)")
            continue
        try:
            d = Draft.model_validate(payload)
        except Exception:
            print(f"{name:20} {'FAIL':8} V-SCHEMA (provider schema)")
            continue
        vs = validate(d, ctx)
        codes = ", ".join(sorted({v.code for v in vs})) or "—"
        print(f"{name:20} {'FAIL' if vs else 'PASS':8} {codes}")
