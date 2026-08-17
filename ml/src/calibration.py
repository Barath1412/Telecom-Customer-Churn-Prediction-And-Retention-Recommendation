"""
Calibrated probabilities, with the isotonic degeneracy fixed.

Why calibration is mandatory here and not a nicety:
    the downstream expected-value calculation is

        EV = P(churn) x CLTV x delta_retention - cost(offer)

    P is multiplied by money. A model that says 0.90 when the true rate is 0.70
    mis-prices every offer by ~30%. Ranking metrics (ROC-AUC) are completely
    blind to this -- a model can rank perfectly and still be badly mis-scaled.

The bug this class exists to fix:
    isotonic regression is a step function and returns EXACTLY 1.0 at the top of
    its range. Measured on this dataset, the highest-risk customer came out at
    P(churn) = 1.000 -- an assertion of certainty. Fed into EV that inflates the
    offer budget for precisely the segment you spend the most on. Clipping to
    [eps, 1-eps] costs nothing and removes the failure mode.
"""
from __future__ import annotations
import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from sklearn.calibration import CalibratedClassifierCV


class ClippedCalibratedClassifier(BaseEstimator, ClassifierMixin):
    """CalibratedClassifierCV whose probabilities can never be exactly 0 or 1."""

    def __init__(self, estimator=None, method="isotonic", cv=5, eps=0.01):
        self.estimator = estimator
        self.method = method
        self.cv = cv
        self.eps = eps

    def fit(self, X, y):
        self.calibrated_ = CalibratedClassifierCV(
            clone(self.estimator), method=self.method, cv=self.cv
        )
        self.calibrated_.fit(X, y)
        self.classes_ = self.calibrated_.classes_
        return self

    def predict_proba(self, X):
        p = self.calibrated_.predict_proba(X)
        p = np.clip(p, self.eps, 1.0 - self.eps)
        return p / p.sum(axis=1, keepdims=True)   # renormalise after clipping

    def predict(self, X):
        return self.classes_[np.argmax(self.predict_proba(X), axis=1)]


def calibration_slope(y_true, p_pred, eps=1e-6) -> float:
    """
    Regress the true outcome on the predicted log-odds.

        slope ~ 1.0  -> well calibrated
        slope < 1.0  -> over-confident (predictions too extreme)
        slope > 1.0  -> under-confident

    A number the promotion gate can assert on, unlike a calibration plot.
    """
    from sklearn.linear_model import LogisticRegression

    p = np.clip(np.asarray(p_pred, dtype=float), eps, 1 - eps)
    logit = np.log(p / (1 - p)).reshape(-1, 1)
    lr = LogisticRegression(C=np.inf, solver="lbfgs", max_iter=1000)  # unpenalised
    lr.fit(logit, np.asarray(y_true))
    return float(lr.coef_[0][0])


def expected_calibration_error(y_true, p_pred, n_bins=10) -> float:
    """Mean |predicted - observed| across equal-width probability bins."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(p_pred, dtype=float)
    edges = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    total, n = 0.0, len(y)
    for b in range(n_bins):
        m = idx == b
        if m.sum() == 0:
            continue
        total += (m.sum() / n) * abs(p[m].mean() - y[m].mean())
    return float(total)
