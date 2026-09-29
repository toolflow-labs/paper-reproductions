import importlib.util
from pathlib import Path
import sys

import numpy as np

spec = importlib.util.spec_from_file_location(
    "repro", Path(__file__).parents[1] / "reproduction.py"
)
repro = importlib.util.module_from_spec(spec)
sys.modules["repro"] = repro
spec.loader.exec_module(repro)


def test_stepwise_cqr_expands_only_needed_horizons():
    y = np.array([[0., 5.], [0., 6.], [0., 7.], [0., 8.]])
    lo = np.array([[-1., 4.], [-1., 4.], [-1., 4.], [-1., 4.]])
    hi = np.array([[1., 6.], [1., 6.], [1., 6.], [1., 6.]])
    clo, chi, q = repro.stepwise_cqr(
        y, lo, hi, lo.copy(), hi.copy(), coverage=0.75
    )
    assert q[0] == 0
    assert q[1] > 0
    assert np.all(clo[:, 0] == lo[:, 0])
    assert np.all(chi[:, 1] >= hi[:, 1])


def test_conformal_quantile_nonnegative():
    assert repro.conformal_quantile(
        np.array([0., 1., 2., 3.]), 0.9
    ) >= 0
