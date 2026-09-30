from .base import Provider, ProviderError
from .cloudinary import Cloudinary
from .local_ffmpeg import LocalFFmpeg
from .url_template import UrlTemplate

REGISTRY = {
    "cloudinary": Cloudinary,
    "local_ffmpeg": LocalFFmpeg,
    "url_template": UrlTemplate,
}


def build(name: str, spec: dict) -> Provider:
    spec = dict(spec)
    kind = spec.pop("type")
    if kind not in REGISTRY:
        raise ProviderError(f"unknown provider type {kind!r}; choose from {sorted(REGISTRY)}")
    return REGISTRY[kind](name, **spec)
