"""
Build tonight's retention queue.

Score everyone -> attribute -> extract levers -> rank offers by EV -> policy
veto -> fairness snapshot -> capacity cut -> assign treatment/control -> write
an auditable queue.

Run:  python -m src.queue_build --capacity 200
"""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .contracts import PROTECTED, load_and_validate, split_features_target
from .decision import Catalog, STATUSES, decide
from .levers import extract_frame, describe

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts"
# CONTROL_FRACTION — audited against the power requirement, not guessed.
#   Established need: n_control >= 50 per (segment, offer) for RMSE 0.053 on Delta.
#   Three offers dominate the mix, so days-to-n=50 per offer:
#       5% at 200/day -> 15 days      10% at 200/day ->  8 days   <- chosen
#      10% at  40/day -> 38 days      20% at 200/day ->  4 days
#   10% reaches usable estimates in ~8 days at 200/day. The binding constraint is
#   AGENT CAPACITY, not the holdout size, so raising the fraction buys little and
#   costs retained customers.
CONTROL_FRACTION = 0.10          # never contacted. the only real proof.


def assign_arm(customer_id: str, experiment_id: str = "retention_2026Q3") -> str:
    """Stable hash -> reproducible, cannot drift between runs."""
    h = hashlib.sha256(f"{customer_id}:{experiment_id}".encode()).hexdigest()
    return "control" if (int(h[:8], 16) % 100) < CONTROL_FRACTION * 100 else "treatment"


