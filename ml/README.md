# Churn retention — the LangGraph, runnable

Nine nodes, one three-way router, one retry cycle, one deterministic fallback, one
human pause. Everything you need to run it is in this folder, including the trained
model, the knowledge base and 34 sample customers.

---

## 1. Install

```bash
python -m venv .venv && source .venv/bin/activate      # optional
pip install -r requirements.txt
```

`langgraph 1.2.11` and `langgraph-checkpoint-sqlite 3.1.1` are pinned. They were
verified to install with **zero changes** to pydantic, numpy, pandas, scikit-learn,
xgboost or google-genai.

## 2. Check your environment first

```bash
python -m src.doctor
```

Reports Python and package versions against the ones the model was pickled with, which
files are present, whether a key is set, and runs one customer through all nine nodes.

**If you see a wall of `InconsistentVersionWarning` and `[attribute] SHAP unavailable`,
that is this:**

```bash
pip install -U "scikit-learn>=1.8.0"
```

The model artifact was pickled with scikit-learn **1.8.0**. On 1.7.1 joblib warns for
every step in the pipeline and SHAP fails with a `ValueError`. The graph deliberately
continues without SHAP rather than failing a whole run over an explanation — so the
result is still correct, it is just missing the "what moved the score" section.

## 3. Run one customer, no API key needed

```bash
python -m src.run_one samples/01_recommended_top_value.json
```

You get every node as it fires, the decision, the offers considered with their
expected values, the note, and the trace. `--provider fake` is the default: a stub
client with no network and no quota.

### The samples — 34 customers, plus 200 for batch

```bash
# run them all, with ranking, a run directory and notes on disk
python -m src.run_batch --input samples/samples_all.jsonl --capacity 10
```

| Outcome | Count | Path |
|---|---|---|
| `recommended` | 16 | `retrieve_evidence → narrate → validate → human_review → persist` |
| `review_no_profitable_offer` | 7 | `explain_no_offer → narrate → validate → human_review → persist` |
| `review_no_applicable_offer` | 4 | same review path |
| `no_action_needed` | 7 | `no_action → persist` — **no model call at all** |

**`src/run_samples.py` was removed in v5.1.** It ran every sample, printed a status
code per line, persisted nothing and asserted nothing — so a run with
`--provider gemini` spent 34 real requests to produce a table. It was doing two jobs
badly. Both now live where they belong:

* **asserting** → `tests/test_samples.py`, which runs every sample through the whole
  graph on `pytest` and fails a build when a policy change moves one;
* **running** → `run_batch --input samples/samples_all.jsonl`, which ranks, writes a
  run directory and keeps every note in `narrations.jsonl`.

`samples/samples_all.jsonl` is generated from the sample files and a test asserts the
two agree, so they cannot drift.

`samples/MANIFEST.json` lists every file with its expected status, risk band, CLTV,
the offers priced for it, and whether that customer actually churned. It is generated
from the files, and `tests/test_samples.py` fails if it goes stale.

Two of the samples are named `13_no_action_below_floor_autopay.json` and
`16_no_action_below_floor_techsup.json`. Both were `recommended` before v5.1, at
expected values of **$0.18 and $0.33**. They are kept deliberately as the worked
example of what the minimum expected value fixed.

### Running the 200-customer file

`samples/customers_200.jsonl` is 200 customer records, one JSON object per line:

```bash
python -m src.run_batch --input samples/customers_200.jsonl --capacity 40 --provider fake
```

No spreadsheet needed. It is a **curated mix** so one run exercises every branch —
120 `recommended`, 72 `no_action_needed`, 5 `review_no_profitable_offer`,
3 `review_no_applicable_offer` — and the records are shuffled, so the order is not
sorted by outcome. In the real population the review cases are only 8 of 1,409, so
this file over-represents them roughly 100× on purpose. For the true distribution:

```bash
python -m src.run_batch --full-base --capacity 200 --provider fake
```

The file has **no ground-truth churn label**, so `actual_churn` is written as `-1`
(unknown) and precision@K is not reported. A `0` there would be a fabricated truth.
`samples/customers_200.README.txt` says all of this next to the file.

To feed your own customers, match the shape — `customer_id`, `cltv`, and a `customer`
object with the 19 account fields. A JSON array works as well as JSONL. Any missing
field is named in the error rather than silently defaulted.

## 4. Run it with the real model — WHERE THE API KEY GOES

Two ways. Pick either.

**A. A `.env` file (recommended — survives between terminals)**

```bash
cp .env.example .env
```

Then open `.env` and paste your key after the `=` sign:

```
GEMINI_API_KEY=AIza...your-real-key...
NARRATION_PROVIDER=gemini
```

`.env` sits in the project root, next to `requirements.txt`. It is read
automatically by `src/narration_client.py` at import time. **Never commit it** —
`.env.example` is the template that gets committed, `.env` is yours.

**B. An environment variable (one terminal only)**

```bash
export GEMINI_API_KEY=AIza...your-real-key...
```

An environment variable always wins over the `.env` file, so you can override for a
single run. Then:

```bash
python -m src.run_one samples/01_recommended_top_value.json --provider gemini
```

