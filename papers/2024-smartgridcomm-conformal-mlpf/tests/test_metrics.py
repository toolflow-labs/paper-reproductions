import numpy as np

from conformal_mlpf.metrics import interval_metrics, nmpi, nrmse, picp


def test_metrics_basic():
    y = np.array([0.0, 1.0, 2.0])
    pred = np.array([0.0, 1.0, 2.0])
    lower = np.array([-0.5, 0.5, 1.5])
    upper = np.array([0.5, 1.5, 2.5])
    assert nrmse(y, pred) == 0.0
    assert picp(y, lower, upper) == 1.0
    assert np.isclose(nmpi(y, lower, upper), 0.5)
    metrics = interval_metrics(y, pred, lower, upper, alpha=0.1)
    assert set(metrics) == {"NRMSE", "PICP", "NMPI", "CWE_proxy"}
