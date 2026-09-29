from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Dict, Iterable, Mapping

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.stats import norm


@dataclass(frozen=True)
class DispatchConfig:
    dt_h: float = 0.25
    e_bat_kwh: float = 200.0
    p_bat_max_kw: float = 150.0
    eta_c: float = 0.95
    eta_d: float = 0.95
    soc_min: float = 0.10
    soc_max: float = 0.90
    soc_initial: float = 0.50
    import_limit_kw: float = 500.0
    export_limit_kw: float = 200.0
    c_buy: float = 0.30
    c_sell: float = 0.08
    c_curt: float = 0.02
    c_deg: float = 0.05
    voll: float = 5.00


@dataclass(frozen=True)
class DemoConfig:
    seed: int = 23
    days: int = 100
    horizon_steps: int = 4
    quantiles: tuple[float, ...] = tuple(np.round(np.arange(0.1, 1.0, 0.1), 1))


def make_demo_microgrid(days: int = 100, seed: int = 23) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = days * 96
    idx = pd.date_range("2025-01-01", periods=n, freq="15min")
    hour = idx.hour.to_numpy() + idx.minute.to_numpy() / 60
    day = np.arange(n) / 96.0

    ghi_base = 980 * np.clip(np.sin(np.pi * (hour - 6) / 12), 0, None)
    cloud = np.zeros(n)
    eps = rng.normal(0, 0.22, n)
    for t in range(1, n):
        cloud[t] = 0.90 * cloud[t - 1] + eps[t]
    trans = np.clip(0.78 - 0.30 * cloud, 0.18, 1.05)
    ghi = np.clip(ghi_base * trans + rng.normal(0, 18, n), 0, None)

    pv = 430 * (ghi / 1000.0) * (0.96 + 0.03 * np.sin(2 * np.pi * day / 365))
    pv += rng.normal(0, 4 + 0.025 * pv, n)
    pv = np.clip(pv, 0, 430)

    morning = 45 * np.exp(-0.5 * ((hour - 8.0) / 1.8) ** 2)
    evening = 75 * np.exp(-0.5 * ((hour - 19.0) / 2.0) ** 2)
    load = 190 + morning + evening + 18 * np.sin(2 * np.pi * day / 7)
    load += rng.normal(0, 8, n)
    load = np.clip(load, 90, None)

    return pd.DataFrame({"pv_kw": pv, "load_kw": load, "ghi": ghi}, index=idx)


def make_demo_forecasts(df: pd.DataFrame, horizon_steps: int = 4, seed: int = 23):
    rng = np.random.default_rng(seed)
    actual = df["pv_kw"].to_numpy()
    persistence = np.roll(actual, horizon_steps)
    persistence[:horizon_steps] = actual[:horizon_steps]

    variability = pd.Series(actual).diff().abs().rolling(8, min_periods=1).mean().to_numpy()
    sigma = 10 + 0.45 * variability + 0.035 * actual
    point = np.clip(actual + rng.normal(0, sigma), 0, 430)

    q = {}
    for tau in np.round(np.arange(0.1, 1.0, 0.1), 1):
        q[float(tau)] = np.clip(point + norm.ppf(tau) * sigma, 0, 430)
    return {"persistence": persistence, "point": point, "quantiles": q, "perfect": actual.copy()}


def _cost_vector(H: int, cfg: DispatchConfig, include_battery: bool = True):
    c = np.zeros(6 * H)
    c[0:H] = cfg.c_deg * cfg.dt_h if include_battery else 0.0
    c[H:2 * H] = cfg.c_deg * cfg.dt_h if include_battery else 0.0
    c[2 * H:3 * H] = cfg.c_buy * cfg.dt_h
    c[3 * H:4 * H] = -cfg.c_sell * cfg.dt_h
    c[4 * H:5 * H] = cfg.c_curt * cfg.dt_h
    c[5 * H:6 * H] = cfg.voll * cfg.dt_h
    return c


