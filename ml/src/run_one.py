"""
Run the graph for ONE customer and print every node as it fires.

This is the tool for checking the flow by hand.

    python -m src.run_one samples/01_recommended_top_value.json
    python -m src.run_one samples/02_review_no_profitable_offer.json
    python -m src.run_one samples/04_no_action_needed.json          # no model call

    # with a real model instead of the fake one
    export GEMINI_API_KEY=...
    python -m src.run_one samples/01_recommended_top_value.json --provider gemini

    # stop at the human pause and resume in a second command
    python -m src.run_one samples/01_recommended_top_value.json --interactive
    python -m src.run_one samples/01_recommended_top_value.json --resume approve

    # make the model misbehave on purpose, to watch the retry and fallback
    python -m src.run_one samples/01_recommended_top_value.json --script invented_discount,ok
    python -m src.run_one samples/01_recommended_top_value.json --script wrong_offer,causal_claim
"""
from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CKPT = ROOT / "artifacts" / "run_one_checkpoints.sqlite"
NOTES = ROOT / "artifacts" / "run_one_notes.jsonl"
PAUSED = ROOT / "artifacts" / "run_one_paused.json"   # customer_id -> thread_id

B, D, G, Y, R, V, X = ("\033[1m", "\033[2m", "\033[32m", "\033[33m",
                       "\033[31m", "\033[35m", "\033[0m")


def _hdr(s: str) -> None:
    print(f"\n{B}{'─' * 78}\n{s}\n{'─' * 78}{X}")


