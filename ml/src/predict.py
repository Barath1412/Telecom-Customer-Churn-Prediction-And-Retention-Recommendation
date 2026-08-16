"""
Scoring a raw customer from the saved artifact.

This is the file that could NOT be written against the notebook's output. There,
the models were dumped but the LabelEncoders and the StandardScaler were not --
and a single `le` instance was refitted in a loop, so no per-column mapping ever
existed. A new customer arriving as "Electronic check" had nothing on disk that
knew it meant 2. The .pkl files were unusable.

Here the whole transform is inside the Pipeline, so one joblib.load gives you a
callable that takes RAW customer fields and returns a calibrated probability.
"""
from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .contracts import FEATURE_COLUMNS, assert_no_leakage

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "artifacts" / "model_registry.json"


@lru_cache(maxsize=1)
def load_model():
    meta = json.loads(REGISTRY.read_text())
    selected = next(m for m in meta["models"] if m["selected"])
    pipe = joblib.load(ROOT / selected["artifact_path"])
    return pipe, selected["model_name"], selected["version"]


def score(customers: list[dict] | dict) -> pd.DataFrame:
    """
    customers: raw field values, exactly as they appear in the source system.
               No manual encoding, no scaling, no column ordering required.
    """
    if isinstance(customers, dict):
        customers = [customers]
    df = pd.DataFrame(customers)

    missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing required fields: {missing}")

    # Anything extra is ignored by remainder='drop', but fail loudly on a banned
    # column rather than silently accepting it -- if it is in the payload, the
    # upstream system is exposing something it should not.
    assert_no_leakage(df.columns)

    pipe, name, version = load_model()
    p = pipe.predict_proba(df[FEATURE_COLUMNS])[:, 1]
    return pd.DataFrame({
        "p_churn": np.round(p, 4),
        "risk_band": pd.cut(p, [0, .25, .50, .75, 1.0],
                            labels=["low", "medium", "high", "critical"]),
        "model": name,
        "model_version": version,
    })


# ---------------------------------------------------------------------------
EXAMPLE = {
    "Gender": "Female", "Senior Citizen": "No", "Partner": "No", "Dependents": "No",
    "Tenure Months": 3, "Phone Service": "Yes", "Multiple Lines": "No",
    "Internet Service": "Fiber optic", "Online Security": "No", "Online Backup": "No",
    "Device Protection": "No", "Tech Support": "No", "Streaming TV": "Yes",
    "Streaming Movies": "Yes", "Contract": "Month-to-month",
    "Paperless Billing": "Yes", "Payment Method": "Electronic check",
    "Monthly Charges": 94.40, "Total Charges": 283.20,
}

LOYAL = {**EXAMPLE, "Tenure Months": 62, "Contract": "Two year",
         "Tech Support": "Yes", "Online Security": "Yes",
         "Payment Method": "Credit card (automatic)", "Total Charges": 5852.80}


if __name__ == "__main__":
    pipe, name, version = load_model()
    print(f"loaded {name} {version} from artifacts/ -- no manual encoding needed\n")
    out = score([EXAMPLE, LOYAL])
    out.insert(0, "customer", ["new/rolling/no-bundles", "long-tenure/2yr/bundled"])
    print(out.to_string(index=False))
