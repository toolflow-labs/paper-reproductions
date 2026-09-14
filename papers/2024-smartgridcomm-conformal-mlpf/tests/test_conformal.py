import numpy as np

from conformal_mlpf.conformal import AbsoluteResidualConformal, SignedResidualInterval


def test_absolute_residual_conformal_is_horizon_wise():
    y = np.array([[0.0, 0.0], [1.0, 2.0], [2.0, 4.0], [3.0, 6.0]])
    pred = np.zeros_like(y)
    cp = AbsoluteResidualConformal(alpha=0.25).fit(y, pred)
    assert cp.q_.shape == (2,)
    lo, hi = cp.predict_interval(np.array([[10.0, 20.0]]))
    assert lo.shape == hi.shape == (1, 2)
    assert np.all(lo <= hi)


def test_signed_residual_interval_can_be_asymmetric():
    y = np.array([[1.0], [2.0], [3.0], [9.0]])
    pred = np.zeros_like(y)
    cp = SignedResidualInterval(alpha=0.25).fit(y, pred)
    lo, hi = cp.predict_interval(np.array([[10.0]]))
    assert lo[0, 0] > 10.0
    assert hi[0, 0] >= lo[0, 0]