def _show_state(st: dict) -> None:
    # ---- THE ACCOUNT REFERENCE, RENDERED FROM THE RECORD ------------------ #
    # These are the fields an agent wants in front of them, and they are printed
    # deterministically from state -- never asked of the model. Re-typing a known
    # fact through a language model adds a hallucination surface and no information.
    c = st.get("customer") or {}
    print(f"  {B}ACCOUNT{X}")
    print(f"    tenure          {st.get('tenure_months')} months")
    print(f"    monthly charge  ${st.get('monthly_charges', 0):,.2f}")
    print(f"    lifetime value  ${st.get('cltv', 0):,.0f}")
    for k in ("Contract", "Internet Service", "Payment Method", "Tech Support",
              "Online Security", "Device Protection", "Senior Citizen"):
        if k in c:
            print(f"    {k:<15} {c[k]}")

    band = st.get("risk_vs_base") or "?"
    band_c = R if band == "above" else (Y if band == "at" else D)
    print(f"\n  status            {B}{st.get('status')}{X}")
    print(f"  churn risk        {st.get('p_churn')}   "
          f"{band_c}{band} the 26.54% portfolio average{X}")
    print(f"  levers            {st.get('lever_labels') or '(none)'}")
    print(f"  {D}  lever codes     {', '.join(st.get('levers') or []) or '(none)'}{X}")
    if st.get("offer_id"):
        print(f"  offer             {G}{st['offer_id']}{X} — {st.get('offer_name')}")
        print(f"  cost / EV         ${st.get('cost', 0):,.2f}  /  ${st.get('ev', 0):,.2f}"
              f"   {D}(internal — not in the note){X}")
    else:
        print(f"  offer             {Y}none survived{X}")
    floor = float(st.get("min_ev_floor") or 0)
    if st.get("considered"):
        for c2 in st["considered"]:
            mark = G if c2["ev"] >= floor else R
            print(f"      considered    {c2['offer_id']:<20} cost ${c2['cost']:>8.2f}  "
                  f"EV {mark}${c2['ev']:>9.2f}{X}")
    if floor:
        print(f"  {D}minimum EV        ${floor:,.2f}  — an action must be worth at least "
              f"this to be queued{X}")
    if st.get("rules_not_evaluable"):
        print(f"  {Y}not evaluable{X}     {', '.join(st['rules_not_evaluable'])}")
    print(f"  evidence          {len(st.get('evidence_ids') or [])} documents: "
          f"{', '.join((st.get('evidence_ids') or [])[:6])}"
          f"{' …' if len(st.get('evidence_ids') or []) > 6 else ''}")
    print(f"  mode              {st.get('mode')}")
    print(f"  attempts          {st.get('attempts')}")
    src = st.get("source")
    colour = V if src == "llm" else (Y if src == "fallback_template" else D)
    print(f"  note source       {colour}{src}{X}")
    if st.get("violations"):
        print(f"  {R}violations{X}")
        for v in st["violations"]:
            print(f"      {R}✗{X} {v}")
    # v5.4 — every attempt, even the ones the fallback erased. When a note ends as
    # `fallback_template` the current violations list is empty, so without this the
    # screen showed a clean run that had in fact been rejected twice.
    hist = st.get("violation_history") or []
    if any(h["outcome"] != "clean" for h in hist):
        print(f"  {B}attempt history{X}")
        for h in hist:
            colour = G if h["outcome"] == "clean" else R
            print(f"      attempt {h['attempt']}  {colour}{h['outcome']}{X}"
                  f"  {D}{h.get('model') or '-'}{X}")
            for v in h["violations"]:
                print(f"          {R}✗{X} {v}")
    d = st.get("draft")
    if d:
        print(f"\n  {B}THE NOTE{X}")
        print(f"    summary     {d['summary']}")
        for label, key in (("why", "why"), ("talk track", "talk_track")):
            words = d[key].split()
            lines, cur = [], ""
            for w in words:
                if len(cur) + len(w) > 66:
                    lines.append(cur); cur = w
                else:
                    cur = f"{cur} {w}".strip()
            lines.append(cur)
            print(f"    {label:<11} {lines[0]}")
            for ln in lines[1:]:
                print(f"                {ln}")
        print(f"    evidence    {', '.join(d['evidence_ids'])}")
    print(f"\n  {B}TRACE{X}  {' → '.join(st.get('trace') or [])}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sample", help="path to a samples/*.json file")
    # DEFAULT IS None, NOT "fake".
    # It was "fake", which silently overrode NARRATION_PROVIDER=gemini in .env --
    # so somebody could paste a real key, run this, and get the stub client's canned
    # text while the header cheerfully said "provider fake". The env var now wins,
    # and the header below states which client actually ran and whether a key exists.
    ap.add_argument("--provider", default=None,
                    help="fake | gemini   (default: NARRATION_PROVIDER from .env, "
                         "else fake)")
    ap.add_argument("--script", default=None,
                    help="comma-separated FakeClient behaviours, e.g. "
                         "invented_discount,ok  or  wrong_offer,causal_claim")
    ap.add_argument("--interactive", action="store_true",
                    help="stop at human_review; resume with --resume")
    ap.add_argument("--resume", default=None,
                    help="approve | edit | reject — resume a paused run")
    a = ap.parse_args()

    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.types import Command
    from .graph import compile_graph
    from .narration_client import FakeClient, build_client

    import os
    payload = json.loads(Path(a.sample).read_text())
    cid = payload["customer_id"]
    provider = (a.provider or os.environ.get("NARRATION_PROVIDER") or "fake").lower()
    if a.script:
        client, provider = FakeClient(script=a.script.split(",")), "fake (scripted)"
    else:
        client = build_client(provider)

    _hdr(f"CUSTOMER {cid}   ·   {Path(a.sample).name}")
    print(f"  {D}{payload.get('_comment', '')}{X}")
    print(f"  expected status   {payload.get('_expected_status')}")
    key = os.environ.get("GEMINI_API_KEY")
    print(f"  provider          {B}{provider}{X}"
          + (f"   script={a.script}" if a.script else ""))
    print(f"  GEMINI_API_KEY    " + (f"found (…{key[-4:]})" if key else f"{D}not set{X}"))
    if provider.startswith("fake"):
        print(f"  {Y}NOTE: this is the stub client. The note below is canned text, not "
              f"model output.{X}")
        print(f"  {D}      set NARRATION_PROVIDER=gemini in .env, or pass "
              f"--provider gemini{X}")

    interactive = a.interactive or a.resume
    # ONE THREAD PER INVOCATION, UNLESS YOU ARE USING THE PAUSE.
    #
    # The thread id used to be `run_one:<customer_id>` against a PERSISTENT sqlite
    # file, so running the same customer twice reused the same thread -- and `trace`
    # is rebuilt from checkpointed state, so the second run's steps were APPENDED to
    # the first run's list. The output read as though the whole graph had run twice
    # in one go, which looked exactly like a resume bug and was not one. Both runs
    # were correct; only the display lied.
    #
    # --interactive / --resume need a STABLE id -- that pair is the whole point of the
    # checkpoint surviving a process boundary -- but a FRESH one each time you start a
    # new pause, or repeated demo cycles pile up in the same thread. So the id is
    # generated when the pause starts and written to a tiny pointer file that --resume
    # reads back. One paused run per customer at a time, which is the real workflow.
    thread = f"run_one:{cid}:{uuid.uuid4().hex[:8]}"
    if a.resume:
        pending = json.loads(PAUSED.read_text()) if PAUSED.exists() else {}
        if cid not in pending:
            print(f"  {R}nothing paused for {cid}{X} — start one with --interactive")
            return 1
        thread = pending[cid]
    elif a.interactive:
        pending = json.loads(PAUSED.read_text()) if PAUSED.exists() else {}
        pending[cid] = thread
        PAUSED.parent.mkdir(exist_ok=True)
        PAUSED.write_text(json.dumps(pending, indent=2))
    CKPT.parent.mkdir(exist_ok=True)
    with SqliteSaver.from_conn_string(str(CKPT)) as cp:
        app = compile_graph(cp)
        cfg = {"configurable": {
            "thread_id": thread,
            "auto_approve": not interactive,
            "client": client,
            # Every run is appended here, so a real model call is never thrown away.
            "narrations_path": str(NOTES),
            # Only the fields the sample file states. persist() skips the rest.
            "expected_decision": {k: v for k, v in (
                ("offer_id", payload.get("_expected_offer_id")),
                ("ev", payload.get("_expected_expected_value"))) if v is not None},
        }}
        if a.resume:
            _hdr(f"RESUMING the paused run with: {a.resume}")
            app.invoke(Command(resume={"action": a.resume, "actor": "agent_42",
                                       "note": "resumed from the command line"}), cfg)
        else:
            app.invoke({"customer_id": cid, "customer": payload["customer"],
                        "cltv": float(payload["cltv"])}, cfg)

        snap = app.get_state(cfg)
        st = dict(snap.values)
        _hdr("RESULT")
        _show_state(st)

        if snap.next:
            print(f"\n  {Y}⏸  PAUSED at {snap.next[0]}{X} — the graph is waiting for a "
                  f"human. State is saved in\n     "
                  f"{CKPT.relative_to(ROOT)}. Resume with:\n"
                  f"     python -m src.run_one {a.sample} --resume approve")
        else:
            print(f"\n  {G}✓ complete{X}   agent_action = {st.get('agent_action')} "
                  f"(actor: {st.get('agent_actor')})")
            exp = payload.get("_expected_status")
            if exp and st.get("status") != exp:
                print(f"  {R}✗ status mismatch: expected {exp}{X}")
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
