from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.stats import norm
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


TAUS = np.array([0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95], dtype=float)


@dataclass
class Config:
    seed: int = 7
    days: int = 365
    lookback: int = 24
    horizon: int = 24
    epochs: int = 5
    batch_size: int = 128
    d_model: int = 32
    nhead: int = 4
    coverage: float = 0.90
    scenarios: int = 100
    cvar_beta: float = 0.90
    risk_lambda: float = 0.7
    eval_days: int = 18


def make_station_data(days: int, seed: int) -> pd.DataFrame:
    """Runnable surrogate for the preprint's Caltech/NASA/CAISO case study."""
    rng = np.random.default_rng(seed)
    n = days * 24
    idx = pd.date_range("2019-01-01", periods=n, freq="1h")
    h = idx.hour.to_numpy()
    dow = idx.dayofweek.to_numpy()
    d = np.arange(n) / 24

    temp = (
        20
        + 8 * np.sin(2 * np.pi * (d / 365 - 0.22))
        + 5 * np.sin(2 * np.pi * (h - 14) / 24)
        + rng.normal(0, 1.1, n)
    )
    cloud = np.zeros(n)
    noise = rng.normal(0, 0.22, n)
    for i in range(1, n):
        cloud[i] = 0.86 * cloud[i - 1] + noise[i]
    cloudiness = np.clip(0.45 + 0.25 * cloud, 0.02, 0.95)

    sun = np.clip(np.sin(np.pi * (h - 6) / 12), 0, None)
    pv = (
        100
        * sun**1.8
        * (1 - 0.65 * cloudiness)
        * (1 - 0.0025 * np.maximum(temp - 25, 0))
    )
    pv += rng.normal(0, 1.2 + 0.03 * pv, n)
    pv = np.clip(pv, 0, 100)

    daytime = 34 * np.exp(-0.5 * ((h - 13) / 3.6) ** 2)
    evening = 18 * np.exp(-0.5 * ((h - 19) / 2.3) ** 2)
    workday = np.where(dow < 5, 1.0, 0.48)
    ev = 8 + workday * (daytime + evening) + rng.normal(0, 4.0, n)
    bursts = rng.random(n) < 0.025
    ev[bursts] += rng.uniform(12, 35, bursts.sum())
    ev = np.clip(ev, 0, 115)

    price = 38 + 12 * np.sin(2 * np.pi * (h - 15) / 24)
    price += 28 * ((h >= 17) & (h <= 21)) + 0.25 * ev + rng.normal(0, 3, n)
    price = np.clip(price, 10, None) / 1000.0

    return pd.DataFrame(
        {
            "ev_kw": ev,
            "pv_kw": pv,
            "temp_c": temp,
            "cloud": cloudiness,
            "price_per_kwh": price,
        },
        index=idx,
    )


def feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["ev"] = df.ev_kw
    out["pv"] = df.pv_kw
    out["temp"] = df.temp_c
    out["cloud"] = df.cloud
    out["sin_hour"] = np.sin(2 * np.pi * df.index.hour / 24)
    out["cos_hour"] = np.cos(2 * np.pi * df.index.hour / 24)
    out["sin_dow"] = np.sin(2 * np.pi * df.index.dayofweek / 7)
    out["cos_dow"] = np.cos(2 * np.pi * df.index.dayofweek / 7)
    out["ev_lag24"] = df.ev_kw.shift(24)
    out["pv_lag24"] = df.pv_kw.shift(24)
    return out


def make_windows(df: pd.DataFrame, lookback: int, horizon: int):
    f = feature_frame(df).to_numpy(dtype=np.float32)
    y = df[["ev_kw", "pv_kw"]].to_numpy(dtype=np.float32)
    origins = np.arange(max(24, lookback), len(df) - horizon)
    X, Y, O = [], [], []
    for o in origins:
        x = f[o - lookback + 1 : o + 1]
        if not np.isfinite(x).all():
            continue
        X.append(x)
        Y.append(y[o + 1 : o + horizon + 1])
        O.append(o)
    return np.asarray(X), np.asarray(Y), np.asarray(O)


def split_indices(n: int):
    a = int(0.60 * n)
    b = int(0.70 * n)
    c = int(0.85 * n)
    return np.arange(0, a), np.arange(a, b), np.arange(b, c), np.arange(c, n)


