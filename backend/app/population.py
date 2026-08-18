"""
Customer records for live narration, read from the source spreadsheet and persistent upload stores.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import pandas as pd

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
    """Read the spreadsheet and all persistent stores into memory. Returns the count."""
    if _records:
        return len(_records)

    from .settings import ML_ROOT
    from src.contracts import load_and_validate  # noqa: E402  (ML package)

    # 1. Base dataset from Excel spreadsheet
    excel_path = ML_ROOT / "data" / "Telco_customer_churn.xlsx"
    if excel_path.exists():
        df, _ = load_and_validate(str(excel_path))
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

    # 2. Load from uploaded_customers.jsonl if present
    up_jsonl = ML_ROOT / "artifacts" / "uploaded_customers.jsonl"
    if up_jsonl.exists():
        try:
            with open(up_jsonl, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rec = json.loads(line)
                            cid = rec.get("customer_id")
                            if cid and rec.get("customer"):
                                _records[cid] = rec
                        except Exception:
                            pass
        except Exception:
            pass

    # 3. Load from uploaded_customers.json if present
    up_json = ML_ROOT / "artifacts" / "uploaded_customers.json"
    if up_json.exists():
        try:
            with open(up_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for rec in data:
                        cid = rec.get("customer_id")
                        if cid and rec.get("customer"):
                            _records[cid] = rec
                elif isinstance(data, dict):
                    for cid, rec in data.items():
                        if rec.get("customer"):
                            _records[cid] = rec
        except Exception:
            pass

    # 4. Load from uploaded_customers.csv if present
    up_csv = ML_ROOT / "artifacts" / "uploaded_customers.csv"
    if up_csv.exists():
        try:
            df_up = pd.read_csv(up_csv)
            for row in df_up.to_dict("records"):
                cid = str(row.get("customer_id", row.get("CustomerID", "")))
                if cid and cid not in _records:
                    rec = synthesize_record_from_queue_row(cid, row)
                    _records[cid] = rec
        except Exception:
            pass

    return len(_records)


def save_customer_records(new_records: list[dict[str, Any]]) -> None:
    """Reliably persist newly uploaded customer records to jsonl and json stores."""
    from .settings import ML_ROOT

    if not new_records:
        return

    art_dir = ML_ROOT / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)

    # 1. Append to uploaded_customers.jsonl
    up_jsonl = art_dir / "uploaded_customers.jsonl"
    try:
        with open(up_jsonl, "a", encoding="utf-8") as f:
            for rec in new_records:
                f.write(json.dumps(rec) + "\n")
    except Exception as exc:
        print(f"Warning: Failed to append to {up_jsonl}: {exc}")

    # 2. Update uploaded_customers.json full dump
    up_json = art_dir / "uploaded_customers.json"
    try:
        existing_recs: dict[str, dict[str, Any]] = {}
        if up_json.exists():
            try:
                with open(up_json, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, list):
                        existing_recs = {r["customer_id"]: r for r in loaded if "customer_id" in r}
                    elif isinstance(loaded, dict):
                        existing_recs = loaded
            except Exception:
                existing_recs = {}
        for rec in new_records:
            cid = rec.get("customer_id")
            if cid:
                existing_recs[cid] = rec
        with open(up_json, "w", encoding="utf-8") as f:
            json.dump(list(existing_recs.values()), f, indent=2)
    except Exception as exc:
        print(f"Warning: Failed to write to {up_json}: {exc}")


def synthesize_record_from_queue_row(cid: str, row: dict[str, Any]) -> dict[str, Any]:
    """
    Construct a complete, valid customer profile when a customer exists in queue_full.csv
    or an uploaded queue batch but lacks a detailed raw survey row.
    """
    try:
        monthly = float(row.get("monthly_charges", 50.0) or 50.0)
    except (ValueError, TypeError):
        monthly = 50.0

    try:
        tenure = int(row.get("tenure_months", 1) or 1)
    except (ValueError, TypeError):
        tenure = 1

    try:
        total = float(row.get("total_charges", monthly * max(1, tenure)) or (monthly * max(1, tenure)))
    except (ValueError, TypeError):
        total = round(monthly * max(1, tenure), 2)

    try:
        cltv = float(row.get("cltv", max(2003.0, min(6500.0, monthly * 45.0))) or 3500.0)
    except (ValueError, TypeError):
        cltv = 3500.0

    levers_str = str(row.get("levers", "") or "") + ";" + str(row.get("lever_summary", "") or "")

    contract = "Month-to-month"
    if "OFF-CONTRACT-2Y" in str(row.get("offer_id", "")) or "TWO_YEAR" in levers_str:
        contract = "Two year"
    elif "OFF-CONTRACT-1Y" in str(row.get("offer_id", "")) or "ONE_YEAR" in levers_str:
        contract = "One year"

    internet = "DSL"
    if "FIBER_PREMIUM" in levers_str or "Fiber" in levers_str:
        internet = "Fiber optic"
    elif "NO_INTERNET" in levers_str or "Phone-only" in levers_str:
        internet = "No"

    tech_support = "No" if "NO_TECH_SUPPORT" in levers_str or "tech support" in levers_str.lower() else ("No internet service" if internet == "No" else "Yes")
    online_sec = "No" if "NO_ONLINE_SECURITY" in levers_str or "security" in levers_str.lower() else ("No internet service" if internet == "No" else "Yes")
    device_prot = "No" if "NO_DEVICE_PROTECTION" in levers_str or "device" in levers_str.lower() else ("No internet service" if internet == "No" else "Yes")
    backup = "No internet service" if internet == "No" else "No"
    streaming_tv = "No internet service" if internet == "No" else "No"
    streaming_mov = "No internet service" if internet == "No" else "No"

    payment = "Electronic check" if "MANUAL_PAYMENT" in levers_str or "Manual" in levers_str else "Bank transfer (automatic)"

    cust_dict = {
        "Gender": "Male",
        "Senior Citizen": "No",
        "Partner": "No",
        "Dependents": "No",
        "Phone Service": "Yes",
        "Multiple Lines": "No",
        "Internet Service": internet,
        "Online Security": online_sec,
        "Online Backup": backup,
        "Device Protection": device_prot,
        "Tech Support": tech_support,
        "Streaming TV": streaming_tv,
        "Streaming Movies": streaming_mov,
        "Paperless Billing": "Yes",
        "Payment Method": payment,
        "Contract": contract,
        "Tenure Months": tenure,
        "Monthly Charges": monthly,
        "Total Charges": total,
    }

    record = {
        "customer_id": cid,
        "customer": cust_dict,
        "cltv": cltv,
    }
    return record


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
    """
    Get customer record. If not already indexed, performs robust check against
    all artifact datasets and queue_full.csv to auto-synthesize if needed.
    """
    if not _records:
        load()

    if customer_id in _records:
        return _records[customer_id]

    # Fallback 1: check if present in queue_full.csv
    from .settings import ML_ROOT
    q_csv = ML_ROOT / "artifacts" / "queue_full.csv"
    if q_csv.exists():
        try:
            df = pd.read_csv(q_csv)
            match = df[df["customer_id"].astype(str) == str(customer_id)]
            if not match.empty:
                row = match.iloc[0].to_dict()
                rec = synthesize_record_from_queue_row(customer_id, row)
                _records[customer_id] = rec
                save_customer_records([rec])
                return rec
        except Exception:
            pass

    return _records.get(customer_id)


def count() -> int:
    if not _records:
        load()
    return len(_records)


def sample_ids(n: int = 5) -> list[str]:
    if not _records:
        load()
    return list(_records.keys())[:n]
