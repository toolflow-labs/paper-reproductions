"""Checks of executed-trajectory accounting and the public experiment runner."""

from collections import defaultdict
import csv
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest
from numpy.testing import assert_allclose


PAPER = Path(__file__).parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, PAPER / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# The command-line script uses sibling imports. Keep them private to this
# import so the other papers' independently loaded modules are unaffected.
_old_modules = {name: sys.modules.get(name) for name in ("model", "scenarios")}
try:
    sys.modules["model"] = _load("storage_runner_model", "model.py")
    sys.modules["scenarios"] = _load("storage_runner_scenarios", "scenarios.py")
    runner = _load("storage_reproduction_runner", "reproduction.py")
finally:
    for _name, _previous in _old_modules.items():
        if _previous is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _previous


def accounting_rows(ending_energy=8.0):
    timestamps = [
        "2016-01-04T23:00:00", "2016-01-04T23:30:00",
        "2016-01-05T00:00:00", "2016-01-05T00:30:00",
    ]
    grids = [2.0, 6.0, -1.0, 4.0]
    return [
        {
            "timestamp": timestamp, "grid_kw": grid,
            "energy_bill": float(i + 1), "throughput_cost": (i + 1) / 10,
            "low_energy_cost": 0.05, "smoothing_cost": [0.0, 0.4, 0.7, 0.2][i],
            "energy_kwh": ending_energy if i == 3 else 10.0,
            "max_simultaneous_kw": 0.0, "solve_seconds": (i + 1) / 100,
            "forecast_objective": 10000.0,
        }
        for i, (timestamp, grid) in enumerate(zip(timestamps, grids))
    ]


@pytest.mark.parametrize("ending_energy, adjustment", [(8.0, 0.5), (12.0, -0.5)])
def test_trajectory_costs_use_executed_steps_and_once_daily_extrema(ending_energy, adjustment):
    costs = replace(runner.Costs(), peak_per_kw=2.0, flat_per_kw=0.5, grid_baseline_kw=3.0)
    metrics = runner.trajectory_metrics(accounting_rows(ending_energy), costs, 10.0, 0.25)
    # First day: peak penalty 6, range penalty 2. Second day: 2 and 2.5.
    expected = {
        "energy_bill": 10.0, "throughput_cost": 1.0,
        "low_energy_cost": 0.2, "smoothing_cost": 1.3,
        "peak_cost": 8.0, "flat_cost": 4.5, "composite_cost": 25.0,
        "inventory_adjustment": adjustment,
        "inventory_adjusted_bill": 10.0 + adjustment,
        "inventory_adjusted_composite": 25.0 + adjustment,
        "initial_energy_kwh": 10.0, "ending_energy_kwh": ending_energy,
        "max_grid_kw": 6.0, "max_simultaneous_kw": 0.0, "solve_seconds": 0.1,
    }
    for key, value in expected.items():
        assert metrics[key] == pytest.approx(value), key


def test_empty_executed_trajectory_is_rejected():
    with pytest.raises(ValueError):
        runner.trajectory_metrics([], runner.Costs(), 10.0, 0.1)


def metric_sample(cost, replication, method="cvar", scale=1.0):
    return {
        "actual_uncertainty_scale": scale, "method": method, "replication": replication,
        "energy_bill": cost, "inventory_adjusted_bill": cost + 2.0,
        "composite_cost": cost + 5.0, "inventory_adjusted_composite": cost + 7.0,
        "ending_energy_kwh": 20.0,
    }