class QuantileTransformer(nn.Module):
    """Small encoder-decoder Transformer with cumulative-softplus noncrossing head."""

    def __init__(
        self,
        in_dim: int,
        horizon: int,
        targets: int,
        quantiles: int,
        d_model: int = 32,
        nhead: int = 4,
    ):
        super().__init__()
        self.horizon, self.targets, self.quantiles = horizon, targets, quantiles
        self.in_proj = nn.Linear(in_dim, d_model)
        self.pos = nn.Parameter(torch.zeros(1, 24, d_model))
        enc = nn.TransformerEncoderLayer(
            d_model,
            nhead,
            dim_feedforward=4 * d_model,
            dropout=0.05,
            batch_first=True,
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(enc, num_layers=1)
        dec = nn.TransformerDecoderLayer(
            d_model,
            nhead,
            dim_feedforward=4 * d_model,
            dropout=0.05,
            batch_first=True,
            norm_first=True,
        )
        self.decoder = nn.TransformerDecoder(dec, num_layers=1)
        self.horizon_query = nn.Parameter(torch.randn(1, horizon, d_model) * 0.02)
        self.out = nn.Linear(d_model, targets * quantiles)

    def forward(self, x):
        mem = self.encoder(self.in_proj(x) + self.pos[:, : x.shape[1]])
        q = self.horizon_query.expand(x.shape[0], -1, -1)
        z = self.decoder(q, mem)
        raw = self.out(z).view(
            x.shape[0], self.horizon, self.targets, self.quantiles
        )
        first = raw[..., :1]
        increments = torch.nn.functional.softplus(raw[..., 1:])
        return torch.cat(
            [first, first + torch.cumsum(increments, dim=-1)], dim=-1
        )


def pinball_loss(pred, y, taus):
    err = y.unsqueeze(-1) - pred
    t = taus.view(1, 1, 1, -1)
    return torch.maximum(t * err, (t - 1) * err).mean()


def train_model(X, Y, train_idx, val_idx, cfg: Config):
    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)

    xmu = X[train_idx].reshape(-1, X.shape[-1]).mean(0)
    xsd = X[train_idx].reshape(-1, X.shape[-1]).std(0) + 1e-6
    ymu = Y[train_idx].reshape(-1, Y.shape[-1]).mean(0)
    ysd = Y[train_idx].reshape(-1, Y.shape[-1]).std(0) + 1e-6
    Xs = (X - xmu) / xsd
    Ys = (Y - ymu) / ysd

    model = QuantileTransformer(
        X.shape[-1],
        cfg.horizon,
        Y.shape[-1],
        len(TAUS),
        cfg.d_model,
        cfg.nhead,
    )
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        opt, factor=0.5, patience=1
    )
    taus_t = torch.tensor(TAUS, dtype=torch.float32)

    ds = TensorDataset(
        torch.tensor(Xs[train_idx]), torch.tensor(Ys[train_idx])
    )
    loader = DataLoader(ds, batch_size=cfg.batch_size, shuffle=True)
    xv = torch.tensor(Xs[val_idx])
    yv = torch.tensor(Ys[val_idx])

    best, best_state = math.inf, None
    for _ in range(cfg.epochs):
        model.train()
        for xb, yb in loader:
            opt.zero_grad(set_to_none=True)
            pred = model(xb)
            loss = pinball_loss(pred, yb, taus_t)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()

        model.eval()
        with torch.no_grad():
            val_loss = float(pinball_loss(model(xv), yv, taus_t))
        scheduler.step(val_loss)
        if val_loss < best:
            best = val_loss
            best_state = {
                k: v.detach().clone() for k, v in model.state_dict().items()
            }

    if best_state is not None:
        model.load_state_dict(best_state)
    return model, (xmu, xsd, ymu, ysd)


def predict(model, X, scaler, idx):
    xmu, xsd, ymu, ysd = scaler
    x = torch.tensor((X[idx] - xmu) / xsd)
    model.eval()
    chunks = []
    with torch.no_grad():
        for i in range(0, len(x), 512):
            chunks.append(model(x[i : i + 512]).cpu().numpy())
    q = np.concatenate(chunks, axis=0)
    return q * ysd[None, None, :, None] + ymu[None, None, :, None]


def conformal_quantile(scores: np.ndarray, coverage: float) -> float:
    s = np.asarray(scores, float)
    level = min(1.0, np.ceil((len(s) + 1) * coverage) / len(s))
    return float(np.quantile(s, level, method="higher"))


