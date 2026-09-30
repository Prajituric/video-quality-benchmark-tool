"""Objective quality metrics (VMAF, PSNR, SSIM) via FFmpeg + libvmaf.

A single FFmpeg pass computes all three metrics per frame. The distorted
stream is scaled to the reference resolution, resampled to the reference
frame rate and converted to the same pixel format so every provider is
scored against the reference on identical terms.
"""
from __future__ import annotations

import json
import os
import shutil
import statistics
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

VMAF_MODELS = {
    "hd": "vmaf_v0.6.1",        # 1080p viewing at 3H
    "4k": "vmaf_4k_v0.6.1",     # 4K viewing at 1.5H
    "phone": "vmaf_v0.6.1",     # combined with the phone flag below
}


class MetricsError(RuntimeError):
    pass


@dataclass
class StreamInfo:
    width: int
    height: int
    fps: float
    duration: float
    bitrate_kbps: float
    codec: str
    pix_fmt: str
    frames: int | None


@dataclass
class MetricSummary:
    mean: float
    harmonic_mean: float
    min: float
    p1: float
    p5: float
    max: float


@dataclass
class QualityResult:
    vmaf: MetricSummary
    psnr_y: MetricSummary
    ssim: MetricSummary
    frames_compared: int
    vmaf_model: str
    ffmpeg_version: str


def require_ffmpeg() -> str:
    """Return the FFmpeg version line, failing if libvmaf is unavailable."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise MetricsError("ffmpeg/ffprobe not found on PATH")
    filters = subprocess.run(
        ["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True, check=True
    ).stdout
    if " libvmaf " not in filters:
        raise MetricsError("this FFmpeg build has no libvmaf filter (build with --enable-libvmaf)")
    return subprocess.run(
        ["ffmpeg", "-version"], capture_output=True, text=True, check=True
    ).stdout.splitlines()[0]


def probe(path: str | Path) -> StreamInfo:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate,codec_name,pix_fmt,nb_frames,bit_rate:format=duration,bit_rate,size",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise MetricsError(f"ffprobe failed on {path}: {out.stderr.strip()}")
    data = json.loads(out.stdout)
    s, f = data["streams"][0], data["format"]
    num, den = (int(x) for x in s["avg_frame_rate"].split("/"))
    duration = float(f.get("duration", 0))
    # Prefer the video stream bitrate; fall back to container size / duration.
    br = s.get("bit_rate") or f.get("bit_rate")
    if br is None and duration:
        br = int(f["size"]) * 8 / duration
    return StreamInfo(
        width=int(s["width"]),
        height=int(s["height"]),
        fps=num / den if den else 0.0,
        duration=duration,
        bitrate_kbps=round(float(br) / 1000, 1) if br else 0.0,
        codec=s["codec_name"],
        pix_fmt=s.get("pix_fmt", ""),
        frames=int(s["nb_frames"]) if s.get("nb_frames", "").isdigit() else None,
    )


def _summary(values: list[float]) -> MetricSummary:
    if not values:
        raise MetricsError("no per-frame values in libvmaf log")
    ordered = sorted(values)

    def pct(p: float) -> float:
        return ordered[min(len(ordered) - 1, int(p / 100 * len(ordered)))]

    # Harmonic mean penalises quality drops; shift by 1 so zeros are defined.
    hmean = len(values) / sum(1.0 / (v + 1.0) for v in values) - 1.0
    return MetricSummary(
        mean=round(statistics.fmean(values), 4),
        harmonic_mean=round(hmean, 4),
        min=round(ordered[0], 4),
        p1=round(pct(1), 4),
        p5=round(pct(5), 4),
        max=round(ordered[-1], 4),
    )


def measure(
    reference: str | Path,
    distorted: str | Path,
    model: str = "hd",
    threads: int | None = None,
    subsample: int = 1,
) -> QualityResult:
    """Score `distorted` against `reference`; returns VMAF, PSNR-Y and SSIM."""
    version = require_ffmpeg()
    ref = probe(reference)
    threads = threads or os.cpu_count() or 4
    model_version = VMAF_MODELS[model]
    model_opt = f"version={model_version}" + ("\\:enable_transform=true" if model == "phone" else "")

    with tempfile.TemporaryDirectory(prefix="vqbench-") as tmp:
        # Relative log path: Windows drive colons break FFmpeg filter-arg parsing.
        log_name = "vmaf.json"
        graph = (
            f"[0:v]scale={ref.width}:{ref.height}:flags=bicubic,fps={ref.fps},"
            f"format=yuv420p,setpts=PTS-STARTPTS[dist];"
            f"[1:v]fps={ref.fps},format=yuv420p,setpts=PTS-STARTPTS[ref];"
            f"[dist][ref]libvmaf=model={model_opt}"
            f":feature=name=psnr|name=float_ssim"
            f":n_threads={threads}:n_subsample={subsample}"
            f":log_fmt=json:log_path={log_name}"
        )
        cmd = [
            "ffmpeg", "-hide_banner", "-nostdin", "-y",
            "-i", str(Path(distorted).resolve()),
            "-i", str(Path(reference).resolve()),
            "-lavfi", graph, "-f", "null", "-",
        ]
        run = subprocess.run(cmd, capture_output=True, text=True, cwd=tmp)
        log_path = Path(tmp) / log_name
        if run.returncode != 0 or not log_path.exists():
            raise MetricsError(f"ffmpeg libvmaf failed:\n{run.stderr[-2000:]}")
        frames = json.loads(log_path.read_text())["frames"]

    vmaf = [fr["metrics"]["vmaf"] for fr in frames]
    psnr = [fr["metrics"]["psnr_y"] for fr in frames]
    ssim = [fr["metrics"]["float_ssim"] for fr in frames]
    return QualityResult(
        vmaf=_summary(vmaf),
        psnr_y=_summary(psnr),
        ssim=_summary(ssim),
        frames_compared=len(frames),
        vmaf_model=model_version + (" (phone)" if model == "phone" else ""),
        ffmpeg_version=version,
    )


def result_to_dict(result: QualityResult) -> dict:
    return asdict(result)
