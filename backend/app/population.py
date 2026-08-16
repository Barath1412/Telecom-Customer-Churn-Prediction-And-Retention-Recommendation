"""
Customer records for live narration, read from the source spreadsheet.

WHY NOT samples/customers_200.jsonl
    That file holds 200 customers. The queue in GET_queue.json holds 40. Only 7 of
    those 40 appear in the jsonl -- so if the queue is on screen and someone clicks
    a row and asks for a note, it fails 33 times out of 40.

    data/Telco_customer_churn.xlsx has all 7,043. Every customer that can appear in
    any queue, present or future, can be narrated. Verified field-by-field against
    the jsonl: all 19 attributes and CLTV match exactly for the customers in both.

The 19 fields below are exactly the keys a sample record carries under "customer",
which is what `graph.invoke` expects. They are the features the model was trained on
plus the account attributes the levers read. Nothing else from the spreadsheet is
passed in -- Churn Label, Churn Score, Churn Reason and CLTV-derived columns are
quarantined by src/gate.py, and handing them to the graph would be leakage.
"""
from __future__ import annotations

from typing import Any

FIELDS = [
    "Gender",
    "Senior Citizen",
    "Partner",
    "Dependents",
    "Phone Service",
    "Multiple Lines",
    "Internet Service",
    "Online Security",
    "Online Backup",
    "Device Protection",
    "Tech Support",
    "Streaming TV",
    "Streaming Movies",
    "Paperless Billing",
    "Payment Method",
    "Contract",
    "Tenure Months",
    "Monthly Charges",
    "Total Charges",
]

ID_COLUMN = "CustomerID"
CLTV_COLUMN = "CLTV"

_records: dict[str, dict[str, Any]] = {}


def _py(v):
    """numpy scalar -> python scalar, so the record is JSON-serialisable."""
    return v.item() if hasattr(v, "item") else v


def load() -> int:
    """Read the spreadsheet once and index it by customer id. Returns the count."""
    if _records:
        return len(_records)

    from src.contracts import load_and_validate  # noqa: E402  (ML package)
    from .settings import ML_ROOT

    df, _ = load_and_validate(str(ML_ROOT / "data" / "Telco_customer_churn.xlsx"))

    missing = [c for c in (*FIELDS, ID_COLUMN, CLTV_COLUMN) if c not in df.columns]
    if missing:
        raise RuntimeError(f"spreadsheet is missing expected columns: {missing}")

    for row in df.to_dict("records"):
        cid = str(row[ID_COLUMN])
        _records[cid] = {
            "customer_id": cid,
            "customer": {k: _py(row[k]) for k in FIELDS},
            "cltv": float(_py(row[CLTV_COLUMN])),
        }
    return len(_records)


def get(customer_id: str) -> dict[str, Any] | None:
    """The graph input for one customer, or None if the id is unknown."""
    if not _records:
        load()
    return _records.get(customer_id)


def count() -> int:
    if not _records:
        load()
    return len(_records)


def sample_ids(n: int = 5) -> list[str]:
    if not _records:
        load()
    return list(_records.keys())[:n]