def fit_interval_scale(y, q, coverage=0.90):
    """Clean-room interpretation of the preprint's undocumented interval-scaling stage."""
    low, med, high = q[..., 0], q[..., 3], q[..., -1]
    H, M = y.shape[1:]
    scales = np.ones((H, M))
    for h in range(H):
        for m in range(M):
            yy, lo, md, hi = (
                y[:, h, m],
                low[:, h, m],
                med[:, h, m],
                high[:, h, m],
            )
            den_lo = np.maximum(md - lo, 1e-4)
            den_hi = np.maximum(hi - md, 1e-4)
            need = np.where(
                yy < md,
                (md - yy) / den_lo,
                np.where(yy > md, (yy - md) / den_hi, 0.0),
            )
            scales[h, m] = max(
                1.0, float(np.quantile(need, coverage, method="higher"))
            )
    return scales


def apply_scale(q, scales):
    med = q[..., 3:4]
    return med + scales[None, :, :, None] * (q - med)


def fit_cqr_delta(y, q_scaled, coverage=0.90):
    low, high = q_scaled[..., 0], q_scaled[..., -1]
    H, M = y.shape[1:]
    delta = np.zeros((H, M))
    for h in range(H):
        for m in range(M):
            s = np.maximum.reduce(
                [
                    low[:, h, m] - y[:, h, m],
                    y[:, h, m] - high[:, h, m],
                    np.zeros(len(y)),
                ]
            )
            delta[h, m] = conformal_quantile(s, coverage)
    return delta


def apply_cqr_to_grid(q_scaled, delta):
    # CQR formally calibrates an interval.  For scenario sampling we taper the
    # q05/q95 correction linearly to zero at q50 and preserve monotonicity.
    w = np.abs(TAUS - 0.5) / 0.45
    sign = np.sign(TAUS - 0.5)
    out = q_scaled + delta[None, :, :, None] * (
        sign * w
    )[None, None, None, :]
    return np.maximum.accumulate(out, axis=-1)


def net_interval(q_grid):
    low = q_grid[..., 0, 0] - q_grid[..., 1, -1]
    high = q_grid[..., 0, -1] - q_grid[..., 1, 0]
    med = q_grid[..., 0, 3] - q_grid[..., 1, 3]
    return low, med, high


def fit_net_cqr(y_net, low, high, coverage=0.90):
    H = y_net.shape[1]
    d = np.zeros(H)
    for h in range(H):
        s = np.maximum.reduce(
            [
                low[:, h] - y_net[:, h],
                y_net[:, h] - high[:, h],
                np.zeros(len(y_net)),
            ]
        )
        d[h] = conformal_quantile(s, coverage)
    return d


def coverage(y, lo, hi):
    return float(np.mean((y >= lo) & (y <= hi)))


def estimate_dependence(y_cal, q_cal):
    med = q_cal[..., 3]
    r = y_cal - med
    phi = []
    for m in range(2):
        a, b = r[:, :-1, m].ravel(), r[:, 1:, m].ravel()
        phi.append(
            float(np.clip(np.corrcoef(a, b)[0, 1], -0.95, 0.95))
        )
    rho = float(
        np.clip(
            np.corrcoef(r[..., 0].ravel(), r[..., 1].ravel())[0, 1],
            -0.95,
            0.95,
        )
    )
    return np.asarray(phi), rho


def generate_scenarios(q_grid_one, phi, rho, S, seed):
    """AR(1) temporal latent Gaussian + Gaussian copula across EV/PV."""
    rng = np.random.default_rng(seed)
    H = q_grid_one.shape[0]
    cov = np.array([[1.0, rho], [rho, 1.0]])
    eps = rng.multivariate_normal([0, 0], cov, size=(S, H))
    z = np.zeros_like(eps)
    z[:, 0] = eps[:, 0]

    for h in range(1, H):
        for m in range(2):
            z[:, h, m] = (
                phi[m] * z[:, h - 1, m]
                + np.sqrt(max(1 - phi[m] ** 2, 1e-6))
                * eps[:, h, m]
            )

    u = np.clip(norm.cdf(z), TAUS[0], TAUS[-1])
    vals = np.zeros_like(z)
    for s in range(S):
        for h in range(H):
            for m in range(2):
                vals[s, h, m] = np.interp(
                    u[s, h, m], TAUS, q_grid_one[h, m]
                )
    return vals[..., 0] - vals[..., 1]


def upper_cvar(x: np.ndarray, beta: float, axis=0):
    if axis != 0:
        raise NotImplementedError
    var = np.quantile(x, beta, axis=axis)
    out = np.zeros(x.shape[1])
    for h in range(x.shape[1]):
        tail = x[:, h][x[:, h] >= var[h]]
        out[h] = tail.mean() if len(tail) else var[h]
    return out


@dataclass
class BESS:
    capacity: float = 100.0
    pmax: float = 50.0
    eta_c: float = 0.95
    eta_d: float = 0.95
    e_min: float = 10.0
    e_max: float = 100.0


