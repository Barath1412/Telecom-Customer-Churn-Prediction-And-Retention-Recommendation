#!/usr/bin/env bash
# Start the API, after checking the three things that actually go wrong.
#
#   ./run.sh                 provider from NARRATION_PROVIDER, default gemini
#   ./run.sh fake            force the stub client — no key, no network, no cost
#   ./run.sh gemini 8001     provider and port
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
PROVIDER="${1:-${NARRATION_PROVIDER:-gemini}}"
PORT="${2:-8000}"

fail() { printf '\n  ERROR: %s\n\n' "$1" >&2; exit 1; }

[ -d "$ROOT/ml/src" ] || fail "no ml/src at $ROOT/ml. Is the ML project in place?"
[ -f "$ROOT/ml/artifacts/churn_model_v1.joblib" ] || \
  fail "no trained model at ml/artifacts/churn_model_v1.joblib"
[ -d "$ROOT/retention-console-frontend/api-contract" ] || \
  fail "no api-contract at $ROOT/retention-console-frontend/api-contract"

python -c "import fastapi, uvicorn" 2>/dev/null || \
  fail "fastapi/uvicorn missing. Run: pip install -r $HERE/requirements.txt"
python -c "import xgboost, langgraph" 2>/dev/null || \
  fail "the pipeline's deps are missing. Run: pip install -r $ROOT/ml/requirements.txt"

if [ "$PROVIDER" = "gemini" ] && [ ! -f "$ROOT/ml/.env" ]; then
  printf '\n  WARNING: no ml/.env — live narration will fail.\n'
  printf '           cp ml/.env.example ml/.env  and paste your GEMINI_API_KEY.\n\n'
fi

export NARRATION_PROVIDER="$PROVIDER"
cd "$HERE"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
