"""
Check the environment before blaming the code.

    python -m src.doctor

Written after a Windows run produced seven InconsistentVersionWarnings and a silent
SHAP failure, because scikit-learn was 1.7.1 and the model was pickled with 1.8.0.
Everything still ran, which is the design working -- but nobody should have to read
a stack of warnings to find that out.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
G, Y, R, D, B, X = ("\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m")

# The versions the model artifact was pickled with. Older than these and joblib
# warns; SHAP may fail outright.
BUILT_WITH = {"scikit-learn": "1.8.0", "xgboost": "3.2.0", "numpy": "2.4.4",
              "pandas": "3.0.2", "python": "3.11"}
REQUIRED = ["pandas", "numpy", "sklearn", "xgboost", "joblib", "yaml", "pydantic",
            "langgraph", "langgraph.checkpoint.sqlite"]
OPTIONAL = {"shap": "SHAP attribution (node 2). Without it the graph still runs, "
                    "but the note has no 'what moved the score' section.",
            "google.genai": "only needed for --provider gemini"}
FILES = ["artifacts/churn_model_v1.joblib", "artifacts/model_registry.json",
         "artifacts/evidence_ids.json", "data/offers.yaml",
         "data/kb/knowledge_base.md", "samples/01_recommended_top_value.json"]

PKG_NAME = {"sklearn": "scikit-learn", "yaml": "pyyaml", "google.genai": "google-genai"}


def _ver(mod: str) -> str | None:
    try:
        m = importlib.import_module(mod)
    except Exception:
        return None
    return getattr(m, "__version__", "installed")


def _cmp(name: str, have: str, want: str) -> tuple[str, str]:
    def parts(v):
        out = []
        for p in v.split("."):
            digits = "".join(c for c in p if c.isdigit())
            out.append(int(digits) if digits else 0)
        return out
    h, w = parts(have), parts(want)
    if h >= w:
        return G, "ok"
    return Y, f"OLDER than the {want} the model was pickled with"


def main() -> int:
    problems, warnings = [], []
    print(f"{B}PYTHON{X}")
    pyv = ".".join(map(str, sys.version_info[:3]))
    col, note = _cmp("python", pyv, BUILT_WITH["python"])
    print(f"  {col}{pyv:<12}{X} {note}   {D}{sys.executable}{X}")
    if sys.version_info < (3, 10):
        problems.append("Python 3.10 or newer is required")

    print(f"\n{B}REQUIRED PACKAGES{X}")
    for mod in REQUIRED:
        v = _ver(mod)
        pretty = PKG_NAME.get(mod, mod)
        if v is None:
            print(f"  {R}{'MISSING':<12}{X} {pretty}")
            problems.append(f"pip install {pretty}")
            continue
        want = BUILT_WITH.get(pretty)
        if want:
            col, note = _cmp(pretty, v, want)
            print(f"  {col}{v:<12}{X} {pretty:<28}{note}")
            if col == Y:
                warnings.append(f'pip install -U "{pretty}>={want}"')
        else:
            print(f"  {G}{v:<12}{X} {pretty}")

    print(f"\n{B}OPTIONAL{X}")
    for mod, why in OPTIONAL.items():
        v = _ver(mod)
        pretty = PKG_NAME.get(mod, mod)
        if v:
            print(f"  {G}{v:<12}{X} {pretty:<28}{D}{why}{X}")
        else:
            print(f"  {Y}{'absent':<12}{X} {pretty:<28}{D}{why}{X}")

    print(f"\n{B}FILES{X}")
    for f in FILES:
        p = ROOT / f
        if p.exists():
            print(f"  {G}{'ok':<12}{X} {f:<44}{D}{p.stat().st_size:>10,} bytes{X}")
        else:
            print(f"  {R}{'MISSING':<12}{X} {f}")
            problems.append(f"missing file: {f}")

    print(f"\n{B}LLM PROVIDER{X}")
    from .narration_client import load_dotenv
    found = load_dotenv()
    env_file = ROOT / ".env"
    print(f"  {'.env':<14}" + (f"{G}found{X}   {D}{len(found)} keys read{X}"
                               if env_file.exists() else
                               f"{Y}absent{X}  {D}cp .env.example .env{X}"))
    provider = (os.environ.get("NARRATION_PROVIDER") or "fake").lower()
    key = os.environ.get("GEMINI_API_KEY")
    print(f"  {'provider':<14}{provider}")
    if key and key not in ("", "paste-your-key-here"):
        print(f"  {'GEMINI_API_KEY':<15}{G}set{X}  {D}…{key[-4:]}{X}")
    else:
        col = Y if provider == "fake" else R
        print(f"  {'GEMINI_API_KEY':<15}{col}not set{X}  "
              f"{D}fine for --provider fake; required for gemini{X}")
        if provider == "gemini":
            problems.append("NARRATION_PROVIDER=gemini but GEMINI_API_KEY is not set")

    print(f"\n{B}SMOKE TEST{X}  one customer through all nine nodes, stub client")
    try:
        from .graph import compile_graph
        from .narration_client import FakeClient
        p = json.loads((ROOT / "samples/01_recommended_top_value.json").read_text())
        out = compile_graph().invoke(
            {"customer_id": p["customer_id"], "customer": p["customer"],
             "cltv": float(p["cltv"])},
            {"configurable": {"thread_id": "doctor", "auto_approve": True,
                              "client": FakeClient()}})
        assert out["status"] == p["_expected_status"]
        assert out["draft"] is not None
        print(f"  {G}pass{X}  {' → '.join(out['trace'])}")
        if not out.get("attribution"):
            warnings.append("SHAP produced no attribution — see the OPTIONAL section")
    except Exception as e:
        print(f"  {R}FAIL{X}  {type(e).__name__}: {e}")
        problems.append(f"smoke test failed: {type(e).__name__}")

    print()
    if problems:
        print(f"{R}{B}{len(problems)} problem(s) to fix:{X}")
        for x in problems:
            print(f"  {R}✗{X} {x}")
    if warnings:
        print(f"{Y}{B}{len(warnings)} thing(s) worth fixing:{X}")
        for x in warnings:
            print(f"  {Y}!{X} {x}")
    if not problems and not warnings:
        print(f"{G}{B}Everything checks out.{X}")
    elif not problems:
        print(f"\n{G}The graph will run.{X} The warnings above cause the "
              f"InconsistentVersionWarning noise and can disable SHAP.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