def optimize_bess(
    net,
    price,
    e0=50.0,
    bess=BESS(),
    peak_weight=0.08,
    cycle_cost=1e-4,
):
    net, price = np.asarray(net), np.asarray(price)
    H = len(net)
    ch = np.arange(H)
    dis = H + np.arange(H)
    imp = 2 * H + np.arange(H)
    peak = 3 * H
    nvar = peak + 1

    c = np.zeros(nvar)
    c[ch] = cycle_cost
    c[dis] = cycle_cost
    c[imp] = price
    c[peak] = peak_weight

    A, b = [], []
    for t in range(H):
        row = np.zeros(nvar)
        row[ch[t]] = 1
        row[dis[t]] = -1
        row[imp[t]] = -1
        A.append(row)
        b.append(-net[t])

        row = np.zeros(nvar)
        row[imp[t]] = 1
        row[peak] = -1
        A.append(row)
        b.append(0)

    for t in range(H):
        row = np.zeros(nvar)
        row[ch[: t + 1]] = bess.eta_c
        row[dis[: t + 1]] = -1 / bess.eta_d
        A.append(row.copy())
        b.append(bess.e_max - e0)
        A.append(-row.copy())
        b.append(e0 - bess.e_min)

    bounds = (
        [(0, bess.pmax)] * (2 * H)
        + [(0, None)] * H
        + [(0, None)]
    )
    res = linprog(
        c,
        A_ub=np.asarray(A),
        b_ub=np.asarray(b),
        bounds=bounds,
        method="highs",
    )
    if not res.success:
        raise RuntimeError(res.message)
    return res.x[ch], res.x[dis]


def optimize_stochastic(
    scenarios,
    price,
    e0=50.0,
    bess=BESS(),
    peak_weight=0.08,
    cycle_cost=1e-4,
):
    """Scenario-embedded stochastic proxy with one common battery schedule."""
    S, H = scenarios.shape
    n_common = 2 * H
    imp0 = n_common
    peak0 = imp0 + S * H
    nvar = peak0 + S

    c = np.zeros(nvar)
    c[:H] = cycle_cost
    c[H : 2 * H] = cycle_cost
    for s in range(S):
        c[imp0 + s * H : imp0 + (s + 1) * H] = price / S
        c[peak0 + s] = peak_weight / S

    A, b = [], []
    for s in range(S):
        for t in range(H):
            row = np.zeros(nvar)
            row[t] = 1
            row[H + t] = -1
            row[imp0 + s * H + t] = -1
            A.append(row)
            b.append(-scenarios[s, t])

            row = np.zeros(nvar)
            row[imp0 + s * H + t] = 1
            row[peak0 + s] = -1
            A.append(row)
            b.append(0)

    for t in range(H):
        row = np.zeros(nvar)
        row[: t + 1] = bess.eta_c
        row[H : H + t + 1] = -1 / bess.eta_d
        A.append(row.copy())
        b.append(bess.e_max - e0)
        A.append(-row.copy())
        b.append(e0 - bess.e_min)

    bounds = (
        [(0, bess.pmax)] * (2 * H)
        + [(0, None)] * (S * H + S)
    )
    res = linprog(
        c,
        A_ub=np.asarray(A),
        b_ub=np.asarray(b),
        bounds=bounds,
        method="highs",
    )
    if not res.success:
        raise RuntimeError(res.message)
    return res.x[:H], res.x[H : 2 * H]


def evaluate_schedule(actual_net, planned_net, price, ch, dis):
    actual_grid = np.maximum(actual_net + ch - dis, 0)
    planned_grid = np.maximum(planned_net + ch - dis, 0)
    base_grid = np.maximum(actual_net, 0)

    base_cost = float(np.sum(price * base_grid))
    cost = float(np.sum(price * actual_grid))
    peak_base = float(base_grid.max())
    peak = float(actual_grid.max())

    return {
        "cost_saving_rate": (base_cost - cost) / max(base_cost, 1e-9),
        "peak_shaving_rate": (peak_base - peak) / max(peak_base, 1e-9),
        "imbalance_mae_kw": float(
            np.mean(np.abs(actual_grid - planned_grid))
        ),
    }


