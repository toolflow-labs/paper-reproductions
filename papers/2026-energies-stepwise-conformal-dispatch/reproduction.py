from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from sklearn.ensemble import HistGradientBoostingRegressor


QUANTILES = (0.05, 0.50, 0.95)


@dataclass
class Config:
    seed: int = 42
    days: int = 120
    lookback: int = 96
    horizon: int = 16
    coverage: float = 0.90
    max_train: int = 5000
    model_iter: int = 60
    dispatch_steps: int = 96 * 10


def make_synthetic_microgrid(days: int = 120, seed: int = 42) -> pd.DataFrame:
    """Generate a deterministic high-PV 15-min microgrid series for a clean-room demo."""
    rng = np.random.default_rng(seed)
    n = days * 96
    idx = pd.date_range("2024-01-01", periods=n, freq="15min")
    hour = idx.hour.to_numpy() + idx.minute.to_numpy() / 60.0
    day = np.arange(n) / 96.0
    dow = idx.dayofweek.to_numpy()

    temp = 18 + 8 * np.sin(2 * np.pi * (day / 365.0 - 0.15)) + 5 * np.sin(2 * np.pi * (hour - 14) / 24)
    cloud = np.zeros(n)
    eps = rng.normal(0, 0.18, n)
    for t in range(1, n):
        cloud[t] = 0.92 * cloud[t - 1] + eps[t]
    cloud_factor = np.clip(0.80 - 0.25 * cloud, 0.20, 1.05)

    sun = np.clip(np.sin(np.pi * (hour - 6) / 12), 0, None)
    pv = 52.1 * sun ** 1.7 * cloud_factor
    pv += rng.normal(0, 0.45 + 0.03 * pv, n)
    pv = np.clip(pv, 0, None)

    morning = 6.0 * np.exp(-0.5 * ((hour - 8.0) / 1.8) ** 2)
    evening = 10.0 * np.exp(-0.5 * ((hour - 19.0) / 2.2) ** 2)
    weekday = np.where(dow < 5, 2.5, -1.0)
    load = 24 + morning + evening + weekday + 0.12 * np.maximum(25 - temp, 0)
    load += rng.normal(0, 1.0, n)
    load = np.clip(load, 8, None)

    price = np.where((hour >= 17) & (hour < 21), 1.10, np.where((hour >= 0) & (hour < 6), 0.35, 0.65))
    return pd.DataFrame(
        {"load_mw": load, "pv_mw": pv, "net_mw": load - pv, "price": price, "temp_c": temp},
        index=idx,
    )


