"""Independent numerical checks of the risk measure and storage LP.

Small cases with known optima matter here: a successful solver exit alone does
not establish that the risk epigraph, units, or storage dynamics are correct.
"""

from dataclasses import replace
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest
from numpy.testing import assert_allclose
from scipy.optimize import linprog


SPEC = importlib.util.spec_from_file_location(
    "cvar_storage_model", Path(__file__).parents[1] / "model.py"
)
model = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = model
SPEC.loader.exec_module(model)


def throughput_costs(rate=0.1):
    """Keep only positive cycling costs to isolate analytical examples."""
    return model.Costs(
        charge_per_kwh=rate,
        discharge_per_kwh=rate,
        low_energy_per_kwh_hour=0.0,
        smoothing_per_kw_hour=0.0,
        peak_per_kw=0.0,
        flat_per_kw=0.0,
        energy_floor_kwh=0.0,
        grid_baseline_kw=100.0,
    )


def unit_battery(**overrides):
    params = dict(
        energy_min_kwh=0.0,
        energy_max_kwh=1.0,
        power_kw=1.0,
        eta_charge=1.0,
        eta_discharge=1.0,
        self_discharge_kw=0.0,
        terminal_energy_kwh=0.0,
        ramp_kw_per_hour=10.0,
    )
    params.update(overrides)
    return model.Battery(**params)


@pytest.mark.parametrize("beta, expected", [(0.0, 5.0), (0.5, 10.0), (0.8, 15.0)])
def test_weighted_cvar_uses_fractional_quantile_mass(beta, expected):
    # The 80% quantile atom has mass .3; only .1 of it lies in the .2 tail.
    actual = model.empirical_cvar([0.0, 10.0, 20.0], beta, weights=[0.6, 0.3, 0.1])
    assert actual == pytest.approx(expected)


def test_cvar_translation_duplicates_and_negative_costs():
    losses = np.array([-5.0, -5.0, 3.0, 3.0])
    assert model.empirical_cvar(losses, 0.6) == pytest.approx(3.0)
    assert model.empirical_cvar(losses, 0.25) == pytest.approx(1.0 / 3.0)
    assert model.empirical_cvar(losses - 20.0, 0.25) == pytest.approx(1.0 / 3.0 - 20.0)
    assert model.empirical_cvar([-7.0] * 5, 0.93) == pytest.approx(-7.0)


@pytest.mark.parametrize("gamma", [0.0, 0.5, 1.0, 1.75, 3.0, 20.0])
def test_budget_support_agrees_with_independent_primal_lp(gamma):
    # For nonnegative exposures the symmetric uncertainty set's maximizer
    # is nonnegative. This primal LP is independent of the sorted formula.
    exposures = np.array([1.0, 4.0, 2.0])
    reference = linprog(
        -exposures,
        A_ub=np.ones((1, 3)),
        b_ub=[gamma],
        bounds=[(0.0, 1.0)] * 3,
        method="highs",
    )
    assert reference.success, reference.message
    assert model.budget_support(exposures, gamma) == pytest.approx(-reference.fun)


@pytest.mark.parametrize("mode", ["nominal", "cvar"])
def test_two_period_arbitrage_has_known_energy_optimum(mode):
    # One kWh shifted from price 3 to price 1 saves 2, with cycling cost .2.
    result = model.solve_dispatch(
        [[1.0, 1.0]], [1.0, 3.0], [0.0, 0.0], [1.0, 1.0], 0.0,
        battery=unit_battery(), costs=throughput_costs(), mode=mode, beta=0.9,
    )
    assert_allclose(result.charge_kw, [1.0, 0.0], atol=1e-8)
    assert_allclose(result.discharge_kw, [0.0, 1.0], atol=1e-8)
    assert_allclose(result.energy_kwh, [0.0, 1.0, 0.0], atol=1e-8)
    assert_allclose(result.grid_kw, [[2.0, 0.0]], atol=1e-8)
    assert result.objective == pytest.approx(2.2, abs=1e-8)


@pytest.mark.parametrize("mode", ["nominal", "cvar", "wcvar"])
def test_export_revenue_allows_negative_loss_and_var(mode):
    uncertainty = (
        dict(gamma=0.0, buy_radius=[0.0, 0.0], sell_radius=[0.0, 0.0])
        if mode == "wcvar" else {}
    )
    result = model.solve_dispatch(
        [[-1.0, -1.0]], [2.0, 4.0], [1.0, 3.0], [1.0, 1.0], 0.0,
        battery=unit_battery(power_kw=0.0), costs=throughput_costs(),
        mode=mode, beta=0.9, **uncertainty,
    )
    assert_allclose(result.scenario_costs, [-4.0], atol=1e-8)
    assert result.objective == pytest.approx(-4.0, abs=1e-8)