def run(cfg: Config, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    df = make_station_data(cfg.days, cfg.seed)
    X, Y, origins = make_windows(df, cfg.lookback, cfg.horizon)
    tr, va, ca, te = split_indices(len(X))

    model, scaler = train_model(X, Y, tr, va, cfg)
    q_cal_raw = predict(model, X, scaler, ca)
    q_test_raw = predict(model, X, scaler, te)
    y_cal, y_test = Y[ca], Y[te]

    scales = fit_interval_scale(y_cal, q_cal_raw, cfg.coverage)
    q_cal_scaled = apply_scale(q_cal_raw, scales)
    q_test_scaled = apply_scale(q_test_raw, scales)

    delta = fit_cqr_delta(y_cal, q_cal_scaled, cfg.coverage)
    q_cal = apply_cqr_to_grid(q_cal_scaled, delta)
    q_test = apply_cqr_to_grid(q_test_scaled, delta)

    raw_cov = [
        coverage(
            y_test[..., m],
            q_test_raw[..., m, 0],
            q_test_raw[..., m, -1],
        )
        for m in range(2)
    ]
    scaled_cov = [
        coverage(
            y_test[..., m],
            q_test_scaled[..., m, 0],
            q_test_scaled[..., m, -1],
        )
        for m in range(2)
    ]
    cqr_cov = [
        coverage(
            y_test[..., m],
            q_test[..., m, 0],
            q_test[..., m, -1],
        )
        for m in range(2)
    ]

    ynet_cal = y_cal[..., 0] - y_cal[..., 1]
    ynet_test = y_test[..., 0] - y_test[..., 1]
    nl_cal, nm_cal, nh_cal = net_interval(q_cal)
    nl_test, nm_test, nh_test = net_interval(q_test)

    net_delta = fit_net_cqr(
        ynet_cal, nl_cal, nh_cal, cfg.coverage
    )
    net_cov_before = coverage(ynet_test, nl_test, nh_test)
    net_cov_after = coverage(
        ynet_test, nl_test - net_delta, nh_test + net_delta
    )

    phi, rho = estimate_dependence(y_cal, q_cal)

    pick = np.arange(0, len(te), cfg.horizon)[: cfg.eval_days]
    results = {
        k: []
        for k in [
            "deterministic",
            "scenario_mean",
            "risk_aware",
            "stochastic_proxy",
        ]
    }

    price = df.price_per_kwh.to_numpy()
    for j, local_i in enumerate(pick):
        test_sample_idx = te[local_i]
        o = origins[test_sample_idx]
        prices = price[o + 1 : o + 1 + cfg.horizon]
        actual = ynet_test[local_i]
        median = nm_test[local_i]

        scen = generate_scenarios(
            q_test[local_i],
            phi,
            rho,
            cfg.scenarios,
            cfg.seed + j,
        )
        mean = scen.mean(0)
        cvar = upper_cvar(scen, cfg.cvar_beta)
        risk = mean + cfg.risk_lambda * np.maximum(cvar - mean, 0)

        ch, dis = optimize_bess(median, prices)
        results["deterministic"].append(
            evaluate_schedule(actual, median, prices, ch, dis)
        )

        ch, dis = optimize_bess(mean, prices)
        results["scenario_mean"].append(
            evaluate_schedule(actual, mean, prices, ch, dis)
        )

        ch, dis = optimize_bess(risk, prices)
        results["risk_aware"].append(
            evaluate_schedule(actual, risk, prices, ch, dis)
        )

        ch, dis = optimize_stochastic(scen, prices)
        results["stochastic_proxy"].append(
            evaluate_schedule(actual, mean, prices, ch, dis)
        )

    agg = {}
    for k, vals in results.items():
        agg[k] = (
            {
                m: float(np.mean([v[m] for v in vals]))
                for m in vals[0]
            }
            if vals
            else {}
        )

    summary = {
        "coverage": {
            "raw_ev": raw_cov[0],
            "raw_pv": raw_cov[1],
            "scaled_ev": scaled_cov[0],
            "scaled_pv": scaled_cov[1],
            "cqr_ev": cqr_cov[0],
            "cqr_pv": cqr_cov[1],
            "net_before_separate_cqr": net_cov_before,
            "net_after_separate_cqr": net_cov_after,
        },
        "dependence": {
            "phi_ev": float(phi[0]),
            "phi_pv": float(phi[1]),
            "rho_ev_pv": rho,
        },
        "dispatch": agg,
    }

    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    pd.DataFrame(agg).T.to_csv(out_dir / "dispatch_metrics.csv")
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="results/demo")
    p.add_argument("--smoke", action="store_true")
    args = p.parse_args()

    cfg = Config()
    if args.smoke:
        cfg.days = 90
        cfg.epochs = 1
        cfg.batch_size = 256
        cfg.d_model = 16
        cfg.nhead = 4
        cfg.scenarios = 30
        cfg.eval_days = 2

    result = run(cfg, Path(args.out))
    print(json.dumps({"config": asdict(cfg), **result}, indent=2))


if __name__ == "__main__":
    main()
