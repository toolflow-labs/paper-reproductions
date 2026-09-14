from __future__ import annotations

import argparse
from pathlib import Path

import requests
from tqdm import tqdm


ZENODO_BASE = "https://zenodo.org/records/5500457/files"
SPS_FILES = [
    "demand_train_set4.csv",
    "demand_test_set4.csv",
    "pv_train_set4.csv",
    "pv_test_set4.csv",
    "weather_train_set4.csv",
]


def download(url: str, path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        print(f"exists: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        with open(path, "wb") as f, tqdm(total=total, unit="B", unit_scale=True, desc=path.name) as bar:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    bar.update(len(chunk))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["sps-uk", "mlvs-pt"], default="sps-uk")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    if args.dataset == "sps-uk":
        raw = root / "data" / "raw" / "sps-uk"
        for name in SPS_FILES:
            download(f"{ZENODO_BASE}/{name}?download=1", raw / name)
        print(f"Downloaded SPS-UK public files to {raw}")
    else:
        raw = root / "data" / "raw" / "mlvs_pt" / "MLVS-PT.parquet"
        print("MLVS-PT has no stable raw-data URL specified in the paper.")
        print(f"Place the parquet file at: {raw}")


if __name__ == "__main__":
    main()
