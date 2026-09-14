from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def plot_prediction_intervals(npz_path: str | Path, output_path: str | Path, n_steps: int = 96) -> None:
    data = np.load(npz_path)
    y = data["y_true"].reshape(-1)[:n_steps]
    point = data["point"].reshape(-1)[:n_steps]
    lower = data["lower"].reshape(-1)[:n_steps]
    upper = data["upper"].reshape(-1)[:n_steps]

    x = np.arange(len(y))
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(x, y, label="True", linewidth=1.8)
    ax.plot(x, point, label="Pred", linewidth=1.5)
    ax.fill_between(x, lower, upper, alpha=0.25, label="90% interval")
    ax.set_xlabel("30-minute step")
    ax.set_ylabel("Net load (MW)")
    ax.set_title("Conformal-MLPF reproduction: prediction interval")
    ax.legend()
    ax.grid(alpha=0.2)
    fig.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_metrics(metrics_csv: str | Path, output_path: str | Path) -> None:
    df = pd.read_csv(metrics_csv)
    summary = df.groupby("method")[["PICP", "NMPI", "NRMSE"]].mean().sort_index()
    methods = list(summary.index)
    x = np.arange(len(methods))
    width = 0.24

    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.bar(x - width, summary["PICP"], width, label="PICP")
    ax.bar(x, summary["NMPI"], width, label="NMPI")
    ax.bar(x + width, summary["NRMSE"], width, label="NRMSE")
    ax.set_xticks(x, methods, rotation=20, ha="right")
    ax.set_ylabel("Metric value")
    ax.set_title("Probabilistic forecast comparison across folds")
    ax.legend()
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
