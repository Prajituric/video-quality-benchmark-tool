#!/usr/bin/env python3
"""Measure delivery latency of the renditions in benchmark_results.json.

For every delivery URL in the latest run:
  * warm: time to first byte (TTFB) over N sequential requests for the
    already-derived rendition, with the CDN cache status header recorded;
  * cold (--cold): one request for a never-before-requested variant (target
    bitrate minus 1 kbps, same settings) timed until the full file arrives,
    which includes on-the-fly transcoding. Retries while the service answers
    "still processing" are included in the time.

Results go to latency_results.json. Latency depends on the client's network
location; the measuring host's public region is not recorded, only its timezone.

    python scripts/measure_latency.py --repeats 5 --cold
"""
from __future__ import annotations

import argparse
import datetime as dt
import http.client
import json
import re
import statistics
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = "video-quality-benchmark-tool/1.0"


def ttfb(url: str) -> tuple[float, int, str]:
    """Return (ms to first response byte, status, cache header) for a GET."""
    u = urllib.parse.urlsplit(url)
    conn = http.client.HTTPSConnection(u.netloc, timeout=120)
    start = time.perf_counter()
    conn.request("GET", u.path + (f"?{u.query}" if u.query else ""), headers={"User-Agent": UA, "Range": "bytes=0-0"})
    resp = conn.getresponse()
    elapsed = (time.perf_counter() - start) * 1000
    cache = resp.getheader("x-cache") or resp.getheader("cf-cache-status") or resp.getheader("age") or ""
    resp.read()
    conn.close()
    return elapsed, resp.status, cache


def full_fetch(url: str, attempts: int = 60, wait: float = 2.0) -> tuple[float, int, int]:
    """Return (ms until the complete body arrived, final status, retries)."""
    start = time.perf_counter()
    for retry in range(attempts):
        u = urllib.parse.urlsplit(url)
        conn = http.client.HTTPSConnection(u.netloc, timeout=600)
        conn.request("GET", u.path, headers={"User-Agent": UA})
        resp = conn.getresponse()
        resp.read()
        conn.close()
        if resp.status == 200:
            return (time.perf_counter() - start) * 1000, resp.status, retry
        if resp.status not in (202, 420, 423):
            return (time.perf_counter() - start) * 1000, resp.status, retry
        time.sleep(wait)
    return (time.perf_counter() - start) * 1000, 0, attempts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--cold", action="store_true", help="also time one uncached variant per URL")
    ap.add_argument("--kbps", type=int, help="only URLs for this target bitrate")
    args = ap.parse_args()

    record = json.loads((ROOT / "benchmark_results.json").read_text())
    rows = []
    for m in record["measurements"]:
        url = (m.get("rendition") or {}).get("delivery_url")
        if not url or (args.kbps and m["target_kbps"] != args.kbps):
            continue
        samples = [ttfb(url) for _ in range(args.repeats)]
        times = [s[0] for s in samples]
        row = {
            "provider": m["provider"],
            "source": m["source"],
            "target_kbps": m["target_kbps"],
            "url": url,
            "warm_ttfb_ms": {
                "median": round(statistics.median(times), 1),
                "min": round(min(times), 1),
                "max": round(max(times), 1),
                "samples": len(times),
            },
            "status": samples[-1][1],
            "cache_header_last": samples[-1][2],
        }
        if args.cold:
            # A bitrate a few kbps under target that no earlier run has requested, so the
            # variant is guaranteed uncached (a fixed offset would be warm on a second run).
            offset = 1 + (int(time.time()) + len(rows)) % 97
            cold_url = re.sub(r"br_(\d+)k", lambda g: f"br_{int(g.group(1)) - offset}k", url, count=1)
            ms, status, retries = full_fetch(cold_url)
            row["cold_full_transcode_ms"] = {"value": round(ms, 1), "status": status, "processing_retries": retries,
                                             "url": cold_url}
        print(f"{row['provider']:<22} {row['source']:<18} {row['target_kbps']:>5}  "
              f"warm TTFB median {row['warm_ttfb_ms']['median']} ms"
              + (f"  cold {row['cold_full_transcode_ms']['value']:.0f} ms" if args.cold else ""), flush=True)
        rows.append(row)

    out = {
        "schema": "vqbench/latency@1",
        "measured_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "client_timezone": time.strftime("%z"),
        "benchmark_run_id": record["run_id"],
        "method": "warm = TTFB of a 1-byte range GET on the derived rendition; cold = full download of a new variant "
                  "(target minus 1-97 kbps, unique per run), including on-the-fly transcoding",
        "results": rows,
    }
    (ROOT / "latency_results.json").write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote latency_results.json ({len(rows)} URLs)")


if __name__ == "__main__":
    main()
