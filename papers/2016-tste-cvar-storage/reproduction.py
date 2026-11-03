"""Receding-horizon experiments for Khodabakhsh & Sirouspour (2016).

The bundled data are synthetic; this is a method reproduction, not a recovery
of the paper's unavailable Burlington Hydro measurements or numerical tables.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
from dataclasses import asdict
from pathlib import Path

import numpy as np
import scipy

from model import Battery, Costs, empirical_cvar, solve_dispatch
from scenarios import (
    BASE_HOURS, PAPER_HOURS, aggregate_horizon, load_csv, price_std,
    rng_for, sample_joint, synthetic_series,
)


def load_config(path=None):
    """Explicit assumptions where the article does not specify a value."""
    config = {
        "battery": asdict(Battery()),
        "costs": asdict(Costs()),
        "initial_energy_kwh": 25.0,
        "inventory_value_per_kwh": 0.062 / 0.95,
        "rho": 0.5,
    }
    if path is not None:
        supplied = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(supplied, dict) or set(supplied) - set(config):
            raise ValueError("config must be an object with documented configuration keys")
        for name, value in supplied.items():
            if name in {"battery", "costs"}:
                if not isinstance(value, dict) or set(value) - set(config[name]):
                    raise ValueError(f"unknown or invalid {name} configuration")
                config[name].update(value)
            else:
                config[name] = value
    Battery(**config["battery"])
    Costs(**config["costs"])
    for key in ("initial_energy_kwh", "inventory_value_per_kwh", "rho"):
        value = float(config[key])
        if not np.isfinite(value):
            raise ValueError(f"{key} must be finite")
        config[key] = value
    if config["inventory_value_per_kwh"] < 0 or not -1 <= config["rho"] <= 1:
        raise ValueError("inventory value must be nonnegative and rho within [-1, 1]")
    return config


def trajectory_metrics(rows, costs, initial_energy, inventory_value):
    """Cost of executed actions, with each day's peak/range charged once.

    A short smoke run has a partial day.  Inventory adjustment is a declared
    evaluation convention, not a terminal recharge action or a paper result.
    """
    if not rows:
        raise ValueError("a trajectory must contain executed actions")
    bill = sum(row["energy_bill"] for row in rows)
    throughput = sum(row["throughput_cost"] for row in rows)
    low_energy = sum(row["low_energy_cost"] for row in rows)
    smoothing = sum(row["smoothing_cost"] for row in rows)
    by_day = {}
    for row in rows:
        by_day.setdefault(row["timestamp"][:10], []).append(row["grid_kw"])
    peak = sum(costs.peak_per_kw * max(max(grid) - costs.grid_baseline_kw, 0)
               for grid in by_day.values())
    flat = sum(costs.flat_per_kw * (max(grid) - min(grid)) for grid in by_day.values())
    ending_energy = rows[-1]["energy_kwh"]
    adjustment = inventory_value * (initial_energy - ending_energy)
    composite = bill + throughput + low_energy + smoothing + peak + flat
    return {
        "energy_bill": bill,
        "throughput_cost": throughput,
        "low_energy_cost": low_energy,
        "smoothing_cost": smoothing,
        "peak_cost": peak,
        "flat_cost": flat,
        "composite_cost": composite,
        "inventory_adjustment": adjustment,
        "inventory_adjusted_bill": bill + adjustment,
        "inventory_adjusted_composite": composite + adjustment,
        "initial_energy_kwh": initial_energy,
        "ending_energy_kwh": ending_energy,
        "max_grid_kw": max(row["grid_kw"] for row in rows),
        "max_simultaneous_kw": max(row["max_simultaneous_kw"] for row in rows),
        "solve_seconds": sum(row["solve_seconds"] for row in rows),
    }


def summarize(metrics, beta):
    groups = {}
    for metric in metrics:
        key = (metric["actual_uncertainty_scale"], metric["method"])
        groups.setdefault(key, []).append(metric)
    summary = []
    for (scale, method), values in sorted(groups.items()):
        out = {"actual_uncertainty_scale": scale, "method": method,
               "replications": len(values)}
        for name in ("energy_bill", "inventory_adjusted_bill", "composite_cost",
                     "inventory_adjusted_composite", "ending_energy_kwh"):
            sample = np.array([value[name] for value in values])
            out[f"mean_{name}"] = float(sample.mean())
            if name != "ending_energy_kwh":
                out[f"cvar_{name}"] = empirical_cvar(sample, beta)
            out[f"std_{name}"] = float(sample.std(ddof=1)) if len(sample) > 1 else None
        summary.append(out)
    return summary


def run_experiment(args):
    config = load_config(args.config)
    battery = Battery(**config["battery"])
    costs = Costs(**config["costs"])
    steps = 4 if args.smoke else 48 * args.days
    replications = 2 if args.smoke else args.replications
    scenario_count = 16 if args.smoke else args.scenarios
    wcvar_count = 8 if args.smoke else args.wcvar_scenarios
    required = steps + 47
    series = (load_csv(args.nominal_csv, required) if args.nominal_csv
              else synthetic_series(required))
    methods = ["nominal", "cvar", "wcvar"]
    if args.include_mean:
        methods.insert(1, "mean")
    dispatch_rows, all_metrics, clipping = [], [], []
    for scale in args.actual_scales:
        for replication in range(replications):
            actual_demand, actual_buy, actual_clipped = sample_joint(
                series.demand_kw[:steps], series.buy_price[:steps], series.sell_price[:steps],
                np.full(steps, BASE_HOURS), 1, rng_for(args.seed, 1, replication),
                scale=scale, rho=config["rho"],
            )
            actual_demand, actual_buy = actual_demand[0], actual_buy[0]
            states = {method: {"energy": config["initial_energy_kwh"], "power": 0., "grid": None}
                      for method in methods}
            runs = {method: [] for method in methods + ["no_storage"]}
            forecast_clipped = 0
            for origin in range(steps):
                nominal_demand, nominal_buy, nominal_sell = aggregate_horizon(series, origin)
                count = max(scenario_count, wcvar_count)
                demands, buys, count_clipped = sample_joint(
                    nominal_demand, nominal_buy, nominal_sell, PAPER_HOURS, count,
                    rng_for(args.seed, 2, replication, origin),
                    scale=args.model_scale, rho=config["rho"],
                )
                forecast_clipped += count_clipped
                for method in methods + ["no_storage"]:
                    if method == "no_storage":
                        charge = discharge = objective = solve_seconds = overlap = 0.
                        energy = config["initial_energy_kwh"]
                        previous_grid = (runs[method][-1]["grid_kw"] if origin else None)
                    else:
                        state = states[method]
                        if method == "nominal":
                            demand, buy = nominal_demand[None, :], nominal_buy
                        elif method == "wcvar":
                            demand, buy = demands[:wcvar_count], nominal_buy
                        else:
                            demand, buy = demands[:scenario_count], buys[:scenario_count]
                        robust = ({"buy_radius": price_std(nominal_buy, PAPER_HOURS, args.model_scale),
                                   "sell_radius": np.zeros_like(nominal_sell), "gamma": args.gamma}
                                  if method == "wcvar" else {})
                        try:
                            result = solve_dispatch(
                                demand, buy, nominal_sell, PAPER_HOURS, state["energy"],
                                battery=battery, costs=costs, beta=args.beta, mode=method,
                                previous_battery_kw=state["power"], previous_grid_kw=state["grid"],
                                **robust,
                            )
                        except (ValueError, RuntimeError) as exc:
                            raise RuntimeError(
                                f"{method}: scale={scale}, replication={replication}, "
                                f"origin={origin}: {exc}"
                            ) from exc
                        charge, discharge = float(result.charge_kw[0]), float(result.discharge_kw[0])
                        energy = state["energy"] + BASE_HOURS * (
                            battery.eta_charge * charge - discharge / battery.eta_discharge
                            - battery.self_discharge_kw
                        )
                        if not np.isclose(energy, result.energy_kwh[1], atol=1e-7, rtol=1e-8):
                            raise RuntimeError("executed SOC does not match first predicted SOC")
                        # Clip numerical roundoff only, after solver feasibility verification.
                        energy = float(np.clip(energy, battery.energy_min_kwh, battery.energy_max_kwh))
                        objective, solve_seconds = result.objective, result.solve_seconds
                        overlap = result.max_simultaneous_kw
                        previous_grid = state["grid"]
                    grid = float(actual_demand[origin] + charge - discharge)
                    bill = BASE_HOURS * (
                        actual_buy[origin] * max(grid, 0.)
                        - series.sell_price[origin] * max(-grid, 0.)
                    )
                    row = {
                        "actual_uncertainty_scale": scale, "replication": replication,
                        "method": method, "step": origin,
                        "timestamp": series.timestamps[origin].isoformat(),
                        "actual_net_load_kw": float(actual_demand[origin]),
                        "actual_buy_price_per_kwh": float(actual_buy[origin]),
                        "actual_sell_price_per_kwh": float(series.sell_price[origin]),
                        "charge_kw": charge, "discharge_kw": discharge, "grid_kw": grid,
                        "energy_kwh": energy, "energy_bill": float(bill),
                        "throughput_cost": BASE_HOURS * (
                            costs.charge_per_kwh * charge + costs.discharge_per_kwh * discharge),
                        "low_energy_cost": (BASE_HOURS * costs.low_energy_per_kwh_hour
                                            * max(costs.energy_floor_kwh - energy, 0.)
                                            if method != "no_storage" else 0.),
                        "smoothing_cost": (BASE_HOURS * costs.smoothing_per_kw_hour
                                           * abs(grid - previous_grid) if previous_grid is not None else 0.),
                        "forecast_objective": float(objective), "solve_seconds": float(solve_seconds),
                        "max_simultaneous_kw": float(overlap),
                    }
                    runs[method].append(row)
                    if method != "no_storage":
                        states[method] = {"energy": energy, "power": charge - discharge, "grid": grid}
            for method, rows in runs.items():
                dispatch_rows.extend(rows)
                metric = trajectory_metrics(rows, costs, config["initial_energy_kwh"],
                                            config["inventory_value_per_kwh"])
                metric.update(actual_uncertainty_scale=scale, replication=replication, method=method)
                all_metrics.append(metric)
            clipping.append({"actual_uncertainty_scale": scale, "replication": replication,
                             "actual_buy_clipped": actual_clipped, "actual_buy_samples": steps,
                             "forecast_buy_clipped": forecast_clipped,
                             "forecast_buy_samples": steps * max(scenario_count, wcvar_count) * len(PAPER_HOURS)})
            print(f"completed scale={scale:g}, replication={replication + 1}/{replications}", flush=True)
    metadata = {
        "paper": "Khodabakhsh & Sirouspour (2016), DOI:10.1109/TSTE.2016.2543024",
        "scope": "method reproduction with synthetic or supplied nominal data; not original numerical replication",
        "seed": args.seed, "smoke": args.smoke, "executed_steps": steps,
        "replications": replications, "cvar_scenarios": scenario_count, "wcvar_scenarios": wcvar_count,
        "beta": args.beta, "hours": PAPER_HOURS.tolist(), "methods": methods + ["no_storage"],
        "model_uncertainty_scale": args.model_scale, "actual_uncertainty_scales": args.actual_scales,
        "gamma": float(2 * np.sqrt(len(PAPER_HOURS)) if args.gamma is None else args.gamma),
        "config": config, "data": series.provenance, "clipping": clipping,
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "evaluation": {
            "tail_unit": "whole executed trajectory total across independent replications",
            "inventory": "adjustment = common inventory_value_per_kwh * (initial_energy - ending_energy)",
            "peak_range": "charged once per calendar day; partial days use only executed samples",
            "small_sample_notice": "Smoke and default runs verify execution; they do not establish tail-risk superiority.",
            "no_storage": "Energy-bill reference; constant bookkeeping inventory, no physical storage or low-SOC cost.",
        },
        "assumptions": [
            "Nominal forecasts are supplied or synthetic; no fitted forecasting model.",
            "Independent forecast blocks; joint demand/buy-price Gaussian before censoring.",
            "Buy prices censored at fixed sell prices; Gaussian moments/correlation change after censoring.",
            "CVAR and optional mean share scenarios; WCVAR shares their demand prefix, with nominal price plus robust radii.",
            "WCVAR protects each scenario separately, using one joint buy/sell uncertainty budget per scenario.",
            "Scenario RNG stream is separate from realized-path RNG; controllers share realized paths.",
            "Mean controller and residual-inventory valuation are evaluation extensions.",
        ],
    }
    return dispatch_rows, all_metrics, {"metadata": metadata, "summary": summarize(all_metrics, args.beta)}


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def make_figures(out, rows, report):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    first_scale = report["metadata"]["actual_uncertainty_scales"][0]
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True, constrained_layout=True)
    for method in report["metadata"]["methods"]:
        data = [row for row in rows if row["method"] == method and row["replication"] == 0
                and row["actual_uncertainty_scale"] == first_scale]
        edges = np.arange(len(data) + 1) * BASE_HOURS
        grid = [row["grid_kw"] for row in data]
        axes[0].step(edges, grid + grid[-1:], where="post", label=method)
        if method != "no_storage":
            power = [row["charge_kw"] - row["discharge_kw"] for row in data]
            axes[1].step(edges, power + power[-1:], where="post", label=method)
            energy = [report["metadata"]["config"]["initial_energy_kwh"]] + [row["energy_kwh"] for row in data]
            axes[2].plot(edges, energy, label=method)
    for ax, label in zip(axes, ["Grid power (kW)", "Battery power (kW)", "Stored energy (kWh)"]):
        ax.set_ylabel(label)
        ax.grid(alpha=.25)
    axes[0].legend(ncol=3)
    axes[0].set_title(f"Method reproduction — first realized path, uncertainty scale {first_scale:g}")
    axes[-1].set_xlabel("Elapsed hours")
    fig.savefig(out / "dispatch.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for method in report["metadata"]["methods"]:
        data = [row for row in report["summary"] if row["method"] == method]
        x = [row["actual_uncertainty_scale"] for row in data]
        axes[0].plot(x, [row["mean_inventory_adjusted_bill"] for row in data], "o-", label=method)
        axes[1].plot(x, [row["cvar_inventory_adjusted_composite"] for row in data], "o-", label=method)
    axes[0].set_ylabel("Mean inventory-adjusted energy bill ($)")
    axes[1].set_ylabel("CVaR of adjusted composite cost ($)")
    for ax in axes:
        ax.set_xlabel("Realized uncertainty scale (model scale fixed)")
        ax.grid(alpha=.25)
    axes[0].legend()
    fig.savefig(out / "costs.png", dpi=160)
    plt.close(fig)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="4 executed half-hours, 2 paths, 16/8 scenarios")
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--replications", type=int, default=3, help="independent realized trajectories, not optimization scenarios")
    parser.add_argument("--scenarios", type=int, default=60, help="joint demand/price scenarios for CVaR and mean")
    parser.add_argument("--wcvar-scenarios", type=int, default=50)
    parser.add_argument("--beta", type=float, default=.9)
    parser.add_argument("--seed", type=int, default=2016)
    parser.add_argument("--model-scale", type=float, default=1., help="fixed forecast-error standard deviation multiplier")
    parser.add_argument("--actual-scales", default="1", help="comma-separated realized-error multipliers, e.g. 0,0.5,1,1.5,2,2.5")
    parser.add_argument("--gamma", type=float, default=None, help="WCVAR budget; default 2*sqrt(14)")
    parser.add_argument("--include-mean", action="store_true", help="additional same-scenario risk-neutral baseline")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--nominal-csv", type=Path)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "results" / "demo")
    args = parser.parse_args(argv)
    try:
        args.actual_scales = [float(value) for value in args.actual_scales.split(",")]
    except ValueError:
        parser.error("--actual-scales must be a comma-separated numeric list")
    if min(args.days, args.replications, args.scenarios, args.wcvar_scenarios) <= 0:
        parser.error("days, replications and scenario counts must be positive")
    if args.seed < 0:
        parser.error("seed must be nonnegative")
    if not np.isfinite(args.beta) or not 0 <= args.beta < 1:
        parser.error("beta must satisfy 0 <= beta < 1")
    if not np.isfinite(args.model_scale) or args.model_scale < 0:
        parser.error("model-scale must be finite and nonnegative")
    if any(not np.isfinite(scale) or scale < 0 for scale in args.actual_scales):
        parser.error("actual-scales must be finite and nonnegative")
    if len(set(args.actual_scales)) != len(args.actual_scales):
        parser.error("actual-scales must not contain duplicates")
    if args.gamma is not None and (not np.isfinite(args.gamma) or args.gamma < 0):
        parser.error("gamma must be finite and nonnegative")
    return args


def main(argv=None):
    args = parse_args(argv)
    rows, metrics, report = run_experiment(args)
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "dispatch.csv", rows)
    write_csv(args.out / "trajectory_metrics.csv", metrics)
    (args.out / "summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8"
    )
    make_figures(args.out, rows, report)
    print(f"Wrote dispatch.csv, trajectory_metrics.csv, summary.json and figures to {args.out}")


if __name__ == "__main__":
    main()
