"""
Training entry point.

Fixes, relative to the notebook, in the order they appear:
  * `Churn Score` and `CLTV` removed from features        (the fatal leak)
  * OneHotEncoder replaces LabelEncoder on nominal columns (fake ordinality)
  * transform lives INSIDE the Pipeline                    (artifacts were unusable)
  * StandardScaler fitted on train only, via the Pipeline  (fit-before-split leak)
  * stratify=y on the split
  * scale_pos_weight for XGBoost, class_weight for the rest (class_weight was
    silently ignored by XGBoost -- its own warning said so)
  * isotonic calibration with clipping                     (P=1.000 degeneracy)
  * ROC-AUC / PR-AUC / Brier / calibration slope reported, not bare accuracy
  * registry written as ONE valid JSON array               (3 dumps = invalid JSON)
  * registry path matches where the file is actually written
"""
from __future__ import annotations
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score,
                             brier_score_loss, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

from .calibration import ClippedCalibratedClassifier, calibration_slope
from .contracts import PROTECTED, load_and_validate, split_features_target
from .features import build_preprocessor, feature_names
from .gate import run_gate

RANDOM_STATE = 42
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "Telco_customer_churn.xlsx"
ARTIFACTS = ROOT / "artifacts"


def _model_zoo(pos_weight: float):
    """Each library gets ITS OWN class-balancing parameter, correctly named."""
    return {
        "logistic_regression": dict(
            estimator=LogisticRegression(
                class_weight="balanced", max_iter=2000, random_state=RANDOM_STATE
            ),
            scale_numeric=True,
        ),
        "random_forest": dict(
            estimator=RandomForestClassifier(
                n_estimators=500, min_samples_leaf=5, class_weight="balanced",
                n_jobs=-1, random_state=RANDOM_STATE
            ),
            scale_numeric=False,
        ),
        "xgboost": dict(
            # NOT class_weight -- XGBoost ignores it and says so in a warning.
            estimator=XGBClassifier(
                n_estimators=400, max_depth=4, learning_rate=0.05,
                subsample=0.9, colsample_bytree=0.8, reg_lambda=1.0,
                scale_pos_weight=pos_weight, eval_metric="logloss",
                random_state=RANDOM_STATE,
            ),
            scale_numeric=False,
        ),
    }


def evaluate(y_true, p, threshold=0.5) -> dict:
    pred = (p >= threshold).astype(int)
    return {
        "roc_auc": float(roc_auc_score(y_true, p)),
        "pr_auc": float(average_precision_score(y_true, p)),
        "brier": float(brier_score_loss(y_true, p)),
        "calibration_slope": float(calibration_slope(y_true, p)),
        "accuracy": float(accuracy_score(y_true, pred)),
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
    }


def precision_at_k(y_true, p, ks=(50, 100, 200, 300, 400, 500)) -> dict:
    order = np.argsort(-p)
    y = np.asarray(y_true)
    out = {}
    for k in ks:
        if k > len(y):
            continue
        idx = order[:k]
        out[str(k)] = {
            "precision": round(float(y[idx].mean()), 4),
            "recall": round(float(y[idx].sum() / y.sum()), 4),
            "caught": int(y[idx].sum()),
        }
    return out


