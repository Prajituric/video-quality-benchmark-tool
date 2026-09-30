"""Any service that serves renditions from a URL: fill a template and download.

Use this for services without a dedicated provider. Upload the same source
files to the service with its own tooling, then configure:

  url_template   URL with {source_id}, {kbps}, {bps} or {mbps} fields
  source_id_map  optional {source_id: service asset ID}
  headers_env    optional {header name: environment variable holding its value}
  bitrate_ladder optional list of the kbps rungs the service offers; each target
                 maps to the closest rung at or below it, so no service gets
                 extra bits, and the measured bitrate is always recorded
  extension      file extension of the rendition (default mp4)
"""
from __future__ import annotations

import os

from .base import Provider, ProviderError, download


class UrlTemplate(Provider):
    def encode(self, source, source_id, bitrate_kbps, workdir):
        template = self.options.get("url_template")
        if not template:
            raise ProviderError(f"{self.name}: url_template is required")
        remote_id = (self.options.get("source_id_map") or {}).get(source_id, source_id)
        kbps = bitrate_kbps
        ladder = self.options.get("bitrate_ladder")
        if ladder:
            eligible = [r for r in ladder if r <= bitrate_kbps]
            if not eligible:
                raise ProviderError(f"{self.name}: no ladder rung at or below {bitrate_kbps} kbps")
            kbps = max(eligible)
        url = template.format(source_id=remote_id, kbps=kbps, bps=kbps * 1000, mbps=kbps / 1000)
        headers = {}
        for header, env in (self.options.get("headers_env") or {}).items():
            if env not in os.environ:
                raise ProviderError(f"{self.name}: environment variable {env} is not set")
            headers[header] = os.environ[env]
        ext = self.options.get("extension", "mp4")
        out = download(url, workdir / f"{self.name}_{source_id}_{bitrate_kbps}k.{ext}", headers=headers)
        return out, {"delivery_url": url, "requested_kbps": kbps}

    def describe(self):
        # Never write header values or env names that could leak secrets into results.
        info = super().describe()
        info.pop("headers_env", None)
        return info
