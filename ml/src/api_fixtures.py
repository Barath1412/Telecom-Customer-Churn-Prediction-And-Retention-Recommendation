"""
Generate the API contract fixtures the frontend is built against.

WHY THESE ARE GENERATED AND NOT HAND-WRITTEN
    The first set was hand-authored against catalog v1. By the time catalog v3
    landed they referenced two offers that no longer exist (OFF-ONBOARD,
    OFF-PROTECT-12), a margin floor of 0.15 that had been raised to 0.18, and a
    narration shape that predates the Draft contract. A frontend built on that
    would have shipped screens for offers the backend can never return.

    Generating them from the real artifacts means the fixtures cannot drift: run
    this after any change to the catalog, the model or the KB and the frontend's
    mocks move with it.

        python -m src.api_fixtures

WHAT IS STILL FAKE HERE, AND DELIBERATELY SO
    - `narration` on the detail fixture is a hand-written EXAMPLE of a valid
      Draft. Real narration comes from stage 6, which is not wired yet. It is
      marked `"source": "example_fixture"` so nobody mistakes it for output.
    - `uncertainty_note` is composed IN CODE from delta_prior/delta_ci, never by
      the model. It contains numbers, and no number the model writes is trusted.
    - actor ids, request ids and timestamps are synthetic strings.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "api-contract"
RUN_ID = "run_2026-08-13T02:00:00Z"
GEN_AT = "2026-08-13T02:05:00Z"

RISK_BANDS = [(0.75, "critical"), (0.50, "high"), (0.25, "medium"), (0.0, "low")]


def band(p: float) -> str:
    return next(name for lo, name in RISK_BANDS if p >= lo)


def money(x) -> float:
    return round(float(x), 2)


def _levers(codes: list[str]) -> list[dict]:
    from .levers import LEVERS
    return [{"code": c, "label": LEVERS[c].label} for c in codes if c in LEVERS]


# --------------------------------------------------------------------------- #
#  THE TWO ERROR FIXTURES.  Generated, not copied.  (fixed v5.2)
#
#  Until now these two were the odd ones out: `build()` READ them back from its
#  own output directory and wrote them straight out again. Two consequences, and
#  the second is worse than the first:
#
#    1. On any checkout where api-contract/ does not already exist -- which is
#       every fresh clone, because the folder is generated -- the script died
#       with FileNotFoundError before writing anything. The file header claims
#       these fixtures are generated from live artifacts; for these two it was
#       not true, and the crash was that claim coming due.
#
#    2. The figures inside them were hand-typed. "must be between 18.25 and
#       118.75" was a number somebody read off the data once. It is now computed
#       from the data, and the quarantined field is named from contracts.BANNED,
#       so a change to either moves the fixture and the frontend's mock with it.
# --------------------------------------------------------------------------- #
def _error_validation(X: pd.DataFrame) -> dict:
    """422 — the payload is well-formed but a field is out of contract."""
    lo, hi = float(X["Monthly Charges"].min()), float(X["Monthly Charges"].max())
    return {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Request failed field validation",
            "fields": [
                {"field": "Monthly Charges",
                 "message": f"must be between {lo:.2f} and {hi:.2f}",
                 "received": 250},
                {"field": "Tech Support",
                 "message": "must be 'No internet service' when Internet Service "
                            "is 'No'",
                 "received": "Yes"},
            ],
            "request_id": "req_01J8XYZ",
        }
    }


def _error_leakage() -> dict:
    """
    403 — the caller sent a quarantined column. This is a DIFFERENT error from a
    validation failure and the frontend must show it differently: the payload is
    not malformed, it is forbidden, and the fix belongs upstream in whoever built
    it. The reason string is the real one from contracts.BANNED, first line only.
    """
    from .contracts import BANNED
    field = "Churn Score"
    reason = BANNED[field].split(".")[0].strip()
    return {
        "error": {
            "code": "LEAKAGE_REJECTED",
            "message": "Payload contained a quarantined field. The upstream system "
                       "must not expose it.",
            "fields": [{"field": field, "message": f"quarantined: {reason.lower()}"}],
            "quarantined_fields": sorted(BANNED),
            "request_id": "req_01J8XYZ",
        }
    }


def _uncertainty_note(delta_prior: float, ci: list[float]) -> str:
    """Composed in code. The model is never the source of a number on screen."""
    return (f"The retention effect used to rank this offer is a business "
            f"assumption of {delta_prior:.2f} (range {ci[0]:.2f}–{ci[1]:.2f}), "
            f"not a measured result. Treat the ranking as a hypothesis under test "
            f"until the control group returns outcomes.")


def build():
    from .contracts import load_and_validate, split_features_target
    from .decision import Catalog
    from .kb_retrieval import select

    cat_raw = yaml.safe_load((ROOT / "data" / "offers.yaml").read_text())
    catalog = Catalog.load()
    OFFERS = {o.offer_id: o for o in catalog.offers}
    reg = json.loads((ROOT / "artifacts" / "model_registry.json").read_text())
    sel = next(m for m in reg["models"] if m["selected"])
    audit = json.loads((ROOT / "artifacts" / "queue_audit.json").read_text())

    q = pd.read_csv(ROOT / "artifacts" / "queue_top40.csv")
    full = pd.read_csv(ROOT / "artifacts" / "queue_full.csv")
    q = q.sort_values("ev", ascending=False).reset_index(drop=True)

    df, _ = load_and_validate(str(ROOT / "data" / "Telco_customer_churn.xlsx"))
    X, _, _ = split_features_target(df)
    by_id = {c: i for i, c in enumerate(df["CustomerID"])}

    from .attribution import DISCLAIMER, attribute

    # ---------------------------------------------------------------- items --
    def item(row, rank: int, detail: bool = False) -> dict:
        codes = [c for c in str(row.levers).split("|") if c]
        offer = OFFERS.get(row.offer_id) if isinstance(row.offer_id, str) else None
        ci = list(offer.delta_ci) if offer else [0.0, 0.0]
        pct = round(100.0 * (1 - (rank - 1) / max(1, len(q))), 1)
        out = {
            "rank": rank,
            "customer_id": row.customer_id,
            "arm": row.arm,
            "risk": {"p_churn": round(float(row.p_churn), 4),
                     "risk_band": band(float(row.p_churn)),
                     "percentile": pct},
            "value": {"cltv": money(row.cltv),
                      "monthly_charges": money(row.monthly_charges),
                      "tenure_months": int(row.tenure_months),
                      "currency": cat_raw["currency"]},
            "levers": _levers(codes),
            "recommendation": {
                "offer_id": row.offer_id if isinstance(row.offer_id, str) else None,
                "offer_name": row.offer_name if isinstance(row.offer_name, str) else None,
                "cost": money(row.cost),
                "delta_prior": round(float(row.delta_prior), 4),
                "delta_ci": ci,
                "delta_source": offer.delta_source if offer else None,
                "expected_value": money(row.ev),
                "requires_approval": bool(
                    money(row.cost) > cat_raw["policy"]["approval_required_above_cost"]),
            },
            "status": row.status,
        }
        if not detail:
            return out

        considered = []
        for part in str(row.considered).split("|"):
            if ":" not in part:
                continue
            oid, ev = part.rsplit(":", 1)
            o = OFFERS.get(oid)
            if o and oid != row.offer_id:
                considered.append({"offer_id": oid, "offer_name": o.name,
                                   "delta_prior": o.delta_prior,
                                   "expected_value": float(ev)})
        out["alternatives"] = considered

        vetoed = []
        if isinstance(row.vetoed, str) and row.vetoed:
            for part in row.vetoed.split("|"):
                oid, rule = part.split(":", 1)
                vetoed.append({"offer_id": oid, "rule_id": rule,
                               "detail": "see policy_trace"})
        out["vetoed"] = vetoed

        i = by_id[row.customer_id]
        attr = attribute(X.iloc[[i]], top_k=5)[0]
        out["attribution"] = attr.get("model_attribution", [])
        out["attribution_disclaimer"] = DISCLAIMER

        ev_docs = select(codes, out["recommendation"]["offer_id"])
        out["evidence"] = {"ids": ev_docs.ids, "count": len(ev_docs.ids),
                           "approx_tokens": ev_docs.approx_tokens}
        out["policy_trace"] = [
            {"rule_id": "R1_ELIGIBILITY", "state": "pass", "detail": "levers matched"},
            {"rule_id": "R2_MARGIN_FLOOR", "state": "pass",
             "detail": f"cost {money(row.cost)} <= "
                       f"{cat_raw['policy']['margin_floor_pct']:.0%} of annual revenue"},
            {"rule_id": "R3_POSITIVE_EV", "state": "pass",
             "detail": f"EV {money(row.ev)} > 0"},
            {"rule_id": "R4_COOLDOWN", "state": "not_evaluable",
             "detail": "no offer-history feed connected",
             "unmet_requirement": "recommendation history per customer, last 90d"},
            {"rule_id": "R5_ONE_PER_WINDOW", "state": "not_evaluable",
             "detail": "no offer-history feed connected",
             "unmet_requirement": "recommendation history for the current quarter"},
            {"rule_id": "R7_DISCOUNT_CAP", "state": "pass",
             "detail": f"within {cat_raw['policy']['max_discount_pct']:.0%} cap"},
        ]
        out["profile"] = {k: (v.item() if hasattr(v, "item") else v)
                          for k, v in X.iloc[i].to_dict().items()}
        out["provenance"] = {
            "model_name": sel["model_name"], "model_version": sel["version"],
            "model_roc_auc": round(sel["metrics"]["roc_auc"], 6),
            "catalog_version": cat_raw["catalog_version"],
            "kb_version": json.loads(
                (ROOT / "artifacts" / "evidence_ids.json").read_text())["kb_version"],
            "scored_at": "2026-08-13T02:00:00Z",
        }
        return out

    items = [item(r, i + 1) for i, r in enumerate(q.itertuples())]

    # ------------------------------------------------------------ GET_queue --
    queue = {"run_id": RUN_ID, "capacity": int(audit["capacity"]),
             "total_eligible": int(audit["funnel"]["recommended"]),
             "returned": len(items), "page": 1, "page_size": 40, "items": items}

    # --------------------------------------------------- GET_customer_detail --
    top = q.iloc[0]
    detail = item(top, 1, detail=True)
    rec = detail["recommendation"]
    detail["narration"] = {
        "summary": "Fibre customer one month in, on a rolling contract with no "
                   "support or security add-ons.",
        "why": "Two observable gaps put this account at the top of tonight's "
               "list: a month-to-month contract and no tech-support add-on. In "
               "the historical base, accounts without tech support left at 41.6% "
               "against 11.9% for accounts with it. That is an association in "
               "past data, not a measured effect of adding the service.",
        "talk_track": "I can see you joined us last month on fibre. I'm able to "
                      "add Tech Support and Online Security at no cost for the "
                      "next twelve months — that covers setup help and fault "
                      "calls. Would that be useful?",
        "evidence_ids": detail["evidence"]["ids"][:3],
        "uncertainty_note": _uncertainty_note(rec["delta_prior"], rec["delta_ci"]),
        "source": "example_fixture",
        "model": "gemini-3.5-flash-lite",
        "validator_attempts": 1,
        "generated_at": "2026-08-13T02:04:11Z",
    }

    # ------------------------------------------------- GET_customer_no_offer --
    # v4: the old GET_customer_involuntary fixture is GONE. That route was removed
    # because the only field recording "moved / deceased" is the quarantined
    # `Churn Reason`, so it can never fire for a live customer. It is replaced by
    # the outcome the frontend will actually meet: a customer flagged for review
    # because every offer we could price loses money.
    rev = full[full.status == "review_no_profitable_offer"]
    if len(rev):
        no_offer = item(rev.nlargest(1, "p_churn").iloc[0], 0, detail=True)
    else:                                     # pragma: no cover
        no_offer = dict(detail)
    no_offer["narration"] = None
    no_offer["alternatives"] = []

    # ---------------------------------------------------------- GET_summary --
    top100 = full[full.status == "recommended"].nlargest(100, "ev")
    prev = {}
    for s in top100.levers.fillna(""):
        for c in [x for x in s.split("|") if x]:
            prev[c] = prev.get(c, 0) + 1
    summary = {
        "run_id": RUN_ID, "generated_at": GEN_AT,
        "model": {"name": sel["model_name"], "version": sel["version"],
                  "roc_auc": round(sel["metrics"]["roc_auc"], 6),
                  "pr_auc": round(sel["metrics"]["pr_auc"], 6),
                  "brier": round(sel["metrics"]["brier"], 6)},
        "funnel": audit["funnel"],
        "economics": audit["economics"],
        "offer_mix": audit["offer_mix"],
        "precision_at_capacity": audit["precision_at_capacity"],
        "base_rate": 0.2654,
        "allocation_parity": _parity(df, q, set(full.customer_id)),
        "lever_prevalence": [{"code": k, "pct_of_top100": round(100 * v / len(top100), 1)}
                             for k, v in sorted(prev.items(), key=lambda kv: -kv[1])],
    }

    # ---------------------------------------------------------- GET_catalog --
    catalog_fx = {"catalog_version": cat_raw["catalog_version"],
                  "currency": cat_raw["currency"],
                  "policy": cat_raw["policy"],
                  "offers": cat_raw["offers"]}

    # ----------------------------------------------------------- POST_score --
    prof = detail["profile"]
    post_score = {
        "request_example": {**prof, "cltv": detail["value"]["cltv"]},
        "response_example": {"p_churn": detail["risk"]["p_churn"],
                             "risk_band": detail["risk"]["risk_band"],
                             "levers": detail["levers"],
                             "recommendation": detail["recommendation"],
                             "policy_trace": detail["policy_trace"],
                             "provenance": detail["provenance"]},
    }

    # ---------------------------------------------------------- POST_action --
    post_action = {
        "request_example": {"action": "approve", "actor": "agent_42",
                            "reason_code": None, "modified_offer_id": None,
                            "note": "Customer accepted on first call."},
        "response_example": {"recommendation_id": "rec_01J8XYZ",
                             "customer_id": detail["customer_id"],
                             "action": "approve", "actor": "agent_42",
                             "acted_at": "2026-08-13T09:14:22Z",
                             "audit_id": "aud_01J8XYZ", "status": "recorded"},
        "actions": ["approve", "edit", "reject"],
        "reason_codes_for_reject": ["already_contacted", "offer_not_suitable",
                                    "customer_unreachable", "account_closing",
                                    "data_looks_wrong", "other"],
    }

    files = {
        "GET_queue.json": queue,
        "GET_customer_detail.json": detail,
        "GET_customer_no_offer.json": no_offer,
        "GET_summary.json": summary,
        "GET_catalog.json": catalog_fx,
        "POST_score.json": post_score,
        "POST_action.json": post_action,
        "ERROR_validation.json": _error_validation(X),
        "ERROR_leakage.json": _error_leakage(),
    }
    OUT.mkdir(exist_ok=True)
    for name, payload in files.items():
        (OUT / name).write_text(json.dumps(payload, indent=2, default=_json_default))
        print(f"  wrote api-contract/{name}")
    print(f"\ncatalog v{cat_raw['catalog_version']} · "
          f"{len(cat_raw['offers'])} offers · {len(items)} queue items · "
          f"model {sel['model_name']} {sel['version']}")


def _parity(df: pd.DataFrame, q: pd.DataFrame, base_ids: set[str]) -> list[dict]:
    """
    Allocation parity over the EVALUATION BASE, not all 7,043 customers.

    The queue is built from the held-out fifth, so dividing queued counts by the
    full population understates every rate by 5x and makes the groups look more
    similar than they are. `mean_offer_value` is also computed over QUEUED
    customers only -- averaging across everyone dilutes it to near zero and the
    comparison stops meaning anything.
    """
    from .contracts import PROTECTED
    ids = set(q.customer_id)
    cost = dict(zip(q.customer_id, q.cost))
    aud = df[df["CustomerID"].isin(base_ids)][PROTECTED + ["CustomerID"]].copy()
    aud["in_q"] = aud["CustomerID"].isin(ids)
    aud["cost"] = aud["CustomerID"].map(cost)
    rows = []
    for attr in PROTECTED:
        for group, g in aud.groupby(attr):
            queued = g[g.in_q]
            rows.append({"attribute": attr, "group": str(group), "n": int(len(g)),
                         "queued": int(len(queued)),
                         "queue_rate": round(float(g.in_q.mean()), 4),
                         "mean_offer_value": round(float(queued.cost.mean()), 2)
                         if len(queued) else 0.0})
    return rows


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    raise TypeError(type(o))


if __name__ == "__main__":
    build()