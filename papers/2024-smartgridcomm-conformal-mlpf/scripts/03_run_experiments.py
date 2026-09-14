from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from conformal_mlpf.conformal import AbsoluteResidualConformal, SignedResidualInterval
from conformal_mlpf.data import Standardizer, WindowArrays, build_windows, read_config, subset_arrays
from conformal_mlpf.metrics import interval_metrics
from conformal_mlpf.models import PointForecaster, QuantileForecaster
from conformal_mlpf.train import (
    FitConfig,
    fit_point_model,
    fit_quantile_model,
    predict_mc_dropout,
    predict_point,
    predict_quantiles,
    resolve_device,
    seed_everything,
)


def _indices(mask: np.ndarray) -> np.ndarray:
    return np.flatnonzero(mask)


def _scale_fold(train: WindowArrays, cal: WindowArrays, test: WindowArrays):
    past_scaler = Standardizer().fit(train.past)
    future_scaler = Standardizer().fit(train.future)
    y_mean = float(train.target.mean())
    y_std = float(train.target.std())
    if y_std < 1e-8:
        y_std = 1.0

    def tx(a: WindowArrays) -> WindowArrays:
        return WindowArrays(
            past=past_scaler.transform(a.past).astype(np.float32),
            future=future_scaler.transform(a.future).astype(np.float32),
            target=((a.target - y_mean) / y_std).astype(np.float32),
            timestamps=a.timestamps,
        )

    return tx(train), tx(cal), tx(test), y_mean, y_std


def _backtest_folds(timestamps: np.ndarray, cfg: dict):
    ts = pd.to_datetime(timestamps)
    first = ts.min()
    last = ts.max()
    train_end = first + pd.DateOffset(months=int(cfg["initial_train_months"]))
    produced = 0
    while produced < int(cfg["n_folds"]):
        test_start = train_end
        test_end = test_start + pd.DateOffset(months=int(cfg["test_months"]))
        if test_start >= last:
            break
        train_idx = _indices(np.asarray(ts < train_end))
        test_idx = _indices(np.asarray((ts >= test_start) & (ts < min(test_end, last + pd.Timedelta(seconds=1)))))
        if len(train_idx) < 100 or len(test_idx) < 10:
            break
        yield produced, train_idx, test_idx, train_end, min(test_end, last)
        produced += 1
        train_end = train_end + pd.DateOffset(months=int(cfg["step_months"]))


def _make_point(config: dict, past_dim: int, future_dim: int, dropout: float) -> PointForecaster:
    d = config["dataset"]
    m = config["model"]
    return PointForecaster(
        lookback=int(d["lookback_steps"]),
        horizon=int(d["horizon_steps"]),
        past_dim=past_dim,
        future_dim=future_dim,
        hidden_dim=int(m["hidden_dim"]),
        hidden_layers=int(m["hidden_layers"]),
        activation=m["activation"],
        dropout=float(dropout),
    )


