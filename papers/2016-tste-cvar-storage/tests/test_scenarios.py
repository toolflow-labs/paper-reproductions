"""Input and sampling checks, independent of the dispatch optimizer."""

import csv
from datetime import datetime, timedelta
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest
from numpy.testing import assert_allclose


SPEC = importlib.util.spec_from_file_location(
    "cvar_storage_scenarios", Path(__file__).parents[1] / "scenarios.py"
)
scenarios = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scenarios
SPEC.loader.exec_module(scenarios)


def test_paper_grid_and_tariff_boundaries():
    assert len(scenarios.PAPER_HOURS) == 14
    assert scenarios.PAPER_HOURS.sum() == 24.0
    series = scenarios.synthetic_series(48 * 8)
    assert np.all((series.demand_kw > 0) & (series.demand_kw < 24))
    assert len(series.timestamps) == 48 * 8
    assert series.timestamps[0] == datetime(2016, 1, 4)
    for hour, expected in [(6.5, .062), (7, .108), (10.5, .108), (11, .092),
                           (16.5, .092), (17, .108), (18.5, .108), (19, .062)]:
        assert series.buy_price[int(hour * 2)] == expected
    assert np.all(series.sell_price == 0)
    assert series.provenance["source"] == "synthetic"


def test_block_averages_preserve_energy_and_price_integral():
    times = tuple(datetime(2016, 1, 1) + timedelta(minutes=30 * n) for n in range(49))
    demand = np.arange(49, dtype=float)
    buy = .1 + demand / 1000
    series = scenarios.NominalSeries(times, demand, buy, np.zeros(49), {})
    block_demand, block_buy, block_sell = scenarios.aggregate_horizon(series, 1)
    assert_allclose(block_demand[:6], [1, 2, 3, 4, 5.5, 7.5])
    assert np.dot(block_demand, scenarios.PAPER_HOURS) == pytest.approx(.5 * demand[1:].sum())
    assert np.dot(block_buy, scenarios.PAPER_HOURS) == pytest.approx(.5 * buy[1:].sum())
    assert np.all(block_sell == 0)
    with pytest.raises(ValueError, match="not enough"):
        scenarios.aggregate_horizon(series, 2)


def test_price_sigma_uses_integrated_cents_before_dollar_conversion():
    # 10 cents/kWh for .5h gives 5 cents/kW; sigma is sqrt(5) cents/kW.
    assert scenarios.price_std(.1, .5) == pytest.approx(np.sqrt(5) / 100 / .5)
    assert scenarios.price_std(.1, 2, scale=2) == pytest.approx(np.sqrt(20) / 100)


def test_zero_uncertainty_and_reproducible_independent_streams():
    args = ([4, -9], [.1, .2], [0, .05], [.5, 2], 11)
    first = scenarios.sample_joint(*args, scenarios.rng_for(12, 1, 0), scale=0)
    assert_allclose(first[0], np.tile([4, -9], (11, 1)))
    assert_allclose(first[1], np.tile([.1, .2], (11, 1)))
    assert first[2] == 0
    one = scenarios.sample_joint(*args, scenarios.rng_for(12, 1, 0))
    same = scenarios.sample_joint(*args, scenarios.rng_for(12, 1, 0))
    other = scenarios.sample_joint(*args, scenarios.rng_for(12, 2, 0))
    assert_allclose(one[0], same[0], rtol=0, atol=0)
    assert_allclose(one[1], same[1], rtol=0, atol=0)
    assert not np.array_equal(one[0], other[0])
    prefix = scenarios.sample_joint(*args[:4], 3, scenarios.rng_for(12, 1, 0))
    assert_allclose(one[0][:3], prefix[0], rtol=0, atol=0)
    assert_allclose(one[1][:3], prefix[1], rtol=0, atol=0)


def test_joint_sampling_censors_prices_and_preserves_pre_censor_correlation():
    # Large nominal buying price and small scale avoid censoring, allowing a
    # direct check of the intended Gaussian cross-variable correlation.
    demand, buy, clipped = scenarios.sample_joint(
        [9], [2], [0], [1], 30000, scenarios.rng_for(1, 1, 0), scale=.1, rho=.5
    )
    assert clipped == 0
    assert np.corrcoef(demand[:, 0], buy[:, 0])[0, 1] == pytest.approx(.5, abs=.02)
    _, censored, count = scenarios.sample_joint(
        [4], [.01], [.01], [.5], 1000, scenarios.rng_for(1, 2, 0)
    )
    assert np.all(censored >= .01)
    assert count == np.count_nonzero(censored == .01)
    assert 400 < count < 600


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "net_load_kw", "buy_price_per_kwh", "sell_price_per_kwh"])
        writer.writerows(rows)


def valid_rows():
    return [["2016-01-01T00:00:00+00:00", "3", ".1", "0"],
            ["2016-01-01T00:30:00+00:00", "4", ".2", ".1"]]


def test_csv_records_provenance_and_accepts_negative_net_load(tmp_path):
    path = tmp_path / "nominal.csv"
    rows = valid_rows()
    rows[0][1] = "-3"
    write_csv(path, rows)
    series = scenarios.load_csv(path, required_steps=2)
    assert_allclose(series.demand_kw, [-3, 4])
    assert series.provenance["source"] == "external_csv"
    assert len(series.provenance["sha256"]) == 64
    with pytest.raises(ValueError, match="at least 3"):
        scenarios.load_csv(path, required_steps=3)


@pytest.mark.parametrize("column,value,error", [
    (0, "2016-01-01T01:00:00+00:00", "30 minutes"),
    (0, "2016-01-01T00:30:00+01:00", "uniform timezone"),
    (0, "bad", "invalid timestamp"),
    (1, "nan", "finite"),
    (2, ".05", "buy >= sell"),
    (3, "-.1", "buy >= sell"),
])
def test_csv_rejects_invalid_rows(tmp_path, column, value, error):
    path = tmp_path / "invalid.csv"
    rows = valid_rows()
    rows[1][column] = value
    write_csv(path, rows)
    with pytest.raises(ValueError, match=error):
        scenarios.load_csv(path, required_steps=2)


@pytest.mark.parametrize("kwargs", [{"scale": -1}, {"rho": 1.1}, {"count": 0}])
def test_sampling_rejects_invalid_parameters(kwargs):
    args = dict(demand=[1], buy=[.1], sell=[0], hours=[.5], count=2,
                rng=scenarios.rng_for(1, 2, 3))
    args.update(kwargs)
    with pytest.raises(ValueError):
        scenarios.sample_joint(**args)