def test_nonuniform_hours_conserve_energy_and_respect_limits():
    hours = np.array([0.5, 1.5, 2.0])
    battery = unit_battery(
        energy_max_kwh=4.0, power_kw=2.0, eta_charge=0.95,
        eta_discharge=0.9, self_discharge_kw=0.01,
        terminal_energy_kwh=2.0, ramp_kw_per_hour=1.0,
    )
    demand = np.array([[1.0, 2.0, 1.0], [2.0, 1.0, 3.0]])
    result = model.solve_dispatch(
        demand, [0.05, 0.4, 0.2], [0.0, 0.0, 0.0], hours, 2.0,
        battery=battery, costs=throughput_costs(0.01), beta=0.5,
        previous_battery_kw=0.0,
    )
    expected_energy = 2.0 + np.cumsum(
        hours * (0.95 * result.charge_kw - result.discharge_kw / 0.9 - 0.01)
    )
    assert_allclose(result.energy_kwh, np.r_[2.0, expected_energy], atol=1e-7)
    assert result.energy_kwh[-1] == pytest.approx(2.0, abs=1e-7)
    assert np.all(result.energy_kwh >= -1e-7)
    assert np.all(result.energy_kwh <= 4.0 + 1e-7)
    assert np.all(result.charge_kw >= -1e-7)
    assert np.all(result.discharge_kw >= -1e-7)
    assert np.all(result.charge_kw <= 2.0 + 1e-7)
    assert np.all(result.discharge_kw <= 2.0 + 1e-7)
    assert np.max(np.minimum(result.charge_kw, result.discharge_kw)) <= 1e-7
    assert result.max_simultaneous_kw <= 1e-7
    battery_power = result.charge_kw - result.discharge_kw
    assert np.all(np.abs(np.diff(np.r_[0.0, battery_power])) <= hours + 1e-7)
    assert_allclose(result.grid_kw, demand + battery_power, atol=1e-7)


def test_first_ramp_uses_previous_power_and_elapsed_hours():
    # Previous power=-.25 and a half-hour ramp allowance=.5 cap first
    # charge at .25 kW. Thus only .125 kWh can move to the expensive step.
    result = model.solve_dispatch(
        [[1.0, 1.0]], [1.0, 3.0], [0.0, 0.0], [0.5, 1.5], 0.0,
        battery=unit_battery(ramp_kw_per_hour=1.0), costs=throughput_costs(),
        previous_battery_kw=-0.25, mode="cvar", beta=0.9,
    )
    assert_allclose(result.charge_kw, [0.25, 0.0], atol=1e-8)
    assert_allclose(result.discharge_kw, [0.0, 1.0 / 12.0], atol=1e-8)
    assert_allclose(result.energy_kwh, [0.0, 0.125, 0.0], atol=1e-8)
    assert result.objective == pytest.approx(4.775, abs=1e-8)


def test_two_scenario_cvar_matches_one_dimensional_policy_search():
    # With initial=terminal SOC=0, unit efficiency and positive cycling cost,
    # every undominated feasible policy charges x then discharges x, 0<=x<=1.
    # The two scenario costs cross at x=5/8.5. At beta=.5 CVaR=max(costs).
    result = model.solve_dispatch(
        [[1.0, 2.0], [1.0, 2.0]], [[1.0, 5.0], [5.0, 0.5]],
        [0.0, 0.0], [1.0, 1.0], 0.0,
        battery=unit_battery(), costs=throughput_costs(), beta=0.5, mode="cvar",
    )
    candidate_x = np.linspace(0.0, 1.0, 10001)
    grid_objective = np.maximum(11.0 - 3.8 * candidate_x, 6.0 + 4.7 * candidate_x)
    assert abs(result.objective - np.min(grid_objective)) <= 5e-4
    assert result.charge_kw[0] == pytest.approx(5.0 / 8.5, abs=1e-7)
    assert result.objective == pytest.approx(11.0 - 3.8 * 5.0 / 8.5, abs=1e-7)


