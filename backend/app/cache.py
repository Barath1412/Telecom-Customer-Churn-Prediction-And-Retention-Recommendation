"""
Cache for LLM narrations.

A cache file (ml/artifacts/runs/live_cache/narrations.jsonl), not a database.
Keeps an in-memory dict refreshed at startup and updated as new notes come in.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .settings import ML_ROOT

CACHE_PATH = ML_ROOT / "artifacts" / "runs" / "live_cache" / "narrations.jsonl"

cached: dict[str, dict[str, Any]] = {}


def load() -> dict[str, dict[str, Any]]:
    """customer_id -> last narration record for that id in the file."""
    global cached
    if not CACHE_PATH.exists():
        cached = {}
        return {}
    out: dict[str, dict[str, Any]] = {}
    for line in CACHE_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            if "customer_id" in rec:
                out[rec["customer_id"]] = rec
        except Exception:
            continue
    cached = out
    return out


def append(record: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


async def autowarm(missing_ids: list[str]) -> None:
    """Warm missing notes in the background, one at a time (skips control-arm customers)."""
    from . import fixtures, narrate as narrate_mod, settings  # noqa: PLC0415

    control_ids = {
        item["customer_id"]
        for item in fixtures.queue().get("items", [])
        if item.get("arm") == "control"
    }
    to_warm = [cid for cid in missing_ids if cid not in control_ids]

    print(f"[cache] warming {len(to_warm)} notes in the background...", flush=True)
    for i, cid in enumerate(to_warm, 1):
        try:
            result = await narrate_mod.narrate(cid, provider=settings.NARRATION_PROVIDER)
            rec = {**result, "customer_id": cid}
            append(rec)
            cached[cid] = rec
            print(f"[cache] {i}/{len(to_warm)} warmed ({cid})", flush=True)
        except Exception as e:
            print(f"[cache] {i}/{len(to_warm)} FAILED ({cid}): {e}", flush=True)
        await asyncio.sleep(1)  # be polite to the Gemini rate limit
    print("[cache] warm-up complete.", flush=True)
