"""
The honest reliability number: run customers NOBODY CHOSE.

    python -m src.eval_random --n 50                    # stub client, free
    python -m src.eval_random --n 50 --provider gemini  # 50 real requests
    python -m src.eval_random --n 30 --seed 7 --stress  # edge-of-range records too

WHY THIS EXISTS
    Every one of the sample files was hand-picked to exercise a branch. Any claim
    about note quality measured on them is circular: they were selected by the same
    person who wrote the prompt. "It works on my 34 examples" is not a measurement,
    and a reviewer will say so.

    This draws a SEEDED RANDOM sample from the held-out fifth -- customers the model
    never trained on and nobody curated -- runs the whole graph, and reports what
    actually happened:

        violation rate   how often the first draft failed a validator
        retry rate       how often it needed a second attempt
        fallback rate    how often it failed twice and shipped the template
        status mix       whether the population lands where the queue expects

    Those four numbers ARE the claim. Quote them with the seed and the sample size.

WHAT THIS DOES NOT MEASURE, AND THE DISTINCTION MATTERS
    It does not validate the PREDICTION. The model is validated on the holdout, by
    the gates in artifacts/model_registry.json (ROC-AUC, Brier, calibration slope,
    calibration parity). This measures the NARRATION LAYER only -- whether the note
    stays faithful to a record it was handed.

    `--stress` goes further and mutates records to the edges of the observed ranges
    (tenure 1 and 72, the cheapest and dearest charges, the largest lifetime value).
    Those are legitimate customers, just where the prompt is least exercised. A
    probability produced for a stressed record is still a real model output, but the
    point of the flag is the WORDING, not the score.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "artifacts" / "eval_random"

B, D, G, Y, R, X = ("\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[31m", "\033[0m")


def _holdout():
    from sklearn.model_selection import train_test_split
    from .contracts import load_and_validate, split_features_target
    df, _ = load_and_validate(str(ROOT / "data" / "Telco_customer_churn.xlsx"))
    feats, y, cltv = split_features_target(df)
    _, idx = train_test_split(np.arange(len(feats)), test_size=0.2, stratify=y,
                              random_state=42)
    return df, feats, cltv, np.sort(idx)


def _stress(row: dict, rng, feats) -> dict:
    """Push ONE field to an edge of its observed range. Never outside it."""
    row = dict(row)
    field = rng.choice(["Tenure Months", "Monthly Charges"])
    col = feats[field]
    row[field] = float(col.min()) if rng.random() < 0.5 else float(col.max())
    if field == "Tenure Months":
        row[field] = int(row[field])
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50, help="how many customers to draw")
    ap.add_argument("--seed", type=int, default=1, help="quote this with the result")
    ap.add_argument("--provider", default=None, help="fake | gemini")
    ap.add_argument("--stress", action="store_true",
                    help="also push one field per record to the edge of its range")
    a = ap.parse_args()

    import os
    from .graph import compile_graph
    from .narration_client import build_client

    provider = (a.provider or os.environ.get("NARRATION_PROVIDER") or "fake").lower()
    client = build_client(provider)
    print(f"{B}provider{X} {provider}   {B}n{X} {a.n}   {B}seed{X} {a.seed}"
          f"{'   stressed' if a.stress else ''}")
    if provider == "fake":
        print(f"{Y}stub client — this measures the PLUMBING, not the model. For the "
              f"real number use --provider gemini.{X}")

    df, feats, cltv, idx = _holdout()
    rng = np.random.default_rng(a.seed)
    pick = rng.choice(idx, size=min(a.n, len(idx)), replace=False)

    app = compile_graph()
    rows, errors = [], []
    for k, i in enumerate(pick, 1):
        cust = feats.iloc[int(i)].to_dict()
        if a.stress:
            cust = _stress(cust, rng, feats)
        cid = df["CustomerID"].iat[int(i)]
        try:
            out = app.invoke(
                {"customer_id": cid, "customer": cust, "cltv": float(cltv.iat[int(i)])},
                {"configurable": {"thread_id": f"eval:{a.seed}:{cid}",
                                  "auto_approve": True, "client": client}})
        except Exception as e:
            errors.append({"customer_id": cid, "error": f"{type(e).__name__}: {e}"})
            continue
        rows.append({
            "customer_id": cid, "status": out["status"],
            "risk_vs_base": out.get("risk_vs_base"),
            "p_churn": out.get("p_churn"), "ev": out.get("ev"),
            "offer_id": out.get("offer_id"),
            "attempts": int(out.get("attempts", 0)),
            "source": out.get("source"),
            "violations": out.get("violations") or [],
            # v5.4: every attempt's verdict, not just the last. Without this a
            # fallback records `[]` and the reason it was rejected is lost.
            "violation_history": out.get("violation_history") or [],
            "llm_model": out.get("llm_model"),
            "draft": out.get("draft"),
        })
        if k % 10 == 0:
            print(f"  ... {k}/{len(pick)}")

    # ---- the four numbers ------------------------------------------------- #
    called = [r for r in rows if r["source"] in ("llm", "fallback_template")]
    n = len(called) or 1
    retried = sum(1 for r in called if r["attempts"] > 1)
    fell_back = sum(1 for r in called if r["source"] == "fallback_template")
    unresolved = sum(1 for r in called if r["violations"])

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = f"seed{a.seed}_n{len(rows)}_{provider}{'_stress' if a.stress else ''}"
    (OUT / f"{stamp}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")

    print(f"\n{B}RESULT{X}  {len(rows)} customers, {len(errors)} errored")
    for s, c in sorted(Counter(r["status"] for r in rows).items()):
        print(f"  {s:30}{c:5d}")
    print(f"\n  {'model was called for':30}{len(called):5d}   "
          f"{D}the rest are no_action_needed and cost nothing{X}")
    print(f"  {'needed a second attempt':30}{retried:5d}   {100*retried/n:5.1f}%")
    print(f"  {'shipped the template instead':30}{fell_back:5d}   {100*fell_back/n:5.1f}%")
    print(f"  {'still had violations at the end':30}{unresolved:5d}   "
          f"{100*unresolved/n:5.1f}%   {R if unresolved else G}"
          f"{'INVESTIGATE' if unresolved else 'clean'}{X}")
    # ---- WHY did anything fail? -------------------------------------------- #
    # This block is the whole point of v5.4. Three seeded runs showed the retry
    # recovering 0 of 7 times and neither the log nor the note could say why.
    rejected = [r for r in rows
                if any(h["outcome"] != "clean" for h in r["violation_history"])]
    if rejected:
        code_count = Counter(c for r in rejected
                             for h in r["violation_history"] for c in h["codes"])
        print(f"\n{B}WHY THEY FAILED{X}  {len(rejected)} customer(s) had at least "
              f"one rejected attempt")
        for code, n in code_count.most_common():
            print(f"  {code:12}{n:4d}")
        print(f"\n{B}THE TRAIL, PER CUSTOMER{X}")
        for r in rejected:
            print(f"\n  {B}{r['customer_id']}{X}  {r['status']}  "
                  f"offer={r['offer_id']}  ended as {r['source']}")
            for h in r["violation_history"]:
                mark = G if h["outcome"] == "clean" else R
                print(f"    attempt {h['attempt']}  {mark}{h['outcome']}{X}"
                      f"  {D}{h.get('model') or '-'}{X}")
                for v in h["violations"][:6]:
                    print(f"        {R}x{X} {v}")

    if errors:
        print(f"\n{R}errors{X}")
        for e in errors[:5]:
            print(f"  {e['customer_id']}  {e['error']}")
    print(f"\nWROTE  artifacts/eval_random/{stamp}.jsonl   "
          f"{D}(every note, so you can read them yourself){X}")
    print(f"{D}Quote this as: n={len(rows)}, seed={a.seed}, provider={provider}.{X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
