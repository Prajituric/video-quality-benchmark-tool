"""Benchmark runner: encode every source at every bitrate on every provider, then score.

    python -m vqbench configs/default.json
    python -m vqbench configs/default.json --providers cloudinary_h264 x264_medium

Writes results/runs/<run_id>.json (full record) and refreshes
benchmark_results.json at the repo root with the newest run.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import statistics
import shutil
import sys
import tempfile
import traceback
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .metrics import VMAF_MODELS, MetricsError, measure, probe, require_ffmpeg
from .providers import ProviderError, build

ROOT = Path(__file__).resolve().parent.parent
BITRATE_TOLERANCE = 0.10  # flag renditions more than 10% above their target


def load_sources(config: dict) -> list[dict]:
    manifest_path = ROOT / "sources" / "manifest.json"
    if not manifest_path.exists():
        sys.exit("sources/manifest.json missing: run `python scripts/prepare_sources.py <config>` first")
    manifest = {m["id"]: m for m in json.loads(manifest_path.read_text())}
    wanted = [s["id"] for s in config["sources"]]
    missing = [w for w in wanted if w not in manifest]
    if missing:
        sys.exit(f"sources not prepared: {missing}")
    return [manifest[w] for w in wanted]


def summarise(measurements: list[dict]) -> dict:
    """Mean of each metric per provider per target bitrate, across all sources."""
    table: dict[str, dict[str, dict]] = {}
    for m in measurements:
        if m.get("error"):
            continue
        cell = table.setdefault(m["provider"], {}).setdefault(str(m["target_kbps"]), {
            "vmaf": [], "vmaf_harmonic": [], "vmaf_p5": [], "psnr_y": [], "ssim": [], "measured_kbps": [],
        })
        cell["vmaf"].append(m["metrics"]["vmaf"]["mean"])
        cell["vmaf_harmonic"].append(m["metrics"]["vmaf"]["harmonic_mean"])
        cell["vmaf_p5"].append(m["metrics"]["vmaf"]["p5"])
        cell["psnr_y"].append(m["metrics"]["psnr_y"]["mean"])
        cell["ssim"].append(m["metrics"]["ssim"]["mean"])
        cell["measured_kbps"].append(m["rendition"]["bitrate_kbps"])
    return {
        provider: {
            kbps: {
                **{f"mean_{k}": round(statistics.fmean(v), 4) for k, v in cell.items()},
                "sources": len(cell["vmaf"]),
            }
            for kbps, cell in sorted(rows.items(), key=lambda kv: int(kv[0]))
        }
        for provider, rows in table.items()
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vqbench", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", type=Path)
    ap.add_argument("--providers", nargs="*", help="subset of provider names from the config")
    ap.add_argument("--keep-renditions", action="store_true", help="keep encoded/downloaded files (path is printed)")
    ap.add_argument("--workdir", type=Path, help="scratch directory for renditions (default: a short system temp dir)")
    ap.add_argument("--no-root-update", action="store_true", help="do not overwrite benchmark_results.json")
    ap.add_argument("--merge", action="store_true",
                    help="keep measurements of providers not run now from the current benchmark_results.json "
                         "(same sources and bitrates required)")
    args = ap.parse_args(argv)

    config_text = args.config.read_text()
    config = json.loads(config_text)
    ffmpeg_version = require_ffmpeg()
    sources = load_sources(config)
    specs = config["providers"]
    names = args.providers or list(specs)
    providers = [build(n, specs[n]) for n in names]

    started = dt.datetime.now(dt.timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    # A short scratch path: encoders' pass logs fail beyond Windows' 260-char limit.
    work = args.workdir or Path(tempfile.mkdtemp(prefix="vqb-"))
    work.mkdir(parents=True, exist_ok=True)

    measurements = []
    for src in sources:
        ref_path = ROOT / src["path"]
        ref_info = probe(ref_path)
        for provider in providers:
            for kbps in config["bitrates_kbps"]:
                label = f"{provider.name} / {src['id']} / {kbps} kbps"
                print(f"[run] {label}", flush=True)
                entry = {"provider": provider.name, "source": src["id"], "target_kbps": kbps}
                try:
                    rendition, meta = provider.encode(ref_path, src["id"], kbps, work)
                    info = probe(rendition)
                    result = measure(ref_path, rendition, model=config.get("vmaf_model", "hd"),
                                     subsample=config.get("vmaf_subsample", 1))
                    entry.update(
                        rendition={**asdict(info), **meta},
                        over_target=info.bitrate_kbps > kbps * (1 + BITRATE_TOLERANCE),
                        metrics={k: v for k, v in asdict(result).items() if k in ("vmaf", "psnr_y", "ssim")},
                        frames_compared=result.frames_compared,
                    )
                    print(f"      VMAF {result.vmaf.mean:.2f}  PSNR-Y {result.psnr_y.mean:.2f} dB  "
                          f"SSIM {result.ssim.mean:.4f}  @ {info.bitrate_kbps} kbps measured", flush=True)
                    if not args.keep_renditions:
                        rendition.unlink(missing_ok=True)
                except (ProviderError, MetricsError) as err:
                    entry["error"] = str(err)
                    print(f"      ERROR {err}", flush=True)
                except Exception:  # keep the run going; record the failure
                    entry["error"] = traceback.format_exc(limit=3)
                    print(f"      ERROR {entry['error']}", flush=True)
                measurements.append(entry)

    provider_specs = [p.describe() for p in providers]
    merged_from = None
    root_file = ROOT / "benchmark_results.json"
    if args.merge and root_file.exists():
        previous = json.loads(root_file.read_text())
        if [s["sha256"] for s in previous["sources"]] != [s["sha256"] for s in sources]                 or previous["bitrates_kbps"] != config["bitrates_kbps"]:
            sys.exit("--merge: previous run used different sources or bitrates")
        ran = {p.name for p in providers}
        measurements = [m for m in previous["measurements"] if m["provider"] not in ran] + measurements
        provider_specs = [p for p in previous["providers"] if p["provider"] not in ran] + provider_specs
        merged_from = previous["run_id"]

    record = {
        "schema": "vqbench/result@1",
        "run_id": run_id,
        "started_utc": started.isoformat(),
        "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tool_version": __version__,
        "environment": {
            "ffmpeg": ffmpeg_version,
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "config_sha256": hashlib.sha256(config_text.encode()).hexdigest(),
        "vmaf_model": config.get("vmaf_model", "hd"),
        "vmaf_model_version": VMAF_MODELS[config.get("vmaf_model", "hd")],
        "description": config.get("description", ""),
        "sources": sources,
        "reference": {"note": "each source file is both the VMAF reference and the input every provider encodes"},
        "merged_from_run": merged_from,
        "providers": provider_specs,
        "bitrates_kbps": config["bitrates_kbps"],
        "summary": summarise(measurements),
        "measurements": measurements,
    }
    runs = ROOT / "results" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    out = runs / f"{run_id}.json"
    out.write_text(json.dumps(record, indent=2) + "\n")
    if not args.no_root_update:
        (ROOT / "benchmark_results.json").write_text(json.dumps(record, indent=2) + "\n")
    if args.keep_renditions:
        print(f"renditions kept in {work}")
    elif not args.workdir:
        shutil.rmtree(work, ignore_errors=True)
    errors = sum(1 for m in measurements if m.get("error"))
    print(f"\nwrote {out.relative_to(ROOT)} ({len(measurements)} measurements, {errors} errors)")
    return 1 if errors == len(measurements) else 0
