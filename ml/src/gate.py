"""
The promotion gate: 7 assertions a model must pass before it is registered.

This is the component that makes the system trustworthy rather than merely
accurate. A model that fails any assertion is NOT written to the registry and
the build fails.

Assertion 3 is the one most teams do not have and most need: an ROC-AUC
*ceiling*. On this dataset an honest model tops out near 0.85. Anything above
0.95 is definitionally a leak, so we encode that as an automated tripwire
instead of hoping somebody notices. The notebook scored 0.977 -- this gate would
have caught it on the first run.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np

from .calibration import expected_calibration_error as ece_fn
from .contracts import BANNED, PROTECTED

AUC_FLOOR = 0.83
AUC_CEILING = 0.95          # leak canary
BRIER_MAX = 0.145
SLOPE_RANGE = (0.90, 1.10)
PARITY_MAX = 0.05          # max gap in expected calibration error between groups


@dataclass
class GateResult:
    checks: list = field(default_factory=list)

    def add(self, num, name, passed, detail):
        self.checks.append(
            {"n": num, "name": name, "passed": bool(passed), "detail": detail}
        )

    @property
    def passed(self) -> bool:
        return all(c["passed"] for c in self.checks)

    def report(self) -> str:
        lines = []
        for c in self.checks:
            mark = "PASS" if c["passed"] else "FAIL"
            lines.append(f"  [{mark}] {c['n']}. {c['name']:<34} {c['detail']}")
        verdict = "PROMOTED" if self.passed else "BLOCKED - model not registered"
        return "\n".join(lines) + f"\n  => {verdict}"


def run_gate(*, feature_names, metrics, y_true, p_pred, protected_frame) -> GateResult:
    g = GateResult()

    # 1. No banned column reached the feature matrix.
    leaked = sorted(set(feature_names) & set(BANNED))
    g.add(1, "No banned column in features", not leaked,
          "clean" if not leaked else f"LEAKED: {leaked}")

    # 2. Performance floor.
    auc = metrics["roc_auc"]
    g.add(2, "ROC-AUC >= floor", auc >= AUC_FLOOR, f"{auc:.4f} >= {AUC_FLOOR}")

    # 3. LEAK CANARY. Nothing honest scores this high on this dataset.
    g.add(3, "ROC-AUC <= ceiling (leak canary)", auc <= AUC_CEILING,
          f"{auc:.4f} <= {AUC_CEILING}"
          + ("" if auc <= AUC_CEILING else "  <-- almost certainly a leak"))

    # 4. Calibration quality -- the EV layer depends on this.
    brier = metrics["brier"]
    g.add(4, "Brier score <= max", brier <= BRIER_MAX, f"{brier:.4f} <= {BRIER_MAX}")

    # 5. Calibration slope near 1.
    slope = metrics["calibration_slope"]
    ok = SLOPE_RANGE[0] <= slope <= SLOPE_RANGE[1]
    g.add(5, "Calibration slope in range", ok,
          f"{slope:.4f} in [{SLOPE_RANGE[0]}, {SLOPE_RANGE[1]}]")

    # 6. No probability asserts certainty (the isotonic degeneracy).
    pmax, pmin = float(np.max(p_pred)), float(np.min(p_pred))
    ok = pmax < 1.0 and pmin > 0.0
    g.add(6, "Probabilities strictly in (0,1)", ok, f"range [{pmin:.4f}, {pmax:.4f}]")

    # 7. Fairness -- CALIBRATION PARITY, not demographic parity.
    #
    #    The first version of this gate asserted that mean predicted risk must be
    #    similar across groups. It failed at |delta| = 0.1755 on Senior Citizen --
    #    and it was the ASSERTION that was wrong, not the model. Seniors really do
    #    churn at 41.7% against 23.6% for non-seniors, an 18.1-point gap. Forcing
    #    equal mean scores would require the model to be deliberately wrong about
    #    a real difference, which helps nobody and costs seniors the retention
    #    offers they actually need.
    #
    #    The defensible question is not "are the scores equal?" but "is the score
    #    equally TRUSTWORTHY for each group?" -- i.e. when the model says 0.7 for
    #    a senior and 0.7 for a non-senior, do both churn at about 70%? That is
    #    calibration parity, and it is what makes a downstream EV calculation
    #    fair, because EV multiplies the probability by money.
    #
    #    Allocation parity -- who actually receives offers, and of what value --
    #    is a DOWNSTREAM check that belongs after the policy engine, not here.
    worst_attr, worst_gap, detail = None, 0.0, ""
    for attr in PROTECTED:
        per_group = {}
        for gv in protected_frame[attr].unique():
            m = protected_frame[attr].values == gv
            if m.sum() < 30:
                continue
            per_group[gv] = ece_fn(y_true[m], p_pred[m])
        if len(per_group) < 2:
            continue
        gap = float(max(per_group.values()) - min(per_group.values()))
        if gap > worst_gap:
            worst_attr, worst_gap = attr, gap
            detail = ", ".join(f"{k}={v:.4f}" for k, v in sorted(per_group.items()))
    g.add(7, "Calibration parity across groups", worst_gap < PARITY_MAX,
          f"max ECE gap = {worst_gap:.4f} ({worst_attr}: {detail}) < {PARITY_MAX}")

    return g
