import importlib.util
from pathlib import Path
import sys

import numpy as np

spec = importlib.util.spec_from_file_location(
    "renkema", Path(__file__).parents[1] / "reproduction.py"
)
r = importlib.util.module_from_spec(spec)
sys.modules["renkema"] = r
spec.loader.exec_module(r)


def test_newsvendor_tau_direction():
    centers = np.array([[30.0, 10.0], [10.0, 30.0]])
    weights = np.array([0.5, 0.5])
    assert np.isclose(r.newsvendor_tau(centers, weights), 0.5)


def test_lower_tail_cvar_is_not_above_mean():
    v = np.array([0.0, 1.0, 2.0, 3.0])
    p = np.full(4, 0.25)
    c = r.lower_tail_cvar(v, p, gamma=0.5)
    assert c <= np.sum(v * p)


def test_eum_bid_stays_in_unit_interval():
    pv = np.linspace(0.2, 0.8, 19)
    centers = np.array([[20.0, 10.0], [30.0, 15.0]])
    weights = np.array([0.6, 0.4])
    bid = r.optimize_eum_bid(
        pv, 60.0, centers, weights, grid_n=21, beta=0.1, gamma=0.6
    )
    assert 0 <= bid <= 1
