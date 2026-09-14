from __future__ import annotations

import argparse
from pathlib import Path

from conformal_mlpf.data import prepare_mlvs_pt, prepare_sps_uk


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["sps-uk", "mlvs-pt"], default="sps-uk")
    parser.add_argument("--weather-override", default=None)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    out = root / "data" / "processed" / f"{args.dataset}.parquet"

    if args.dataset == "sps-uk":
        df = prepare_sps_uk(
            root / "data" / "raw" / "sps-uk",
            out,
            weather_override=args.weather_override,
        )
    else:
        df = prepare_mlvs_pt(
            root / "data" / "raw" / "mlvs_pt" / "MLVS-PT.parquet",
            out,
        )

    print(f"prepared: {out}")
    print(f"rows={len(df):,}  range={df['timestamp'].min()} -> {df['timestamp'].max()}")
    print(df.head())


if __name__ == "__main__":
    main()
