"""
Customer records for live narration, read from the source spreadsheet.
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

    # Also load previously uploaded batch customers from uploaded_customers.jsonl if present
    up_jsonl = ML_ROOT / "artifacts" / "uploaded_customers.jsonl"
    if up_jsonl.exists():
        import json
        try:
            with open(up_jsonl, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rec = json.loads(line)
                            cid = rec.get("customer_id")
                            if cid:
                                _records[cid] = rec
                        except Exception:
                            pass
        except Exception:
            pass

    return len(_records)


def add_customer(customer_id: str, customer_dict: dict[str, Any], cltv: float) -> None:
    """Dynamically register a newly uploaded customer into memory."""
    if not _records:
        load()
    _records[customer_id] = {
        "customer_id": customer_id,
        "customer": {k: _py(customer_dict.get(k)) for k in FIELDS},
        "cltv": float(cltv),
    }


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
