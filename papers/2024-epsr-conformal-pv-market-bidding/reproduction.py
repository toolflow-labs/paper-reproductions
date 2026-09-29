from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestRegressor
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler


@dataclass
class Config:
    seed: int = 22
    days: int = 4 * 365
    k_neighbors: int = 50
    mondrian_bins: int = 15
    price_clusters: int = 20
    pv_scenarios: int = 99
    eum_grid: int = 41
    cvar_gamma: float = 0.60
    cvar_beta: float = 0.10
    max_eval: int = 180


def make_demo_market(days: int = 4 * 365, seed: int = 22) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = days * 24
    idx = pd.date_range("2014-01-01", periods=n, freq="1h")
    h = idx.hour.to_numpy()
    doy = idx.dayofyear.to_numpy()

    clear_sky = np.clip(np.sin(np.pi * (h - 5.5) / 13), 0, None)
    seasonal = np.clip(0.75 + 0.25 * np.sin(2 * np.pi * (doy - 80) / 365), 0.45, 1.0)
    cloud_state = np.zeros(n)
    noise = rng.normal(0, 0.20, n)
    for i in range(1, n):
        cloud_state[i] = 0.91 * cloud_state[i - 1] + noise[i]
    cloud = np.clip(0.48 + 0.28 * cloud_state, 0.02, 0.98)

    pv = clear_sky * seasonal * (1 - 0.78 * cloud)
    pv += rng.normal(0, 0.025 + 0.06 * clear_sky, n)
    pv = np.clip(pv, 0, 1)

    cloud_fc = np.clip(cloud + rng.normal(0, 0.09, n), 0, 1)
    ssrd_fc = np.clip(
        clear_sky * seasonal * (1 - 0.68 * cloud_fc) + rng.normal(0, 0.04, n),
        0,
        1.2,
    )
    temp = 10 + 9 * np.sin(2 * np.pi * (doy - 170) / 365) + 4 * np.sin(
        2 * np.pi * (h - 14) / 24
    )
    temp_fc = temp + rng.normal(0, 1.2, n)
    wind = np.clip(
        5 + 1.5 * np.sin(2 * np.pi * doy / 11) + rng.normal(0, 1.0, n),
        0,
        None,
    )

    da = 55 + 12 * np.sin(2 * np.pi * (h - 15) / 24) + 10 * (1 - pv) + rng.normal(0, 5, n)
    da = np.clip(da, 5, None)
    delta_up = np.clip(18 + 18 * cloud + rng.gamma(2.0, 3.5, n), 2, 90)
    delta_down = np.clip(12 + 8 * (1 - cloud) + rng.gamma(2.0, 2.5, n), 2, 70)
    p_up = da + delta_up
    p_down = np.maximum(0, da - delta_down)

    return pd.DataFrame(
        {
            "pv": pv,
            "clear_sky": clear_sky * seasonal,
            "cloud_fc": cloud_fc,
            "ssrd_fc": ssrd_fc,
            "temp_fc": temp_fc,
            "wind_fc": wind,
            "da_price": da,
            "up_price": p_up,
            "down_price": p_down,
        },
        index=idx,
    )


def features(df: pd.DataFrame) -> np.ndarray:
    h = df.index.hour.to_numpy()
    doy = df.index.dayofyear.to_numpy()
    return np.column_stack(
        [
            np.sin(2 * np.pi * h / 24),
            np.cos(2 * np.pi * h / 24),
            np.sin(2 * np.pi * doy / 365),
            np.cos(2 * np.pi * doy / 365),
            df["clear_sky"].to_numpy(),
            df["cloud_fc"].to_numpy(),
            df["ssrd_fc"].to_numpy(),
            df["temp_fc"].to_numpy(),
            df["wind_fc"].to_numpy(),
        ]
    )


def split_daylight(df: pd.DataFrame):
    daylight = np.flatnonzero(df["clear_sky"].to_numpy() > 0.01)
    n = len(daylight)
    a, b = int(0.50 * n), int(0.75 * n)
    return daylight[:a], daylight[a:b], daylight[b:]