def _origin_features(df: pd.DataFrame, origins: np.ndarray, horizon: int) -> np.ndarray:
    lags = np.array([1, 4, 8, 16, 48, 96], dtype=int)
    rows = []
    for o in origins:
        vals = []
        for col in ("net_mw", "load_mw", "pv_mw"):
            a = df[col].to_numpy()
            vals.extend(a[o - lags])
        ts = df.index[o]
        fh = (ts.hour + ts.minute / 60.0 + horizon * 0.25) % 24
        fdow = (ts.dayofweek + int((ts.hour + ts.minute / 60.0 + horizon * 0.25) // 24)) % 7
        vals.extend(
            [
                np.sin(2 * np.pi * fh / 24),
                np.cos(2 * np.pi * fh / 24),
                np.sin(2 * np.pi * fdow / 7),
                np.cos(2 * np.pi * fdow / 7),
                float(df["temp_c"].iloc[o]),
            ]
        )
        rows.append(vals)
    return np.asarray(rows, dtype=float)


def chronological_origins(n: int, lookback: int, horizon: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    origins = np.arange(lookback, n - horizon)
    n_all = len(origins)
    a = int(0.67 * n_all)
    b = int(0.82 * n_all)
    return origins[:a], origins[a:b], origins[b:]


def fit_multi_horizon_quantiles(
    df: pd.DataFrame, cfg: Config
) -> Tuple[Dict[float, np.ndarray], np.ndarray, np.ndarray, np.ndarray]:
    """Fit one quantile model per horizon and quantile.

    The paper does not disclose a complete neural architecture, so the clean-room
    reproduction uses fast histogram gradient boosting as the black-box quantile model.
    The downstream stepwise CQR is model-agnostic and is reproduced exactly at method level.
    """
    train_o, cal_o, test_o = chronological_origins(len(df), cfg.lookback, cfg.horizon)
    if len(train_o) > cfg.max_train:
        train_o = train_o[-cfg.max_train :]

    pred = {q: np.zeros((len(cal_o) + len(test_o), cfg.horizon), dtype=float) for q in QUANTILES}
    eval_o = np.concatenate([cal_o, test_o])
    y = df["net_mw"].to_numpy()

    for h in range(1, cfg.horizon + 1):
        x_train = _origin_features(df, train_o, h)
        x_eval = _origin_features(df, eval_o, h)
        y_train = y[train_o + h]
        for q in QUANTILES:
            model = HistGradientBoostingRegressor(
                loss="quantile",
                quantile=q,
                max_iter=cfg.model_iter,
                learning_rate=0.08,
                max_leaf_nodes=21,
                min_samples_leaf=20,
                l2_regularization=0.1,
                random_state=cfg.seed,
            )
            model.fit(x_train, y_train)
            pred[q][:, h - 1] = model.predict(x_eval)

    y_eval = np.stack([y[eval_o + h] for h in range(1, cfg.horizon + 1)], axis=1)
    return pred, y_eval, cal_o, test_o


def conformal_quantile(scores: np.ndarray, coverage: float) -> float:
    """Finite-sample split-conformal quantile using the standard 'higher' convention."""
    scores = np.asarray(scores, dtype=float)
    scores = scores[np.isfinite(scores)]
    if scores.size == 0:
        return 0.0
    level = min(1.0, np.ceil((scores.size + 1) * coverage) / scores.size)
    return float(np.quantile(scores, level, method="higher"))


def stepwise_cqr(
    y_cal: np.ndarray,
    low_cal: np.ndarray,
    high_cal: np.ndarray,
    low_test: np.ndarray,
    high_test: np.ndarray,
    coverage: float = 0.90,
):
    """Paper Eq. (10)-(12): one nonconformity distribution and correction per horizon."""
    h = y_cal.shape[1]
    qhat = np.zeros(h)
    for j in range(h):
        s = np.maximum.reduce(
            [low_cal[:, j] - y_cal[:, j], y_cal[:, j] - high_cal[:, j], np.zeros(len(y_cal))]
        )
        qhat[j] = conformal_quantile(s, coverage)
    return low_test - qhat, high_test + qhat, qhat


def interval_metrics(y: np.ndarray, low: np.ndarray, high: np.ndarray, data_range: float) -> dict:
    covered = (y >= low) & (y <= high)
    return {
        "picp": float(covered.mean()),
        "pinaw": float(np.mean(high - low) / max(data_range, 1e-9)),
        "horizon_picp": covered.mean(axis=0).tolist(),
        "horizon_width": np.mean(high - low, axis=0).tolist(),
    }


def classify_daily_pv_volatility(
    df: pd.DataFrame, train_end: pd.Timestamp
) -> Tuple[pd.Series, Tuple[float, float]]:
    ramp = df["pv_mw"].diff().abs().fillna(0)
    daily = ramp.groupby(df.index.floor("D")).mean()
    train_daily = daily[daily.index <= train_end.floor("D")]
    q1, q2 = np.quantile(train_daily, [1 / 3, 2 / 3])
    cls = pd.cut(daily, bins=[-np.inf, q1, q2, np.inf], labels=["low", "mid", "high"])
    return cls, (float(q1), float(q2))


@dataclass
class BESS:
    capacity_mwh: float = 123.0
    pmax_mw: float = 30.5
    eta_c: float = 0.95
    eta_d: float = 0.95
    e_min: float = 12.3
    e_max: float = 123.0
    dt_h: float = 0.25


def optimize_schedule(
    net_forecast: np.ndarray,
    price: np.ndarray,
    e0: float,
    bess: BESS,
    peak_weight: float = 2.0,
    cycle_cost: float = 1e-3,
):
    """Transparent LP used to operationalize the paper's information comparison.

    The paper does not publish the exact dispatch objective. Variables are
    charge[h], discharge[h], import[h], peak; export has zero value.
    """
    net_forecast = np.asarray(net_forecast, dtype=float)
    price = np.asarray(price, dtype=float)
    H = len(net_forecast)
    nvar = 3 * H + 1
    ch = np.arange(H)
    dis = H + np.arange(H)
    imp = 2 * H + np.arange(H)
    peak = 3 * H

    c = np.zeros(nvar)
    c[ch] = cycle_cost
    c[dis] = cycle_cost
    c[imp] = price * bess.dt_h
    c[peak] = peak_weight

    A_ub, b_ub = [], []
    for t in range(H):
        row = np.zeros(nvar)
        row[ch[t]] = 1
        row[dis[t]] = -1
        row[imp[t]] = -1
        A_ub.append(row)
        b_ub.append(-net_forecast[t])

        row2 = np.zeros(nvar)
        row2[imp[t]] = 1
        row2[peak] = -1
        A_ub.append(row2)
        b_ub.append(0.0)

    for t in range(H):
        coeff = np.zeros(nvar)
        coeff[ch[: t + 1]] = bess.eta_c * bess.dt_h
        coeff[dis[: t + 1]] = -bess.dt_h / bess.eta_d
        A_ub.append(coeff.copy())
        b_ub.append(bess.e_max - e0)
        A_ub.append(-coeff.copy())
        b_ub.append(e0 - bess.e_min)

    bounds = [(0, bess.pmax_mw)] * (2 * H) + [(0, None)] * H + [(0, None)]
    res = linprog(
        c,
        A_ub=np.asarray(A_ub),
        b_ub=np.asarray(b_ub),
        bounds=bounds,
        method="highs",
    )
    if not res.success:
        return None
    x = res.x
    return x[ch], x[dis]


def rolling_dispatch(
    actual: np.ndarray,
    median: np.ndarray,
    upper: np.ndarray,
    prices: np.ndarray,
    horizon: int,
    max_steps: int,
    bess: BESS,
) -> dict:
    strategies = {"ideal": [], "point": [], "interval": []}
    n = min(len(actual), max_steps)
    for name in strategies:
        e = 0.55 * bess.capacity_mwh
        cost = 0.0
        peak = 0.0
        infeasible = 0
        soc_viol = 0
        for i in range(n):
            f = actual[i] if name == "ideal" else median[i] if name == "point" else upper[i]
            sched = optimize_schedule(f[:horizon], prices[i, :horizon], e, bess)
            if sched is None:
                infeasible += 1
                ch0 = dis0 = 0.0
            else:
                ch0, dis0 = float(sched[0][0]), float(sched[1][0])
            grid = max(actual[i, 0] + ch0 - dis0, 0.0)
            cost += prices[i, 0] * grid * bess.dt_h
            peak = max(peak, grid)
            e = e + bess.eta_c * ch0 * bess.dt_h - dis0 * bess.dt_h / bess.eta_d
            if e < bess.e_min - 1e-7 or e > bess.e_max + 1e-7:
                soc_viol += 1
            e = float(np.clip(e, bess.e_min, bess.e_max))
        strategies[name] = {
            "cost_proxy": cost,
            "peak_import_mw": peak,
            "soc_violations": soc_viol,
            "infeasible": infeasible,
        }
    return strategies


def run(cfg: Config, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = make_synthetic_microgrid(cfg.days, cfg.seed)
    pred, y_eval, cal_o, test_o = fit_multi_horizon_quantiles(df, cfg)
    ncal = len(cal_o)
    y_cal, y_test = y_eval[:ncal], y_eval[ncal:]
    low_cal, low_test = pred[0.05][:ncal], pred[0.05][ncal:]
    med_test = pred[0.50][ncal:]
    high_cal, high_test = pred[0.95][:ncal], pred[0.95][ncal:]
    c_low, c_high, qhat = stepwise_cqr(
        y_cal, low_cal, high_cal, low_test, high_test, cfg.coverage
    )

    rng = float(df["net_mw"].max() - df["net_mw"].min())
    metrics = {
        "raw": interval_metrics(y_test, low_test, high_test, rng),
        "stepwise_cqr": interval_metrics(y_test, c_low, c_high, rng),
        "qhat_by_horizon": qhat.tolist(),
    }

    train_end = df.index[cal_o[0] - 1]
    _, thresholds = classify_daily_pv_volatility(df, train_end)
    metrics["pv_ramp_daily_tercile_thresholds"] = list(thresholds)

    price_arr = df["price"].to_numpy()
    price_test = np.stack(
        [price_arr[test_o + h] for h in range(1, cfg.horizon + 1)], axis=1
    )
    metrics["dispatch"] = rolling_dispatch(
        y_test,
        med_test,
        c_high,
        price_test,
        cfg.horizon,
        min(cfg.dispatch_steps, len(y_test)),
        BESS(),
    )

    pd.DataFrame(
        {
            "horizon_step": np.arange(1, cfg.horizon + 1),
            "qhat": qhat,
            "raw_picp": np.mean(
                (y_test >= low_test) & (y_test <= high_test), axis=0
            ),
            "calibrated_picp": np.mean(
                (y_test >= c_low) & (y_test <= c_high), axis=0
            ),
            "raw_width": np.mean(high_test - low_test, axis=0),
            "calibrated_width": np.mean(c_high - c_low, axis=0),
        }
    ).to_csv(out_dir / "horizon_metrics.csv", index=False)
    (out_dir / "summary.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    return metrics


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="results/demo")
    p.add_argument("--smoke", action="store_true")
    args = p.parse_args()
    cfg = Config()
    if args.smoke:
        cfg.days = 55
        cfg.horizon = 8
        cfg.max_train = 1800
        cfg.model_iter = 20
        cfg.dispatch_steps = 80
    metrics = run(cfg, Path(args.out))
    print(json.dumps({"config": asdict(cfg), **metrics}, indent=2))


if __name__ == "__main__":
    main()
