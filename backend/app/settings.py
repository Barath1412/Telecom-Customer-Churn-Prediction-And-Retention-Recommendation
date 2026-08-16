"""
Every path is resolved from THIS FILE's location, never from the working directory.

That matters more than it looks. The ML package already does the same thing
(`ROOT = Path(__file__).resolve().parent.parent` in graph.py, decision.py and
kb_retrieval.py), which is why `python -m src.run_one` works from any folder. The
backend keeps that property, so `uvicorn app.main:app` behaves identically whether
you start it from the repo root, from backend/, or from an IDE run button.

Every value can be overridden with an environment variable, so nothing here has to
be edited to move the app.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# backend/app/settings.py -> backend/app -> backend -> repo root
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
REPO_ROOT = BACKEND_DIR.parent

ML_ROOT = Path(os.environ.get("ML_ROOT") or REPO_ROOT / "ml").resolve()

API_CONTRACT_DIR = Path(
    os.environ.get("API_CONTRACT_DIR")
    or REPO_ROOT / "retention-console-frontend" / "api-contract"
).resolve()

# --------------------------------------------------------------------------- #
#  Load ml/.env BEFORE reading any environment variable that it may supply.
#
#  Problem this fixes (FIX 3):
#      os.environ.get("NARRATION_PROVIDER") is evaluated at import time.
#      ml/src/narration_client.py calls load_dotenv() at its OWN import time,
#      which happens later (inside narrate.warm()).  So the value in ml/.env is
#      always ignored and the built-in default ("gemini") wins, even when .env
#      says NARRATION_PROVIDER=fake.
#
#  load_dotenv uses os.environ.setdefault, so a real environment variable (e.g.
#  NARRATION_PROVIDER=fake python -m uvicorn ...) still beats .env.
# --------------------------------------------------------------------------- #
if str(ML_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_ROOT))

try:
    from src.narration_client import load_dotenv as _load_dotenv  # noqa: E402

    _load_dotenv()          # reads ML_ROOT/.env; no-op if absent
except Exception:           # noqa: BLE001
    pass                    # no ml package yet (bare checkout) — proceed anyway



# gemini | fake.  `fake` runs the entire graph with a stub client: same nodes, same
# validators, same response shape, no API key and no network. Use it to test.
# Read AFTER load_dotenv() so ml/.env supplies the value when no shell var is set.
NARRATION_PROVIDER = (os.environ.get("NARRATION_PROVIDER") or "gemini").lower()

# Hard ceiling on a single live narration. A hung request in front of an audience is
# worse than an error, so this is deliberately short.
NARRATE_TIMEOUT_S = float(os.environ.get("NARRATE_TIMEOUT_S") or 30)

# The Vite dev server. vite.config.ts also proxies /api -> :8000, which makes CORS
# irrelevant in dev, but the app may be opened directly against :8000 during a demo.
CORS_ORIGINS = [
    o.strip()
    for o in (
        os.environ.get("CORS_ORIGINS")
        or "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]


def describe() -> dict:
    """Shown at startup and by /api/health, so a misconfigured path is obvious."""
    return {
        "repo_root": str(REPO_ROOT),
        "ml_root": str(ML_ROOT),
        "api_contract_dir": str(API_CONTRACT_DIR),
        "narration_provider": NARRATION_PROVIDER,
        "narrate_timeout_s": NARRATE_TIMEOUT_S,
    }