**`run_one` and `run_batch` now print which client actually ran**, and warn you in
yellow when it is the stub. If the header says `provider fake`, the note you are
reading is canned text — not model output. Set `NARRATION_PROVIDER=gemini` in `.env`
or pass `--provider gemini`.

Get a key from https://aistudio.google.com/apikey. There is **no key anywhere in the
code** — `os.environ.get("GEMINI_API_KEY")` in `src/narration_client.py` is the only
place it is read, and it raises a clear error if unset.

Model: `gemini-3.5-flash-lite`. No `temperature` is set — Google's Gemini 3 guidance
says changing it can cause looping. `thinking_level` is pinned to `low`, because
thinking tokens are billed and a 120-word note needs no deep reasoning.

Prompt size is about **2,600 tokens** in, ~350 out. One customer, one prompt, always.

## 5. Watch the retry, the fallback and the human pause

```bash
# the model invents a 25% discount, then behaves. V-MONEY catches it and it rewrites.
python -m src.run_one samples/01_recommended_top_value.json --script invented_discount,ok
#   → trace: ... narrate#1 → validate → narrate#2 → validate → human_review → persist

# the model misbehaves twice. The plain template ships instead; the queue never stalls.
python -m src.run_one samples/01_recommended_top_value.json --script invented_discount,wrong_offer
#   → trace: ... narrate#1 → validate → narrate#2 → validate → fallback → ...

# stop at the human pause, then resume in a SEPARATE command
python -m src.run_one samples/01_recommended_top_value.json --interactive
python -m src.run_one samples/01_recommended_top_value.json --resume approve
```

Available `--script` behaviours: `ok`, `invented_discount`, `wrong_offer`,
`fake_citation`, `causal_claim`, `missing_field`, `garbage`.

## 6. Run the batch

```bash
python -m src.run_batch --limit 200 --capacity 40 --provider fake
```

Writes `artifacts/runs/<run_id>/` — `queue.csv` (everyone), `call_list.csv` (tonight's
calls), `narrations.jsonl` (one line per note), `audit.json`.

**Nothing is overwritten.** Each run gets its own folder, which is what makes
`nights_waiting` computable — and `nights_waiting` is a **display column only**, never
added to the expected value. Inflating EV would put a number on the agent's screen
that is not the real expected value.

To pause every customer for real approval instead of auto-approving:

```bash
python -m src.run_batch --limit 20 --interactive        # writes checkpoints.sqlite
```

## 6b. The minimum expected value  (new in v5.1)

`R3_POSITIVE_EV` used to read `EV > 0`. It was written as a **tripwire** — never make
an offer that loses money — and it was quietly doing a second job it was never
designed for: **is this worth an agent's time?** Two questions, two numbers, only one
supplied. A real customer was recommended at an expected value of **$0.18**.

`data/offers.yaml` now carries `min_expected_value_usd: 20.0` and R3 tests against it.

**Why $20, measured two ways.** An agent at ~$35/hour spending ~12 minutes on a call
costs about $7, so $20 is ~3× the labour it consumes. And `python -m src.sensitivity`
shows that halving every `delta_prior` moves only 13% of the top 200 but changes the
eligible population by 1,107 — delta uncertainty lands almost entirely on near-zero-EV
customers, so the floor is also the buffer against the least trustworthy number in the
catalogue.

**Measured consequence** on the 1,409-customer holdout:

| floor | recommended | dropped | EV removed | precision@40 |
|---|---|---|---|---|
| $0 | 752 | 0 | — | 0.700 |
| **$20** | **688** | **64** | **0.46%** | **0.700** |
| $50 | 613 | 139 | 2.48% | 0.700 |
| $100 | 476 | 276 | 10.03% | 0.700 |

Precision@40 does not move at **any** floor up to $200, because the 40th-ranked
customer sits far above it. The floor only removes people an agent was never going to
reach.

Two properties worth knowing:

* **The floor never changes which offer is chosen.** Candidates are ranked by EV
  before the veto, so if the top one fails the minimum, every one below it fails too.
  It can only ever move a customer out of `recommended`.
* **`review_no_profitable_offer` now has two sub-cases** — every offer loses money, or
  the best offer *makes* money but not enough of it. The prompt and the template say
  which, because saying "every offer loses money" about a $19.59 offer is simply
  false.

**`risk_vs_base`** is a new column on every row: `below` / `at` / `above` the 26.54%
portfolio average. It is **display only** — no route, no rank, no EV depends on it.
Low risk is not the same as low value: 0.20 risk × $8,000 lifetime value × 14% is $224
against a $60 offer, which is +$164 and worth a call. The agent should see the flag
and judge; the system should not quietly drop them.

## 6c. The number you can actually defend

```bash
python -m src.eval_random --n 50 --seed 1 --provider gemini
python -m src.eval_random --n 30 --seed 7 --stress          # edge-of-range records
```

Every sample file was hand-picked to exercise a branch, so any claim about note
quality measured on them is circular. This draws a **seeded random** sample from the
held-out fifth — customers nobody curated — runs the whole graph and reports the
violation rate, retry rate, fallback rate and status mix. Quote those four numbers
with the seed and `n`. Notes are written to `artifacts/eval_random/` so you can read
them yourself.

