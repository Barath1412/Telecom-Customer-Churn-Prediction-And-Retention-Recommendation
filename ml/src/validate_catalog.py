"""
Cross-validate the offer catalog and policy engine AGAINST THE DATASET.

The question this answers: is every offer and every rule GROUNDED in something the
dataset actually contains, or are we asking a language model to write persuasive
prose about actions the data cannot describe?

Ungrounded offers are the single largest hallucination risk in the system. If an
offer's action cannot be expressed as a change to a real dataset field, then:
  * the counterfactual engine cannot estimate its effect,
  * the cost cannot be derived from the price list,
  * the LLM has nothing concrete to anchor on, so it will invent detail.

Seven checks per offer, all objective. Run before any LLM integration.

    python -m src.validate_catalog
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml

from .contracts import load_and_validate, split_features_target
from .levers import extract

ROOT = Path(__file__).resolve().parent.parent

# Which DATASET FIELD does each offer actually mutate, and to what value?
# `None` means the offer's action has no representation in the dataset at all.
# v3: OFF-PROTECT-12, OFF-PLANFIT, OFF-ONBOARD and OFF-RETENTION-CALL were removed
# from the catalog after this validator scored them 6/7, 3/7, 3/7 and 2/7. Their
# entries are gone from here too, so re-adding any of them to offers.yaml will fail
# check 4 with "no action mapping registered" rather than passing silently.
OFFER_ACTION = {
    "OFF-CONTRACT-1Y":   [("Contract", "One year")],
    "OFF-CONTRACT-2Y":   [("Contract", "Two year")],
    "OFF-TECHSUP-12":    [("Tech Support", "Yes")],
    "OFF-SEC-12":        [("Online Security", "Yes")],
    # v3: Device Protection dropped -- it added dP 0.0044 for $60.24. See offers.yaml.
    "OFF-BUNDLE-ALL":    [("Tech Support", "Yes"), ("Online Security", "Yes")],
    "OFF-AUTOPAY":       [("Payment Method", "Credit card (automatic)")],
}

# Which field does each lever READ? Used to confirm the trigger is real.
LEVER_FIELD = {
    "NO_TECH_SUPPORT": "Tech Support", "NO_ONLINE_SECURITY": "Online Security",
    "NO_DEVICE_PROTECTION": "Device Protection", "MONTH_TO_MONTH": "Contract",
    "MANUAL_PAYMENT": "Payment Method", "HIGH_CHARGE_LOW_BUNDLE": "Monthly Charges",
    "NEW_CUSTOMER": "Tenure Months", "FIBER_PREMIUM": "Internet Service",
    "NO_INTERNET": "Internet Service",
}


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def validate():
    df, _ = load_and_validate(str(ROOT / "data" / "Telco_customer_churn.xlsx"))
    X, y, cltv = split_features_target(df)
    base = y.mean()
    reg = json.loads((ROOT / "artifacts" / "model_registry.json").read_text())
    sel = next(m for m in reg["models"] if m["selected"])
    pipe = joblib.load(ROOT / sel["artifact_path"])
    p0 = pipe.predict_proba(X)[:, 1]
    cat = yaml.safe_load((ROOT / "data" / "offers.yaml").read_text())
    levers_per_row = [set(extract(X.iloc[i])) for i in range(len(X))]

    # Derived price list, for the cost check. ONE regression, in ONE place.
    # This block used to import statsmodels and repeat src/derive_costs.py's
    # regression verbatim -- a second copy of the design matrix, a second service
    # list to keep in step, and a second undeclared dependency. It now calls the
    # module that owns that calculation, on the dataframe already loaded above.
    from .derive_costs import implied_price_series
    price = implied_price_series(df)

    results = []
    for o in cat["offers"]:
        oid = o["offer_id"]
        req = o["requires_levers"]
        checks: list[Check] = []

        # 1 -- does every required lever read a real dataset field?
        missing = [l for l in req if LEVER_FIELD.get(l) not in df.columns]
        checks.append(Check("trigger fields exist", not missing,
                            "all lever fields present" if not missing else f"MISSING {missing}"))

        # 2 -- is the triggered segment big enough to matter?
        mask = np.array([set(req).issubset(lv) for lv in levers_per_row]) if req \
            else np.ones(len(X), bool)
        n = int(mask.sum())
        checks.append(Check("segment size >= 100", n >= 100, f"n = {n:,}"))

        # 3 -- does the segment churn MORE than base rate? (else wrong target)
        seg = y.values[mask].mean() if n else 0.0
        checks.append(Check("segment churn > base rate", seg > base,
                            f"{seg*100:.1f}% vs base {base*100:.1f}%"))

        # 4 -- is the ACTION a real field mutation? THE CRITICAL CHECK
        act = OFFER_ACTION.get(oid)
        ok_act = act is not None and all(
            f in df.columns and v in set(df[f].unique()) for f, v in act)
        checks.append(Check("action maps to a real field", bool(ok_act),
                            " + ".join(f"{f} -> {v}" for f, v in act) if act
                            else "NO FIELD -- action not representable in the dataset"))

        # 5 -- can the counterfactual measure it? (only if 4 passes)
        cf = None
        if ok_act and n:
            Xc = X.copy()
            for f, v in act:
                Xc.loc[mask, f] = v
            cf = float((p0 - pipe.predict_proba(Xc)[:, 1])[mask].mean())
        checks.append(Check("counterfactual measurable", cf is not None,
                            f"mean ΔP = {cf:+.4f}" if cf is not None
                            else "cannot be evaluated -- no field to flip"))

        # 6 -- does the model agree the action reduces risk?
        checks.append(Check("model says risk falls", cf is not None and cf > 0.01,
                            f"ΔP {cf:+.4f} > 0.01" if cf is not None else "unmeasurable"))

        # 7 -- is the cost traceable to the derived price list?
        if o["cost_type"] == "pct_of_annual":
            cost_ok, cost_note = True, "% of the customer's real Monthly Charges"
        elif oid == "OFF-AUTOPAY":
            # A billing CREDIT, not a service. Its cost is true by construction
            # ($5/mo x 12) and cannot come from the service price list.
            cost_ok = abs(o["unit_cost"] - 60.0) < 0.01
            cost_note = f"${o['unit_cost']:.2f} by construction ($5/mo credit x 12)"
        elif act:
            want = sum(price.get(f, 0) for f, _ in act) * 12
            cost_ok = abs(o["unit_cost"] - want) / max(want, 1) < 0.05
            cost_note = f"${o['unit_cost']:.2f} vs derived ${want:.2f}"
        else:
            cost_ok, cost_note = False, f"${o['unit_cost']:.2f} INVENTED -- no derivation"
        checks.append(Check("cost traceable to data", cost_ok, cost_note))

        results.append((oid, o, checks, n, seg, cf))
    return results, base


def main():
    results, base = validate()
    print("OFFER CATALOG CROSS-VALIDATION AGAINST THE DATASET")
    print("=" * 100)
    print(f"{'offer_id':22}{'1 fld':>6}{'2 n':>5}{'3 chn':>6}{'4 act':>6}{'5 cf':>5}"
          f"{'6 dir':>6}{'7 cost':>7}{'score':>8}   verdict")
    print("-" * 100)
    tally = {"GROUNDED": [], "PARTIAL": [], "UNGROUNDED": []}
    for oid, o, checks, n, seg, cf in results:
        marks = "".join("  Y  " if c.passed else "  .  " for c in checks)
        score = sum(c.passed for c in checks)
        critical = checks[3].passed          # action maps to a real field
        verdict = ("GROUNDED" if score == 7 else
                   "PARTIAL" if critical else "UNGROUNDED")
        tally[verdict].append(oid)
        cells = "".join(f"{'Y' if c.passed else '.':>6}" for c in checks)
        print(f"{oid:22}{cells}{score:>6}/7   {verdict}")
    print()
    for k, v in tally.items():
        if v:
            print(f"  {k:11} {len(v)}  {v}")

    print("\n" + "=" * 100)
    print("DETAIL FOR EVERY OFFER THAT IS NOT FULLY GROUNDED")
    print("=" * 100)
    for oid, o, checks, n, seg, cf in results:
        if all(c.passed for c in checks):
            continue
        print(f"\n{oid}  ({o['name']})")
        for c in checks:
            if not c.passed:
                print(f"   FAIL  {c.name:28} {c.detail}")
    print("\n" + "=" * 100)
    print("CHECK LEGEND")
    print("=" * 100)
    print("""  1 trigger fields exist        the levers that fire this offer read real columns
  2 segment size >= 100         enough customers for the offer to be meaningful
  3 segment churn > base rate   we are targeting people who actually leave more
  4 action maps to a real field CRITICAL -- can the offer's action be expressed as a
                                change to a dataset column? If not, nothing downstream
                                can verify, price, or explain it.
  5 counterfactual measurable   follows from 4
  6 model says risk falls       the model agrees flipping that field lowers risk
  7 cost traceable to data      unit cost derived from the implied price list""")


if __name__ == "__main__":
    main()
