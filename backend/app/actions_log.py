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
