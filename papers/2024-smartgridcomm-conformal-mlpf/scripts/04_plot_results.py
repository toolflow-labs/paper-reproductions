from __future__ import annotations

import argparse
from pathlib import Path

from conformal_mlpf.plotting import plot_metrics, plot_prediction_intervals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["sps-uk", "mlvs-pt"], default="sps-uk")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    result_dir = root / "results" / args.dataset
    fig_dir = result_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    plot_prediction_intervals(
        result_dir / "fold_predictions.npz",
        fig_dir / "prediction_intervals.png",
    )
    plot_metrics(
        result_dir / "metrics.csv",
        fig_dir / "metrics_comparison.png",
    )
    print(f"figures: {fig_dir}")


if __name__ == "__main__":
    main()
