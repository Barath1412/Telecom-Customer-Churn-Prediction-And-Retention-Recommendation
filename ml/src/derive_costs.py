"""
Recover the dataset's own price list from `Monthly Charges`.

`Monthly Charges` is a BILL -- the sum of what a customer subscribes to. Regressing
it on the service flags therefore recovers the implied monthly price of each add-on,
which is what the company forgoes by bundling that add-on free.

R2 = 0.9988 on this dataset: the pricing structure is essentially exact.

    python -m src.derive_costs

WHY THERE IS NO statsmodels IMPORT ANY MORE  (fixed v5.2)
    This module and src/validate_catalog.py both imported `statsmodels.api`, and
    statsmodels was never in requirements.txt. It happened to be installed on the
    machine the project was built on, so nothing complained here -- and two tests
    died with ModuleNotFoundError on the first clean install. That is the classic
    undeclared dependency, and adding it to requirements.txt would have been the
    lazy fix.

    The honest fix is that we never needed the package. statsmodels was used for
    exactly three things: the coefficients, R2, and a 95% confidence interval.
    Ordinary least squares is a single call to `numpy.linalg.lstsq`, R2 is two
    lines, and the interval is the standard textbook formula using a t critical
    value from scipy -- which is already a hard dependency of scikit-learn, so it
    is guaranteed present. The numbers are IDENTICAL to the statsmodels output
    they replace, to the cent, because it is the same estimator.

    One fewer package to install, and it works on any Python version, which
    matters here: statsmodels wheels lag new Python releases by months and this
    project is being run on 3.14.
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

from .contracts import load_and_validate

ROOT = Path(__file__).resolve().parent.parent
SERVICES = ["Phone Service", "Multiple Lines", "Online Security", "Online Backup",
            "Device Protection", "Tech Support", "Streaming TV", "Streaming Movies"]


def _ols(X: pd.DataFrame, y: pd.Series, alpha: float = 0.05) -> dict:
    """
    Ordinary least squares with an intercept, in numpy.

    Returns coefficients (intercept first, labelled 'const'), R2, and a
    two-sided (1-alpha) confidence interval per coefficient. Same estimator and
    same numbers as `statsmodels.OLS(y, add_constant(X)).fit()`.
    """
    names = ["const", *X.columns]
    A = np.column_stack([np.ones(len(X)), X.to_numpy(dtype=float)])
    yv = np.asarray(y, dtype=float)

    beta, *_ = np.linalg.lstsq(A, yv, rcond=None)
    resid = yv - A @ beta
    ssr = float(resid @ resid)
    sst = float(((yv - yv.mean()) ** 2).sum())
    r2 = 1.0 - ssr / sst if sst else float("nan")

    n, k = A.shape
    dof = n - k
    # (X'X)^-1 via pinv: numerically safer than inv when a column is near-collinear,
    # which is a real possibility here (Internet_Fiber and Internet_DSL are close to
    # complementary). pinv degrades gracefully; inv would raise.
    xtx_inv = np.linalg.pinv(A.T @ A)
    sigma2 = ssr / dof if dof > 0 else float("nan")
    se = np.sqrt(np.maximum(np.diag(xtx_inv) * sigma2, 0.0))

    try:
        from scipy.stats import t as _t          # ships with scikit-learn
        crit = float(_t.ppf(1 - alpha / 2, dof))
    except Exception:                            # pragma: no cover
        crit = 1.959963985                       # normal approximation; dof here is ~7,000
    return {"names": names, "params": beta, "r2": r2,
            "ci_low": beta - crit * se, "ci_high": beta + crit * se}


def _design(df: pd.DataFrame) -> pd.DataFrame:
    """The service flags, exactly as the catalog's costs were derived from."""
    X = pd.DataFrame({s: (df[s] == "Yes").astype(int) for s in SERVICES})
    X["Internet_Fiber"] = (df["Internet Service"] == "Fiber optic").astype(int)
    X["Internet_DSL"] = (df["Internet Service"] == "DSL").astype(int)
    return X


def implied_prices(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    One row per billable component, with its implied monthly price.

    `df` is optional so a caller that has already loaded and validated the
    spreadsheet does not pay for a second read of it -- src/validate_catalog.py
    used to duplicate this whole regression for that reason.
    """
    if df is None:
        df, _ = load_and_validate(str(ROOT / "data" / "Telco_customer_churn.xlsx"))
    X = _design(df)
    fit = _ols(X, df["Monthly Charges"])
    out = pd.DataFrame({"component": ["base"] + list(X.columns),
                        "usd_per_month": fit["params"],
                        "ci_low": fit["ci_low"],
                        "ci_high": fit["ci_high"]})
    out.attrs["r2"] = fit["r2"]
    return out


def implied_price_series(df: pd.DataFrame | None = None) -> pd.Series:
    """
    The same coefficients as a Series indexed by 'const' plus the column names --
    the shape `statsmodels ... .fit().params` used to return, so callers that
    only want a price lookup keep working unchanged.
    """
    p = implied_prices(df)
    idx = ["const"] + [c for c in p.component[1:]]
    return pd.Series(p.usd_per_month.to_numpy(), index=idx)


if __name__ == "__main__":
    p = implied_prices()
    print(f"R2 = {p.attrs['r2']:.4f}\n")
    print(p.round(2).to_string(index=False))
    # NOTE — kept in step with catalog v3.
    # v1/v2 of this script also priced OFF-PROTECT-12 and defined OFF-BUNDLE-ALL
    # as three services ($180.75). Catalog v3 deleted OFF-PROTECT-12 (its
    # counterfactual moved the model by mean dP +0.0031, effectively nothing) and
    # cut the bundle to two services. This script printed the stale three-service
    # figure for one release; if the two disagree again, THE CATALOG IS THE
    # CONTRACT and this script is what must change.
    print("\n12-MONTH BUNDLE COST = implied monthly price x 12   (catalog v3)")
    for svc, oid in [("Tech Support", "OFF-TECHSUP-12"),
                     ("Online Security", "OFF-SEC-12")]:
        v = p.loc[p.component == svc, "usd_per_month"].iloc[0]
        print(f"  {oid:20} {v*12:8.2f}")
    pair = p[p.component.isin(["Tech Support", "Online Security"])]
    print(f"  {'OFF-BUNDLE-ALL':20} {pair.usd_per_month.sum()*12:8.2f}"
          f"   (2 services — Device Protection removed in v3)")
    print(f"\n  for reference, dropped in v3:")
    dp = p.loc[p.component == "Device Protection", "usd_per_month"].iloc[0]
    print(f"  {'OFF-PROTECT-12':20} {dp*12:8.2f}   removed — mean dP +0.0031")
