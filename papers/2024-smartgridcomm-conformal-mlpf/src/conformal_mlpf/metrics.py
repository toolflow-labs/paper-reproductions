from __future__ import annotations

import numpy as np


def nrmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    value_range = float(np.nanmax(y_true) - np.nanmin(y_true))
    return rmse / value_range if value_range > 0 else float("nan")


def picp(y_true: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> float:
    y_true = np.asarray(y_true)
    return float(np.mean((y_true >= lower) & (y_true <= upper)))


def nmpi(y_true: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> float:
    y_true = np.asarray(y_true)
    widths = np.asarray(upper) - np.asarray(lower)
    value_range = float(np.nanmax(y_true) - np.nanmin(y_true))
    return float(np.median(widths) / value_range) if value_range > 0 else float("nan")


def cwe_proxy(y_true: np.ndarray, lower: np.ndarray, upper: np.ndarray, nominal_coverage: float) -> float:
    """Documented proxy, not claimed to exactly match the paper's CWE implementation."""
    coverage = picp(y_true, lower, upper)
    width = nmpi(y_true, lower, upper)
    coverage_score = max(0.0, 1.0 - abs(coverage - nominal_coverage))
    sharpness_score = max(0.0, 1.0 - min(width, 1.0))
    denom = coverage_score + sharpness_score
    return 0.0 if denom == 0 else 2.0 * coverage_score * sharpness_score / denom


def interval_metrics(
    y_true: np.ndarray,
    point: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    alpha: float,
) -> dict[str, float]:
    return {
        "NRMSE": nrmse(y_true, point),
        "PICP": picp(y_true, lower, upper),
        "NMPI": nmpi(y_true, lower, upper),
        "CWE_proxy": cwe_proxy(y_true, lower, upper, 1.0 - alpha),
    }
