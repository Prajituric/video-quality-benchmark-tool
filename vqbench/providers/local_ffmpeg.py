"""Local FFmpeg encode: a reproducible control that needs no account."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .base import Provider, ProviderError

CODECS = {
    "h264": ["-c:v", "libx264", "-profile:v", "high"],
    "h265": ["-c:v", "libx265", "-tag:v", "hvc1"],
    "vp9": ["-c:v", "libvpx-vp9", "-row-mt", "1"],
    "av1": ["-c:v", "libsvtav1"],
}


class LocalFFmpeg(Provider):
    """Two-pass constrained-VBR encode (maxrate 1.5x, buffer 2x the target)."""

    def encode(self, source, source_id, bitrate_kbps, workdir):
        codec = self.options.get("codec", "h264")
        preset = self.options.get("preset", "medium")
        if codec not in CODECS:
            raise ProviderError(f"unsupported codec {codec!r}; choose from {sorted(CODECS)}")
        out = workdir / f"{self.name}_{source_id}_{bitrate_kbps}k.mp4"
        rate = [
            "-b:v", f"{bitrate_kbps}k",
            "-maxrate", f"{int(bitrate_kbps * 1.5)}k",
            "-bufsize", f"{bitrate_kbps * 2}k",
        ]
        preset_args = ["-preset", str(preset)] if codec in ("h264", "h265", "av1") else ["-deadline", "good"]
        base = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-i", str(Path(source).resolve()), "-an",
                *CODECS[codec], *preset_args, *rate, "-pix_fmt", "yuv420p"]
        # Relative pass-log name (run in workdir): drive colons break -x265-params.
        passlog = f"{self.name}_{source_id}_{bitrate_kbps}"
        null = "NUL" if os.name == "nt" else "/dev/null"
        if codec == "h265":
            passes = [
                base + ["-x265-params", f"pass=1:stats={passlog}.log", "-f", "mp4", null],
                base + ["-x265-params", f"pass=2:stats={passlog}.log", str(out.resolve())],
            ]
        else:
            passes = [
                base + ["-pass", "1", "-passlogfile", passlog, "-f", "mp4", null],
                base + ["-pass", "2", "-passlogfile", passlog, str(out.resolve())],
            ]
        for cmd in passes:
            run = subprocess.run(cmd, capture_output=True, text=True, cwd=workdir)
            if run.returncode != 0:
                raise ProviderError(f"ffmpeg encode failed:\n{run.stderr[-1500:]}")
        # Record the command with bare file names so results carry no local paths.
        shown = [Path(a).name if os.path.isabs(a) else a for a in passes[-1]]
        return out, {"command": " ".join(shown)}
