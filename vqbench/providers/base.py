"""Provider interface and shared HTTP helpers."""
from __future__ import annotations

import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path

USER_AGENT = "video-quality-benchmark-tool/1.0"


class ProviderError(RuntimeError):
    pass


class Provider(ABC):
    """Produces an encoded rendition of a source clip at a target bitrate."""

    name: str

    def __init__(self, name: str, **options):
        self.name = name
        self.options = options

    @abstractmethod
    def encode(self, source: Path, source_id: str, bitrate_kbps: int, workdir: Path) -> tuple[Path, dict]:
        """Return (path to the rendition on disk, metadata such as the delivery URL)."""

    def describe(self) -> dict:
        """Settings recorded in results so every run is reproducible."""
        return {"provider": self.name, "type": type(self).__name__, **self.options}


def download(url: str, dest: Path, headers: dict | None = None, attempts: int = 30, wait: float = 10.0) -> Path:
    """Download `url`, retrying while a service is still transcoding on the fly.

    Many media APIs answer 423/202/404 until a derived rendition is ready.
    """
    retry_codes = {202, 404, 420, 423, 429, 500, 502, 503, 504}
    last = None
    for _ in range(attempts):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                if resp.status == 202:
                    last = "202 Accepted (still processing)"
                    time.sleep(wait)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "wb") as fh:
                    while chunk := resp.read(1 << 20):
                        fh.write(chunk)
                return dest
        except urllib.error.HTTPError as err:
            last = f"HTTP {err.code}: {err.headers.get('X-Cld-Error', '') or err.reason}"
            if err.code not in retry_codes:
                break
            time.sleep(wait)
        except urllib.error.URLError as err:
            last = str(err.reason)
            time.sleep(wait)
    raise ProviderError(f"download failed for {url}: {last}")
