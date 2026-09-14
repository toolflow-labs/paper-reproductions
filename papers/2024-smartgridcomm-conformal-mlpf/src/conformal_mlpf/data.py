from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset


@dataclass
class WindowArrays:
    past: np.ndarray
    future: np.ndarray
    target: np.ndarray
    timestamps: np.ndarray


class WindowDataset(Dataset):
    def __init__(self, arrays: WindowArrays):
        self.past = torch.as_tensor(arrays.past, dtype=torch.float32)
        self.future = torch.as_tensor(arrays.future, dtype=torch.float32)
        self.target = torch.as_tensor(arrays.target, dtype=torch.float32)

    def __len__(self) -> int:
        return len(self.target)

    def __getitem__(self, idx: int):
        return self.past[idx], self.future[idx], self.target[idx]


class Standardizer:
    def __init__(self):
        self.mean_: np.ndarray | None = None
        self.std_: np.ndarray | None = None

    def fit(self, x: np.ndarray) -> "Standardizer":
        axes = tuple(range(x.ndim - 1))
        self.mean_ = np.nanmean(x, axis=axes, keepdims=True)
        self.std_ = np.nanstd(x, axis=axes, keepdims=True)
        self.std_ = np.where(self.std_ < 1e-8, 1.0, self.std_)
        return self

    def transform(self, x: np.ndarray) -> np.ndarray:
        if self.mean_ is None or self.std_ is None:
            raise RuntimeError("Standardizer is not fitted")
        return (x - self.mean_) / self.std_

    def inverse_transform(self, x: np.ndarray) -> np.ndarray:
        if self.mean_ is None or self.std_ is None:
            raise RuntimeError("Standardizer is not fitted")
        return x * self.std_ + self.mean_


def read_config(path: str | Path) -> dict:
    import yaml

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _pick_datetime_column(df: pd.DataFrame) -> str:
    preferred = [c for c in df.columns if any(k in c.lower() for k in ("datetime", "timestamp", "date", "time"))]
    for c in preferred + list(df.columns):
        parsed = pd.to_datetime(df[c], errors="coerce")
        if parsed.notna().mean() > 0.9:
            return c
    raise ValueError(f"Could not identify a datetime column. Columns={list(df.columns)}")


def _pick_numeric_column(df: pd.DataFrame, include: Iterable[str], exclude: Iterable[str] = ()) -> str:
    include = tuple(s.lower() for s in include)
    exclude = tuple(s.lower() for s in exclude)
    candidates = []
    for c in df.columns:
        name = c.lower()
        if any(k in name for k in include) and not any(k in name for k in exclude):
            candidates.append(c)
    candidates += [c for c in df.select_dtypes(include=[np.number]).columns if c not in candidates]
    if not candidates:
        raise ValueError(f"Could not identify numeric column in {list(df.columns)}")
    return candidates[0]


def _read_timeseries_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    dt = _pick_datetime_column(df)
    df[dt] = pd.to_datetime(df[dt], errors="coerce")
    return df.dropna(subset=[dt]).sort_values(dt).rename(columns={dt: "timestamp"})


