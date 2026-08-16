"""
How much do the INVENTED numbers actually matter?

The offer catalog and policy engine contain values nobody measured. Rather than
argue about whether that is acceptable, this measures it: perturb each invented
parameter and report how much the top-K queue changes. A parameter the output is
insensitive to is safe to guess. A parameter the output hinges on must be sourced
from the business before launch.

    python -m src.sensitivity
"""
from __future__ import annotations
import copy, json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .contracts import load_and_validate, split_features_target
from .decision import Catalog, decide

ROOT = Path(__file__).resolve().parent.parent
K = 200


def _queue(cat, df, X, p, cltv):
    recs = [decide(customer_id=df["CustomerID"].iat[i], p_churn=p[i],
                   cltv=float(cltv.iat[i]), row=X.iloc[i], catalog=cat) for i in range(len(df))]
    q = pd.DataFrame([{"cid": r.customer_id, "offer": r.offer_id, "ev": r.ev,
                       "cost": r.cost, "status": r.status} for r in recs])
    q = q[q.status == "recommended"].sort_values("ev", ascending=False)
    return q, set(q.head(K).cid), q.head(K).offer.value_counts().to_dict()


def main():
    reg = json.loads((ROOT / "artifacts" / "model_registry.json").read_text())
    sel = next(m for m in reg["models"] if m["selected"])
    pipe = joblib.load(ROOT / sel["artifact_path"])
    df, _ = load_and_validate(str(ROOT / "data" / "Telco_customer_churn.xlsx"))
    X, y, cltv = split_features_target(df)
    p = pipe.predict_proba(X)[:, 1]

    base = Catalog.load()
    q0, top0, mix0 = _queue(base, df, X, p, cltv)
    print(f"BASELINE  catalog v{base.version}: {len(q0)} eligible, top-{K} queue")
    print(f"  offer mix: {mix0}\n")

    print("=" * 92)
    print(f"SENSITIVITY — how much does the top-{K} queue change when an invented value moves?")
    print("=" * 92)
    print(f"{'parameter perturbed':40}{'eligible':>10}{'Δ elig':>9}{'top-K overlap':>15}{'mix changed':>14}")

    def run(label, mutate):
        c = copy.deepcopy(base)
        mutate(c)
        q, top, mix = _queue(c, df, X, p, cltv)
        ov = len(top & top0)
        print(f"{label:40}{len(q):10d}{len(q)-len(q0):+9d}{ov}/{K} = {100*ov/K:3.0f}%"
              f"{'yes' if mix != mix0 else 'no':>14}")
        return len(q), ov

    print("\n-- offer COSTS (now data-derived, R2 0.9988 -- but test anyway) --")
    for f in [0.5, 0.75, 1.5, 2.0]:
        def mk(f=f):
            return lambda c: [setattr(o, "unit_cost", (o.unit_cost or 0) * f) for o in c.offers]
        run(f"all unit_costs x {f}", mk())

    print("\n-- Δ PRIORS (invented judgment; the biggest unknown) --")
    for f in [0.5, 0.75, 1.5, 2.0]:
        def mk(f=f):
            return lambda c: [setattr(o, "delta_prior", o.delta_prior * f) for o in c.offers]
        run(f"all delta_priors x {f}", mk())

    print("\n-- POLICY THRESHOLDS (all five are invented placeholders) --")
    for v in [0.10, 0.15, 0.25, 0.40]:
        def mk(v=v):
            return lambda c: c.policy.__setitem__("margin_floor_pct", v)
        run(f"margin_floor_pct 0.18 -> {v}", mk())
    for v in [0.05, 0.10, 0.30]:
        def mk(v=v):
            return lambda c: c.policy.__setitem__("max_discount_pct", v)
        run(f"max_discount_pct 0.20 -> {v}", mk())

    print("\n-- REMOVING the offer the counterfactual flagged --")
    run("drop OFF-PROTECT-12",
        lambda c: setattr(c, "offers", [o for o in c.offers if o.offer_id != "OFF-PROTECT-12"]))

    print("\n" + "=" * 92)
    print("HOW TO READ THIS")
    print("=" * 92)
    print("""  A parameter with HIGH top-K overlap is one the queue barely notices -- guessing it
  is low-risk. A parameter with LOW overlap decides who gets contacted, so it must be
  sourced from the business before launch. The overlap column is the whole answer to
  'does inventing these numbers cause problems?'""")


if __name__ == "__main__":
    main()