def test_zero_uncertainty_budget_recovers_cvar_and_larger_budget_cannot_help():
    common = dict(
        demand_kw=[[1.0, 2.0], [2.0, 1.0]], buy_price=[0.2, 0.4],
        sell_price=[0.05, 0.05], hours=[1.0, 1.0], initial_energy_kwh=0.0,
        battery=unit_battery(), costs=throughput_costs(0.01), beta=0.5,
    )
    nominal_prices = model.solve_dispatch(**common, mode="cvar")
    robust = [
        model.solve_dispatch(
            **common, mode="wcvar", buy_radius=[0.02, 0.03],
            sell_radius=[0.01, 0.01], gamma=gamma,
        )
        for gamma in [0.0, 1.0, 2.0]
    ]
    assert robust[0].objective == pytest.approx(nominal_prices.objective, abs=1e-7)
    assert robust[1].objective >= robust[0].objective - 1e-7
    assert robust[2].objective >= robust[1].objective - 1e-7


def test_fixed_storage_robust_losses_match_hand_calculated_support():
    # Scenario 0 exposures: (.025,.24,0,0); scenario 1: (0,.36,.02,0).
    # Gamma=1.5 selects the largest exposure plus half the second largest.
    result = model.solve_dispatch(
        [[1.0, 2.0], [-2.0, 3.0]], [0.2, 0.4], [0.1, 0.1], [0.5, 1.5], 0.0,
        battery=unit_battery(power_kw=0.0), costs=throughput_costs(),
        mode="wcvar", beta=0.5, buy_radius=[0.05, 0.08],
        sell_radius=[0.02, 0.03], gamma=1.5,
    )
    assert_allclose(result.scenario_costs, [1.3 + 0.2525, 1.7 + 0.37], atol=1e-8)
    assert result.objective == pytest.approx(2.07, abs=1e-8)


@pytest.mark.parametrize(
    "losses, beta, weights",
    [([], 0.9, None), ([1.0, np.nan], 0.9, None), ([1.0], 1.0, None),
     ([1.0], -0.1, None), ([1.0, 2.0], 0.9, [-0.1, 1.1]),
     ([1.0, 2.0], 0.9, [0.0, 0.0])],
)
def test_invalid_cvar_inputs_raise(losses, beta, weights):
    with pytest.raises(ValueError):
        model.empirical_cvar(losses, beta, weights=weights)


@pytest.mark.parametrize("gamma", [-0.1, np.nan, np.inf])
def test_invalid_uncertainty_budgets_raise(gamma):
    with pytest.raises(ValueError):
        model.budget_support([1.0, 2.0], gamma)


@pytest.mark.parametrize(
    "override",
    [
        {"hours": [0.0, 1.0]},
        {"hours": [1.0]},
        {"demand_kw": [[np.nan, 1.0]]},
        {"buy_price": [0.0, 1.0], "sell_price": [0.1, 0.0]},
        {"beta": 1.0},
        {"mode": "not-a-policy"},
    ],
)
def test_invalid_dispatch_inputs_raise(override):
    args = dict(
        demand_kw=[[1.0, 1.0]], buy_price=[1.0, 3.0], sell_price=[0.0, 0.0],
        hours=[1.0, 1.0], initial_energy_kwh=0.0,
        battery=unit_battery(), costs=throughput_costs(),
    )
    args.update(override)
    with pytest.raises(ValueError):
        model.solve_dispatch(**args)


def test_zero_charge_efficiency_is_rejected():
    with pytest.raises(ValueError):
        model.solve_dispatch(
            [[1.0, 1.0]], [1.0, 3.0], [0.0, 0.0], [1.0, 1.0], 0.0,
            battery=unit_battery(eta_charge=0.0), costs=throughput_costs(),
        )


def test_unreachable_terminal_energy_is_reported():
    with pytest.raises((ValueError, RuntimeError)):
        model.solve_dispatch(
            [[1.0]], [1.0], [0.0], [0.5], 0.0,
            battery=unit_battery(energy_max_kwh=10.0, terminal_energy_kwh=10.0),
            costs=throughput_costs(),
        )


def test_nonphysical_simultaneous_cycling_is_rejected():
    # With losses, simultaneous cycling dissipates energy while ending at the
    # initial SOC. A large smoothing penalty can reward that artifact even
    # with positive cycling cost. The LP result must not be silently executed.
    costs = replace(throughput_costs(0.001), smoothing_per_kw_hour=1.0)
    with pytest.raises(RuntimeError):
        model.solve_dispatch(
            [[-1.0]], [0.0], [0.0], [1.0], 0.0,
            battery=unit_battery(eta_charge=0.95, eta_discharge=0.9),
            costs=costs, previous_grid_kw=0.0,
        )