def prepare_sps_uk(raw_dir: str | Path, output_path: str | Path, weather_override: str | Path | None = None) -> pd.DataFrame:
    raw_dir = Path(raw_dir)
    output_path = Path(output_path)

    demand_parts = [_read_timeseries_csv(raw_dir / "demand_train_set4.csv")]
    pv_parts = [_read_timeseries_csv(raw_dir / "pv_train_set4.csv")]
    if (raw_dir / "demand_test_set4.csv").exists():
        demand_parts.append(_read_timeseries_csv(raw_dir / "demand_test_set4.csv"))
    if (raw_dir / "pv_test_set4.csv").exists():
        pv_parts.append(_read_timeseries_csv(raw_dir / "pv_test_set4.csv"))

    demand = pd.concat(demand_parts, ignore_index=True).drop_duplicates("timestamp")
    pv = pd.concat(pv_parts, ignore_index=True).drop_duplicates("timestamp")

    demand_col = _pick_numeric_column(demand, ("demand", "power", "mw"), ("irradiance", "temp"))
    pv_col = _pick_numeric_column(pv, ("pv_power", "power", "mw"), ("irradiance", "temp"))
    irr_col = _pick_numeric_column(pv, ("irradiance", "radiation", "ghi"), ("power",))
    panel_temp_col = _pick_numeric_column(pv, ("temp", "temperature"), ())

    base = demand[["timestamp", demand_col]].rename(columns={demand_col: "demand_mw"})
    base = base.merge(
        pv[["timestamp", pv_col, irr_col, panel_temp_col]].rename(
            columns={pv_col: "pv_mw", irr_col: "pv_irradiance", panel_temp_col: "panel_temperature"}
        ),
        on="timestamp",
        how="inner",
    )

    weather_path = Path(weather_override) if weather_override else raw_dir / "weather_train_set4.csv"
    if weather_path.exists():
        weather = _read_timeseries_csv(weather_path)
        num_cols = [c for c in weather.select_dtypes(include=[np.number]).columns]
        temp_cols = [c for c in num_cols if any(k in c.lower() for k in ("temp", "t2m"))]
        rad_cols = [c for c in num_cols if any(k in c.lower() for k in ("solar", "radiation", "irradiance", "ghi", "swgdn"))]
        if temp_cols:
            weather["weather_temperature"] = weather[temp_cols].mean(axis=1)
        if rad_cols:
            weather["weather_irradiance"] = weather[rad_cols].mean(axis=1)
        keep = ["timestamp"] + [c for c in ("weather_temperature", "weather_irradiance") if c in weather]
        weather = weather[keep].set_index("timestamp").resample("30min").interpolate("time").reset_index()
        base = base.merge(weather, on="timestamp", how="left")

    base["temperature"] = base.get("weather_temperature", base["panel_temperature"])
    if "weather_temperature" in base:
        base["temperature"] = base["temperature"].fillna(base["panel_temperature"])
    base["irradiance"] = base.get("weather_irradiance", base["pv_irradiance"])
    if "weather_irradiance" in base:
        base["irradiance"] = base["irradiance"].fillna(base["pv_irradiance"])

    # Paper definition: net-load = load demand - PV generation.
    base["net_load_mw"] = base["demand_mw"] - base["pv_mw"]
    base = add_time_features(base)
    base = base[[
        "timestamp", "demand_mw", "pv_mw", "net_load_mw", "irradiance", "temperature",
        "hour_sin", "hour_cos", "dow_sin", "dow_cos", "doy_sin", "doy_cos", "session",
    ]].dropna().sort_values("timestamp").drop_duplicates("timestamp")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    base.to_parquet(output_path, index=False)
    return base


def prepare_mlvs_pt(raw_file: str | Path, output_path: str | Path) -> pd.DataFrame:
    raw_file = Path(raw_file)
    if not raw_file.exists():
        raise FileNotFoundError(
            f"MLVS-PT file not found: {raw_file}. Expected the parquet layout used in the authors' later tutorials."
        )
    df = pd.read_parquet(raw_file)
    required = {"timestamp", "NetLoad(kW)", "Ghi", "Temperature"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"MLVS-PT parquet missing columns: {sorted(missing)}")
    out = df[["timestamp", "NetLoad(kW)", "Ghi", "Temperature"]].copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"])
    out["net_load_mw"] = out["NetLoad(kW)"] / 1000.0
    out["irradiance"] = out["Ghi"]
    out["temperature"] = out["Temperature"]
    out = add_time_features(out)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(output_path, index=False)
    return out


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    ts = pd.to_datetime(out["timestamp"])
    hour = ts.dt.hour + ts.dt.minute / 60.0
    dow = ts.dt.dayofweek
    doy = ts.dt.dayofyear
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    out["dow_sin"] = np.sin(2 * np.pi * dow / 7.0)
    out["dow_cos"] = np.cos(2 * np.pi * dow / 7.0)
    out["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    out["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    out["session"] = ((hour >= 6.0) & (hour < 18.0)).astype(float)
    return out


def build_windows(
    df: pd.DataFrame,
    past_features: list[str],
    future_features: list[str],
    target: str,
    lookback: int,
    horizon: int,
) -> WindowArrays:
    p = df[past_features].to_numpy(dtype=np.float32)
    f = df[future_features].to_numpy(dtype=np.float32)
    y = df[target].to_numpy(dtype=np.float32)
    t = pd.to_datetime(df["timestamp"]).to_numpy()

    past, future, targets, timestamps = [], [], [], []
    for i in range(lookback, len(df) - horizon + 1):
        past.append(p[i - lookback:i])
        future.append(f[i:i + horizon])
        targets.append(y[i:i + horizon])
        timestamps.append(t[i])
    return WindowArrays(
        past=np.asarray(past, dtype=np.float32),
        future=np.asarray(future, dtype=np.float32),
        target=np.asarray(targets, dtype=np.float32),
        timestamps=np.asarray(timestamps),
    )


def subset_arrays(arrays: WindowArrays, idx: np.ndarray) -> WindowArrays:
    return WindowArrays(
        past=arrays.past[idx],
        future=arrays.future[idx],
        target=arrays.target[idx],
        timestamps=arrays.timestamps[idx],
    )