It measures the **narration layer only**. The prediction is validated on the holdout
by the gates in `artifacts/model_registry.json`. Keep those two claims apart.

## 7. Tests

```bash
python -m pytest tests -q          # 254 passing, no API key required
python -m pytest tests/test_graph.py -v
```

`tests/test_graph.py` (33 tests) covers the control flow: each outcome's path, the
retry cycle, the attempt limit, the fallback for all six broken fixtures, the pause
surviving a fresh SQLite connection, and the assertion that the model cannot change a
decision.

---

## What the graph looks like

```
START
  1 score_customer      predict_proba, never predict — a 0/1 label cannot be ranked
  2 attribute           SHAP top-5, labelled model_attribution, never "reason"
  3 extract_levers      9 deterministic field lookups
  4 decide              price · rank by EV · 6 policy rules
  |
  +--> route_by_outcome --------------------+---------------------------+
  |                                         |                           |
  5a retrieve_evidence                  5b explain_no_offer          5c no_action
     (recommended)                         (both review_*)              (no_action_needed)
       \                                    /                             |
        +----------> 6 narrate <-----------+     <-- the only AI step     |
                        |                                                 |
                     7 validate --+ violations & attempts<2 --> narrate   |
                        |         + violations & attempts=2 --> fallback  |
                        | clean                                    |      |
                     8 human_review  interrupt()  <----------------+      |
                        |                                                 |
                     9 persist <------------------------------------------+
                       END
```

`artifacts/graph.mermaid` is generated by the code
(`python -m src.graph`), so the diagram can never disagree with what runs.

### What is deliberately NOT in the graph

The capacity cut. A single customer's node cannot know its own rank — rank is a
property of the group. Ranking lives in `src/run_batch.py`.

### Node 1 re-scores on purpose

The batch runner already scored everyone in order to rank them. Node 1 scores again,
costing about two milliseconds, so the graph is self-contained — you can hand it one
JSON file. It also doubles as a consistency check: node 9 asserts the offer, cost and
expected value are unchanged from what the runner computed, and raises if not.

That assertion earned its place during development. It fired on a **$0.03**
discrepancy, which turned out to be real: `decide()` was reporting `round(p, 4)` while
computing the expected value from the full-precision float, so the same customer could
produce two different expected values. Now the probability is rounded once, at the top
of `decide()`, and used everywhere.

---

## The five validators

Every note — from the model, from the fallback template, in either mode — passes
through `src/validators.py`:

| Check | Rejects |
|---|---|
| `V-OFFER` | naming an offer that was not chosen and not priced for this customer |
| `V-MONEY` | any money or percent figure not in the customer's record or the evidence shown |
| `V-CITE` | a fabricated document id, or a real one that was not shown to this customer |
| `V-CAUSAL` | "will reduce", "guaranteed", "proven to" — no effect here has been measured |
| `V-SCHEMA` | empty, truncated or overlong fields; zero citations |

**A review-mode note may name the offers it rejected.** That is the whole point of it
— "the closest was OFF-CONTRACT-1Y at $113.16, short by $7.50" — so the offers
actually priced for this customer, and their costs, join the permitted set. An offer
that was never priced is still a violation. The test suite caught this: without it, the
validator rejected the truth.

---

## Files

```
.env                      YOUR API KEY GOES HERE  (copy from .env.example)
.env.example              the committed template
src/graph.py              the graph: nodes, routers, edges, state
src/doctor.py             check versions, files, key, then smoke-test  <- run this first
src/run_one.py            run one customer, print every node        <- then this
src/run_batch.py          score everyone, rank, run the graph per customer
src/prompts.py            the two prompt modes and the retry prompt
src/fallback.py           the deterministic note, for all four outcomes
src/validators.py         the five checks
src/narration_client.py   the LLM boundary: Gemini + a fake client
src/decision.py           the four outcomes, EV ranking, 6 policy rules
src/eval_random.py        run N RANDOM holdout customers — the uncurated number
src/kb_retrieval.py       deterministic evidence retrieval, no embeddings
src/levers.py             the 9 levers
src/contracts.py          the data contract and the leakage quarantine
src/attribution.py        SHAP
samples/*.json            34 customers across all four outcomes
samples/MANIFEST.json     what each sample is, and what to expect
samples/customers_200.jsonl  200 customers for batch testing
samples/samples_all.jsonl    the 34 samples as one file, for run_batch --input
tests/test_graph.py       33 control-flow tests
tests/test_samples.py     every sample, through the graph, asserted
artifacts/                the trained model, the registry, the evidence registry
data/                     the dataset, the offer catalog, the knowledge base
```

## Two things to know before demo day

**Rate limits.** Your Gemini free tier allows a limited number of requests per day.
A 200-customer batch makes at most one request per customer that needs a note — and
`no_action_needed` customers make none. Use `--provider fake` for anything that is not
a real demo.

**`auto_approve` is for testing only.** It skips the human pause. Nothing may reach a
real customer without a person clicking approve.

