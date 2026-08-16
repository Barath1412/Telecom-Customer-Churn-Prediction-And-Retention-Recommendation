"""
The batch runner. Everything the graph cannot do, because it needs all customers at once.

    python -m src.run_batch --limit 200 --capacity 40 --provider fake --auto-approve

WHAT THIS DOES AND THE GRAPH DOES NOT
    Ranking. A single customer's node cannot know its own rank -- rank is a property
    of the group. So: score everyone, sort by expected value, and only then run the
    graph once per customer, one at a time.

RUN HISTORY, AND WHY IT MATTERS MORE THAN IT LOOKS
    Every run writes to artifacts/runs/<run_id>/ and NOTHING is overwritten. Before
    v5 the queue files were replaced each night, which meant:
      * the same data produced the same top 40 every night, forever -- measured, 40
        of 40 identical -- so customers at rank 41+ were never contacted, ever;
      * R4_COOLDOWN and R5_ONE_PER_WINDOW could never be evaluated, because nothing
        recorded what we did yesterday.
    Keeping history fixes both. `nights_waiting` counts consecutive previous runs in
    which a customer was recommended and NOT actioned.

    `nights_waiting` is VISIBLE ONLY. It is a column, never a bonus added to the
    expected value. Inflating EV would put a number on the agent's screen that is not
    the real expected value, and they would be reading a fiction.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "artifacts" / "runs"


# --------------------------------------------------------------------------- #
def _load_population(limit: int | None, holdout_only: bool, input_path: str | None = None):
    """
    Two sources, one shape.

    input_path=None                 read the spreadsheet, take the held-out fifth
    input_path=*.jsonl / *.json     read customer records straight from a file

    The JSONL route is the one to use for a demo: it needs no spreadsheet, no
    train/test split and no scikit-learn split reproducibility -- just records. It
    has no ground-truth `Churn Value`, so `actual_churn` comes out as -1 (unknown)
    rather than a fabricated 0, and precision@K is not reported for it.
    """
    if input_path:
        return _load_from_file(input_path, limit)

    from sklearn.model_selection import train_test_split
    from .contracts import load_and_validate, split_features_target
    df, _ = load_and_validate(str(ROOT / "data" / "Telco_customer_churn.xlsx"))
    X, y, cltv = split_features_target(df)
    if holdout_only:
        _, idx = train_test_split(np.arange(len(X)), test_size=0.2, stratify=y,
                                  random_state=42)
        idx = np.sort(idx)
        df, X, y, cltv = df.iloc[idx], X.iloc[idx], y.iloc[idx], cltv.iloc[idx]
    if limit:
        df, X, y, cltv = df.head(limit), X.head(limit), y.head(limit), cltv.head(limit)
    return df, X, y, cltv


def _load_from_file(path: str, limit: int | None):
    """
    Accepts either JSONL (one record per line) or a JSON array. Each record needs
    `customer_id`, `cltv` and a `customer` object holding the raw account fields.
    """
    from .contracts import NOMINAL, NUMERIC, ORDINAL
    f = Path(path)
    if not f.is_absolute():
        f = ROOT / path
    if not f.exists():
        raise FileNotFoundError(f"no such input file: {f}")

    text = f.read_text().strip()
    if text.startswith("["):
        records = json.loads(text)
    else:
        records = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    if limit:
        records = records[:limit]

    cols = [*NOMINAL, *ORDINAL, *NUMERIC]
    rows, ids, cltvs = [], [], []
    for i, r in enumerate(records):
        for key in ("customer_id", "cltv", "customer"):
            if key not in r:
                raise ValueError(f"record {i} is missing {key!r}")
        missing = [c for c in cols if c not in r["customer"]]
        if missing:
            raise ValueError(f"record {i} ({r['customer_id']}) is missing account "
                             f"fields: {missing}")
        rows.append({c: r["customer"][c] for c in cols})
        ids.append(r["customer_id"])
        cltvs.append(float(r["cltv"]))

    X = pd.DataFrame(rows)
    df = pd.DataFrame({"CustomerID": ids})
    # -1 means "we do not know". A 0 here would be a fabricated ground truth, and
    # precision@K computed against it would be a lie.
    y = pd.Series([-1] * len(X), name="Churn Value")
    print(f"input: {f.name} — {len(X)} customers, no ground truth "
          f"(precision@K not reported)")
    return df, X, y, pd.Series(cltvs, name="CLTV")


def _nights_waiting() -> dict[str, int]:
    """
    Consecutive previous runs (most recent first) in which a customer appeared as
    `recommended` and was not actioned. Stops counting at the first run where they
    were actioned or absent.
    """
    if not RUNS.exists():
        return {}
    runs = sorted((p for p in RUNS.iterdir() if p.is_dir()), reverse=True)
    counts: dict[str, int] = {}
    settled: set[str] = set()
    for r in runs:
        f = r / "queue.csv"
        if not f.exists():
            continue
        q = pd.read_csv(f)
        if "actioned" not in q.columns:
            q["actioned"] = False
        for cid, status, actioned in zip(q.customer_id, q.status,
                                         q.actioned.fillna(False)):
            if cid in settled:
                continue
            if bool(actioned):
                settled.add(cid)
            elif status == "recommended":
                counts[cid] = counts.get(cid, 0) + 1
    return counts


# --------------------------------------------------------------------------- #
def main(limit: int | None = 200, capacity: int = 40, provider: str | None = None,
         auto_approve: bool = True, holdout_only: bool = True,
         run_id: str | None = None, quiet: bool = False,
         input_path: str | None = None) -> dict:
    from .decision import STATUSES, Catalog, decide
    from .graph import _model, compile_graph
    from .levers import describe, extract

    run_id = run_id or datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")
    out_dir = RUNS / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    pipe, sel = _model()
    catalog = Catalog.load()
    df, X, y, cltv = _load_population(limit, holdout_only, input_path)
    p = pipe.predict_proba(X)[:, 1]

    # ---- phase 1: score and decide for EVERYONE (cheap, no LLM) ----------
    rows = []
    for i in range(len(df)):
        rec = decide(customer_id=df["CustomerID"].iat[i], p_churn=float(p[i]),
                     cltv=float(cltv.iat[i]), row=X.iloc[i], catalog=catalog)
        rows.append({"customer_id": rec.customer_id, "status": rec.status,
                     "p_churn": rec.p_churn, "cltv": rec.cltv,
                     "monthly_charges": rec.monthly_charges,
                     "tenure_months": rec.tenure_months,
                     "offer_id": rec.offer_id, "offer_name": rec.offer_name,
                     "cost": rec.cost, "ev": rec.ev,
                     # DISPLAY ONLY. It changes no route, no rank and no EV. It is
                     # here because "below average risk" and "not worth acting on"
                     # are different facts and the queue was showing neither.
                     "risk_vs_base": rec.risk_vs_base,
                     "min_ev_floor": rec.min_ev_floor,
                     "levers": "|".join(rec.levers),
                     "lever_summary": describe(rec.levers),
                     "actual_churn": int(y.iat[i]), "actioned": False})
    q = pd.DataFrame(rows)

    # ---- phase 2: THE PART THE GRAPH CANNOT DO -- rank across everyone ----
    waiting = _nights_waiting()
    q["nights_waiting"] = q.customer_id.map(waiting).fillna(0).astype(int)
    q = q.sort_values(["status", "ev"], ascending=[True, False])
    q = pd.concat([q[q.status == "recommended"].sort_values("ev", ascending=False),
                   q[q.status != "recommended"]]).reset_index(drop=True)
    q["rank"] = np.where(q.status == "recommended",
                         (q.status == "recommended").cumsum(), 0)

    # ---- phase 3: one graph run per customer ------------------------------
    # The whole population goes through the graph. `capacity` decides who is
    # CONTACTED, not who is processed -- every customer gets a stored decision and
    # a note, so nobody is silently dropped.
    app = compile_graph()          # no checkpointer: auto-approve, no pause possible
    if not auto_approve:
        from langgraph.checkpoint.sqlite import SqliteSaver
        cm = SqliteSaver.from_conn_string(str(out_dir / "checkpoints.sqlite"))
        cp = cm.__enter__()
        app = compile_graph(cp)
    else:
        cm = None

    # RESOLVE THE PROVIDER ONCE, HERE, AND SAY WHICH ONE RAN.
    # Leaving it unresolved meant `audit.json` recorded the string "env-default",
    # which tells nobody afterwards whether those notes came from a model or from a
    # stub. It is the first question anyone asks of a saved run.
    import os
    from .narration_client import build_client
    provider = (provider or os.environ.get("NARRATION_PROVIDER") or "fake").lower()
    narrations = out_dir / "narrations.jsonl"
    client = build_client(provider)
    if not quiet:
        key = os.environ.get("GEMINI_API_KEY")
        print(f"provider {provider}"
              + (f"   key …{key[-4:]}" if key else "   (no GEMINI_API_KEY set)"))
        if provider == "fake":
            print("  NOTE: stub client — every note below is canned text, not model "
                  "output. Set NARRATION_PROVIDER=gemini or pass --provider gemini.")

    processed, failed = 0, []
    for r in q.itertuples():
        pos = int(np.where(df["CustomerID"].values == r.customer_id)[0][0])
        cust = X.iloc[pos].to_dict()
        cfg = {"configurable": {
            "thread_id": f"{run_id}:{r.customer_id}",
            "auto_approve": auto_approve,
            "client": client,
            "narrations_path": str(narrations),
            "expected_decision": {"offer_id": r.offer_id if isinstance(r.offer_id, str)
                                  else None, "cost": r.cost, "ev": r.ev},
        }}
        try:
            app.invoke({"customer_id": r.customer_id, "customer": cust,
                        "cltv": float(r.cltv)}, cfg)
            processed += 1
        except Exception as e:
            failed.append({"customer_id": r.customer_id,
                           "error": f"{type(e).__name__}: {e}"})
        if not quiet and processed % 25 == 0:
            print(f"  ... {processed}/{len(q)}")

    if cm is not None:
        cm.__exit__(None, None, None)

    # ---- phase 4: write the run ------------------------------------------
    cols = ["rank", "customer_id", "status", "risk_vs_base", "nights_waiting",
            "p_churn", "cltv", "monthly_charges", "tenure_months",
            "offer_id", "offer_name", "cost", "ev", "min_ev_floor",
            "levers", "lever_summary", "actual_churn", "actioned"]
    q[cols].to_csv(out_dir / "queue.csv", index=False)
    contact = q[(q.status == "recommended") & (q["rank"] <= capacity)]
    contact[cols].to_csv(out_dir / "call_list.csv", index=False)

    funnel = {s: int((q.status == s).sum()) for s in STATUSES}
    audit = {
        "run_id": run_id, "run_utc": datetime.now(timezone.utc).isoformat(),
        "model": {k: sel[k] for k in ("model_name", "version", "artifact_path")},
        "model_roc_auc": sel["metrics"]["roc_auc"],
        "catalog_version": catalog.version,
        "population": len(q), "holdout_only": holdout_only,
        "input": input_path or "data/Telco_customer_churn.xlsx",
        "ground_truth_available": bool((q.actual_churn >= 0).all()),
        "funnel": funnel, "capacity": capacity,
        "call_list": int(len(contact)),
        "graph_runs_ok": processed, "graph_runs_failed": failed,
        "provider": provider, "auto_approve": auto_approve,
        "min_expected_value_usd": float(catalog.policy.get("min_expected_value_usd", 0)),
        "nights_waiting_is_display_only": True,
    }
    (out_dir / "audit.json").write_text(json.dumps(audit, indent=2))

    if not quiet:
        print(f"\nRUN {run_id}   population {len(q)}   graph runs {processed} ok, "
              f"{len(failed)} failed")
        for s in STATUSES:
            print(f"  {s:28} {funnel[s]:5d}")
        print(f"  {'call list (capacity ' + str(capacity) + ')':28} {len(contact):5d}")
        if len(q[q.nights_waiting > 0]):
            print(f"  {'customers waiting 1+ nights':28} "
                  f"{int((q.nights_waiting > 0).sum()):5d}   (display only)")
        src = _source_mix(narrations)
        if src:
            print(f"\nNOTE SOURCES  {src}")
        print(f"\nWROTE  artifacts/runs/{run_id}/")
        for f in sorted(out_dir.iterdir()):
            print(f"  {f.name}")
    return audit


def _source_mix(path: Path) -> dict:
    if not path.exists():
        return {}
    mix: dict[str, int] = {}
    for line in path.read_text().splitlines():
        try:
            s = json.loads(line).get("source") or "unknown"
        except Exception:
            continue
        mix[s] = mix.get(s, 0) + 1
    return mix


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200,
                    help="how many customers to process (default 200)")
    ap.add_argument("--capacity", type=int, default=40,
                    help="how many the team can call tonight")
    # DEFAULT IS None, NOT "fake" -- the same bug that was fixed in run_one and left
    # in place here. "fake" silently overrode NARRATION_PROVIDER=gemini from .env, so
    # a real key produced canned stub text while the audit recorded provider "fake".
    # The environment now wins unless you pass the flag.
    ap.add_argument("--provider", default=None,
                    help="fake | gemini   (default: NARRATION_PROVIDER from .env, "
                         "else fake. fake needs no API key)")
    ap.add_argument("--interactive", action="store_true",
                    help="pause at human_review instead of auto-approving")
    ap.add_argument("--full-base", action="store_true",
                    help="score all 7,043 instead of the held-out fifth")
    ap.add_argument("--input", default=None,
                    help="a .jsonl or .json file of customer records, e.g. "
                         "samples/customers_200.jsonl. Skips the spreadsheet entirely.")
    ap.add_argument("--run-id", default=None)
    a = ap.parse_args()
    main(limit=a.limit, capacity=a.capacity, provider=a.provider,
         auto_approve=not a.interactive, holdout_only=not a.full_base,
         run_id=a.run_id, input_path=a.input)
