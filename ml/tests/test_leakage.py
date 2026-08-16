"""
The test that must never be skipped.

Leakage is not a mistake you make once and clean up in a notebook. It re-enters
every time somebody adds a feature, widens a select, or "just tries" a column
that looks useful. This suite runs in CI and fails the build.

Run:  pytest tests/ -v
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

from src.contracts import (BANNED, FEATURE_COLUMNS, LeakageError, TARGET,
                           assert_no_leakage, load_and_validate,
                           split_features_target)
from src.features import build_preprocessor, feature_names

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "Telco_customer_churn.xlsx"


@pytest.fixture(scope="module")
def data():
    df, _ = load_and_validate(str(DATA))
    return df


# ---------------------------------------------------------------- the guard --
def test_permitted_features_are_clean():
    assert_no_leakage(FEATURE_COLUMNS)


def test_guard_rejects_each_banned_column():
    """Every entry in BANNED must actually be caught. No decorative denylist."""
    for col in BANNED:
        with pytest.raises(LeakageError):
            assert_no_leakage(FEATURE_COLUMNS + [col])


def test_guard_catches_the_exact_notebook_bug():
    """
    The notebook's drop list omitted `Churn Score`, so it survived into X.
    This is that exact list. It must raise.
    """
    notebook_drop = ["CustomerID", "Count", "Country", "State", "City", "Zip Code",
                     "Lat Long", "Latitude", "Longitude", "Churn Reason", "Churn Label"]
    df = pd.read_excel(DATA)
    notebook_features = [c for c in df.columns
                         if c not in notebook_drop and c != TARGET]
    assert "Churn Score" in notebook_features          # confirm we reproduced it
    with pytest.raises(LeakageError, match="Churn Score"):
        assert_no_leakage(notebook_features)


def test_pipeline_output_is_clean(data):
    X, y, _ = split_features_target(data)
    assert_no_leakage(X.columns)
    pre = build_preprocessor().fit(X)
    assert_no_leakage(feature_names(pre))              # also after one-hot expansion


def test_preprocessor_drops_unlisted_columns(data):
    """
    remainder='drop' means a column appearing in the input but not in the
    contract cannot reach the model even if someone forgets to filter it.
    """
    X, y, _ = split_features_target(data)
    X_dirty = X.copy()
    X_dirty["Churn Score"] = data["Churn Score"].values
    pre = build_preprocessor().fit(X_dirty)
    assert "Churn Score" not in feature_names(pre)


# ------------------------------------------------------------ the tripwires --
def test_auc_ceiling_catches_a_deliberate_leak(data):
    """
    Inject `Churn Score` and prove the ceiling fires. This is the assertion the
    notebook needed: an honest model here tops out near 0.85, so 0.95+ is a leak,
    not a triumph.
    """
    from src.gate import AUC_CEILING
    from sklearn.metrics import roc_auc_score
    from sklearn.preprocessing import OneHotEncoder
    from sklearn.compose import ColumnTransformer
    from src.contracts import NOMINAL, ORDINAL, NUMERIC

    X, y, _ = split_features_target(data)
    X_leak = X.copy()
    X_leak["Churn Score"] = data["Churn Score"].values

    pre = ColumnTransformer(
        [("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False),
          NOMINAL + list(ORDINAL))],
        remainder="passthrough",          # numerics + the injected Churn Score
    )
    pipe = Pipeline([("pre", pre),
                     ("clf", XGBClassifier(n_estimators=200, max_depth=4,
                                           eval_metric="logloss", random_state=42))])
    Xtr, Xte, ytr, yte = train_test_split(X_leak, y, test_size=0.2,
                                          stratify=y, random_state=42)
    pipe.fit(Xtr, ytr)
    auc = roc_auc_score(yte, pipe.predict_proba(Xte)[:, 1])
    assert auc > AUC_CEILING, (
        f"leaked model scored {auc:.4f}; expected it to breach the {AUC_CEILING} "
        "ceiling. If this fails, the canary threshold needs revisiting."
    )


def test_honest_model_sits_below_the_ceiling():
    reg = json.loads((ROOT / "artifacts" / "model_registry.json").read_text())
    from src.gate import AUC_CEILING, AUC_FLOOR
    for m in reg["models"]:
        auc = m["metrics"]["roc_auc"]
        assert AUC_FLOOR <= auc <= AUC_CEILING, f"{m['model_name']} ROC-AUC {auc}"


# ------------------------------------------------------- contract integrity --
def test_churn_reason_nullity_is_the_label(data):
    """Documents WHY Churn Reason is banned, so the reason survives refactors."""
    aligned = (data["Churn Reason"].isna() == (data["Churn Label"] == "No")).all()
    assert aligned
    leak_only = (~data["Churn Reason"].isna()).astype(int)
    assert (leak_only == data[TARGET]).mean() == 1.0     # accuracy 1.000


def test_churn_reason_nulls_are_nan_not_empty_string(data):
    """A `== ''` check finds zero nulls and misses all 5,174. Pin the behaviour."""
    assert data["Churn Reason"].isna().sum() == 5174
    assert (data["Churn Reason"].astype(str).str.strip() == "").sum() == 0


def test_total_charges_blanks_are_new_customers(data):
    raw = pd.read_excel(DATA)
    blank = raw["Total Charges"].astype(str).str.strip() == ""
    assert blank.sum() == 11
    assert (raw.loc[blank, "Tenure Months"] == 0).all()
    assert (data.loc[blank.values, "Total Charges"] == 0.0).all()   # filled, not dropped


def test_no_label_encoder_ordinality_on_nominals():
    """
    LabelEncoder on Payment Method invents Bank=0 < Credit=1 < E-check=2 < Mail=3
    while real churn is 16.7 / 15.2 / 45.3 / 19.1 -- the spike is in the MIDDLE.
    Assert the encoder we ship is one-hot for that column.
    """
    from src.contracts import NOMINAL
    assert "Payment Method" in NOMINAL
    assert "Contract" not in NOMINAL          # genuinely ordered, ordinal is correct


# ----------------------------------------------------------- artifact sanity --
def test_registry_is_valid_json():
    """The notebook wrote {...}{...}{...} into one handle. json.load() rejects it."""
    obj = json.loads((ROOT / "artifacts" / "model_registry.json").read_text())
    assert isinstance(obj, dict) and obj["models"]


def test_registry_path_points_at_a_real_file():
    """The notebook recorded ./registry/x.pkl but wrote x.pkl."""
    reg = json.loads((ROOT / "artifacts" / "model_registry.json").read_text())
    sel = [m for m in reg["models"] if m["selected"]]
    assert len(sel) == 1
    assert (ROOT / sel[0]["artifact_path"]).exists()


def test_probabilities_never_assert_certainty():
    import joblib
    reg = json.loads((ROOT / "artifacts" / "model_registry.json").read_text())
    sel = [m for m in reg["models"] if m["selected"]][0]
    pipe = joblib.load(ROOT / sel["artifact_path"])
    df, _ = load_and_validate(str(DATA))
    X, _, _ = split_features_target(df)
    p = pipe.predict_proba(X)[:, 1]
    assert p.max() < 1.0 and p.min() > 0.0, "isotonic degeneracy is back"