def _fit_cfg(config: dict, quick: bool) -> FitConfig:
    m = config["model"]
    return FitConfig(
        epochs=3 if quick else int(m["epochs"]),
        batch_size=int(m["batch_size"]),
        learning_rate=float(m["learning_rate"]),
        weight_decay=float(m["weight_decay"]),
        l1_l2_lambda=float(m["l1_l2_lambda"]),
        num_workers=int(config["runtime"]["num_workers"]),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["sps-uk", "mlvs-pt"], default="sps-uk")
    parser.add_argument("--config", default="configs/paper.yaml")
    parser.add_argument("--quick", action="store_true", help="1 fold, 3 epochs and capped samples for a smoke run")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    config = read_config(root / args.config)
    seed_everything(int(config["seed"]))
    device = resolve_device(config["runtime"]["device"])
    print(f"device={device}")

    df = pd.read_parquet(root / "data" / "processed" / f"{args.dataset}.parquet")
    dcfg = config["dataset"]
    arrays = build_windows(
        df,
        past_features=list(dcfg["past_features"]),
        future_features=list(dcfg["future_features"]),
        target=dcfg["target"],
        lookback=int(dcfg["lookback_steps"]),
        horizon=int(dcfg["horizon_steps"]),
    )

    if args.quick:
        config["backtest"]["n_folds"] = 1

    alpha = float(config["conformal"]["alpha"])
    quantiles = [float(q) for q in config["model"]["quantiles"]]
    fit_cfg = _fit_cfg(config, args.quick)
    rows: list[dict] = []
    saved_prediction = None

    for fold, train_all_idx, test_idx, train_end, test_end in _backtest_folds(arrays.timestamps, config["backtest"]):
        cal_fraction = float(config["backtest"]["calibration_fraction"])
        n_cal = max(1, int(np.ceil(len(train_all_idx) * cal_fraction)))
        model_idx, cal_idx = train_all_idx[:-n_cal], train_all_idx[-n_cal:]

        if args.quick:
            model_idx = model_idx[-min(len(model_idx), 2500):]
            cal_idx = cal_idx[-min(len(cal_idx), 600):]
            test_idx = test_idx[:min(len(test_idx), 600)]

        train_raw = subset_arrays(arrays, model_idx)
        cal_raw = subset_arrays(arrays, cal_idx)
        test_raw = subset_arrays(arrays, test_idx)
        train, cal, test, y_mean, y_std = _scale_fold(train_raw, cal_raw, test_raw)

        past_dim = train.past.shape[-1]
        future_dim = train.future.shape[-1]
        batch_size = fit_cfg.batch_size

        print(
            f"fold={fold} train={len(model_idx)} cal={len(cal_idx)} test={len(test_idx)} "
            f"test_range={train_end} -> {test_end}"
        )

        # 1) Deterministic MLPF + conformal calibration.
        seed_everything(int(config["seed"]) + fold)
        point_model = _make_point(config, past_dim, future_dim, float(config["model"]["point_dropout"]))
        point_model = fit_point_model(point_model, train, fit_cfg, device)
        cal_pred = predict_point(point_model, cal, batch_size, device) * y_std + y_mean
        test_pred = predict_point(point_model, test, batch_size, device) * y_std + y_mean

        abs_cp = AbsoluteResidualConformal(alpha).fit(cal_raw.target, cal_pred)
        abs_lower, abs_upper = abs_cp.predict_interval(test_pred)
        metrics = interval_metrics(test_raw.target, test_pred, abs_lower, abs_upper, alpha)
        rows.append({"fold": fold, "method": "conformal_abs", **metrics})

        signed_cp = SignedResidualInterval(alpha).fit(cal_raw.target, cal_pred)
        signed_lower, signed_upper = signed_cp.predict_interval(test_pred)
        metrics = interval_metrics(test_raw.target, test_pred, signed_lower, signed_upper, alpha)
        rows.append({"fold": fold, "method": "conformal_signed", **metrics})

        # 2) Quantile-regression baseline.
        seed_everything(int(config["seed"]) + 1000 + fold)
        qr_model = QuantileForecaster(
            lookback=int(dcfg["lookback_steps"]),
            horizon=int(dcfg["horizon_steps"]),
            past_dim=past_dim,
            future_dim=future_dim,
            hidden_dim=int(config["model"]["hidden_dim"]),
            hidden_layers=int(config["model"]["hidden_layers"]),
            activation=config["model"]["activation"],
            dropout=float(config["model"]["point_dropout"]),
            quantiles=quantiles,
        )
        qr_model = fit_quantile_model(qr_model, train, fit_cfg, device, quantiles)
        qr = predict_quantiles(qr_model, test, batch_size, device) * y_std + y_mean
        q_index = {q: i for i, q in enumerate(quantiles)}
        lower_q = min(quantiles, key=lambda q: abs(q - alpha / 2.0))
        median_q = min(quantiles, key=lambda q: abs(q - 0.5))
        upper_q = min(quantiles, key=lambda q: abs(q - (1.0 - alpha / 2.0)))
        qr_lower, qr_point, qr_upper = qr[..., q_index[lower_q]], qr[..., q_index[median_q]], qr[..., q_index[upper_q]]
        metrics = interval_metrics(test_raw.target, qr_point, qr_lower, qr_upper, alpha)
        rows.append({"fold": fold, "method": "mlp_qr", **metrics})

        # 3) MC-dropout baseline.
        seed_everything(int(config["seed"]) + 2000 + fold)
        mcd_model = _make_point(config, past_dim, future_dim, float(config["model"]["mcd_dropout"]))
        mcd_model = fit_point_model(mcd_model, train, fit_cfg, device)
        mc_samples = 20 if args.quick else int(config["model"]["mc_samples"])
        mcd_point_s, mcd_lower_s, mcd_upper_s = predict_mc_dropout(
            mcd_model, test, batch_size, device, mc_samples, alpha
        )
        mcd_point = mcd_point_s * y_std + y_mean
        mcd_lower = mcd_lower_s * y_std + y_mean
        mcd_upper = mcd_upper_s * y_std + y_mean
        metrics = interval_metrics(test_raw.target, mcd_point, mcd_lower, mcd_upper, alpha)
        rows.append({"fold": fold, "method": "mlp_mcd", **metrics})

        saved_prediction = {
            "y_true": test_raw.target,
            "point": test_pred,
            "lower": abs_lower,
            "upper": abs_upper,
        }

    if not rows:
        raise RuntimeError("No valid backtest folds could be constructed from the prepared dataset")

    out_dir = root / "results" / args.dataset
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_df = pd.DataFrame(rows)
    metrics_df.to_csv(out_dir / "metrics.csv", index=False)
    if saved_prediction is not None:
        np.savez_compressed(out_dir / "fold_predictions.npz", **saved_prediction)

    print("\nMean metrics across folds")
    print(metrics_df.groupby("method")[["NRMSE", "PICP", "NMPI", "CWE_proxy"]].mean().round(4))
    print(f"\nresults: {out_dir}")


if __name__ == "__main__":
    main()