def finite_conformal_quantile(x: np.ndarray, level: float) -> float:
    x = np.asarray(x, float)
    level = min(1.0, np.ceil((len(x) + 1) * level) / len(x))
    return float(np.quantile(x, level, method="higher"))


class CPBundle:
    """Paper M1-M5 uncertainty interfaces around one point model."""

    def __init__(self, x_cal, y_cal, p_cal, k=50, bins=15):
        self.x_cal = np.asarray(x_cal, float)
        self.y_cal = np.asarray(y_cal, float)
        self.p_cal = np.asarray(p_cal, float)
        self.resid = self.y_cal - self.p_cal
        self.abs_resid = np.abs(self.resid)
        self.k = min(k, max(2, len(self.y_cal) - 1))
        self.bins = min(bins, max(2, len(self.y_cal) // 30))

        self.scaler = StandardScaler().fit(self.x_cal)
        z = self.scaler.transform(self.x_cal)
        self.nn_cal = NearestNeighbors(n_neighbors=self.k + 1).fit(z)
        _, ind = self.nn_cal.kneighbors(z)
        neigh = ind[:, 1:]
        self.scale_cal = np.maximum(self.abs_resid[neigh].mean(axis=1), 1e-4)
        self.norm_abs = self.abs_resid / self.scale_cal
        self.norm_signed = self.resid / self.scale_cal

        edges = np.quantile(self.p_cal, np.linspace(0, 1, self.bins + 1))
        edges[0], edges[-1] = -np.inf, np.inf
        for j in range(1, len(edges)):
            if edges[j] <= edges[j - 1]:
                edges[j] = edges[j - 1] + 1e-9
        self.edges = edges
        self.bin_cal = np.clip(
            np.digitize(self.p_cal, edges[1:-1]), 0, self.bins - 1
        )
        self.nn_test = NearestNeighbors(n_neighbors=self.k).fit(z)

    def _test_scale(self, x):
        z = self.scaler.transform(np.asarray(x, float))
        _, ind = self.nn_test.kneighbors(z)
        return np.maximum(self.abs_resid[ind].mean(axis=1), 1e-4)

    def _bins_for_pred(self, p):
        return np.clip(
            np.digitize(p, self.edges[1:-1]), 0, self.bins - 1
        )

    def quantile(self, method: str, x: np.ndarray, point: np.ndarray, tau: float) -> np.ndarray:
        point = np.asarray(point, float)
        if abs(tau - 0.5) < 1e-12:
            return np.clip(point, 0, 1)
        scale = self._test_scale(x)
        bins = self._bins_for_pred(point)
        out = np.zeros(len(point))

        for i in range(len(point)):
            if method == "M1":
                level = abs(2 * tau - 1)
                q = finite_conformal_quantile(self.abs_resid, level)
                out[i] = point[i] + (q if tau > 0.5 else -q)
            elif method == "M2":
                level = abs(2 * tau - 1)
                q = finite_conformal_quantile(self.norm_abs, level)
                out[i] = point[i] + (q if tau > 0.5 else -q) * scale[i]
            elif method == "M3":
                mask = self.bin_cal == bins[i]
                scores = self.norm_abs[mask]
                if len(scores) < 10:
                    scores = self.norm_abs
                level = abs(2 * tau - 1)
                q = finite_conformal_quantile(scores, level)
                out[i] = point[i] + (q if tau > 0.5 else -q) * scale[i]
            elif method in {"M4", "M5"}:
                scores = self.norm_signed
                if method == "M5":
                    mask = self.bin_cal == bins[i]
                    if mask.sum() >= 10:
                        scores = scores[mask]
                q = float(np.quantile(scores, tau, method="linear"))
                out[i] = point[i] + q * scale[i]
            else:
                raise ValueError(f"unknown method {method}")
        return np.clip(out, 0, 1)

    def scenarios(
        self, method: str, x_row: np.ndarray, point: float, n: int = 99
    ) -> np.ndarray:
        taus = np.arange(1, n + 1) / (n + 1)
        vals = np.array(
            [
                self.quantile(
                    method,
                    np.asarray(x_row, float)[None, :],
                    np.asarray([point]),
                    float(t),
                )[0]
                for t in taus
            ]
        )
        return np.clip(np.sort(vals), 0, 1)


def fit_price_clusters(df_cal: pd.DataFrame, n_clusters: int, seed: int = 22):
    up_delta = (df_cal["up_price"] - df_cal["da_price"]).to_numpy()
    down_delta = (df_cal["da_price"] - df_cal["down_price"]).to_numpy()
    data = np.column_stack([up_delta, down_delta])
    k = min(n_clusters, max(2, len(data) // 30))
    km = KMeans(n_clusters=k, random_state=seed, n_init=10).fit(data)
    centers = km.cluster_centers_
    counts = np.bincount(km.labels_, minlength=k).astype(float)
    weights = counts / counts.sum()
    return centers, weights


def newsvendor_tau(price_centers: np.ndarray, weights: np.ndarray) -> float:
    up = price_centers[:, 0]
    down = price_centers[:, 1]
    tau = down / np.maximum(down + up, 1e-9)
    return float(np.sum(weights * tau))


def profit_scenarios(
    bid: float,
    pv_scenarios: np.ndarray,
    da: float,
    centers: np.ndarray,
    weights: np.ndarray,
):
    pv = np.asarray(pv_scenarios)[:, None]
    up_delta = centers[:, 0][None, :]
    down_delta = centers[:, 1][None, :]
    p_up = da + up_delta
    p_down = np.maximum(0, da - down_delta)
    deficit = np.maximum(bid - pv, 0)
    surplus = np.maximum(pv - bid, 0)
    profit = bid * da - deficit * p_up + surplus * p_down
    prob = np.repeat(
        weights[None, :] / len(pv_scenarios),
        len(pv_scenarios),
        axis=0,
    )
    return profit.ravel(), prob.ravel()


def lower_tail_cvar(values: np.ndarray, prob: np.ndarray, gamma: float) -> float:
    order = np.argsort(values)
    v, p = values[order], prob[order]
    target = 1 - gamma
    acc, total = 0.0, 0.0
    for vi, pi in zip(v, p):
        take = min(pi, target - total)
        if take > 0:
            acc += take * vi
            total += take
        if total >= target - 1e-12:
            break
    return float(acc / max(total, 1e-12))


def optimize_eum_bid(
    pv_scenarios,
    da,
    centers,
    weights,
    grid_n=41,
    beta=0.0,
    gamma=0.6,
):
    best_bid, best_obj = 0.0, -np.inf
    for bid in np.linspace(0, 1, grid_n):
        profits, prob = profit_scenarios(
            bid, pv_scenarios, da, centers, weights
        )
        mean = float(np.sum(profits * prob))
        cvar = lower_tail_cvar(profits, prob, gamma)
        obj = (1 - beta) * mean + beta * cvar
        if obj > best_obj:
            best_obj, best_bid = obj, float(bid)
    return best_bid


def realized_profit(
    bid: np.ndarray,
    pv: np.ndarray,
    da: np.ndarray,
    up_price: np.ndarray,
    down_price: np.ndarray,
):
    deficit = np.maximum(bid - pv, 0)
    surplus = np.maximum(pv - bid, 0)
    return bid * da - deficit * up_price + surplus * down_price


def evaluate_bids(name: str, bid, df_test):
    pv = df_test["pv"].to_numpy()
    b = np.asarray(bid, float)
    profit = realized_profit(
        b,
        pv,
        df_test["da_price"].to_numpy(),
        df_test["up_price"].to_numpy(),
        df_test["down_price"].to_numpy(),
    )
    return {
        "method_strategy": name,
        "profit": float(np.sum(profit)),
        "mean_abs_imbalance": float(np.mean(np.abs(pv - b))),
        "rmse_imbalance": float(np.sqrt(np.mean((pv - b) ** 2))),
    }


def run(cfg: Config, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    df = make_demo_market(cfg.days, cfg.seed)
    X = features(df)
    tr, ca, te = split_daylight(df)
    te = te[: cfg.max_eval]

    rf = RandomForestRegressor(
        n_estimators=160,
        max_features=3,
        min_samples_leaf=3,
        random_state=cfg.seed,
        n_jobs=-1,
    )
    rf.fit(X[tr], df["pv"].to_numpy()[tr])
    p_cal = np.clip(rf.predict(X[ca]), 0, 1)
    p_test = np.clip(rf.predict(X[te]), 0, 1)
    y_cal = df["pv"].to_numpy()[ca]

    cp = CPBundle(
        X[ca],
        y_cal,
        p_cal,
        cfg.k_neighbors,
        cfg.mondrian_bins,
    )
    centers, weights = fit_price_clusters(
        df.iloc[ca], cfg.price_clusters, cfg.seed
    )
    nv_tau = newsvendor_tau(centers, weights)

    rows = []
    test_df = df.iloc[te].copy()
    perfect = test_df["pv"].to_numpy()
    rows.append(
        evaluate_bids("perfect_information", perfect, test_df)
    )
    rows.append(
        evaluate_bids("RFR_trust_point", p_test, test_df)
    )

    methods = ["M1", "M2", "M3", "M4", "M5"]
    for method in methods:
        med = cp.quantile(method, X[te], p_test, 0.5)
        low = cp.quantile(method, X[te], p_test, 0.05)
        nv = cp.quantile(method, X[te], p_test, nv_tau)
        rows.append(
            evaluate_bids(f"{method}_trust", med, test_df)
        )
        rows.append(
            evaluate_bids(f"{method}_worst_case", low, test_df)
        )
        rows.append(
            evaluate_bids(f"{method}_newsvendor", nv, test_df)
        )

        eum, eum_cvar = [], []
        for j, idx in enumerate(te):
            scen = cp.scenarios(
                method, X[idx], p_test[j], cfg.pv_scenarios
            )
            da = float(df.iloc[idx]["da_price"])
            eum.append(
                optimize_eum_bid(
                    scen,
                    da,
                    centers,
                    weights,
                    cfg.eum_grid,
                    beta=0.0,
                    gamma=cfg.cvar_gamma,
                )
            )
            eum_cvar.append(
                optimize_eum_bid(
                    scen,
                    da,
                    centers,
                    weights,
                    cfg.eum_grid,
                    beta=cfg.cvar_beta,
                    gamma=cfg.cvar_gamma,
                )
            )
        rows.append(
            evaluate_bids(
                f"{method}_EUM", np.asarray(eum), test_df
            )
        )
        rows.append(
            evaluate_bids(
                f"{method}_EUM_CVaR",
                np.asarray(eum_cvar),
                test_df,
            )
        )

    metrics = pd.DataFrame(rows).set_index("method_strategy")
    perfect_profit = float(
        metrics.loc["perfect_information", "profit"]
    )
    metrics["profit_fraction_of_perfect"] = (
        metrics["profit"] / max(perfect_profit, 1e-9)
    )
    metrics.to_csv(out_dir / "bidding_metrics.csv")

    urows = []
    ytest = test_df["pv"].to_numpy()
    for method in methods:
        lo = cp.quantile(method, X[te], p_test, 0.05)
        hi = cp.quantile(method, X[te], p_test, 0.95)
        urows.append(
            {
                "method": method,
                "picp_90": float(
                    np.mean((ytest >= lo) & (ytest <= hi))
                ),
                "mean_width_90": float(np.mean(hi - lo)),
            }
        )
    pd.DataFrame(urows).set_index("method").to_csv(
        out_dir / "uncertainty_metrics.csv"
    )

    summary = {
        "config": asdict(cfg),
        "newsvendor_probability_quantile": nv_tau,
        "best_demo_profit_strategy": str(
            metrics["profit"].idxmax()
        ),
        "M5_EUM_CVaR_profit_fraction_of_perfect": float(
            metrics.loc[
                "M5_EUM_CVaR",
                "profit_fraction_of_perfect",
            ]
        ),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="results/demo")
    p.add_argument("--smoke", action="store_true")
    args = p.parse_args()
    cfg = Config()
    if args.smoke:
        cfg.days = 180
        cfg.k_neighbors = 20
        cfg.mondrian_bins = 5
        cfg.price_clusters = 5
        cfg.pv_scenarios = 19
        cfg.eum_grid = 15
        cfg.max_eval = 20
    result = run(cfg, Path(args.out))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