def solve_commitment(pv_commit: np.ndarray, load: np.ndarray, soc0: float, cfg: DispatchConfig):
    pv_commit = np.asarray(pv_commit, float)
    load = np.asarray(load, float)
    H = len(load)
    n = 6 * H
    ch = np.arange(H)
    dis = H + np.arange(H)
    imp = 2 * H + np.arange(H)
    exp = 3 * H + np.arange(H)
    curt = 4 * H + np.arange(H)
    ens = 5 * H + np.arange(H)

    Aeq, beq = [], []
    for t in range(H):
        row = np.zeros(n)
        row[ch[t]] = -1
        row[dis[t]] = 1
        row[imp[t]] = 1
        row[exp[t]] = -1
        row[curt[t]] = -1
        row[ens[t]] = 1
        Aeq.append(row)
        beq.append(load[t] - pv_commit[t])

    Aub, bub = [], []
    e0 = soc0 * cfg.e_bat_kwh
    emin = cfg.soc_min * cfg.e_bat_kwh
    emax = cfg.soc_max * cfg.e_bat_kwh
    for t in range(H):
        row = np.zeros(n)
        row[ch[: t + 1]] = cfg.eta_c * cfg.dt_h
        row[dis[: t + 1]] = -cfg.dt_h / cfg.eta_d
        Aub.append(row.copy())
        bub.append(emax - e0)
        Aub.append(-row.copy())
        bub.append(e0 - emin)

    bounds = (
        [(0, cfg.p_bat_max_kw)] * H
        + [(0, cfg.p_bat_max_kw)] * H
        + [(0, cfg.import_limit_kw)] * H
        + [(0, cfg.export_limit_kw)] * H
        + [(0, float(max(pv_commit[t], 0.0))) for t in range(H)]
        + [(0, None)] * H
    )
    res = linprog(
        _cost_vector(H, cfg, include_battery=True),
        A_ub=np.asarray(Aub),
        b_ub=np.asarray(bub),
        A_eq=np.asarray(Aeq),
        b_eq=np.asarray(beq),
        bounds=bounds,
        method="highs",
    )
    if not res.success:
        raise RuntimeError(f"commitment LP failed: {res.message}")
    x = res.x
    return {"ch": x[ch], "dis": x[dis]}