def main(capacity: int = 200, out_prefix: str = "queue", holdout_only: bool = True):
    """
    holdout_only=True  -> build and EVALUATE the queue on the 1,409 rows the
                          model never saw. Any precision@K quoted from a queue
                          built over training rows is optimistic and must not be
                          reported. This is the same evaluation-leak trap that
                          inflated the notebooks; do not reintroduce it here.
    holdout_only=False -> score the whole base, as production would. Then the
                          `actual_churn` column is NOT a valid scoreboard.
    """
    from sklearn.model_selection import train_test_split

    reg = json.loads((ARTIFACTS / "model_registry.json").read_text())
    sel = next(m for m in reg["models"] if m["selected"])
    pipe = joblib.load(ROOT / sel["artifact_path"])

    df, _ = load_and_validate(str(ROOT / "data" / "Telco_customer_churn.xlsx"))
    X, y, cltv = split_features_target(df)

    if holdout_only:
        # identical split to train.py: same seed, same stratification
        _, idx = train_test_split(np.arange(len(X)), test_size=0.2,
                                  stratify=y, random_state=42)
        idx = np.sort(idx)
        df, X, y, cltv = df.iloc[idx], X.iloc[idx], y.iloc[idx], cltv.iloc[idx]
        capacity = max(1, round(capacity * 0.2))     # scale K to the smaller base
        print(f"EVALUATION MODE: held-out only -- {len(X)} unseen customers, "
              f"K scaled to {capacity}\n")

    p = pipe.predict_proba(X)[:, 1]
    assert p.max() < 1.0 and p.min() > 0.0, "probability asserts certainty"

    catalog = Catalog.load()
    print(f"catalog v{catalog.version}: {len(catalog.offers)} offers | "
          f"model {sel['model_name']} {sel['version']} (ROC-AUC "
          f"{sel['metrics']['roc_auc']:.4f})\n")

    recs = []
    for i in range(len(df)):
        recs.append(decide(customer_id=df["CustomerID"].iat[i], p_churn=p[i],
                           cltv=float(cltv.iat[i]), row=X.iloc[i], catalog=catalog))

    q = pd.DataFrame([r.to_row() for r in recs])
    q["actual_churn"] = y.values                     # ground truth, for evaluation only
    q["arm"] = [assign_arm(c) for c in q["customer_id"]]
    q["lever_summary"] = [describe(r.levers) for r in recs]

    # ---------------- funnel ----------------
    n = len(q)
    elig = q[q.status == "recommended"]
    print("DECISION FUNNEL")
    print(f"  scored                       {n:6d}")
    for st in STATUSES:
        print(f"  {st:28} {(q.status == st).sum():6d}")

    # ---------------- capacity cut ----------------
    ranked = elig.sort_values("ev", ascending=False).reset_index(drop=True)
    today = ranked.head(capacity).copy()
    contact = today[today.arm == "treatment"]
    control = today[today.arm == "control"]

    print(f"\nCAPACITY CUT  K={capacity}")
    print(f"  in queue today               {len(today):6d}")
    print(f"    -> contacted (treatment)   {len(contact):6d}")
    print(f"    -> held back (control)     {len(control):6d}   never contacted, tracked")
    print(f"  precision@{capacity} (actual churn) {today.actual_churn.mean():.4f}"
          f"   vs base rate {y.mean():.4f}"
          f"   = {today.actual_churn.mean()/y.mean():.2f}x lift")
    print(f"  churners captured            {int(today.actual_churn.sum()):6d}"
          f" of {int(y.sum())}  (recall {today.actual_churn.sum()/y.sum():.3f})")

    # ---------------- economics ----------------
    spend = contact.cost.sum()
    ev_total = contact.ev.sum()
    print(f"\nECONOMICS (treatment arm only)")
    print(f"  offer spend                  {spend:10,.2f}")
    print(f"  expected value               {ev_total:10,.2f}")
    print(f"  CLTV at risk in queue        {(today.p_churn*today.cltv).sum():10,.2f}")
    print(f"  mean cost per contact        {contact.cost.mean():10,.2f}")

    print(f"\nOFFER MIX  (top {capacity})")
    mix = today.groupby("offer_id").agg(
        n=("offer_id", "size"), mean_ev=("ev", "mean"),
        mean_cost=("cost", "mean"), mean_p=("p_churn", "mean")).sort_values("n", ascending=False)
    print(mix.round(2).to_string())

    # ---------------- allocation fairness ----------------
    # The check the architecture doc specified: disparate impact on WHO RECEIVES
    # offers and of what value -- not on the score. Score parity would be the
    # wrong test, since seniors genuinely churn at 41.7% vs 23.6%.
    print(f"\nALLOCATION PARITY  (downstream fairness -- offers, not scores)")
    aud = df[PROTECTED].copy()
    aud["in_queue"] = df["CustomerID"].isin(set(today.customer_id)).values
    aud["cost"] = df["CustomerID"].map(dict(zip(today.customer_id, today.cost))).fillna(0).values
    for attr in PROTECTED:
        g = aud.groupby(attr).agg(n=("in_queue", "size"), queued=("in_queue", "sum"),
                                  mean_offer_value=("cost", "mean"))
        g["queue_rate"] = (g.queued / g.n).round(4)
        print(f"  {attr}:")
        for k, r in g.iterrows():
            print(f"    {str(k):8} n={int(r.n):5d}  queued={int(r.queued):4d}"
                  f"  rate={r.queue_rate:.4f}  mean offer value={r.mean_offer_value:6.2f}")

    # ---------------- write ----------------
    ARTIFACTS.mkdir(exist_ok=True)
    cols = ["customer_id", "arm", "p_churn", "risk_vs_base", "cltv", "monthly_charges",
            "tenure_months", "offer_id", "offer_name", "cost", "delta_prior", "ev",
            "min_ev_floor", "lever_summary",
            "levers", "considered", "vetoed", "status", "catalog_version", "actual_churn"]
    today[cols].to_csv(ARTIFACTS / f"{out_prefix}_top{capacity}.csv", index=False)
    q[cols].to_csv(ARTIFACTS / f"{out_prefix}_full.csv", index=False)

    audit = {
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "model": {k: sel[k] for k in ("model_name", "version", "artifact_path")},
        "model_roc_auc": sel["metrics"]["roc_auc"],
        "catalog_version": catalog.version,
        "policy": catalog.policy,
        "capacity": capacity,
        "control_fraction": CONTROL_FRACTION,
        "funnel": {
            "scored": int(n),
            **{st: int((q.status == st).sum()) for st in STATUSES},
            "queued_today": int(len(today)),
            "treatment": int(len(contact)), "control": int(len(control)),
        },
        "economics": {"offer_spend": round(float(spend), 2),
                      "expected_value": round(float(ev_total), 2)},
        "precision_at_capacity": round(float(today.actual_churn.mean()), 4),
        "offer_mix": {k: int(v) for k, v in today.offer_id.value_counts().items()},
        "delta_priors_are_hypotheses": True,
        "delta_source": "business_judgment_v1 -- replace with measured effects "
                        "once the control arm returns outcomes",
    }
    (ARTIFACTS / f"{out_prefix}_audit.json").write_text(json.dumps(audit, indent=2))

    print(f"\nWROTE")
    print(f"  artifacts/{out_prefix}_top{capacity}.csv")
    print(f"  artifacts/{out_prefix}_full.csv")
    print(f"  artifacts/{out_prefix}_audit.json")
    return today, q


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--capacity", type=int, default=200)
    ap.add_argument("--out", default="queue")
    ap.add_argument("--full-base", action="store_true",
                    help="score all 7,043 (production mode). precision@K then NOT valid.")
    a = ap.parse_args()
    main(a.capacity, a.out, holdout_only=not a.full_base)
