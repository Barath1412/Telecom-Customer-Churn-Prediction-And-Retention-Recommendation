"""
Durable audit logging for agent actions (approve, edit, reject).

Appends one JSON line per action to ML_ROOT/artifacts/actions/actions.jsonl.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .settings import ML_ROOT

LOG_PATH = ML_ROOT / "artifacts" / "actions" / "actions.jsonl"


def append(record: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def remove_customer_actions(customer_ids: set[str]) -> None:
    """Remove actions for specific customer IDs when they are re-uploaded in a fresh batch."""
    if not LOG_PATH.exists() or not customer_ids:
        return
    try:
        recs = []
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        r = json.loads(line)
                        if str(r.get("customer_id")) not in customer_ids:
                            recs.append(r)
                    except Exception:
                        pass
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")
    except Exception as exc:
        print(f"Warning: Failed to prune actions log: {exc}")


def clear_all_actions() -> None:
    """Reset all recorded actions for clean testing or demo resets."""
    if LOG_PATH.exists():
        try:
            LOG_PATH.write_text("", encoding="utf-8")
        except Exception:
            pass
