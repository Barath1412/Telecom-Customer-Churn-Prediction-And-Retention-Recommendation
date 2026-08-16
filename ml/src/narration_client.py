"""
The LLM boundary — the ONLY file in this project that talks to a language model.

WHY THIS FILE IS A PROTOCOL AND NOT JUST A FUNCTION
    Provider quotas, model names and prices change on a weekly cadence; our
    graph must not. Everything downstream depends on `NarrationClient` and on
    `Draft`, never on Gemini. Swapping provider is a config change, and the
    whole test suite runs against `FakeClient` with no API key and no network.

MODEL: gemini-3.5-flash-lite, falling back to gemini-3.1-flash-lite
    (both verified against ai.google.dev/gemini-api/docs/pricing, Aug 2026)

                              input / 1M      output / 1M    free tier
    gemini-3.5-flash-lite     $0.30           $2.50          yes
    gemini-3.1-flash-lite     $0.25           $1.50          yes

    input limit      1,048,576 tokens   (our prompt is ~3.7k -- 0.4% of it)
    output limit        65,536 tokens
    supported        structured outputs, context caching, thinking, batch API
    Rate limits are NOT published in the docs -- read them off the AI Studio
    dashboard for the key you are actually using before demo day.

THE FALLBACK MODEL, AND THE LINE IT MUST NOT CROSS  (added v5.2)

    `gemini-3.1-flash-lite` is tried when the primary model cannot be REACHED.
    It is not tried when the primary model answers badly. That distinction is
    the whole design and it is worth stating plainly:

      * TRANSPORT failure (timeout, 429 quota, 5xx, connection reset, model
        retired) -> retry the primary once, then the fallback model. The two
        models have SEPARATE free-tier quotas, so a 429 on one is very often
        served immediately by the other. This is an AVAILABILITY remedy.

      * CONTENT failure (the model returned JSON that does not match `Draft`,
        or a note that a validator rejects) -> DO NOT change model. The graph
        already has the right remedy: `narrate` runs again with the exact
        validator complaint attached (`prompts.retry_block`). Swapping models
        mid-correction would throw that feedback at a model that never made the
        mistake, and we would learn nothing from either.

      * AUTHENTICATION or MALFORMED REQUEST (401, 403, 400 invalid argument)
        -> give up at once. The same key and the same request will fail on the
        fallback model in exactly the same way; a second call would just be a
        second failure and a slower error message.

    Nothing here can stall the queue. When every attempt fails the result comes
    back with `ok == False`, the graph counts it as a violation, and after two
    attempts `src/fallback.py` ships the deterministic template instead.

    THE NOTE ALWAYS RECORDS WHICH MODEL WROTE IT. `NarrationResult.model` is the
    model that actually produced the text, not the one we asked for first, and
    `usage["attempts"]` carries the trail. A note silently written by a cheaper
    model, with the audit log naming the expensive one, would be a lie in the
    one place that has to be true.

THREE THINGS THAT ARE EASY TO GET WRONG ON THIS MODEL FAMILY

 1. DO NOT SET temperature / top_p / top_k.
    Google's Gemini 3 guidance is explicit: "Changing the temperature (setting
    it below 1.0) may lead to unexpected behavior, such as looping or degraded
    performance". An earlier draft of our plan said temperature=0.2, which is
    the habit from the 2.x era. Those parameters are deliberately absent below.
    Reproducibility comes from the validators, not from a low temperature.

 2. thinking_level IS BILLED.
    "Response pricing is the sum of output tokens and thinking tokens." Writing
    a 120-word retention note needs no deep reasoning, so we pin it to "low".
    Leaving it at the model default would silently multiply the output bill
    across a 200-row nightly queue. This is a cost knob, not a quality knob --
    measure before raising it.

 3. STRUCTURED OUTPUT IS NOT VALIDATION.
    `response_format` guarantees the JSON *parses* and has the right shape. It
    says nothing about whether the money figures are real, the offer is the one
    we chose, or the citations exist. That is what src/validators.py is for.
    Schema-valid and truthful are different properties. Measured: the schema
    catches 2 of the 5 failure modes. Run `python -m src.narration_client`.

Usage:
    from src.narration_client import build_client
    client = build_client()                  # reads NARRATION_PROVIDER / GEMINI_API_KEY
    result = client.narrate(system_prompt, user_block)
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pathlib import Path

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
#  .env support, with no extra dependency.
#  Asked for because "export GEMINI_API_KEY=..." is easy to forget between
#  terminals. A real key must never be committed -- .env is for the developer's
#  machine, .env.example is the template that IS committed.
# --------------------------------------------------------------------------- #
def load_dotenv(path: str | Path | None = None) -> dict[str, str]:
    """
    Reads KEY=VALUE lines from .env at the project root. Existing environment
    variables always win, so `GEMINI_API_KEY=... python -m ...` overrides the file.
    """
    f = Path(path) if path else Path(__file__).resolve().parent.parent / ".env"
    found: dict[str, str] = {}
    if not f.exists():
        return found
    for raw in f.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        found[k] = v
        os.environ.setdefault(k, v)
    return found


load_dotenv()

# ---------------------------------------------------------------------------
# Published prices, USD per 1M tokens. Verified Aug 2026 against
# https://ai.google.dev/gemini-api/docs/pricing -- re-check before quoting a
# cost to anyone. Free tier is $0 on BOTH models, so these only matter past the
# free quota.
# ---------------------------------------------------------------------------
PRICE = {
    "gemini-3.5-flash-lite": {"in": 0.30, "out": 2.50,
                              "batch_in": 0.15, "batch_out": 1.25},
    "gemini-3.1-flash-lite": {"in": 0.25, "out": 1.50,
                              "batch_in": 0.125, "batch_out": 0.75},
}

# Both are overridable without touching code, because a model id is exactly the
# kind of thing that gets renamed or retired between now and demo day.
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL") or "gemini-3.5-flash-lite"
FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL") or "gemini-3.1-flash-lite"
DEFAULT_THINKING = "low"          # minimal | low | medium | high


# ---------------------------------------------------------------------------
# THE OUTPUT CONTRACT
# These four fields are the entire surface the model is allowed to fill.
# Note what is NOT here: no offer_id, no cost, no probability, no expected
# value. Those are written into the graph state by decide() before the model
# runs and are re-asserted afterwards, so the model cannot influence any of
# them even if it tries.
# ---------------------------------------------------------------------------
class Draft(BaseModel):
    summary: str = Field(
        min_length=20, max_length=240,
        description="One sentence a retention agent can read in three seconds: "
                    "who this customer is and why they are on tonight's list. "
                    "State tenure, the monthly charge and the churn risk as "
                    "figures, never as 'new' or 'high'.")
    why: str = Field(
        min_length=40, max_length=700,
        description="Why THIS offer suits THIS customer, grounded only in the "
                    "levers and evidence documents supplied. Describe patterns "
                    "as association, never as cause. No lever codes, no expected "
                    "value, no 'assumed effect' -- plain words only.")
    talk_track: str = Field(
        min_length=40, max_length=700,
        description="DEPENDS ON THE MODE STATED IN THE PROMPT. In recommend mode: "
                    "what the agent says out loud, including what the customer "
                    "gets, what it costs them and for how long. In review mode "
                    "there is NO call -- this is an internal instruction to the "
                    "agent, and it must never address the customer.")
    evidence_ids: list[str] = Field(
        min_length=1, max_length=6,
        description="The document ids from the supplied evidence that this note "
                    "relies on. Ids that were not supplied are rejected.")


@dataclass
class NarrationResult:
    """Everything the graph and the audit log need from one model call."""
    draft: Draft | None
    raw_text: str
    provider: str
    model: str                       # the model that ACTUALLY produced this text
    usage: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    # Every model touched, in order, and how each one ended. Empty on a clean
    # first-attempt success, so it costs nothing to carry.
    attempt_log: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.draft is not None

    @property
    def fallback_used(self) -> bool:
        return self.model != DEFAULT_MODEL and self.model in PRICE

    def cost_usd(self, batch: bool = False) -> float | None:
        """None when the model is unpriced (fake / local) or usage is absent."""
        p = PRICE.get(self.model)
        if not p or not self.usage:
            return None
        tin = self.usage.get("input_tokens") or 0
        tout = (self.usage.get("output_tokens") or 0) + (self.usage.get("thinking_tokens") or 0)
        ki, ko = ("batch_in", "batch_out") if batch else ("in", "out")
        return round(tin / 1e6 * p[ki] + tout / 1e6 * p[ko], 6)


@runtime_checkable
class NarrationClient(Protocol):
    name: str
    model: str

    def narrate(self, system: str, user: str) -> NarrationResult: ...


# ---------------------------------------------------------------------------
# FAILURE CLASSIFICATION
#
# The SDK raises different exception classes across versions and the HTTP status
# is not always on a stable attribute, so this matches on the text as well. That
# is deliberately crude, and the default is deliberately the SAFE one: anything
# unrecognised is treated as fatal, which costs one failed call and a template
# note. Guessing "transient" on an unknown error would burn the whole retry
# budget against a request that can never succeed.
# ---------------------------------------------------------------------------
_TRANSIENT = ("429", "500", "502", "503", "504", "rate limit", "rate_limit",
              "resource exhausted", "resource_exhausted", "quota", "timeout",
              "timed out", "deadline", "unavailable", "overloaded", "internal error",
              "connection", "connectionerror", "temporarily")
_MODEL_GONE = ("404", "not found", "not_found", "is not supported",
               "no longer available", "deprecated", "unsupported model")
_FATAL = ("401", "403", "invalid api key", "api key not valid", "permission denied",
          "unauthenticated", "400", "invalid argument", "invalid_argument")


def classify_error(e: BaseException) -> str:
    """'transient' -> retry then fall back · 'model_gone' -> fall back now · 'fatal' -> stop."""
    blob = f"{type(e).__name__}: {e}".lower()
    # Checked before _TRANSIENT because a 400 message can contain the word "quota".
    if any(m in blob for m in _FATAL):
        return "fatal"
    if any(m in blob for m in _MODEL_GONE):
        return "model_gone"
    if any(m in blob for m in _TRANSIENT):
        return "transient"
    return "fatal"


# ---------------------------------------------------------------------------
# GEMINI
# ---------------------------------------------------------------------------
class GeminiClient:
    """
    Uses the current Interactions API (`client.interactions.create`), not the
    legacy `generate_content`. Install:  pip install -U google-genai
    Key:  export GEMINI_API_KEY=...   (or put it in .env)

    Model order is [model, fallback_model]. Set fallback_model=None to disable
    the second model entirely -- useful when you are deliberately measuring one
    model's behaviour and do not want a silent substitution in your numbers.
    """
    name = "gemini"

    def __init__(self, model: str = DEFAULT_MODEL,
                 fallback_model: str | None = FALLBACK_MODEL,
                 thinking_level: str = DEFAULT_THINKING,
                 api_key: str | None = None, timeout: float = 60.0,
                 retries_per_model: int = 1, backoff_seconds: float = 1.0,
                 _transport: Any = None):
        """
        _transport is a TEST SEAM and nothing else: a callable
        (model, system, user) -> interaction object, used to exercise the
        fallback chain offline. Left as None it builds a real client.
        """
        self.model = model
        self.fallback_model = fallback_model if fallback_model != model else None
        self.thinking_level = thinking_level
        self.timeout = timeout
        self.retries_per_model = max(0, int(retries_per_model))
        self.backoff_seconds = max(0.0, float(backoff_seconds))
        self._transport = _transport
        self._client = None
        if _transport is None:
            try:
                from google import genai
            except ImportError as e:                              # pragma: no cover
                raise ImportError("pip install -U google-genai") from e
            key = api_key or os.environ.get("GEMINI_API_KEY")
            if not key:
                raise RuntimeError("GEMINI_API_KEY is not set")
            self._client = genai.Client(api_key=key)

    # -- one call to one model -------------------------------------------- #
    def _call(self, model: str, system: str, user: str) -> Any:
        if self._transport is not None:
            return self._transport(model, system, user)
        return self._client.interactions.create(
            model=model,
            system_instruction=system,
            input=user,
            response_format={"type": "text",
                             "mime_type": "application/json",
                             "schema": Draft.model_json_schema()},
            # NO temperature / top_p / top_k -- see module docstring, item 1.
            generation_config={"thinking_level": self.thinking_level},
            timeout=self.timeout,
        )

    @property
    def _chain(self) -> list[str]:
        return [m for m in (self.model, self.fallback_model) if m]

    def narrate(self, system: str, user: str) -> NarrationResult:
        log: list[str] = []
        last: NarrationResult | None = None

        for model in self._chain:
            for attempt in range(self.retries_per_model + 1):
                try:
                    it = self._call(model, system, user)
                except Exception as e:                     # network, quota, 5xx, auth
                    kind = classify_error(e)
                    log.append(f"{model}: {kind} — {type(e).__name__}: {e}")
                    last = NarrationResult(
                        None, "", self.name, model, {"attempts": list(log)},
                        error=f"{type(e).__name__}: {e}", attempt_log=list(log))
                    if kind == "fatal":
                        # The same key and the same request fail identically on
                        # the other model. Stop rather than pay for that twice.
                        return last
                    if kind == "transient" and attempt < self.retries_per_model:
                        time.sleep(self.backoff_seconds * (attempt + 1))
                        continue
                    break                                   # next model in the chain

                # A REPLY CAME BACK. From here on it is a CONTENT question, and
                # content is never a reason to change model -- the graph retries
                # this same model with the validator's complaint attached.
                raw = it.output_text or ""
                usage = _usage_dict(getattr(it, "usage", None))
                if log:
                    usage["attempts"] = list(log)
                try:
                    draft = Draft.model_validate_json(raw)
                except Exception as e:
                    log.append(f"{model}: schema — {type(e).__name__}")
                    usage["attempts"] = list(log)
                    return NarrationResult(None, raw, self.name, model, usage,
                                           error=f"V-SCHEMA: {type(e).__name__}: {e}",
                                           attempt_log=list(log))
                return NarrationResult(draft, raw, self.name, model, usage,
                                       attempt_log=list(log))

        # Every model in the chain was unreachable. The graph treats this as a
        # violation; two of them and the deterministic template ships instead.
        return last or NarrationResult(None, "", self.name, self.model,
                                       {"attempts": list(log)},
                                       error="no model in the chain was reachable",
                                       attempt_log=list(log))


def _usage_dict(u: Any) -> dict[str, Any]:
    """Provider usage objects differ and get renamed; never let one crash a run."""
    if u is None:
        return {}
    try:
        d = u.model_dump() if hasattr(u, "model_dump") else dict(u)
    except Exception:
        return {"raw": str(u)}
    def pick(*names):
        for n in names:
            v = d.get(n)
            if isinstance(v, (int, float)):
                return int(v)
        return None
    return {"input_tokens":    pick("input_tokens", "prompt_token_count", "prompt_tokens"),
            "output_tokens":   pick("output_tokens", "candidates_token_count", "completion_tokens"),
            "thinking_tokens": pick("thinking_tokens", "thoughts_token_count", "reasoning_tokens"),
            "total_tokens":    pick("total_tokens", "total_token_count"),
            "raw": d}


# ---------------------------------------------------------------------------
# FAKE — WHAT IT IS FOR. Read this before deciding it is scaffolding.
#
# It is a TEST DOUBLE for the language model: same `narrate(system, user)`
# signature, same `NarrationResult` out, no key, no network, no quota, and the
# same answer every time. It exists for four distinct reasons, and only the
# first is the obvious one.
#
#  1. THE TEST SUITE MUST RUN WITHOUT A KEY.
#     255 tests, every one of them exercising the graph, on a laptop with no
#     internet and in CI where a secret would have to be injected. A suite that
#     needs a paid credential is a suite people stop running.
#
#  2. IT MAKES THE VALIDATORS PROVABLE — THIS IS THE REAL REASON.
#     A test double that only ever behaves correctly tests nothing. The whole
#     purpose of node 7 is the BAD cases: an invented discount, a substituted
#     offer, a fabricated citation, a causal claim, a truncated field. You
#     cannot ask a real model to hallucinate on cue, so the failures are
#     scripted here and each one has a named validator that MUST catch it:
#
#         invented_discount -> V-MONEY     wrong_offer   -> V-OFFER
#         fake_citation     -> V-CITE      causal_claim  -> V-CAUSAL
#         missing_field     -> V-SCHEMA    garbage       -> V-SCHEMA
#         provider_error    -> the transport-failure path
#
#     `--script invented_discount,ok` reproduces the retry cycle on demand;
#     `--script invented_discount,wrong_offer` reproduces the fallback. Those
#     two behaviours are the hardest part of the graph and they would otherwise
#     be untestable.
#
#  3. IT IS THE DEMO AND DEVELOPMENT CLIENT.
#     A 200-customer batch is ~150 requests. Running that repeatedly while
#     building the ranking, the CSV columns or the frontend would burn a free
#     tier for output nobody reads. `--provider fake` costs nothing and is
#     instant, so the LLM is only spent on runs a human is actually going to
#     read. Every runner prints a warning when the stub is active, because a
#     canned note mistaken for model output is the one way this could mislead.
#
#  4. IT PROVES THE BOUNDARY IS REAL.
#     Everything downstream depends on `NarrationClient`, never on Gemini. The
#     fact that the entire graph runs against a 30-line stub is the evidence
#     that swapping provider is a config change, not a rewrite.
#
# WHAT IT IS NOT: a simulator. It does not approximate Gemini's writing. A note
# from FakeClient tells you the PLUMBING works. It tells you nothing about note
# quality -- for that, `python -m src.eval_random --provider gemini`.
# ---------------------------------------------------------------------------
BAD_DRAFTS: dict[str, dict | None] = {
    "invented_discount": {
        "summary": "High-risk fiber customer on a rolling contract.",
        "why": "Customers like this respond well to price relief.",
        "talk_track": "Good news -- I can take 25% off your bill today.",
        "evidence_ids": ["LEVER-060"]},                      # V-MONEY must fire
    "wrong_offer": {
        "summary": "High-risk fiber customer on a rolling contract.",
        "why": "A two-year agreement is the strongest retention play here.",
        "talk_track": "Let's move you to the 2-year contract at 15% off.",
        "evidence_ids": ["LEVER-060"]},                      # V-OFFER must fire
    "fake_citation": {
        "summary": "High-risk fiber customer on a rolling contract.",
        "why": "Support gaps are associated with elevated churn.",
        "talk_track": "I can add Tech Support at no cost for twelve months.",
        "evidence_ids": ["HIST-REASON-099"]},                # V-CITE must fire
    "causal_claim": {
        "summary": "High-risk fiber customer on a rolling contract.",
        "why": "Adding Tech Support will reduce their churn risk by 8 points.",
        "talk_track": "This is proven to keep customers like you with us.",
        "evidence_ids": ["LEVER-060"]},                      # V-CAUSAL must fire
    "missing_field": {
        "summary": "High-risk fiber customer on a rolling contract.",
        "why": "",
        "talk_track": "I can add Tech Support at no cost for twelve months.",
        "evidence_ids": []},                                 # V-SCHEMA must fire
    "garbage": None,                                          # not even JSON
    # Not a bad DRAFT -- a bad CALL. The provider never answered. Scripted so the
    # graph's transport-failure path can be exercised without unplugging a cable.
    "provider_error": None,
}

GOOD_DRAFT = {
    "summary": "Fiber customer, 7 months in, on a rolling month-to-month plan "
               "with no support add-ons.",
    "why": "Two observable gaps put this account in tonight's list: a rolling "
           "contract and no tech-support add-on. In our historical base, "
           "accounts without tech support left at 41.6% against 11.9% for "
           "accounts with it. That is an association in past data, not a "
           "measured effect of adding the service.",
    "talk_track": "I can see you've been with us seven months on fiber. I'm "
                  "able to add our Tech Support package at no cost for the next "
                  "twelve months -- it covers setup and fault calls. Would that "
                  "be useful to you?",
    "evidence_ids": ["LEVER-060"],
}


# A draft that is valid for ANY customer, because it contains no figures and cites
# only POLICY-001 -- the one document retrieved for everybody. GOOD_DRAFT above is
# specific to a tech-support customer: its 41.6% / 11.9% come from LEVER-060, so for a
# customer without that lever V-MONEY and V-CITE correctly reject it. That is the
# validators working, not a bug -- but a test double should not fail for reasons the
# test is not about, so batch runs use this one.
GENERIC_DRAFT = {
    "summary": "Account flagged by tonight's run with actionable gaps on the record.",
    "why": "The recommendation follows from observable attributes on this account and "
           "the policy rules that govern which offers may be made. Patterns referenced "
           "here are associations in past data, not measured effects of any action.",
    "talk_track": "Confirm the account details on screen, then present the offer shown. "
                  "Do not quote any figure that does not appear on this screen.",
    "evidence_ids": ["POLICY-001"],
}

# THE REVIEW-MODE STUB.  (added v5.2)
# GENERIC_DRAFT says "present the offer shown" -- which is correct for a recommend
# note and WRONG for a review one, where the entire outcome is that there is no offer
# and no call. Anyone running `--provider fake` on a review sample read a stub telling
# them to pitch something, which is the exact defect we had just fixed in the real
# prompt. A test double that models the wrong behaviour teaches the wrong behaviour.
GENERIC_REVIEW_DRAFT = {
    "summary": "Account flagged by tonight's run with no offer available to it.",
    "why": "No offer in the catalogue cleared both the eligibility rules and the "
           "minimum value an action has to be worth for this account. The figures "
           "behind that are on screen. Patterns referenced here are associations in "
           "past data, not measured effects of any action.",
    "talk_track": "Internal note — do not call this customer, and do not raise any of "
                  "this with them. Review the priced offers shown on screen and take "
                  "it to a supervisor, or to the owner of the offer catalogue, if you "
                  "believe this account warrants an exception.",
    "evidence_ids": ["POLICY-001"],
}


class FakeClient:
    """
    script=None            -> a well-formed draft, matched to the prompt's MODE
    script=["invented_discount", "ok"]
                           -> first call bad, second call good  (tests the retry)
    script=["garbage", "garbage"]
                           -> both calls fail  (tests the fallback branch)
    script=["provider_error", "ok"]
                           -> the provider is unreachable once, then answers

    IT READS THE MODE OFF THE PROMPT, WHICH IS THE POINT.
    `narrate()` only ever receives two strings, so the stub decides what to return
    the same way a real model does: by reading them. `src/prompts.py` opens every
    user block with `MODE: recommend` or `MODE: review`, so a one-line check picks
    the right shape of note. This keeps the double honest -- if the prompt ever
    stops declaring its mode, the stub degrades to the recommend note and the
    review samples start failing, which is the correct alarm.
    """
    name = "fake"
    model = "fake-1"

    def __init__(self, script: list[str] | None = None):
        self.script = list(script) if script else []
        self.calls: list[tuple[str, str]] = []

    @staticmethod
    def _mode_of(user: str) -> str:
        head = user[:200].lower()
        if "mode: review" in head:
            return "review"
        if "mode: recommend" in head:
            return "recommend"
        return "recommend"

    def narrate(self, system: str, user: str) -> NarrationResult:
        self.calls.append((system, user))
        key = self.script.pop(0) if self.script else "ok"

        if key == "provider_error":
            # Shaped like a real transport failure: no text, no draft, and an
            # error string the graph records as a violation.
            return NarrationResult(
                None, "", self.name, self.model, {"attempts": ["fake: transient"]},
                error="ServerError: 503 The model is overloaded (simulated)",
                attempt_log=["fake: transient — simulated 503"])

        if key == "ok":
            payload = (GENERIC_REVIEW_DRAFT if self._mode_of(user) == "review"
                       else GENERIC_DRAFT)
        else:
            payload = BAD_DRAFTS.get(key, GENERIC_DRAFT)

        if payload is None:                                   # not valid JSON at all
            return NarrationResult(None, "I'm sorry, I can't do that.",
                                   self.name, self.model,
                                   {"input_tokens": 0, "output_tokens": 0},
                                   error="V-SCHEMA: output was not JSON")
        raw = json.dumps(payload)
        usage = {"input_tokens": len(system) // 4 + len(user) // 4,
                 "output_tokens": len(raw) // 4, "thinking_tokens": 0}
        try:
            return NarrationResult(Draft.model_validate_json(raw), raw,
                                   self.name, self.model, usage)
        except Exception as e:
            # A deliberately schema-invalid fixture -- return it as a failure,
            # which is exactly what the graph will see from a real provider.
            return NarrationResult(None, raw, self.name, self.model, usage,
                                   error=f"V-SCHEMA: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
def build_client(provider: str | None = None, **kw) -> NarrationClient:
    """
    NARRATION_PROVIDER=gemini   (default)   real calls, needs GEMINI_API_KEY
    NARRATION_PROVIDER=fake                 tests, demos, CI -- no key needed

    Ollama and Groq are deliberately NOT here yet. Adding one is a ~30-line
    class implementing narrate(); nothing else in the project changes. Ship the
    two that are tested before adding a third that isn't.
    """
    p = (provider or os.environ.get("NARRATION_PROVIDER") or "gemini").lower()
    if p == "fake":
        return FakeClient(**kw)
    if p == "gemini":
        return GeminiClient(**kw)
    raise ValueError(f"unknown NARRATION_PROVIDER {p!r} (gemini | fake)")


if __name__ == "__main__":
    # Smoke test: no key, no network. Shows exactly which failures the SCHEMA
    # catches and which ones it lets straight through -- the latter are the
    # reason src/validators.py has to exist -- then exercises the model chain
    # through the test seam.
    print(f"{'fixture':20} {'schema':8} {'must be caught by'}")
    print("-" * 62)
    expect = {"invented_discount": "V-MONEY", "wrong_offer": "V-OFFER",
              "fake_citation": "V-CITE", "causal_claim": "V-CAUSAL",
              "missing_field": "V-SCHEMA", "garbage": "V-SCHEMA",
              "provider_error": "the transport path (no draft at all)",
              "ok": "-- nothing"}
    for k in list(BAD_DRAFTS) + ["ok"]:
        r = FakeClient(script=[k]).narrate("SYSTEM", "MODE: recommend\nUSER")
        print(f"{k:20} {'PASSES' if r.ok else 'FAILS ':8} {expect[k]}")
    print("\nSchema catches 2 of the 5 draft failure modes. The other 3 are "
          "well-formed JSON that is simply untrue.")

    print(f"\n{'-' * 62}\nMODE-AWARE STUB")
    for mode in ("recommend", "review"):
        d = FakeClient().narrate("S", f"MODE: {mode} — ...").draft
        print(f"  {mode:10} talk_track: {d.talk_track[:64]}...")

    print(f"\n{'-' * 62}\nMODEL CHAIN  {DEFAULT_MODEL} -> {FALLBACK_MODEL}")

    class _Reply:
        def __init__(self, text): self.output_text, self.usage = text, None

    good = json.dumps(GENERIC_DRAFT)

    def scenario(label, behaviour):
        c = GeminiClient(_transport=behaviour, backoff_seconds=0)
        r = c.narrate("S", "MODE: recommend")
        print(f"  {label:34} -> ok={str(r.ok):5} model={r.model}")
        for line in r.attempt_log:
            print(f"       {line[:88]}")

    scenario("primary answers", lambda m, s, u: _Reply(good))

    def quota(m, s, u):
        if m == DEFAULT_MODEL:
            raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")
        return _Reply(good)
    scenario("primary 429, fallback answers", quota)

    def retired(m, s, u):
        if m == DEFAULT_MODEL:
            raise RuntimeError("404 model not found")
        return _Reply(good)
    scenario("primary retired, fallback answers", retired)

    def badkey(m, s, u):
        raise RuntimeError("401 UNAUTHENTICATED: API key not valid")
    scenario("bad key — must NOT try fallback", badkey)

    def down(m, s, u):
        raise RuntimeError("503 UNAVAILABLE: the service is overloaded")
    scenario("both down — template ships", down)