"""Cloudinary: upload the source once, then fetch on-the-fly transformations.

Credentials come from the CLOUDINARY_URL environment variable
(cloudinary://<api_key>:<api_secret>@<cloud_name>), never from config files.
Set `public_id_map` in the config to reuse assets that are already uploaded.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from .base import USER_AGENT, Provider, ProviderError, download


def _credentials() -> tuple[str, str, str]:
    url = os.environ.get("CLOUDINARY_URL", "")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "cloudinary" or not (parsed.username and parsed.password and parsed.hostname):
        raise ProviderError("set CLOUDINARY_URL=cloudinary://<api_key>:<api_secret>@<cloud_name>")
    return parsed.hostname, parsed.username, parsed.password


class Cloudinary(Provider):
    """Options:
    cloud_name       delivery cloud (defaults to the one in CLOUDINARY_URL)
    video_codec      vc_ value, e.g. h264, h265, vp9, auto (default h264)
    bitrate_mode     "vbr" (br_ is a ceiling) or "constant" (default vbr)
    quality          optional q_ value, e.g. auto, auto:best
    extra            optional extra transformation string appended to the chain
    public_id_map    {source_id: public_id} for assets already uploaded
    folder           upload folder (default vqbench)
    """

    def __init__(self, name, **options):
        super().__init__(name, **options)
        self._uploaded: dict[str, str] = dict(options.get("public_id_map") or {})

    def _upload(self, source: Path, source_id: str) -> str:
        cloud, key, secret = _credentials()
        public_id = f"{self.options.get('folder', 'vqbench')}/{source_id}"
        params = {"public_id": public_id, "overwrite": "true", "timestamp": str(int(time.time()))}
        to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params))
        params["signature"] = hashlib.sha1((to_sign + secret).encode()).hexdigest()
        params["api_key"] = key

        boundary = uuid.uuid4().hex
        parts = []
        for k, v in params.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{source.name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n".encode()
            + source.read_bytes() + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(
            f"https://api.cloudinary.com/v1_1/{cloud}/video/upload",
            data=b"".join(parts),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": USER_AGENT},
        )
        # Files over 100 MB need chunked upload; keep benchmark clips short.
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                return json.loads(resp.read())["public_id"]
        except urllib.error.HTTPError as err:
            raise ProviderError(f"Cloudinary upload failed: HTTP {err.code} {err.read()[:500]!r}") from err

    def transformation(self, bitrate_kbps: int) -> str:
        steps = [f"vc_{self.options.get('video_codec', 'h264')}"]
        br = f"br_{bitrate_kbps}k"
        if self.options.get("bitrate_mode", "vbr") == "constant":
            br += ":constant"
        steps.append(br)
        if self.options.get("quality"):
            steps.append(f"q_{self.options['quality']}")
        chain = ",".join(steps)
        if self.options.get("extra"):
            chain += "/" + self.options["extra"]
        return chain

    def delivery_url(self, public_id: str, bitrate_kbps: int) -> str:
        cloud = self.options.get("cloud_name") or _credentials()[0]
        ext = "webm" if self.options.get("video_codec") == "vp9" else "mp4"
        return f"https://res.cloudinary.com/{cloud}/video/upload/{self.transformation(bitrate_kbps)}/{public_id}.{ext}"

    def encode(self, source, source_id, bitrate_kbps, workdir):
        if source_id not in self._uploaded:
            self._uploaded[source_id] = self._upload(source, source_id)
        url = self.delivery_url(self._uploaded[source_id], bitrate_kbps)
        ext = url.rsplit(".", 1)[-1]
        out = download(url, workdir / f"{self.name}_{source_id}_{bitrate_kbps}k.{ext}")
        return out, {"delivery_url": url, "public_id": self._uploaded[source_id]}
