#!/usr/bin/env python3
"""Check UNSW CANVAS upstream resources and optionally try the public data folder.

The CANVAS README historically linked a Google Drive folder containing public
PV demonstration data. As of 2026-09-29 that folder returns 404 to gdown.
This script keeps the original official link documented and makes it easy to
re-check if UNSW restores access later.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"

UPSTREAM_REPO = "https://github.com/UNSW-CEEM/Solar-Curtailment.git"
UPSTREAM_PAGE = "https://github.com/UNSW-CEEM/Solar-Curtailment"
PYPI_PAGE = "https://pypi.org/project/solarcurtailment/2.0.0/"
DATA_FOLDER = "https://drive.google.com/drive/folders/1pQ3h7HCYYzm1rxQpw1sw4qD8-uZYcZ5R?usp=sharing"

def check_url(url: str) -> tuple[bool, str]:
    try:
        req = Request(url, headers={"User-Agent": "paper-reproductions/1.0"})
        with urlopen(req, timeout=30) as r:
            return 200 <= r.status < 400, f"HTTP {r.status}"
    except Exception as e:
        return False, str(e)

def clone_upstream() -> None:
    target = RAW_DIR / "Solar-Curtailment"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if target.exists():
        subprocess.run(["git", "-C", str(target), "pull", "--ff-only"], check=True)
    else:
        subprocess.run(["git", "clone", "--depth", "1", UPSTREAM_REPO, str(target)], check=True)
    print(f"Upstream source available at: {target}")

def try_data() -> int:
    gdown = shutil.which("gdown")
    if not gdown:
        print("gdown is not installed. Install it first: pip install gdown", file=sys.stderr)
        return 2

    target = RAW_DIR / "public-data"
    target.mkdir(parents=True, exist_ok=True)
    cmd = [gdown, "--folder", DATA_FOLDER, "-O", str(target)]
    print("Trying CANVAS README public-data link...")
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        print(
            "\nThe official README data folder is currently unavailable. "
            "This was also verified on 2026-09-29 (HTTP/Drive 404). "
            "Do not substitute an unofficial mirror without checking provenance and permission.",
            file=sys.stderr,
        )
        return proc.returncode

    files = [p for p in target.rglob("*") if p.is_file()]
    print(f"Downloaded {len(files)} files:")
    for p in files:
        print(f"  {p.relative_to(target)} ({p.stat().st_size} bytes)")
    return 0

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clone-upstream", action="store_true")
    parser.add_argument("--try-data", action="store_true")
    args = parser.parse_args()

    for name, url in [
        ("GitHub", UPSTREAM_PAGE),
        ("PyPI", PYPI_PAGE),
    ]:
        ok, detail = check_url(url)
        print(f"{name}: {'OK' if ok else 'FAILED'} — {detail}")

    if args.clone_upstream:
        clone_upstream()
    if args.try_data:
        raise SystemExit(try_data())

if __name__ == "__main__":
    main()
