#!/usr/bin/env python3
"""Download and profile Connecticut Energy Storage Solutions public datasets."""

from __future__ import annotations

import csv
import gzip
import hashlib
import os
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"
PROFILE_PATH = BASE_DIR / "DATASET.md"

DATASETS = [
    {
        "name": "ESS Aggregate Loadshape",
        "dataset_id": "jjyf-pk6e",
        "filename": "ess_aggregate_loadshape.csv",
        "url": "https://data.ct.gov/api/v3/views/jjyf-pk6e/export.csv?accessType=DOWNLOAD",
        "landing": "https://catalog.data.gov/dataset/energy-storage-solutions-ess-aggregate-loadshape",
        "official_note": "15 分钟聚合储能功率时间序列；正值表示充电，负值表示向本地负荷或电网放电。",
    },
    {
        "name": "ESS Enrollment",
        "dataset_id": "uy2c-bbdw",
        "filename": "ess_enrollment.csv",
        "url": "https://data.ct.gov/api/v3/views/uy2c-bbdw/export.csv?accessType=DOWNLOAD",
        "landing": "https://catalog.data.gov/dataset/energy-storage-solutions-ess-enrollment",
        "official_note": "匿名化的 ESS 已批准项目清单，包含系统规模、成本、参与承包商等申请信息。",
    },
]

DATE_FORMATS = [
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%m/%d/%Y %I:%M:%S %p",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y",
]

def download(url: str, path: Path) -> None:
    req = Request(url, headers={"User-Agent": "paper-reproductions/1.0"})
    with urlopen(req, timeout=180) as r, open(path, "wb") as f:
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def parse_datetime(value: str):
    s = value.strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return open(path, "r", encoding="utf-8-sig", newline="")

def maybe_compress(path: Path) -> Path:
    # GitHub blocks individual files >=100 MiB. Leave normal-sized CSVs uncompressed
    # for convenience, but transparently gzip very large snapshots.
    if path.stat().st_size < 90 * 1024 * 1024:
        return path
    gz_path = path.with_suffix(path.suffix + ".gz")
    with open(path, "rb") as src, gzip.open(gz_path, "wb", compresslevel=9) as dst:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            dst.write(chunk)
    path.unlink()
    return gz_path

def profile_csv(path: Path):
    with open_text(path) as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        missing = {h: 0 for h in headers}
        samples = {h: [] for h in headers}
        temporal = {
            h: {"min": None, "max": None}
            for h in headers
            if any(k in h.lower() for k in ("date", "time", "timestamp"))
        }
        rows = 0
        for row in reader:
            rows += 1
            for h in headers:
                v = (row.get(h) or "").strip()
                if not v:
                    missing[h] += 1
                    continue
                if len(samples[h]) < 3:
                    samples[h].append(v)
                if h in temporal:
                    dt = parse_datetime(v)
                    if dt is not None:
                        if temporal[h]["min"] is None or dt < temporal[h]["min"]:
                            temporal[h]["min"] = dt
                        if temporal[h]["max"] is None or dt > temporal[h]["max"]:
                            temporal[h]["max"] = dt
    return {
        "rows": rows,
        "headers": headers,
        "missing": missing,
        "samples": samples,
        "temporal": temporal,
    }

def fmt_dt(dt):
    return dt.isoformat(sep=" ") if dt else "未能自动解析"

def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for ds in DATASETS:
        target = RAW_DIR / ds["filename"]
        print(f"Downloading {ds['name']} -> {target}")
        download(ds["url"], target)
        stored = maybe_compress(target)
        info = profile_csv(stored)
        downloaded.append((ds, stored, info))

    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Connecticut ESS VPP 数据说明",
        "",
        f"- 本次下载时间（UTC）：`{now}`",
        "- 数据来源：Connecticut Open Data / Data.gov 官方公开数据。",
        "- 说明：官方会持续对遥测历史数据做质量控制并可能修订，因此本目录应视为固定快照。",
        "",
    ]

    for ds, path, info in downloaded:
        rel = path.relative_to(BASE_DIR)
        lines += [
            f"## {ds['name']}",
            "",
            f"- 官方数据集 ID：`{ds['dataset_id']}`",
            f"- 本地文件：`{rel.as_posix()}`",
            f"- 官方页面：{ds['landing']}",
            f"- 官方 CSV：{ds['url']}",
            f"- 官方说明：{ds['official_note']}",
            f"- 数据行数（不含表头）：**{info['rows']:,}**",
            f"- 字段数：**{len(info['headers'])}**",
            f"- 文件大小：**{path.stat().st_size / 1024 / 1024:.2f} MiB**",
            f"- SHA256：`{sha256(path)}`",
            "",
        ]

        temporal_lines = []
        for h, r in info["temporal"].items():
            if r["min"] is not None or r["max"] is not None:
                temporal_lines.append(
                    f"- `{h}`：{fmt_dt(r['min'])} ～ {fmt_dt(r['max'])}"
                )
        if temporal_lines:
            lines += ["### 可识别时间范围", ""] + temporal_lines + [""]

        lines += [
            "### 字段概览",
            "",
            "| 字段 | 缺失数 | 缺失率 | 示例值 |",
            "|---|---:|---:|---|",
        ]
        for h in info["headers"]:
            miss = info["missing"][h]
            rate = (miss / info["rows"] * 100) if info["rows"] else 0.0
            sample = " / ".join(info["samples"][h]).replace("|", "\\|")
            lines.append(f"| `{h}` | {miss:,} | {rate:.2f}% | {sample} |")
        lines += [""]

    lines += [
        "## 使用注意",
        "",
        "1. **聚合负荷曲线不是单户 Powerwall 数据。** 它是 ESS VPP 内储能资源的聚合功率表现，不能直接反推出单个家庭的 SOC 或控制策略。",
        "2. **功率正负号按官方定义解释。** 正值为充电，负值为向本地负荷或电网放电。",
        "3. **Enrollment 是匿名化项目清单。** 不应假设它能与聚合曲线逐户一一关联，除非后续官方文档明确给出连接键。",
        "4. **历史数据可能被回溯修订。** 论文实验应固定使用本目录快照并在实验记录中引用 SHA256。",
        "5. **适合的论文问题**包括 VPP 可调容量评估、聚合功率预测、响应可靠性、容量承诺偏差、灵活性区间/概率建模，以及与合成微观储能群的交叉验证。",
        "",
    ]

    PROFILE_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {PROFILE_PATH}")

if __name__ == "__main__":
    main()
