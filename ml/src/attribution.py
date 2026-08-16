"""
SHAP attribution — what drove the MODEL's prediction.

READ THIS BEFORE USING THE OUTPUT
SHAP explains the model, not the customer, and it is NOT causal:

  * `Contract = Month-to-month` will dominate almost every attribution. That does
    NOT mean moving someone to a 2-year contract lowers their risk. Customers who
    already intended to stay are the ones who chose long contracts. The 15x churn
    gap between contract types is mostly selection, not treatment.
  * Attribution is therefore for TRIAGE and TRANSPARENCY ("why did the model flag
    this person?"), never for choosing an offer. Offers are chosen by the lever
    extractor + expected value, which are separate and deterministic.
  * Every field this module emits is named `model_attribution`, never `reason`.

For a per-customer estimate of "what happens if we change this", use
`src.counterfactual` instead — that re-scores the model under a hypothetical
feature change, which is a different and more honest question.
"""
from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "artifacts" / "model_registry.json"

DISCLAIMER = (
    "Model attribution, not customer motive. These values show what drove the "
    "model's prediction. They are not causal and are not the customer's stated "
    "reason for leaving."
)


@lru_cache(maxsize=1)
def _load():
    import shap
    meta = json.loads(REGISTRY.read_text())
    sel = next(m for m in meta["models"] if m["selected"])
    twin = joblib.load(ROOT / sel["artifact_path"].replace(".joblib", "_attribution.joblib"))
    pre, clf = twin.named_steps["pre"], twin.named_steps["clf"]
    names = list(pre.get_feature_names_out())
    return pre, clf, names, shap.TreeExplainer(clf), sel


def _pretty(name: str, raw_row: pd.Series) -> str:
    """`Contract_Two year` -> `Contract = Two year`; numerics get their value."""
    for col in raw_row.index:
        if name == col:
            v = raw_row[col]
            return f"{col} = {v:.2f}" if isinstance(v, float) else f"{col} = {v}"
        if name.startswith(col + "_"):
            return f"{col} = {name[len(col) + 1:]}"
    return name


def attribute(X: pd.DataFrame, top_k: int = 5) -> list[dict]:
    """One dict per row: top-k signed contributions in log-odds space."""
    pre, clf, names, explainer, sel = _load()
    Z = pre.transform(X)
    sv = explainer.shap_values(Z)
    if isinstance(sv, list):            # older shap returns a list per class
        sv = sv[1]
    sv = np.asarray(sv)
    if sv.ndim == 3:                    # (n, features, classes)
        sv = sv[:, :, 1]

    out = []
    for i in range(len(X)):
        vals = sv[i]
        order = np.argsort(-np.abs(vals))[:top_k]
        out.append({
            "model_attribution": [
                {"feature": _pretty(names[j], X.iloc[i]),
                 "contribution": round(float(vals[j]), 4),
                 "direction": "increases_risk" if vals[j] > 0 else "decreases_risk"}
                for j in order
            ],
            "attribution_disclaimer": DISCLAIMER,
            "attribution_basis": "shap_treeexplainer_log_odds",
            "attribution_model": f"{sel['model_name']} {sel['version']} (uncalibrated twin)",
        })
    return out


def global_importance(X: pd.DataFrame, sample: int = 2000) -> pd.DataFrame:
    """Mean |SHAP| across a sample — the portfolio view, for the summary screen."""
    pre, clf, names, explainer, _ = _load()
    Xs = X.sample(min(sample, len(X)), random_state=42)
    sv = explainer.shap_values(pre.transform(Xs))
    if isinstance(sv, list):
        sv = sv[1]
    sv = np.asarray(sv)
    if sv.ndim == 3:
        sv = sv[:, :, 1]
    return (pd.DataFrame({"feature": names, "mean_abs_shap": np.abs(sv).mean(axis=0)})
            .sort_values("mean_abs_shap", ascending=False).reset_index(drop=True))


if __name__ == "__main__":
    from .contracts import load_and_validate, split_features_target
    df, _ = load_and_validate(str(ROOT / "data" / "Telco_customer_churn.xlsx"))
    X, y, cltv = split_features_target(df)
    print("GLOBAL IMPORTANCE (mean |SHAP|, 2000-row sample)\n")
    print(global_importance(X).head(12).to_string(index=False))
    print("\n\nPER-CUSTOMER ATTRIBUTION — 2 examples\n")
    import joblib as _j
    pipe = _j.load(ROOT / "artifacts" / "churn_model_v1.joblib")
    p = pipe.predict_proba(X)[:, 1]
    for i in [int(np.argmax(p)), int(np.argmin(p))]:
        a = attribute(X.iloc[[i]])[0]
        print(f"{df['CustomerID'].iat[i]}   P(churn) = {p[i]:.4f}   CLTV = {cltv.iat[i]:.0f}")
        for f in a["model_attribution"]:
            arrow = "^" if f["direction"] == "increases_risk" else "v"
            print(f"    {arrow} {f['feature']:38} {f['contribution']:+.4f}")
        print()
    print(a["attribution_disclaimer"])
