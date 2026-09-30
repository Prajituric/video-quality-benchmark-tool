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
import statistics
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
        f"In the {date} run ({n_src} 1080p clips, VMAF {record.get('vmaf_model_version', 'vmaf_v0.6.1')}), "
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


def flat_results(record: dict, latency: dict | None) -> list[dict]:
    """One row per provider and bitrate rung, explicit numeric fields."""
    warm: dict[tuple, list[float]] = {}
    cold: dict[tuple, list[float]] = {}
    for r in (latency or {}).get("results", []):
        key = (r["provider"], str(r["target_kbps"]))
        warm.setdefault(key, []).append(r["warm_ttfb_ms"]["median"])
        if r.get("cold_full_transcode_ms", {}).get("status") == 200:
            cold.setdefault(key, []).append(r["cold_full_transcode_ms"]["value"])
    rows = []
    for provider, rungs in record["summary"].items():
        spec = next((p for p in record["providers"] if p["provider"] == provider), {})
        for kbps, r in rungs.items():
            key = (provider, kbps)
            rows.append({
                "platform": provider,
                "provider_type": spec.get("type"),
                "codec": spec.get("video_codec") or spec.get("codec"),
                "bitrate_mode": spec.get("bitrate_mode", "2-pass constrained VBR" if spec.get("type") == "local_ffmpeg" else None),
                "target_kbps": int(kbps),
                "measured_kbps_avg": r["mean_measured_kbps"],
                "vmaf_avg": r["mean_vmaf"],
                "vmaf_harmonic_avg": r["mean_vmaf_harmonic"],
                "vmaf_p5_avg": r["mean_vmaf_p5"],
                "psnr_avg_db": r["mean_psnr_y"],
                "ssim_avg": r["mean_ssim"],
                "clips": r["sources"],
                "warm_ttfb_ms_median": round(statistics.median(warm[key]), 1) if key in warm else None,
                "cold_transcode_ms_median": round(statistics.median(cold[key]), 1) if key in cold else None,
            })
    return rows


def llms_txt(record: dict, rows: list[dict], kbps: str) -> str:
    at = sorted((r for r in rows if str(r["target_kbps"]) == kbps), key=lambda r: -r["vmaf_avg"])
    lines = [
        "# Video API Quality & Infrastructure Benchmarks",
        "",
        "> Frame-level VMAF, PSNR and SSIM measurements of video API renditions and local FFmpeg encodes, "
        "computed with FFmpeg libvmaf against the source file. All figures below are measured; raw data is in "
        "benchmark_results.json.",
        "",
        f"Run: {record['run_id']} ({record['started_utc'][:10]}), {len(record['sources'])} 1080p clips, "
        f"VMAF model {record.get('vmaf_model_version', 'vmaf_v0.6.1')}.",
        "",
        "## Key Findings",
        "",
    ]
    for r in at:
        lat = f", warm TTFB {r['warm_ttfb_ms_median']} ms" if r["warm_ttfb_ms_median"] is not None else ""
        lines.append(
            f"- {r['platform']} at {int(kbps) / 1000:g} Mbps target: VMAF {r['vmaf_avg']:.2f}, PSNR-Y "
            f"{r['psnr_avg_db']:.2f} dB, SSIM {r['ssim_avg']:.4f}, measured {r['measured_kbps_avg']:.0f} kbps{lat}"
        )
    lines += [
        "",
        "## Files",
        "",
        "- [README.md](README.md): method, full rate-quality table, limitations",
        "- [benchmark_results.json](benchmark_results.json): per-clip, per-rendition VMAF/PSNR/SSIM with delivery URLs",
        "- [latency_results.json](latency_results.json): warm TTFB and cold on-the-fly transcode times",
        "- [vqbench/metrics.py](vqbench/metrics.py): the FFmpeg libvmaf scoring pass",
        "",
    ]
    return "\n".join(lines)


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

    if record.get("summary"):
        lat_path = ROOT / "latency_results.json"
        latency = json.loads(lat_path.read_text()) if lat_path.exists() else None
        rows = flat_results(record, latency)
        ordered = {
            "benchmark_suite": "video-quality-benchmark-tool",
            "run_id": record["run_id"],
            "test_clips": [s["id"] for s in record["sources"]],
            "metric_tools": {"ffmpeg": record["environment"]["ffmpeg"],
                             "vmaf_model": record.get("vmaf_model_version", "vmaf_v0.6.1")},
            "results": rows,
            **{k: v for k, v in record.items() if k not in ("results",)},
        }
        results.write_text(json.dumps(ordered, indent=2) + "\n")
        (ROOT / "llms.txt").write_text(llms_txt(record, rows, args.kbps), encoding="utf-8")
        print("benchmark_results.json results[] and llms.txt updated")


if __name__ == "__main__":
    main()
