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
    # customer_id -> the FULL action record: {action, offer_id, modified_offer_id,
    # reason_code, actor, note, acted_at}. Store the whole thing, not just
    # action/acted_at — the Approved/Rejected views need to say *which offer* was
    # actually decided on, not just that something was decided.
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
        """
        The offer actually decided on for this customer — the whole reason this
        method exists. `modified_offer_id` wins if the agent used "Edit offer" /
        "Present this instead" to swap away from the model's top pick; otherwise
        it's the original `offer_id` recorded at the moment of the action. Never
        recompute this from a live re-run of the graph — the model's current top
        pick can differ from what was actually offered days or minutes ago, and
        this method is the one place that must not drift from what really
        happened.
        """
        rec = self.actioned.get(customer_id)
        if not rec:
            return None
        return rec.get("modified_offer_id") or rec.get("offer_id")

    def record_action(self, customer_id: str, record: dict) -> list[str]:
        """
        Apply a full action record (as written to actions.jsonl) and return
        newly-promoted customer ids (for auto-warm). `record` must contain at
        least `action` and `acted_at`; `offer_id`/`modified_offer_id` should be
        included whenever available so `offered_offer_id()` stays accurate.
        """
        before = set(self.active_ids())
        self.actioned[customer_id] = record
        after = set(self.active_ids())
        promoted = after - before
        self._last_pending_snapshot = after
        return list(promoted)


def load_eligible_ids() -> list[str]:
    csv_path = ML_ROOT / "artifacts" / "queue_full.csv"
    if not csv_path.exists():
        return []
    df = pd.read_csv(csv_path)
    rec_df = df[df["status"] == "recommended"].sort_values("ev", ascending=False).reset_index(drop=True)
    return rec_df["customer_id"].tolist()


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
