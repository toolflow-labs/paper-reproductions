"""Sparse LP reproduction of the storage control and CVaR formulations.

The battery action is common to all demand scenarios (an open-loop horizon
plan).  Only the first action should be applied by a receding-horizon caller.
Positive battery power means charging.  Energy is in kWh, power in kW, and
``hours`` supplies the duration of each, potentially unequal, horizon step.

This is a continuous charging/discharging relaxation.  Every returned solution
is checked for simultaneous charging and discharging; a nonphysical optimum
raises an error instead of being silently reported as a valid dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from time import perf_counter

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix


@dataclass(frozen=True)
class Battery:
    energy_min_kwh: float = 0.0
    energy_max_kwh: float = 50.0
    power_kw: float = 10.0
    eta_charge: float = 0.95
    eta_discharge: float = 0.9
    self_discharge_kw: float = 0.0
    terminal_energy_kwh: float = 25.0
    ramp_kw_per_hour: float = 20.0


@dataclass(frozen=True)
class Costs:
    charge_per_kwh: float = 0.005
    discharge_per_kwh: float = 0.005
    low_energy_per_kwh_hour: float = 0.001
    smoothing_per_kw_hour: float = 0.001
    peak_per_kw: float = 0.001
    flat_per_kw: float = 0.001
    energy_floor_kwh: float = 25.0
    grid_baseline_kw: float = 9.5


@dataclass(frozen=True)
class DispatchResult:
    charge_kw: np.ndarray
    discharge_kw: np.ndarray
    energy_kwh: np.ndarray
    grid_kw: np.ndarray
    scenario_costs: np.ndarray
    objective: float
    solve_seconds: float
    max_simultaneous_kw: float


def _array(value, name: str) -> np.ndarray:
    try:
        out = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain real numbers") from exc
    if not np.all(np.isfinite(out)):
        raise ValueError(f"{name} must contain only finite values")
    return out


def _scalar(value, name: str) -> float:
    out = _array(value, name)
    if out.ndim != 0:
        raise ValueError(f"{name} must be a scalar")
    return float(out)


def _beta(value) -> float:
    beta = _scalar(value, "beta")
    if not 0.0 <= beta < 1.0:
        raise ValueError("beta must satisfy 0 <= beta < 1")
    return beta


def empirical_cvar(losses, beta, weights=None) -> float:
    """Return upper-tail CVaR, including a fractional quantile atom.

    ``weights`` are nonnegative scenario masses and are normalized to sum to
    one.  Zero masses are allowed.  With no weights all scenarios are equally
    likely.  ``beta=0`` gives the mean; ``beta`` must be strictly below one.
    This is the discrete Rockafellar--Uryasev CVaR, not a mean of all samples
    whose loss happens to be greater than or equal to a sample quantile.
    """
    values = _array(losses, "losses")
    if values.ndim != 1 or values.size == 0:
        raise ValueError("losses must be a nonempty one-dimensional array")
    beta = _beta(beta)
    if weights is None:
        mass = np.full(values.size, 1.0 / values.size)
    else:
        mass = _array(weights, "weights")
        if mass.shape != values.shape or np.any(mass < 0.0):
            raise ValueError("weights must match losses and be nonnegative")
        # Scaling before summation also avoids overflow for large raw masses.
        scale = float(np.max(mass))
        if scale <= 0.0:
            raise ValueError("weights must have a positive total mass")
        mass = mass / scale
        mass = mass / mass.sum()
    order = np.argsort(values)[::-1]
    sorted_mass = mass[order]
    prefix = np.concatenate(([0.0], np.cumsum(sorted_mass[:-1])))
    tail_mass = 1.0 - beta
    used_mass = np.minimum(sorted_mass, np.maximum(tail_mass - prefix, 0.0))
    return float(np.dot(used_mass / tail_mass, values[order]))


def budget_support(exposures, gamma) -> float:
    """Support of ``|zeta| <= 1, sum(|zeta|) <= gamma``.

    A fractional budget takes that fraction of the next largest absolute
    exposure.  A budget greater than the dimension is equivalent to a box.
    """
    values = _array(exposures, "exposures")
    if values.ndim != 1:
        raise ValueError("exposures must be a one-dimensional array")
    gamma = _scalar(gamma, "gamma")
    if gamma < 0.0:
        raise ValueError("gamma must be nonnegative")
    magnitudes = np.sort(np.abs(values))[::-1]
    capped = min(gamma, float(values.size))
    whole = int(np.floor(capped))
    support = float(magnitudes[:whole].sum())
    if whole < values.size:
        support += (capped - whole) * float(magnitudes[whole])
    return support


class _LinearProgram:
    """Small sparse-matrix builder; rows are never expanded to dense matrices."""

    def __init__(self):
        self.bounds = []
        self.eq_rows, self.eq_cols, self.eq_data, self.eq_rhs = [], [], [], []
        self.ub_rows, self.ub_cols, self.ub_data, self.ub_rhs = [], [], [], []

    def variables(self, shape, lower=0.0, upper=None):
        size = int(np.prod(shape))
        first = len(self.bounds)
        self.bounds.extend([(lower, upper)] * size)
        return np.arange(first, first + size).reshape(shape)

    def row(self, coefficients, rhs=0.0, equality=False):
        if equality:
            rows, cols, data, targets = (
                self.eq_rows, self.eq_cols, self.eq_data, self.eq_rhs
            )
        else:
            rows, cols, data, targets = (
                self.ub_rows, self.ub_cols, self.ub_data, self.ub_rhs
            )
        row_number = len(targets)
        for index, coefficient in coefficients:
            if coefficient:
                rows.append(row_number)
                cols.append(int(index))
                data.append(float(coefficient))
        targets.append(float(rhs))

    def matrices(self):
        n = len(self.bounds)
        equalities = coo_matrix(
            (self.eq_data, (self.eq_rows, self.eq_cols)),
            shape=(len(self.eq_rhs), n),
        ).tocsr()
        inequalities = coo_matrix(
            (self.ub_data, (self.ub_rows, self.ub_cols)),
            shape=(len(self.ub_rhs), n),
        ).tocsr()
        return equalities, np.asarray(self.eq_rhs), inequalities, np.asarray(self.ub_rhs)


def _scenario_array(value, name, scenarios, horizon):
    values = _array(value, name)
    if values.shape == (horizon,):
        return np.broadcast_to(values, (scenarios, horizon))
    if values.shape != (scenarios, horizon):
        raise ValueError(
            f"{name} must have shape ({horizon},) or ({scenarios}, {horizon})"
        )
    return values


def _parameters(battery, costs, initial_energy_kwh, previous_battery_kw):
    if battery is None:
        battery = Battery()
    if costs is None:
        costs = Costs()
    if not isinstance(battery, Battery) or not isinstance(costs, Costs):
        raise ValueError("battery and costs must be Battery and Costs instances")
    battery = Battery(**{
        field.name: _scalar(getattr(battery, field.name), f"battery.{field.name}")
        for field in fields(Battery)
    })
    costs = Costs(**{
        field.name: _scalar(getattr(costs, field.name), f"costs.{field.name}")
        for field in fields(Costs)
    })
    initial = _scalar(initial_energy_kwh, "initial_energy_kwh")
    previous = _scalar(previous_battery_kw, "previous_battery_kw")
    if battery.energy_min_kwh < 0 or battery.energy_max_kwh < battery.energy_min_kwh:
        raise ValueError("battery energy bounds must satisfy 0 <= min <= max")
    if not battery.energy_min_kwh <= initial <= battery.energy_max_kwh:
        raise ValueError("initial_energy_kwh must be within battery energy bounds")
    if not battery.energy_min_kwh <= battery.terminal_energy_kwh <= battery.energy_max_kwh:
        raise ValueError("terminal_energy_kwh must be within battery energy bounds")
    if battery.power_kw < 0 or battery.ramp_kw_per_hour < 0 or battery.self_discharge_kw < 0:
        raise ValueError("battery power, ramp, and self-discharge must be nonnegative")
    if abs(previous) > battery.power_kw:
        raise ValueError("previous_battery_kw must be within the battery power rating")
    if not (0 < battery.eta_charge <= 1 and 0 < battery.eta_discharge <= 1):
        raise ValueError("battery efficiencies must satisfy 0 < efficiency <= 1")
    cost_names = (
        "charge_per_kwh", "discharge_per_kwh", "low_energy_per_kwh_hour",
        "smoothing_per_kw_hour", "peak_per_kw", "flat_per_kw",
    )
    if any(getattr(costs, name) < 0 for name in cost_names):
        raise ValueError("cost penalty coefficients must be nonnegative")
    return battery, costs, initial, previous


def solve_dispatch(
    demand_kw,
    buy_price,
    sell_price,
    hours,
    initial_energy_kwh,
    battery=None,
    costs=None,
    beta=0.9,
    mode="cvar",
    buy_radius=None,
    sell_radius=None,
    gamma=None,
    previous_battery_kw=0.0,
    previous_grid_kw=None,
) -> DispatchResult:
    """Solve one shared-action, multi-scenario storage horizon.

    ``nominal`` and ``mean`` minimize the equally weighted mean cost (use one
    scenario for a deterministic forecast).  ``cvar`` minimizes pure CVaR.
    ``wcvar`` applies CVaR to costs protected against a *joint* buy/sell price
    budget, independently for each demand scenario.  Radius arrays follow the
    same (H,) or (S,H) convention as prices and default to zero.  Its default
    budget is ``2*sqrt(H)``.  Radius/budget arguments are rejected in other
    modes to avoid accidentally requesting risk protection that is ignored.
    Prices and price radii are interval-average rates in currency/kWh; this
    function multiplies them by ``hours``.  Do not pass the paper's already
    time-integrated price coefficients without first dividing by step hours.

    ``previous_grid_kw`` may be a scalar measured previous grid power, or an
    (S,) vector.  When omitted, no penalty is assigned to the first grid step.
    Low-energy penalties use the energy at the end of each horizon step.
    Throughput, low-energy and smoothing rates are multiplied by step hours;
    peak and maximum-minus-minimum penalties are charged once per horizon.
    """
    demand = _array(demand_kw, "demand_kw")
    if demand.ndim != 2 or min(demand.shape) == 0:
        raise ValueError("demand_kw must be a nonempty (scenarios, horizon) array")
    scenarios, horizon = demand.shape
    durations = _array(hours, "hours")
    if durations.shape != (horizon,) or np.any(durations <= 0):
        raise ValueError(f"hours must have shape ({horizon},) with strictly positive values")
    buy = _scenario_array(buy_price, "buy_price", scenarios, horizon)
    sell = _scenario_array(sell_price, "sell_price", scenarios, horizon)
    if np.any(sell < 0) or np.any(buy < sell):
        raise ValueError("prices must satisfy buy_price >= sell_price >= 0")
    beta = _beta(beta)
    if mode not in {"nominal", "mean", "cvar", "wcvar"}:
        raise ValueError("mode must be nominal, mean, cvar, or wcvar")
    battery, costs, initial, previous = _parameters(
        battery, costs, initial_energy_kwh, previous_battery_kw
    )
    previous_grid = None
    if previous_grid_kw is not None:
        previous_grid = _array(previous_grid_kw, "previous_grid_kw")
        if previous_grid.ndim == 0:
            previous_grid = np.full(scenarios, float(previous_grid))
        elif previous_grid.shape != (scenarios,):
            raise ValueError(f"previous_grid_kw must be a scalar or shape ({scenarios},)")
    robust = mode == "wcvar"
    if not robust and any(value is not None for value in (buy_radius, sell_radius, gamma)):
        raise ValueError("price radii and gamma are only used in wcvar mode")
    buy_uncertainty = np.zeros_like(demand)
    sell_uncertainty = np.zeros_like(demand)
    budget = 0.0
    if robust:
        if buy_radius is not None:
            buy_uncertainty = _scenario_array(buy_radius, "buy_radius", scenarios, horizon)
        if sell_radius is not None:
            sell_uncertainty = _scenario_array(sell_radius, "sell_radius", scenarios, horizon)
        if np.any(buy_uncertainty < 0) or np.any(sell_uncertainty < 0):
            raise ValueError("price uncertainty radii must be nonnegative")
        budget = 2.0 * np.sqrt(horizon) if gamma is None else _scalar(gamma, "gamma")
        if budget < 0:
            raise ValueError("gamma must be nonnegative")
        budget = min(budget, 2.0 * horizon)

    lp = _LinearProgram()
    charge = lp.variables((horizon,), upper=battery.power_kw)
    discharge = lp.variables((horizon,), upper=battery.power_kw)
    energy = lp.variables(
        (horizon + 1,), lower=battery.energy_min_kwh, upper=battery.energy_max_kwh
    )
    lp.bounds[int(energy[0])] = (initial, initial)
    lp.bounds[int(energy[-1])] = (battery.terminal_energy_kwh, battery.terminal_energy_kwh)
    low = lp.variables((horizon,))
    imports = lp.variables((scenarios, horizon))
    exports = lp.variables((scenarios, horizon))
    smooth = lp.variables((scenarios, horizon))
    peak = lp.variables((scenarios,))
    grid_max = lp.variables((scenarios,), lower=None)
    grid_min = lp.variables((scenarios,), lower=None)
    if robust:
        threshold = lp.variables((scenarios,))
        buy_excess = lp.variables((scenarios, horizon))
        sell_excess = lp.variables((scenarios, horizon))
    risk_objective = mode in {"cvar", "wcvar"}
    if risk_objective:
        quantile = lp.variables((1,), lower=None)[0]
        excess = lp.variables((scenarios,))

    for t, duration in enumerate(durations):
        lp.row([
            (energy[t + 1], 1), (energy[t], -1),
            (charge[t], -duration * battery.eta_charge),
            (discharge[t], duration / battery.eta_discharge),
        ], -duration * battery.self_discharge_kw, equality=True)
        lp.row([(energy[t + 1], -1), (low[t], -1)], -costs.energy_floor_kwh)
        ramp = [(charge[t], 1), (discharge[t], -1)]
        before = previous if t == 0 else 0.0
        if t:
            ramp.extend([(charge[t - 1], -1), (discharge[t - 1], 1)])
        limit = battery.ramp_kw_per_hour * duration
        lp.row(ramp, limit + before)
        lp.row([(index, -coefficient) for index, coefficient in ramp], limit - before)

    shared_cost = []
    for t, duration in enumerate(durations):
        shared_cost.extend([
            (charge[t], duration * costs.charge_per_kwh),
            (discharge[t], duration * costs.discharge_per_kwh),
            (low[t], duration * costs.low_energy_per_kwh_hour),
        ])
    objective = np.zeros(len(lp.bounds))
    if risk_objective:
        objective[quantile] = 1.0
        objective[excess] = 1.0 / (scenarios * (1.0 - beta))

    for s in range(scenarios):
        scenario_cost = list(shared_cost)
        scenario_cost.extend([
            (peak[s], costs.peak_per_kw),
            (grid_max[s], costs.flat_per_kw),
            (grid_min[s], -costs.flat_per_kw),
        ])
        if robust:
            scenario_cost.append((threshold[s], budget))
        for t, duration in enumerate(durations):
            # imports - exports = demand + charge - discharge.
            lp.row([
                (imports[s, t], 1), (exports[s, t], -1),
                (charge[t], -1), (discharge[t], 1),
            ], demand[s, t], equality=True)
            lp.row([(charge[t], 1), (discharge[t], -1), (peak[s], -1)],
                   costs.grid_baseline_kw - demand[s, t])
            lp.row([(charge[t], 1), (discharge[t], -1), (grid_max[s], -1)],
                   -demand[s, t])
            lp.row([(charge[t], -1), (discharge[t], 1), (grid_min[s], 1)],
                   demand[s, t])
            if t or previous_grid is not None:
                grid_change = [(charge[t], 1), (discharge[t], -1)]
                if t:
                    grid_change.extend([(charge[t - 1], -1), (discharge[t - 1], 1)])
                    constant = demand[s, t] - demand[s, t - 1]
                else:
                    constant = demand[s, t] - previous_grid[s]
                lp.row(grid_change + [(smooth[s, t], -1)], -constant)
                lp.row([(index, -coefficient) for index, coefficient in grid_change]
                       + [(smooth[s, t], -1)], constant)
                scenario_cost.append((smooth[s, t], duration * costs.smoothing_per_kw_hour))
            else:
                lp.bounds[int(smooth[s, t])] = (0.0, 0.0)
            scenario_cost.extend([
                (imports[s, t], duration * buy[s, t]),
                (exports[s, t], -duration * sell[s, t]),
            ])
            if robust:
                lp.row([
                    (imports[s, t], duration * buy_uncertainty[s, t]),
                    (threshold[s], -1), (buy_excess[s, t], -1),
                ])
                lp.row([
                    (exports[s, t], duration * sell_uncertainty[s, t]),
                    (threshold[s], -1), (sell_excess[s, t], -1),
                ])
                scenario_cost.extend([(buy_excess[s, t], 1), (sell_excess[s, t], 1)])
        if risk_objective:
            lp.row(scenario_cost + [(quantile, -1), (excess[s], -1)])
        else:
            for index, coefficient in scenario_cost:
                objective[index] += coefficient / scenarios

    a_eq, b_eq, a_ub, b_ub = lp.matrices()
    if not (np.all(np.isfinite(a_eq.data)) and np.all(np.isfinite(a_ub.data))
            and np.all(np.isfinite(b_eq)) and np.all(np.isfinite(b_ub))
            and np.all(np.isfinite(objective))):
        raise ValueError("input magnitudes overflow the LP coefficients")
    started = perf_counter()
    solution = linprog(
        objective, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq,
        bounds=lp.bounds, method="highs",
    )
    elapsed = perf_counter() - started
    if not solution.success:
        raise RuntimeError(
            f"Dispatch LP failed (status {solution.status}): {solution.message}. "
            "Check energy, terminal-state, power, ramp, and self-discharge feasibility."
        )
    if not np.all(np.isfinite(solution.x)) or not np.isfinite(solution.fun):
        raise RuntimeError("Dispatch LP returned a non-finite solution")

    charging = solution.x[charge].copy()
    discharging = solution.x[discharge].copy()
    power_tolerance = 1e-7 * max(1.0, battery.power_kw)
    simultaneous = float(np.max(np.minimum(charging, discharging)))
    if simultaneous > power_tolerance:
        raise RuntimeError(
            f"LP relaxation produced simultaneous charge/discharge ({simultaneous:.6g} kW). "
            "This solution is not a physically valid battery dispatch; use a mixed-integer "
            "complementarity model or revise the operating assumptions/costs."
        )
    net = charging - discharging
    actual_energy = np.concatenate(([initial], initial + np.cumsum(
        durations * (battery.eta_charge * charging
                     - discharging / battery.eta_discharge - battery.self_discharge_kw)
    )))
    energy_tolerance = 1e-7 * max(1.0, battery.energy_max_kwh, float(durations.sum()) * battery.power_kw)
    ramp_changes = np.diff(np.concatenate(([previous], net)))
    if (
        np.any(charging < -power_tolerance)
        or np.any(discharging < -power_tolerance)
        or np.any(charging > battery.power_kw + power_tolerance)
        or np.any(discharging > battery.power_kw + power_tolerance)
        or np.any(actual_energy < battery.energy_min_kwh - energy_tolerance)
        or np.any(actual_energy > battery.energy_max_kwh + energy_tolerance)
        or abs(actual_energy[-1] - battery.terminal_energy_kwh) > energy_tolerance
        or np.max(np.abs(actual_energy - solution.x[energy])) > energy_tolerance
        or np.any(np.abs(ramp_changes) > battery.ramp_kw_per_hour * durations + power_tolerance)
    ):
        raise RuntimeError("Dispatch LP solution failed independent battery feasibility checks")

    # Recompute from the physical schedule, never from slack epigraph variables.
    # In pure CVaR, non-tail scenarios need not have tight auxiliary variables.
    grid = demand + net[None, :]
    real_imports = np.maximum(grid, 0.0)
    real_exports = np.maximum(-grid, 0.0)
    changes = np.zeros_like(grid)
    changes[:, 1:] = np.abs(np.diff(grid, axis=1))
    if previous_grid is not None:
        changes[:, 0] = np.abs(grid[:, 0] - previous_grid)
    battery_cost = float(np.sum(durations * (
        costs.charge_per_kwh * charging + costs.discharge_per_kwh * discharging
        + costs.low_energy_per_kwh_hour * np.maximum(costs.energy_floor_kwh - actual_energy[1:], 0)
    )))
    scenario_costs = (
        battery_cost + np.sum(durations * (buy * real_imports - sell * real_exports), axis=1)
        + costs.smoothing_per_kw_hour * np.sum(durations * changes, axis=1)
        + costs.peak_per_kw * np.maximum(grid.max(axis=1) - costs.grid_baseline_kw, 0)
        + costs.flat_per_kw * (grid.max(axis=1) - grid.min(axis=1))
    )
    if robust:
        for s in range(scenarios):
            scenario_costs[s] += budget_support(np.concatenate((
                durations * buy_uncertainty[s] * real_imports[s],
                durations * sell_uncertainty[s] * real_exports[s],
            )), budget)
    actual_objective = (empirical_cvar(scenario_costs, beta) if risk_objective
                        else float(scenario_costs.mean()))
    if not np.all(np.isfinite(scenario_costs)) or not np.isclose(
        actual_objective, solution.fun, rtol=1e-6, atol=1e-7
    ):
        raise RuntimeError(
            "Dispatch objective failed independent cost reconstruction: "
            f"physical={actual_objective:.12g}, LP={solution.fun:.12g}"
        )
    return DispatchResult(
        charge_kw=charging, discharge_kw=discharging, energy_kwh=actual_energy,
        grid_kw=grid, scenario_costs=scenario_costs, objective=actual_objective,
        solve_seconds=elapsed, max_simultaneous_kw=max(simultaneous, 0.0),
    )
