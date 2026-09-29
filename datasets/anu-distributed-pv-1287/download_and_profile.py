#!/usr/bin/env python3
"""Download ANU's 1,287-site distributed-PV dataset from the official Zenodo record.

The dataset's bespoke research-use terms prohibit redistribution, so downloaded
files are stored under raw/ and must remain untracked by Git.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import os
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"
LOCAL_PROFILE = BASE_DIR / "DATASET.local.md"
ZENODO_RECORD = "https://zenodo.org/records/2635887"

FILES = {
    "data.zip": {
        "md5": "281aa841f57217fe316ec225470b18b8",
        "required": True,
    },
    "license and metadata.txt": {
        "md5": "5d772b6504c17f6bdb67526dc60d15d9",
        "required": True,
    },
}

def official_url(name: str) -> str:
    return f"{ZENODO_RECORD}/files/{quote(name)}?download=1"

def md5sum(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def download(name: str, path: Path) -> None:
    req = Request(
        official_url(name),
        headers={"User-Agent": "paper-reproductions/anu-distributed-pv-1287"},
    )
    temp = path.with_suffix(path.suffix + ".part")
    with urlopen(req, timeout=300) as r, temp.open("wb") as f:
        total = r.headers.get("Content-Length")
        total = int(total) if total and total.isdigit() else None
        done = 0
        while True:
            chunk = r.read(4 * 1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"  {name}: {done / 1024 / 1024:.1f}/{total / 1024 / 1024:.1f} MiB", end="\r")
    temp.replace(path)
    print(f"  {name}: downloaded {path.stat().st_size / 1024 / 1024:.1f} MiB")

def ensure_file(name: str, expected_md5: str) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / name
    if path.exists() and md5sum(path) == expected_md5:
        print(f"{name}: already present and checksum OK")
        return path
    if path.exists():
        print(f"{name}: checksum mismatch, downloading again")
        path.unlink()
    download(name, path)
    actual = md5sum(path)
    if actual != expected_md5:
        raise RuntimeError(f"MD5 mismatch for {name}: expected {expected_md5}, got {actual}")
    print(f"{name}: MD5 OK ({actual})")
    return path

def fmt_bytes(n: int) -> str:
    units = ["B", "KiB", "MiB", "GiB"]
    x = float(n)
    for unit in units:
        if x < 1024 or unit == units[-1]:
            return f"{x:.2f} {unit}"
        x /= 1024
    return f"{n} B"

def top_level(path: str) -> str:
    parts = [p for p in path.split("/") if p]
    return parts[0] if len(parts) > 1 else "(root)"

def sample_text_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int = 8192) -> str:
    try:
        with zf.open(info) as f:
            data = f.read(limit)
        return data.decode("utf-8-sig", errors="replace")
    except Exception:
        return ""

def guess_delimiter(text: str) -> str | None:
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        return dialect.delimiter
    except Exception:
        return None

def profile_zip(zip_path: Path) -> list[str]:
    lines: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        total_uncompressed = sum(i.file_size for i in infos)
        by_group: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "bytes": 0})
        suffix_counts: dict[str, int] = defaultdict(int)

        for info in infos:
            group = top_level(info.filename)
            by_group[group]["count"] += 1
            by_group[group]["bytes"] += info.file_size
            suffix = Path(info.filename).suffix.lower() or "(no suffix)"
            suffix_counts[suffix] += 1

        lines += [
            "## data.zip 结构摘要",
            "",
            f"- ZIP 文件大小：**{fmt_bytes(zip_path.stat().st_size)}**",
            f"- ZIP MD5：`{md5sum(zip_path)}`",
            f"- 压缩包内文件数：**{len(infos):,}**",
            f"- 解压后总大小：**{fmt_bytes(total_uncompressed)}**",
            "",
            "### 顶层目录 / 文件组",
            "",
            "| 组 | 文件数 | 解压后大小 |",
            "|---|---:|---:|",
        ]
        for group, stat in sorted(by_group.items(), key=lambda kv: (-kv[1]["bytes"], kv[0])):
            lines.append(f"| `{group}` | {stat['count']:,} | {fmt_bytes(stat['bytes'])} |")

        lines += ["", "### 文件类型", "", "| 后缀 | 文件数 |", "|---|---:|"]
        for suffix, count in sorted(suffix_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"| `{suffix}` | {count:,} |")

        # Show archive members compactly. Full list if manageable, otherwise representative samples.
        lines += ["", "### 文件清单", ""]
        if len(infos) <= 250:
            for info in infos:
                lines.append(f"- `{info.filename}` — {fmt_bytes(info.file_size)}")
        else:
            for info in sorted(infos, key=lambda x: x.filename)[:200]:
                lines.append(f"- `{info.filename}` — {fmt_bytes(info.file_size)}")
            lines.append(f"- ……其余 {len(infos) - 200:,} 个文件省略")

        # Inspect small tabular/text members for schema only; do not reproduce raw rows.
        candidates = [
            i for i in infos
            if Path(i.filename).suffix.lower() in {".csv", ".txt", ".tsv"}
            and i.file_size <= 20 * 1024 * 1024
        ][:40]

        if candidates:
            lines += ["", "### 可解析文本 / 表格文件概览", ""]
            for info in candidates:
                text = sample_text_member(zf, info)
                first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
                delim = guess_delimiter(text)
                if delim and first_line:
                    try:
                        header = next(csv.reader([first_line], delimiter=delim))
                        header = [h.strip() for h in header]
                        header_text = ", ".join(f"`{h}`" for h in header[:30])
                        if len(header) > 30:
                            header_text += ", …"
                    except Exception:
                        header_text = "未能自动解析"
                else:
                    header_text = "文本文件 / 未能自动判断分隔符"

                lines += [
                    f"#### `{info.filename}`",
                    "",
                    f"- 大小：{fmt_bytes(info.file_size)}",
                    f"- 首行字段：{header_text}",
                    "",
                ]

    return lines

def write_profile(zip_path: Path) -> None:
    lines = [
        "# ANU 1287 户分布式光伏数据：本地结构摘要",
        "",
        "> 本文件由 `download_and_profile.py` 从研究者本人下载的官方数据生成；不包含原始测量值，不能替代官方数据下载。",
        "",
        "## 官方数据概况",
        "",
        "- 站点数量：1,287 个居民光伏系统",
        "- 主要地区：Canberra、Perth、Adelaide",
        "- 时间范围：2016-09 ～ 2017-03",
        "- 时间分辨率：10 分钟",
        "- 数据类型：真实逆变器功率测量 + 站点元数据",
        "- 版本：raw、quality-controlled (QC)、tuned",
        "- DOI：10.25911/5ca6a0640869a",
        "",
    ]
    lines += profile_zip(zip_path)
    lines += [
        "",
        "## 使用提醒",
        "",
        "1. 原始数据采用自定义科研使用条款，不应重新上传到 GitHub 或其他镜像。",
        "2. 论文中应按官方说明引用 Bright et al. (2019) 数据论文。",
        "3. 使用 QC / tuned 数据时，还应补充引用官方要求的质量控制和 tuning 方法论文。",
        "4. 建议研究代码只记录数据路径、筛选规则和处理脚本，不把原始数据打包进 release。",
        "",
    ]
    LOCAL_PROFILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {LOCAL_PROFILE}")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-profile", action="store_true", help="download only; do not scan data.zip")
    args = parser.parse_args()

    print("ANU 1287-site PV dataset")
    print(f"Official record: {ZENODO_RECORD}")
    print("The original data must not be redistributed. Downloading from the official source only.")

    paths = {}
    for name, meta in FILES.items():
        paths[name] = ensure_file(name, meta["md5"])

    if not args.no_profile:
        write_profile(paths["data.zip"])

if __name__ == "__main__":
    main()