def test_summary_tail_is_over_independent_trajectory_totals():
    # Four complete-path totals; the top 37.5% contains one whole path and
    # half the second-largest. It is not a tail of a path's individual steps.
    samples = [metric_sample(value, i) for i, value in enumerate([1.0, 10.0, 100.0, 1000.0])]
    samples += [metric_sample(7.0, 0, scale=2.0), metric_sample(9.0, 0, method="nominal")]
    summary = {
        (row["actual_uncertainty_scale"], row["method"]): row
        for row in runner.summarize(samples, beta=0.625)
    }
    assert len(summary) == 3
    main = summary[(1.0, "cvar")]
    assert main["replications"] == 4
    assert main["mean_energy_bill"] == pytest.approx(277.75)
    assert main["cvar_energy_bill"] == pytest.approx(700.0)
    assert main["cvar_inventory_adjusted_bill"] == pytest.approx(702.0)
    assert main["cvar_composite_cost"] == pytest.approx(705.0)
    assert main["cvar_inventory_adjusted_composite"] == pytest.approx(707.0)
    assert main["std_energy_bill"] == pytest.approx(np.std([1, 10, 100, 1000], ddof=1))
    singleton = summary[(2.0, "cvar")]
    assert singleton["replications"] == 1
    assert singleton["cvar_energy_bill"] == pytest.approx(7.0)
    assert singleton["std_energy_bill"] is None


@pytest.mark.parametrize(
    "argv",
    [
        ["--days", "0"], ["--replications", "-1"], ["--scenarios", "0"],
        ["--wcvar-scenarios", "0"], ["--seed", "-1"],
        ["--beta", "1"], ["--beta", "nan"],
        ["--model-scale", "-0.1"], ["--model-scale", "inf"],
        ["--actual-scales", ""], ["--actual-scales", "0,no"],
        ["--actual-scales=-1,0"], ["--actual-scales", "0,nan"],
        ["--actual-scales", "1,1"], ["--gamma", "-0.1"], ["--gamma", "inf"],
    ],
)
def test_cli_invalid_parameters_exit_with_usage_error(argv):
    with pytest.raises(SystemExit) as error:
        runner.parse_args(argv)
    assert error.value.code == 2


@pytest.fixture(scope="module")
def smoke_results():
    args = runner.parse_args(["--smoke", "--include-mean", "--seed", "2016"])
    first = runner.run_experiment(args)
    second = runner.run_experiment(args)
    return first, second


def without_solve_seconds(rows):
    return [{key: value for key, value in row.items() if key != "solve_seconds"} for row in rows]


def test_smoke_same_seed_reproduces_results_except_wall_clock(smoke_results):
    (rows1, metrics1, report1), (rows2, metrics2, report2) = smoke_results
    assert without_solve_seconds(rows1) == without_solve_seconds(rows2)
    assert without_solve_seconds(metrics1) == without_solve_seconds(metrics2)
    assert report1 == report2
    assert len(rows1) == 4 * 2 * 5
    assert len(metrics1) == 2 * 5


def test_smoke_methods_share_actual_path_and_preserve_physical_state(smoke_results):
    rows, _, report = smoke_results[0]
    config = report["metadata"]["config"]
    battery = runner.Battery(**config["battery"])
    costs = runner.Costs(**config["costs"])
    actual_paths, trajectories = defaultdict(list), defaultdict(list)
    for row in rows:
        actual_paths[(row["actual_uncertainty_scale"], row["replication"], row["step"])].append(row)
        trajectories[(row["actual_uncertainty_scale"], row["replication"], row["method"])].append(row)
    for same_step in actual_paths.values():
        for field in ("timestamp", "actual_net_load_kw", "actual_buy_price_per_kwh", "actual_sell_price_per_kwh"):
            assert len({row[field] for row in same_step}) == 1
    for (_, _, method), path in trajectories.items():
        previous_energy = config["initial_energy_kwh"]
        previous_power = 0.0
        previous_grid = None
        for row in path:
            charge, discharge, grid = row["charge_kw"], row["discharge_kw"], row["grid_kw"]
            assert grid == pytest.approx(row["actual_net_load_kw"] + charge - discharge)
            expected_bill = 0.5 * (
                row["actual_buy_price_per_kwh"] * max(grid, 0.0)
                - row["actual_sell_price_per_kwh"] * max(-grid, 0.0)
            )
            assert row["energy_bill"] == pytest.approx(expected_bill)
            expected_throughput = 0.5 * (costs.charge_per_kwh * charge + costs.discharge_per_kwh * discharge)
            assert row["throughput_cost"] == pytest.approx(expected_throughput)
            expected_smoothing = 0.0 if previous_grid is None else 0.5 * costs.smoothing_per_kw_hour * abs(grid - previous_grid)
            assert row["smoothing_cost"] == pytest.approx(expected_smoothing)
            if method == "no_storage":
                assert charge == discharge == row["low_energy_cost"] == 0.0
                assert row["energy_kwh"] == config["initial_energy_kwh"]
            else:
                expected_energy = previous_energy + 0.5 * (
                    battery.eta_charge * charge - discharge / battery.eta_discharge - battery.self_discharge_kw
                )
                assert row["energy_kwh"] == pytest.approx(expected_energy, abs=1e-7)
                assert battery.energy_min_kwh - 1e-7 <= row["energy_kwh"] <= battery.energy_max_kwh + 1e-7
                assert abs(charge - discharge - previous_power) <= 0.5 * battery.ramp_kw_per_hour + 1e-7
                assert min(charge, discharge) <= 1e-7
                expected_low = 0.5 * costs.low_energy_per_kwh_hour * max(costs.energy_floor_kwh - row["energy_kwh"], 0.0)
                assert row["low_energy_cost"] == pytest.approx(expected_low)
            previous_energy, previous_power, previous_grid = row["energy_kwh"], charge - discharge, grid


