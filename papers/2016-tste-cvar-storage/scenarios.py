"""Nominal inputs and reproducible uncertainty for the 2016 storage example.

The included load is a synthetic substitute, not the unavailable Burlington
Hydro data.  Each input row represents a known nominal half-hour forecast.
Sampling a test realization and sampling optimization scenarios must use
different ``rng_for`` stream identifiers to avoid look-ahead leakage.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
from pathlib import Path

import numpy as np


BASE_HOURS = 0.5
PAPER_HOURS = np.array([0.5, 0.5, 0.5, 0.5, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3])
_BLOCK_LENGTHS = (PAPER_HOURS / BASE_HOURS).astype(int)
_COLUMNS = (
    "timestamp", "net_load_kw", "buy_price_per_kwh", "sell_price_per_kwh"
)


def _positive_integer(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be a positive integer")
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def _nonnegative_scalar(value, name):
    raw = np.asarray(value, dtype=float)
    if raw.ndim != 0 or not np.isfinite(raw) or raw < 0:
        raise ValueError(f"{name} must be a finite nonnegative scalar")
    return float(raw)


def _vector(value, name):
    arr = np.asarray(value, dtype=float)
    if arr.ndim != 1 or arr.size == 0 or not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must be a nonempty finite one-dimensional array")
    return arr


@dataclass(frozen=True)
class NominalSeries:
    timestamps: tuple[datetime, ...]
    demand_kw: np.ndarray
    buy_price: np.ndarray
    sell_price: np.ndarray
    provenance: dict

    def __post_init__(self):
        demand = _vector(self.demand_kw, "demand_kw")
        buy = _vector(self.buy_price, "buy_price")
        sell = _vector(self.sell_price, "sell_price")
        times = tuple(self.timestamps)
        if buy.shape != demand.shape or sell.shape != demand.shape:
            raise ValueError("nominal demand and prices must have matching lengths")
        if len(times) != len(demand):
            raise ValueError("timestamps must match nominal data length")
        if any(not isinstance(value, datetime) for value in times):
            raise ValueError("timestamps must be datetime values")
        # Requiring a consistent UTC offset avoids silent clock/DST changes in
        # a fixed 48-row day.  Naive local times are also accepted consistently.
        offset = times[0].utcoffset()
        if any(value.utcoffset() != offset for value in times):
            raise ValueError("timestamps must use a uniform timezone/UTC offset")
        if any(right - left != timedelta(minutes=30)
               for left, right in zip(times, times[1:])):
            raise ValueError("timestamps must be increasing and exactly 30 minutes apart")
        if np.any(sell < 0) or np.any(buy < sell):
            raise ValueError("nominal prices must satisfy buy >= sell >= 0")
        # Own the arrays: callers cannot accidentally change their source data
        # through a shared array while preparing an optimization scenario.
        for name, values in (("demand_kw", demand), ("buy_price", buy), ("sell_price", sell)):
            owned = values.copy()
            owned.setflags(write=False)
            object.__setattr__(self, name, owned)
        object.__setattr__(self, "timestamps", times)


def synthetic_series(steps: int) -> NominalSeries:
    """Return a deterministic positive load (<24 kW) and Ontario winter TOU.

    The tariff schedule is the historical schedule specified in the paper,
    applied on every synthetic day; calendar/holiday tariff exceptions are
    not modeled.  Prices are dollars per kWh throughout the public API.
    """
    steps = _positive_integer(steps, "steps")
    start = datetime(2016, 1, 4)
    times = tuple(start + timedelta(minutes=30 * index) for index in range(steps))
    time = np.arange(steps) * BASE_HOURS
    clock = np.mod(time, 24.0)
    day = np.floor(time / 24.0)
    demand = (
        7.0
        + 7.0 * np.exp(-0.5 * ((clock - 8.0) / 1.8) ** 2)
        + 12.0 * np.exp(-0.5 * ((clock - 18.0) / 2.5) ** 2)
        + 0.7 * np.cos(2.0 * np.pi * day / 7.0)
    )
    off_peak = (clock < 7.0) | (clock >= 19.0)
    mid_peak = (clock >= 11.0) & (clock < 17.0)
    buy = np.where(off_peak, 0.062, np.where(mid_peak, 0.092, 0.108))
    return NominalSeries(
        times, demand, buy, np.zeros(steps),
        {
            "source": "synthetic",
            "description": "Deterministic morning/evening load; not Burlington Hydro observations",
            "start": start.isoformat(),
            "tariff": "Paper's Ontario winter TOU, applied every day; sell price zero",
        },
    )


def load_csv(path, required_steps: int) -> NominalSeries:
    """Read a complete half-hour nominal forecast series from a CSV.

    Extra columns are allowed.  No gaps are filled and no invalid rows are
    dropped.  ``required_steps`` includes the final rolling forecast window.
    """
    required_steps = _positive_integer(required_steps, "required_steps")
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = set(_COLUMNS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"CSV is missing columns: {', '.join(sorted(missing))}")
        timestamps, demand, buy, sell = [], [], [], []
        for line, row in enumerate(reader, start=2):
            try:
                timestamp = datetime.fromisoformat(row["timestamp"].strip())
                values = [float(row[column]) for column in _COLUMNS[1:]]
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError(f"CSV row {line} has an invalid timestamp or numeric field") from exc
            timestamps.append(timestamp)
            demand.append(values[0])
            buy.append(values[1])
            sell.append(values[2])
    if len(timestamps) < required_steps:
        raise ValueError(
            f"CSV has {len(timestamps)} rows; at least {required_steps} are required "
            "including the rolling forecast look-ahead"
        )
    return NominalSeries(
        tuple(timestamps), np.asarray(demand), np.asarray(buy), np.asarray(sell),
        {
            "source": "external_csv",
            "filename": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "rows": len(timestamps),
            "interpretation": "Known nominal forecasts, not realized future observations",
        },
    )


def aggregate_horizon(series: NominalSeries, origin: int):
    """Aggregate the next 48 half-hours into the paper's 14 power/price blocks.

    Return rate averages, not energy/integrated price.  ``model.solve_dispatch``
    applies each block's duration exactly once to convert rates to totals.
    """
    if isinstance(origin, (bool, np.bool_)) or not isinstance(origin, (int, np.integer)) or origin < 0:
        raise ValueError("origin must be a nonnegative integer")
    if origin + int(_BLOCK_LENGTHS.sum()) > len(series.demand_kw):
        raise ValueError("not enough nominal rows for the full 24-hour horizon")
    boundaries = origin + np.concatenate(([0], np.cumsum(_BLOCK_LENGTHS)))
    return tuple(
        np.array([array[left:right].mean() for left, right in zip(boundaries, boundaries[1:])])
        for array in (series.demand_kw, series.buy_price, series.sell_price)
    )


def price_std(buy_price, hours, scale=1.0):
    """Price-rate sigma from the paper's square root of integrated *cents*.

    A block's mean price coefficient is ``100 * buy_price * hours`` cents/kW.
    Take its square root first, then convert cents back to dollars and divide
    by duration.  Taking the square root of dollar coefficients instead would
    inflate the resulting dollar uncertainty by a factor of ten.
    """
    scale = _nonnegative_scalar(scale, "scale")
    buy, duration = np.broadcast_arrays(
        np.asarray(buy_price, dtype=float), np.asarray(hours, dtype=float)
    )
    if not np.all(np.isfinite(buy)) or np.any(buy < 0):
        raise ValueError("buy_price must contain finite nonnegative values")
    if not np.all(np.isfinite(duration)) or np.any(duration <= 0):
        raise ValueError("hours must contain finite positive durations")
    return 0.01 * np.sqrt(100.0 * buy * duration) * scale / duration


def sample_joint(demand, buy, sell, hours, count, rng, scale=1.0, rho=0.5):
    """Sample correlated load and buying price, independent across blocks.

    Gaussian buying prices below the fixed selling price are censored to the
    selling price to preserve ``buy >= sell``.  Return the censor count along
    with both arrays; the post-censor moments/correlation are not exactly the
    input Gaussian moments/correlation.  Net demand can legitimately be negative.
    """
    demand, buy, sell, duration = (
        _vector(value, name)
        for value, name in ((demand, "demand"), (buy, "buy"), (sell, "sell"), (hours, "hours"))
    )
    if any(array.shape != demand.shape for array in (buy, sell, duration)):
        raise ValueError("demand, buy, sell, and hours must have matching shapes")
    if np.any(sell < 0) or np.any(buy < sell):
        raise ValueError("nominal prices must satisfy buy >= sell >= 0")
    if np.any(duration <= 0):
        raise ValueError("hours must be positive")
    count = _positive_integer(count, "count")
    scale = _nonnegative_scalar(scale, "scale")
    correlation = np.asarray(rho, dtype=float)
    if correlation.ndim != 0 or not np.isfinite(correlation) or abs(correlation) > 1:
        raise ValueError("rho must be a finite scalar in [-1, 1]")
    if not isinstance(rng, np.random.Generator):
        raise ValueError("rng must be a numpy.random.Generator")
    # The first dimension keeps demand scenario prefixes invariant when the
    # caller asks for more scenarios.  Demand draws also match WCVAR prefixes.
    normals = rng.standard_normal((count, len(demand), 2))
    demand_noise = normals[:, :, 0]
    price_noise = float(correlation) * demand_noise + np.sqrt(1 - float(correlation) ** 2) * normals[:, :, 1]
    sampled_demand = demand + np.sqrt(np.abs(demand)) * scale * demand_noise
    raw_buy = buy + price_std(buy, duration, scale) * price_noise
    return sampled_demand, np.maximum(raw_buy, sell), int(np.count_nonzero(raw_buy < sell))


def rng_for(seed, stream, replication, origin=0):
    """Create a stable stream, independent of controller ordering and run size."""
    values = (seed, stream, replication, origin)
    if any(isinstance(value, (bool, np.bool_))
           or not isinstance(value, (int, np.integer)) or value < 0 for value in values):
        raise ValueError("seed, stream, replication, and origin must be nonnegative integers")
    return np.random.default_rng(np.random.SeedSequence([int(value) for value in values]))
