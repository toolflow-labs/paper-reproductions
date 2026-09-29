import importlib.util
from pathlib import Path
import sys

import numpy as np
import torch

spec = importlib.util.spec_from_file_location(
    "repro", Path(__file__).parents[1] / "reproduction.py"
)
repro = importlib.util.module_from_spec(spec)
sys.modules["repro"] = repro
spec.loader.exec_module(repro)


def test_monotonic_quantile_head():
    model = repro.QuantileTransformer(
        10, 24, 2, len(repro.TAUS), d_model=16, nhead=4
    )
    x = torch.randn(3, 24, 10)
    with torch.no_grad():
        q = model(x).numpy()
    assert q.shape == (3, 24, 2, len(repro.TAUS))
    assert np.all(np.diff(q, axis=-1) >= -1e-7)


def test_scenario_generation_shape_and_cvar():
    q = np.zeros((24, 2, len(repro.TAUS)))
    q[:, 0, :] = np.linspace(10, 50, len(repro.TAUS))
    q[:, 1, :] = np.linspace(0, 30, len(repro.TAUS))
    s = repro.generate_scenarios(
        q, np.array([0.7, 0.8]), 0.3, 40, 1
    )
    assert s.shape == (40, 24)
    c = repro.upper_cvar(s, 0.9)
    assert np.all(c >= np.mean(s, axis=0) - 1e-8)