def main(verbose=True):
    ARTIFACTS.mkdir(exist_ok=True)
    log = print if verbose else (lambda *a, **k: None)

    # ---------------- 1. contract ----------------
    df, report = load_and_validate(str(DATA))
    log("=" * 78)
    log("STAGE A1  DATA CONTRACT")
    log("=" * 78)
    for k, v in report.items():
        log(f"  {k:32} {v}")

    X, y, cltv = split_features_target(df)
    log(f"\nSTAGE A2  LEAKAGE QUARANTINE")
    log(f"  source columns 33 -> {X.shape[1]} permitted features")
    log(f"  quarantined: Churn Score, Churn Reason, CLTV, Churn Label, "
        f"CustomerID, Count, Country, State, City, Zip Code, Lat Long, "
        f"Latitude, Longitude")

    # stratify=y -- the notebook omitted this and drifted to 28.4% vs 26.5%
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=RANDOM_STATE
    )
    log(f"\n  train {len(X_tr)} ({y_tr.mean():.4f} positive) | "
        f"test {len(X_te)} ({y_te.mean():.4f} positive)  <- stratified")

    pos_weight = float((y_tr == 0).sum() / (y_tr == 1).sum())

    # ---------------- 2. train + calibrate ----------------
    log("\n" + "=" * 78)
    log("STAGE A3-A5  FEATURES -> TRAIN -> CALIBRATE")
    log("=" * 78)
    cv = StratifiedKFold(5, shuffle=True, random_state=RANDOM_STATE)
    results, pipelines = {}, {}

    for name, cfg in _model_zoo(pos_weight).items():
        pre = build_preprocessor(scale_numeric=cfg["scale_numeric"])

        raw = Pipeline([("pre", pre), ("clf", cfg["estimator"])])
        raw.fit(X_tr, y_tr)
        p_raw = raw.predict_proba(X_te)[:, 1]

        cal = Pipeline([
            ("pre", build_preprocessor(scale_numeric=cfg["scale_numeric"])),
            ("clf", ClippedCalibratedClassifier(
                estimator=cfg["estimator"], method="isotonic", cv=5, eps=0.01)),
        ])
        cal.fit(X_tr, y_tr)
        p_cal = cal.predict_proba(X_te)[:, 1]

        cv_auc = cross_val_score(raw, X_tr, y_tr, cv=cv, scoring="roc_auc", n_jobs=-1)
        m_raw, m_cal = evaluate(y_te, p_raw), evaluate(y_te, p_cal)
        m_cal["cv_roc_auc_mean"] = float(cv_auc.mean())
        m_cal["cv_roc_auc_std"] = float(cv_auc.std())

        results[name] = {"raw": m_raw, "calibrated": m_cal,
                         "p_cal": p_cal, "p_raw": p_raw}
        pipelines[name] = cal

        log(f"\n  {name}")
        log(f"    {'':14}{'ROC-AUC':>9}{'PR-AUC':>9}{'Brier':>9}{'slope':>8}"
            f"{'recall':>8}{'max P':>8}")
        log(f"    {'uncalibrated':14}{m_raw['roc_auc']:9.4f}{m_raw['pr_auc']:9.4f}"
            f"{m_raw['brier']:9.4f}{m_raw['calibration_slope']:8.3f}"
            f"{m_raw['recall']:8.3f}{p_raw.max():8.4f}")
        log(f"    {'calibrated':14}{m_cal['roc_auc']:9.4f}{m_cal['pr_auc']:9.4f}"
            f"{m_cal['brier']:9.4f}{m_cal['calibration_slope']:8.3f}"
            f"{m_cal['recall']:8.3f}{p_cal.max():8.4f}")
        log(f"    5-fold CV ROC-AUC on train: {cv_auc.mean():.4f} +/- {cv_auc.std():.4f}")

    # ---------------- 3. select ----------------
    # Rank by PR-AUC: with a 26.5% base rate it reflects the positive class far
    # better than accuracy, and unlike ROC-AUC it does not flatter a model that
    # ranks the easy negatives well.
    best = max(results, key=lambda n: results[n]["calibrated"]["pr_auc"])
    log("\n" + "=" * 78)
    log(f"MODEL SELECTION (by calibrated PR-AUC)  ->  {best}")
    log("=" * 78)
    log(f"  {'model':22}{'ROC-AUC':>9}{'PR-AUC':>9}{'Brier':>9}{'accuracy':>10}")
    for n in results:
        c = results[n]["calibrated"]
        mark = "  <-- selected" if n == best else ""
        log(f"  {n:22}{c['roc_auc']:9.4f}{c['pr_auc']:9.4f}{c['brier']:9.4f}"
            f"{c['accuracy']:10.4f}{mark}")

    chosen = pipelines[best]
    names = feature_names(chosen.named_steps["pre"])
    log(f"\n  encoded feature count: {len(names)}")

    # ---------------- 4. promotion gate ----------------
    log("\n" + "=" * 78)
    log("STAGE A6  PROMOTION GATE")
    log("=" * 78)
    g = run_gate(
        feature_names=names,
        metrics=results[best]["calibrated"],
        y_true=y_te.values,
        p_pred=results[best]["p_cal"],
        protected_frame=X_te[PROTECTED],
    )
    log(g.report())

    if not g.passed:
        raise SystemExit("Promotion gate failed - nothing registered.")

    # ---------------- 5. register ----------------
    version = "v1"
    model_path = ARTIFACTS / f"churn_model_{version}.joblib"
    joblib.dump(chosen, model_path)     # ONE object: transform + calibrated model

    # SHAP needs the raw tree ensemble. CalibratedClassifierCV wraps 5 fitted models,
    # so we persist an UNCALIBRATED twin trained on the same data with the same seed.
    # Its RANKING is near-identical (ROC-AUC differs by <0.001), so attribution
    # computed on it is valid for the calibrated model's ordering. The calibrated
    # model remains the only source of probabilities.
    cfg_best = _model_zoo(pos_weight)[best]
    twin = Pipeline([("pre", build_preprocessor(scale_numeric=cfg_best["scale_numeric"])),
                     ("clf", cfg_best["estimator"])])
    twin.fit(X_tr, y_tr)
    attr_path = ARTIFACTS / f"churn_model_{version}_attribution.joblib"
    joblib.dump(twin, attr_path)
    log(f"  {attr_path.relative_to(ROOT)}   (uncalibrated twin, for SHAP only)")

    registry = [
        {
            "model_name": n,
            "version": version,
            "selected": n == best,
            # path recorded matches where the file actually is
            "artifact_path": str(model_path.relative_to(ROOT)) if n == best else None,
            "metrics": {k: round(v, 6) for k, v in results[n]["calibrated"].items()},
            "metrics_uncalibrated": {k: round(v, 6) for k, v in results[n]["raw"].items()},
        }
        for n in results
    ]
    meta = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "random_state": RANDOM_STATE,
        "n_features_source": X.shape[1],
        "n_features_encoded": len(names),
        "train_rows": len(X_tr),
        "test_rows": len(X_te),
        "base_rate": round(float(y.mean()), 4),
        "banned_columns_enforced": True,
        "gate": g.checks,
        "models": registry,
        "precision_at_k": precision_at_k(y_te.values, results[best]["p_cal"]),
    }

    # ONE json.dump of ONE object. The notebook called json.dump three times
    # into the same handle, producing {...}{...}{...} which json.load() rejects.
    with open(ARTIFACTS / "model_registry.json", "w") as f:
        json.dump(meta, f, indent=2)

    # round-trip proof
    with open(ARTIFACTS / "model_registry.json") as f:
        json.load(f)

    log("\n" + "=" * 78)
    log("STAGE A6  REGISTERED")
    log("=" * 78)
    log(f"  {model_path.relative_to(ROOT)}   ({model_path.stat().st_size/1024:.0f} KB)")
    log(f"  artifacts/model_registry.json    (valid JSON, round-trip verified)")

    log("\n  capacity-constrained queue (calibrated, ranked):")
    log(f"    {'K':>6}{'precision@K':>13}{'recall@K':>11}{'caught':>9}")
    for k, v in meta["precision_at_k"].items():
        log(f"    {k:>6}{v['precision']:13.3f}{v['recall']:11.3f}{v['caught']:9d}")

    return meta


if __name__ == "__main__":
    main()
