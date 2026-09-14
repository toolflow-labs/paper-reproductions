from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _finite_sample_quantile(scores: np.ndarray, alpha: float) -> np.ndarray:
    """Finite-sample split-conformal quantile, computed independently per horizon."""
    if scores.ndim != 2:
        raise ValueError("scores must have shape [n_samples, horizon]")
    n = scores.shape[0]
    if n < 1:
        raise ValueError("empty calibration scores")
    rank = int(np.ceil((n + 1) * (1.0 - alpha)))
    rank = min(max(rank, 1), n)
    # kth is zero-indexed; partition avoids interpolation and matches order-statistic CP.
    return np.partition(scores, rank - 1, axis=0)[rank - 1]


@dataclass
class AbsoluteResidualConformal:
    alpha: float = 0.10
    q_: np.ndarray | None = None

    def fit(self, y_true: np.ndarray, y_pred: np.ndarray) -> "AbsoluteResidualConformal":
        scores = np.abs(np.asarray(y_true) - np.asarray(y_pred))
        self.q_ = _finite_sample_quantile(scores, self.alpha)
        return self

    def predict_interval(self, y_pred: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self.q_ is None:
            raise RuntimeError("Conformal calibrator is not fitted")
        pred = np.asarray(y_pred)
        return pred - self.q_, pred + self.q_


@dataclass
class SignedResidualInterval:
    """Transparent reconstruction for the paper's signed-residual experiment.

    The paper defines signed residual scores but does not fully specify the two-sided
    transformation. We use empirical equal-tail residual quantiles and label this as
    an explicit reproduction assumption.
    """

    alpha: float = 0.10
    lower_q_: np.ndarray | None = None
    upper_q_: np.ndarray | None = None

    def fit(self, y_true: np.ndarray, y_pred: np.ndarray) -> "SignedResidualInterval":
        residual = np.asarray(y_true) - np.asarray(y_pred)
        self.lower_q_ = np.quantile(residual, self.alpha / 2.0, axis=0, method="lower")
        self.upper_q_ = np.quantile(residual, 1.0 - self.alpha / 2.0, axis=0, method="higher")
        return self

    def predict_interval(self, y_pred: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self.lower_q_ is None or self.upper_q_ is None:
            raise RuntimeError("Signed residual calibrator is not fitted")
        pred = np.asarray(y_pred)
        return pred + self.lower_q_, pred + self.upper_q_