def test_smoke_metrics_and_summary_match_executed_paths(smoke_results):
    rows, metrics, report = smoke_results[0]
    config = report["metadata"]["config"]
    costs = runner.Costs(**config["costs"])
    summaries = {(item["actual_uncertainty_scale"], item["method"]): item for item in report["summary"]}
    for metric in metrics:
        path = [row for row in rows if all(row[key] == metric[key] for key in ("actual_uncertainty_scale", "replication", "method"))]
        energy_bill = sum(row["energy_bill"] for row in path)
        grid = [row["grid_kw"] for row in path]
        # Smoke covers one partial calendar day: extrema must be charged once.
        peak = costs.peak_per_kw * max(max(grid) - costs.grid_baseline_kw, 0.0)
        flat = costs.flat_per_kw * (max(grid) - min(grid))
        composite = energy_bill + peak + flat + sum(
            row["throughput_cost"] + row["low_energy_cost"] + row["smoothing_cost"] for row in path
        )
        adjustment = config["inventory_value_per_kwh"] * (config["initial_energy_kwh"] - path[-1]["energy_kwh"])
        assert metric["energy_bill"] == pytest.approx(energy_bill)
        assert metric["composite_cost"] == pytest.approx(composite)
        assert metric["inventory_adjustment"] == pytest.approx(adjustment)
        assert metric["inventory_adjusted_composite"] == pytest.approx(composite + adjustment)
    for (scale, method), summary in summaries.items():
        path_totals = [metric["inventory_adjusted_composite"] for metric in metrics
                       if metric["actual_uncertainty_scale"] == scale and metric["method"] == method]
        assert len(path_totals) == summary["replications"] == 2
        # At beta=.9, two equally weighted trajectories have CVaR=max(total).
        assert summary["cvar_inventory_adjusted_composite"] == pytest.approx(max(path_totals))
        assert summary["mean_inventory_adjusted_composite"] == pytest.approx(sum(path_totals) / 2)


def test_smoke_csv_and_json_roundtrip_preserve_metrics(smoke_results, tmp_path):
    rows, metrics, report = smoke_results[0]
    dispatch_path = tmp_path / "dispatch.csv"
    metrics_path = tmp_path / "trajectory_metrics.csv"
    runner.write_csv(dispatch_path, rows)
    runner.write_csv(metrics_path, metrics)
    with dispatch_path.open(newline="") as handle:
        saved_rows = list(csv.DictReader(handle))
    with metrics_path.open(newline="") as handle:
        saved_metrics = list(csv.DictReader(handle))
    assert len(saved_rows) == len(rows)
    assert len(saved_metrics) == len(metrics)
    assert_allclose([float(row["energy_kwh"]) for row in saved_rows], [row["energy_kwh"] for row in rows])
    assert_allclose([float(row["inventory_adjusted_composite"]) for row in saved_metrics],
                    [row["inventory_adjusted_composite"] for row in metrics])
    # This is also a finite-value check on every emitted numeric field.
    saved_report = json.loads(json.dumps(report, allow_nan=False))
    assert saved_report == report
