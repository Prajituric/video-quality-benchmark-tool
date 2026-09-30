#!/usr/bin/env python3
"""Fetch the Xiph.org test clips listed in the config and make lossless mezzanines.

Each clip is streamed from media.xiph.org (only the frames needed are read),
trimmed, and stored as lossless H.264 (qp 0, yuv420p) under sources/. That
mezzanine is both what gets uploaded to each service and the VMAF reference,
so every service starts from bit-identical input.

    python scripts/prepare_sources.py configs/default.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def prepare(src: dict, out_dir: Path) -> dict:
    out = out_dir / f"{src['id']}.mp4"
    if not out.exists():
        cmd = [
            "ffmpeg", "-hide_banner", "-nostdin", "-y",
            "-i", src["url"],
            "-frames:v", str(src.get("frames", 300)),
            "-an", "-c:v", "libx264", "-qp", "0", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            str(out),
        ]
        print(f"[prepare] {src['id']}: {src['url']}", flush=True)
        run = subprocess.run(cmd, capture_output=True, text=True)
        if run.returncode != 0:
            out.unlink(missing_ok=True)
            sys.exit(f"failed to prepare {src['id']}:\n{run.stderr[-1500:]}")
    return {"id": src["id"], "path": out.relative_to(ROOT).as_posix(), "sha256": sha256(out)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config")
    args = ap.parse_args()
    config = json.loads(Path(args.config).read_text())
    out_dir = ROOT / "sources"
    out_dir.mkdir(exist_ok=True)
    manifest = [prepare(s, out_dir) for s in config["sources"]]
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for m in manifest:
        print(f"{m['id']}: {m['path']} sha256={m['sha256'][:16]}...")


if __name__ == "__main__":
    main()