def solve_recourse(actual_pv: np.ndarray, load: np.ndarray, schedule: Mapping[str, np.ndarray], cfg: DispatchConfig):
    actual_pv = np.asarray(actual_pv, float)
    load = np.asarray(load, float)
    ch = np.asarray(schedule["ch"], float)
    dis = np.asarray(schedule["dis"], float)
    H = len(load)
    imp = np.arange(H)
    exp = H + np.arange(H)
    curt = 2 * H + np.arange(H)
    ens = 3 * H + np.arange(H)
    n = 4 * H

    Aeq, beq = [], []
    for t in range(H):
        row = np.zeros(n)
        row[imp[t]] = 1
        row[exp[t]] = -1
        row[curt[t]] = -1
        row[ens[t]] = 1
        Aeq.append(row)
        beq.append(load[t] + ch[t] - dis[t] - actual_pv[t])

    c = np.zeros(n)
    c[imp] = cfg.c_buy * cfg.dt_h
    c[exp] = -cfg.c_sell * cfg.dt_h
    c[curt] = cfg.c_curt * cfg.dt_h
    c[ens] = cfg.voll * cfg.dt_h
    bounds = (
        [(0, cfg.import_limit_kw)] * H
        + [(0, cfg.export_limit_kw)] * H
        + [(0, float(max(actual_pv[t], 0.0))) for t in range(H)]
        + [(0, None)] * H
    )
    res = linprog(c, A_eq=np.asarray(Aeq), b_eq=np.asarray(beq), bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(f"recourse LP failed: {res.message}")
    x = res.x
    throughput_cost = cfg.c_deg * cfg.dt_h * float(np.sum(ch + dis))
    components = {
        "import_cost": cfg.c_buy * cfg.dt_h * float(np.sum(x[imp])),
        "export_revenue": cfg.c_sell * cfg.dt_h * float(np.sum(x[exp])),
        "curtailment_cost": cfg.c_curt * cfg.dt_h * float(np.sum(x[curt])),
        "degradation_cost": throughput_cost,
        "ens_cost": cfg.voll * cfg.dt_h * float(np.sum(x[ens])),
        "ens_kwh": cfg.dt_h * float(np.sum(x[ens])),
        "battery_throughput_kwh": cfg.dt_h * float(np.sum(ch + dis)),
        "import_kwh": cfg.dt_h * float(np.sum(x[imp])),
        "export_kwh": cfg.dt_h * float(np.sum(x[exp])),
        "curtailment_kwh": cfg.dt_h * float(np.sum(x[curt])),
    }
    components["total_cost"] = (
        components["import_cost"]
        - components["export_revenue"]
        + components["curtailment_cost"]
        + components["degradation_cost"]
        + components["ens_cost"]
    )
    return components


def _end_soc(soc0: float, schedule: Mapping[str, np.ndarray], cfg: DispatchConfig) -> float:
    e = soc0 * cfg.e_bat_kwh
    e += cfg.dt_h * (cfg.eta_c * np.sum(schedule["ch"]) - np.sum(schedule["dis"]) / cfg.eta_d)
    return float(np.clip(e / cfg.e_bat_kwh, cfg.soc_min, cfg.soc_max))


def evaluate_commitment_series(
    df: pd.DataFrame,
    pv_commit: np.ndarray,
    cfg: DispatchConfig,
    return_schedules: bool = False,
):
    pv = df["pv_kw"].to_numpy()
    load = df["load_kw"].to_numpy()
    pv_commit = np.asarray(pv_commit, float)
    n_days = len(df) // 96
    soc = cfg.soc_initial
    daily = []
    schedules = []
    for d in range(n_days):
        sl = slice(d * 96, (d + 1) * 96)
        sched = solve_commitment(pv_commit[sl], load[sl], soc, cfg)
        rec = solve_recourse(pv[sl], load[sl], sched, cfg)
        rec["day"] = str(df.index[d * 96].date())
        daily.append(rec)
        schedules.append(sched)
        soc = _end_soc(soc, sched, cfg)
    daily_df = pd.DataFrame(daily)
    agg = {k: float(daily_df[k].sum()) for k in daily_df.columns if k not in {"day"}}
    costs = daily_df["total_cost"].to_numpy()
    if len(costs):
        q95 = np.quantile(costs, 0.95)
        agg["daily_cost_cvar95"] = float(costs[costs >= q95].mean())
        agg["mean_daily_cost"] = float(costs.mean())
    if return_schedules:
        return agg, daily_df, schedules
    return agg, daily_df


def reprice_fixed_commitments(
    df: pd.DataFrame,
    schedules: Iterable[Mapping[str, np.ndarray]],
    cfg: DispatchConfig,
):
    pv = df["pv_kw"].to_numpy()
    load = df["load_kw"].to_numpy()
    rows = []
    for d, sched in enumerate(schedules):
        sl = slice(d * 96, (d + 1) * 96)
        rec = solve_recourse(pv[sl], load[sl], sched, cfg)
        rec["day"] = str(df.index[d * 96].date())
        rows.append(rec)
    x = pd.DataFrame(rows)
    return float(x.total_cost.sum()), float(x.ens_kwh.sum())


def value_metrics(costs: Mapping[str, float], point_name: str = "point") -> Dict[str, dict]:
    cpersist = float(costs["persistence"])
    cperfect = float(costs["perfect"])
    cpoint = float(costs[point_name])
    upper = cpersist - cperfect
    out = {}
    for name, cm in costs.items():
        cm = float(cm)
        ev_persist = cpersist - cm
        out[name] = {
            "cost": cm,
            "ev_vs_persistence": ev_persist,
            "ev_vs_point": cpoint - cm,
            "perfect_value_upper_bound": upper,
            "value_capture_ratio": (ev_persist / upper) if abs(upper) > 1e-9 else None,
            "value_capture_gap": cm - cperfect,
        }
    return out


def run(cfg_demo: DemoConfig, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    full = make_demo_microgrid(cfg_demo.days, cfg_demo.seed)
    forecasts = make_demo_forecasts(full, cfg_demo.horizon_steps, cfg_demo.seed)

    df = full.iloc[cfg_demo.horizon_steps:].copy()
    for k in ("persistence", "point", "perfect"):
        forecasts[k] = forecasts[k][cfg_demo.horizon_steps:]
    forecasts["quantiles"] = {a: v[cfg_demo.horizon_steps:] for a, v in forecasts["quantiles"].items()}
    keep = (len(df) // 96) * 96
    df = df.iloc[-keep:]
    for k in ("persistence", "point", "perfect"):
        forecasts[k] = forecasts[k][-keep:]
    forecasts["quantiles"] = {a: v[-keep:] for a, v in forecasts["quantiles"].items()}

    central_cfg = DispatchConfig()
    strategy_commitments = {
        "persistence": forecasts["persistence"],
        "point": forecasts["point"],
        "perfect": forecasts["perfect"],
    }
    for a in cfg_demo.quantiles:
        strategy_commitments[f"q{a:.1f}"] = forecasts["quantiles"][float(a)]

    central_rows = []
    schedules_by_strategy = {}
    total_costs = {}
    for name, commitment in strategy_commitments.items():
        agg, _, schedules = evaluate_commitment_series(df, commitment, central_cfg, return_schedules=True)
        total_costs[name] = agg["total_cost"]
        schedules_by_strategy[name] = schedules
        central_rows.append({"strategy": name, **agg})
    central = pd.DataFrame(central_rows).set_index("strategy")

    values = value_metrics(total_costs)
    value_table = pd.DataFrame(values).T
    qscan = value_table.loc[[f"q{a:.1f}" for a in cfg_demo.quantiles]].copy()
    qscan.index.name = "strategy"

    boundary_rows = []
    boundary_strategies = ["persistence", "point", "q0.1", "q0.5", "q0.7", "q0.9", "perfect"]
    for imp in (0.0, 50.0, 150.0, 500.0):
        for voll in (1.0, 5.0, 20.0):
            bcfg = replace(central_cfg, import_limit_kw=imp, voll=voll)
            cell_costs = {}
            cell_ens = {}
            for name in boundary_strategies:
                cost, ens = reprice_fixed_commitments(df, schedules_by_strategy[name], bcfg)
                cell_costs[name] = cost
                cell_ens[name] = ens
            cell_values = value_metrics(cell_costs)
            for name in boundary_strategies:
                boundary_rows.append(
                    {
                        "import_limit_kw": imp,
                        "voll": voll,
                        "strategy": name,
                        "cost": cell_costs[name],
                        "ens_kwh": cell_ens[name],
                        "value_capture_ratio": cell_values[name]["value_capture_ratio"],
                        "ev_vs_persistence": cell_values[name]["ev_vs_persistence"],
                    }
                )
    boundary = pd.DataFrame(boundary_rows)

    island_cfg = replace(central_cfg, import_limit_kw=0.0, export_limit_kw=0.0, voll=20.0)
    island_rows = []
    island_costs = {}
    for name in boundary_strategies:
        agg, _ = evaluate_commitment_series(df, strategy_commitments[name], island_cfg)
        island_costs[name] = agg["total_cost"]
        island_rows.append({"strategy": name, **agg})
    island_values = value_metrics(island_costs)
    island = pd.DataFrame(island_rows).set_index("strategy")
    island["value_capture_ratio"] = [island_values[x]["value_capture_ratio"] for x in island.index]

    central.to_csv(out_dir / "central_dispatch.csv")
    value_table.to_csv(out_dir / "decision_value.csv")
    qscan.to_csv(out_dir / "quantile_scan.csv")
    boundary.to_csv(out_dir / "fixed_commitment_boundary.csv", index=False)
    island.to_csv(out_dir / "islanded_reoptimized.csv")

    summary = {
        "demo_config": asdict(cfg_demo),
        "dispatch_config": asdict(central_cfg),
        "best_demo_quantile_by_cost": str(qscan["cost"].idxmin()),
        "perfect_value_upper_bound": float(value_table.loc["perfect", "perfect_value_upper_bound"]),
        "point_value_capture_ratio": value_table.loc["point", "value_capture_ratio"],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="results/demo")
    p.add_argument("--smoke", action="store_true")
    args = p.parse_args()
    cfg = DemoConfig(days=12 if args.smoke else 100)
    result = run(cfg, Path(args.out))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
