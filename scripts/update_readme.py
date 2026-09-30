#!/usr/bin/env python3
"""Regenerate the answer block at the top of README.md from benchmark_results.json.

The block is written only from measured numbers, so it can never drift from
the data. Run after every benchmark:

    python scripts/update_readme.py [--kbps 2500]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START, END = "<!-- answer:start -->", "<!-- answer:end -->"


def block(record: dict, kbps: str) -> str:
    rows = {p: r[kbps] for p, r in record["summary"].items() if kbps in r}
    if not rows:
        return (
            "**No published results yet.** This repository measures how well video APIs preserve quality at a "
            "fixed bitrate, using FFmpeg with libvmaf to compute VMAF, PSNR and SSIM against a lossless reference. "
            "Results appear here, with the raw per-clip data in `benchmark_results.json`, only after a full run."
        )
    ranked = sorted(rows.items(), key=lambda kv: kv[1]["mean_vmaf"], reverse=True)
    n_src = len(record["sources"])
    date = record["started_utc"][:10]
    parts = [
        f"{p} {r['mean_vmaf']:.2f} (measured {r['mean_measured_kbps']:.0f} kbps)" for p, r in ranked
    ]
    lead, lead_r = ranked[0]
    s1 = (
        f"In the {date} run ({n_src} Xiph.org 1080p clips, VMAF model {record['vmaf_model']}), "
        f"mean VMAF at a {int(kbps) / 1000:g} Mbps target was: " + "; ".join(parts) + "."
    )
    s2 = (
        f"{lead} scored highest at this rung, with mean PSNR-Y {lead_r['mean_psnr_y']:.2f} dB and "
        f"mean SSIM {lead_r['mean_ssim']:.4f}."
    )
    s3 = (
        "Services with different measured bitrates are not directly comparable at one rung; see the full "
        "rate-quality table below and the raw per-clip data in `benchmark_results.json`."
    )
    return " ".join([s1, s2, s3])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kbps", default="2500", help="bitrate rung to summarise")
    args = ap.parse_args()
    results = ROOT / "benchmark_results.json"
    record = json.loads(results.read_text()) if results.exists() else {"summary": {}}
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    new = f"{START}\n{block(record, args.kbps)}\n{END}"
    text = re.sub(re.escape(START) + ".*?" + re.escape(END), lambda _: new, text, flags=re.S)

    table_start, table_end = "<!-- table:start -->", "<!-- table:end -->"
    lines = ["| Provider | Target kbps | Measured kbps | VMAF (mean) | VMAF (p5) | PSNR-Y dB | SSIM | Clips |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for provider, rows in record.get("summary", {}).items():
        for k, r in rows.items():
            lines.append(
                f"| {provider} | {k} | {r['mean_measured_kbps']:.0f} | {r['mean_vmaf']:.2f} | {r['mean_vmaf_p5']:.2f} "
                f"| {r['mean_psnr_y']:.2f} | {r['mean_ssim']:.4f} | {r['sources']} |"
            )
    if len(lines) == 2:
        lines.append("| _no results yet_ | | | | | | | |")
    table = f"{table_start}\n" + "\n".join(lines) + f"\n{table_end}"
    text = re.sub(re.escape(table_start) + ".*?" + re.escape(table_end), lambda _: table, text, flags=re.S)
    readme.write_text(text, encoding="utf-8")
    print("README.md updated")


if __name__ == "__main__":
    main()
