from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import pandas as pd

from . import fixtures
from .settings import ML_ROOT


@dataclass
class QueueState:
    eligible_ids: list[str]      # ranked, best EV first — built once at startup
    capacity: int
    actioned: dict[str, dict] = field(default_factory=dict)
    _last_pending_snapshot: set[str] = field(default_factory=set)

    def pending_ids(self) -> list[str]:
        return [c for c in self.eligible_ids if c not in self.actioned]

    def active_ids(self) -> list[str]:
        """Position <= capacity within pending — today's actionable queue."""
        return self.pending_ids()[: self.capacity]

    def approved_ids(self) -> list[str]:
        ordered = sorted(
            (c for c, v in self.actioned.items() if v.get("action") in ("approve", "edit")),
            key=lambda c: self.actioned[c].get("acted_at", ""),
            reverse=True,
        )
        return ordered

    def rejected_ids(self) -> list[str]:
        ordered = sorted(
            (c for c, v in self.actioned.items() if v.get("action") == "reject"),
            key=lambda c: self.actioned[c].get("acted_at", ""),
            reverse=True,
        )
        return ordered

    def offered_offer_id(self, customer_id: str) -> str | None:
        rec = self.actioned.get(customer_id)
        if not rec:
            return None
        return rec.get("modified_offer_id") or rec.get("offer_id")

    def record_action(self, customer_id: str, record: dict) -> list[str]:
        before = set(self.active_ids())
        self.actioned[customer_id] = record
        after = set(self.active_ids())
        promoted = after - before
        self._last_pending_snapshot = after
        return list(promoted)

    def remove_actions(self, customer_ids: set[str]) -> list[str]:
        """Remove actions for re-uploaded customer IDs so they enter the queue as Pending."""
        before = set(self.active_ids())
        for cid in customer_ids:
            self.actioned.pop(cid, None)
        after = set(self.active_ids())
        promoted = after - before
        self._last_pending_snapshot = after
        return list(promoted)

    def reset_all_actions(self) -> None:
        """Clear all actions."""
        self.actioned.clear()
        self._last_pending_snapshot = set(self.active_ids())

    def reload(self) -> None:
        self.eligible_ids = load_eligible_ids()
        self.actioned = load_actioned()
        self._last_pending_snapshot = set(self.active_ids())

    def add_eligible_customers(self, new_customers_with_ev: list[dict[str, Any]]) -> list[str]:
        """Dynamically add and re-rank new customers into eligible_ids by EV descending."""
        # Un-action any re-uploaded customers so they start fresh in Pending
        uploaded_ids = {str(r.get("customer_id")) for r in new_customers_with_ev if r.get("customer_id")}
        for cid in uploaded_ids:
            self.actioned.pop(cid, None)

        before = set(self.active_ids())
        self.eligible_ids = load_eligible_ids()
        after = set(self.active_ids())
        promoted = after - before
        self._last_pending_snapshot = after
        return list(promoted)

    def total_scored_count(self) -> int:
        csv_path = ML_ROOT / "artifacts" / "queue_full.csv"
        if not csv_path.exists():
            return len(self.eligible_ids)
        try:
            df = pd.read_csv(csv_path)
            return len(df)
        except Exception:
            return len(self.eligible_ids)


def load_eligible_ids() -> list[str]:
    csv_path = ML_ROOT / "artifacts" / "queue_full.csv"
    if not csv_path.exists():
        return []
    df = pd.read_csv(csv_path)
    rec_df = df[df["status"] == "recommended"].sort_values("ev", ascending=False).reset_index(drop=True)
    return rec_df["customer_id"].tolist()


def category_counts() -> dict[str, int]:
    csv_path = ML_ROOT / "artifacts" / "queue_full.csv"
    if not csv_path.exists():
        return {
            "no_action_needed": 700,
            "review_no_profitable_offer": 18,
            "review_no_applicable_offer": 3,
        }
    try:
        df = pd.read_csv(csv_path)
        counts = df["status"].value_counts().to_dict()
        return {
            "no_action_needed": int(counts.get("no_action_needed", 0)),
            "review_no_profitable_offer": int(counts.get("review_no_profitable_offer", 0)),
            "review_no_applicable_offer": int(counts.get("review_no_applicable_offer", 0)),
        }
    except Exception:
        return {
            "no_action_needed": 700,
            "review_no_profitable_offer": 18,
            "review_no_applicable_offer": 3,
        }


def load_category_ids(category: str) -> list[str]:
    csv_path = ML_ROOT / "artifacts" / "queue_full.csv"
    if not csv_path.exists():
        return []
    try:
        df = pd.read_csv(csv_path)
        if category == "all_scored":
            return df["customer_id"].tolist()
        elif category in ("no_action_needed", "review_no_profitable_offer", "review_no_applicable_offer"):
            return df[df["status"] == category]["customer_id"].tolist()
        return []
    except Exception:
        return []


def load_actioned(log_path: Path | None = None) -> dict[str, dict]:
    path = log_path or (ML_ROOT / "artifacts" / "actions" / "actions.jsonl")
    if not path.exists():
        return {}
    records: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        return {}

    records.sort(key=lambda r: r.get("acted_at", ""))
    result: dict[str, dict] = {}
    for r in records:
        cid = r.get("customer_id")
        if cid:
            result[cid] = r
    return result


def init_state() -> QueueState:
    try:
        cap = fixtures.queue()["capacity"]
    except Exception:
        cap = 40
    st = QueueState(
        eligible_ids=load_eligible_ids(),
        capacity=cap,
        actioned=load_actioned(),
    )
    st._last_pending_snapshot = set(st.active_ids())
    return st


state: QueueState = init_state()
