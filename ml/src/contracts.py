"""
Data contract + leakage quarantine.

This module is the single source of truth for WHICH COLUMNS MAY BECOME FEATURES.
Nothing else in the codebase is allowed to decide that. `assert_no_leakage()` is
called from the training pipeline AND from tests/test_leakage.py, so a leaked
column cannot reach a model without breaking the build.
"""
from __future__ import annotations
import pandas as pd
import numpy as np

TARGET = "Churn Value"

# ---------------------------------------------------------------------------
# THE DENYLIST. Every entry carries the reason it is banned, because a denylist
# without reasons gets "cleaned up" by the next person who reads it.
# ---------------------------------------------------------------------------
BANNED: dict[str, str] = {
    "Churn Reason": (
        "POST-OUTCOME LEAK. Non-null for exactly the 1,869 churners, null for "
        "exactly the 5,174 retained. `isna()` alone reproduces the label with "
        "accuracy 1.000. It is an exit-survey field that does not exist for a "
        "live customer."
    ),
    "Churn Score": (
        "MODEL-OUTPUT LEAK. IBM's own pre-computed churn score shipped with the "
        "dataset (corr 0.665 with the label). Including it takes ROC-AUC to "
        "0.98 and makes the model a copy of another model. Alone it scores "
        "0.93 ROC-AUC - better than every honest feature combined."
    ),
    "Churn Label": "TARGET. Yes/No string form of Churn Value.",
    "Churn Value": "TARGET.",
    "CLTV": (
        "BUSINESS FIELD, NOT A FEATURE. Retained downstream as the value "
        "multiplier in the expected-value calculation. Using it as a predictor "
        "AND as the EV multiplier double-counts it."
    ),
    "CustomerID": "IDENTIFIER. Unique per row; memorisation risk, zero signal.",
    "Count": "CONSTANT. One unique value (1).",
    "Country": "CONSTANT. One unique value (United States).",
    "State": "CONSTANT. One unique value (California).",
    "Lat Long": "DUPLICATE of Latitude/Longitude, as an unparsed string.",
    "City": "HIGH CARDINALITY. 1,129 levels over 7,043 rows.",
    "Zip Code": "HIGH CARDINALITY. 1,652 levels; geographic identifier.",
    "Latitude": "GEOGRAPHIC IDENTIFIER. 1,652 levels; proxy for Zip Code.",
    "Longitude": "GEOGRAPHIC IDENTIFIER. 1,651 levels; proxy for Zip Code.",
}

# ---------------------------------------------------------------------------
# The permitted feature columns, by role.
# ---------------------------------------------------------------------------
NOMINAL = [  # unordered -> OneHotEncoder. NEVER LabelEncoder.
    "Gender", "Senior Citizen", "Partner", "Dependents",
    "Phone Service", "Multiple Lines", "Internet Service",
    "Online Security", "Online Backup", "Device Protection",
    "Tech Support", "Streaming TV", "Streaming Movies",
    "Paperless Billing", "Payment Method",
]
ORDINAL = {  # genuinely ordered -> integer codes are meaningful here
    "Contract": ["Month-to-month", "One year", "Two year"],
}
NUMERIC = ["Tenure Months", "Monthly Charges", "Total Charges"]

FEATURE_COLUMNS = NOMINAL + list(ORDINAL) + NUMERIC

# Protected attributes we must monitor for disparate impact. They stay in the
# feature set (removing them hides bias rather than fixing it) but the promotion
# gate checks allocation parity across them.
PROTECTED = ["Gender", "Senior Citizen"]

EXPECTED_SHAPE = (7043, 33)


class LeakageError(AssertionError):
    """Raised when a banned column reaches the feature matrix."""


def assert_no_leakage(columns) -> None:
    """The guard. Called by the pipeline and by CI. Never remove this."""
    found = sorted(set(columns) & set(BANNED))
    if found:
        detail = "\n".join(f"  - {c}: {BANNED[c]}" for c in found)
        raise LeakageError(
            f"{len(found)} banned column(s) reached the feature matrix:\n{detail}\n"
            "Add them to the drop list in load_and_validate(), or justify and "
            "remove them from contracts.BANNED explicitly."
        )


def load_and_validate(path: str) -> pd.DataFrame:
    """Load the snapshot and enforce the data contract before anything else."""
    df = pd.read_excel(path)
    problems: list[str] = []

    if df.shape != EXPECTED_SHAPE:
        problems.append(f"expected shape {EXPECTED_SHAPE}, got {df.shape}")

    missing = [c for c in FEATURE_COLUMNS + [TARGET] if c not in df.columns]
    if missing:
        problems.append(f"missing required columns: {missing}")

    # --- Defect 1: `Total Charges` arrives as strings with 11 blanks. ---------
    # All 11 have Tenure Months == 0: brand-new customers, never billed.
    # Coerce, then fill with 0.0 -- NOT with the mean, which would invent spend.
    n_blank = int((df["Total Charges"].astype(str).str.strip() == "").sum())
    df["Total Charges"] = pd.to_numeric(
        df["Total Charges"].astype(str).str.strip().replace("", np.nan), errors="coerce"
    )
    blank_rows = df["Total Charges"].isna()
    if blank_rows.any():
        bad_tenure = df.loc[blank_rows & (df["Tenure Months"] != 0)]
        if len(bad_tenure):
            problems.append(
                f"{len(bad_tenure)} rows have blank Total Charges but non-zero tenure"
            )
        df.loc[blank_rows, "Total Charges"] = 0.0

    # --- Defect 2: `Churn Reason` is true NaN, not empty string. --------------
    # A `== ''` check finds ZERO nulls and misses all 5,174. Assert the real
    # structure so nobody re-learns this the hard way.
    n_null_reason = int(df["Churn Reason"].isna().sum())
    aligned = bool((df["Churn Reason"].isna() == (df["Churn Label"] == "No")).all())
    if not aligned:
        problems.append("Churn Reason nullity no longer aligns with the label")

    # --- Categorical domains -------------------------------------------------
    for col, allowed in ORDINAL.items():
        unexpected = set(df[col].dropna().unique()) - set(allowed)
        if unexpected:
            problems.append(f"{col} has unexpected levels: {unexpected}")

    if problems:
        raise ValueError("Data contract violated:\n  - " + "\n  - ".join(problems))

    report = {
        "rows": len(df),
        "blank_total_charges_filled": n_blank,
        "churn_reason_nulls": n_null_reason,
        "churn_reason_null_pct": round(100 * n_null_reason / len(df), 2),
        "base_rate": round(float(df[TARGET].mean()), 4),
    }
    return df, report


def split_features_target(df: pd.DataFrame):
    """Return (X, y, cltv). X contains ONLY permitted columns."""
    assert_no_leakage(FEATURE_COLUMNS)          # guard the contract itself
    X = df[FEATURE_COLUMNS].copy()
    assert_no_leakage(X.columns)                # guard the actual matrix
    y = df[TARGET].astype(int).copy()
    cltv = df["CLTV"].copy()                    # business field, not a feature
    return X, y, cltv
