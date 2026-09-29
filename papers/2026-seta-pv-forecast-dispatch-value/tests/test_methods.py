import importlib.util
from pathlib import Path
import sys

import numpy as np

spec = importlib.util.spec_from_file_location(
    "guo", Path(__file__).parents[1] / "reproduction.py"
)
gu = importlib.util.module_from_spec(spec)
sys.modules["guo"] = gu
spec.loader.exec_module(gu)


def test_value_capture_identity():
    v = gu.value_metrics(
        {"persistence": 100.0, "point": 92.0, "perfect": 80.0, "q0.7": 90.0}
    )
    assert np.isclose(v["q0.7"]["ev_vs_persistence"], 10.0)
    assert np.isclose(v["q0.7"]["value_capture_ratio"], 0.5)
    assert np.isclose(v["q0.7"]["value_capture_gap"], 10.0)


def test_commitment_and_recourse_are_feasible():
    cfg = gu.DispatchConfig()
    pv = np.array([0, 0, 50, 100, 120, 50, 0, 0], dtype=float)
    load = np.full(len(pv), 180.0)
    sched = gu.solve_commitment(pv, load, 0.5, cfg)
    rec = gu.solve_recourse(pv * 0.9, load, sched, cfg)
    assert len(sched["ch"]) == len(pv)
    assert rec["ens_kwh"] >= 0
    assert np.isfinite(rec["total_cost"])
