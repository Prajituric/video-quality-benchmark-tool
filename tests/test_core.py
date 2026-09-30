import json
import os
import unittest
from unittest import mock

from vqbench.metrics import _summary
from vqbench.providers import build
from vqbench.run import summarise


class SummaryTests(unittest.TestCase):
    def test_percentiles_and_harmonic_mean(self):
        s = _summary([90.0, 95.0, 100.0, 50.0])
        self.assertEqual(s.min, 50.0)
        self.assertEqual(s.max, 100.0)
        self.assertAlmostEqual(s.mean, 83.75)
        self.assertLess(s.harmonic_mean, s.mean)  # drops are penalised

    def test_summarise_skips_errors(self):
        m = {"vmaf": {"mean": 90, "harmonic_mean": 89, "p5": 80}, "psnr_y": {"mean": 40}, "ssim": {"mean": 0.98}}
        rows = summarise([
            {"provider": "a", "target_kbps": 2500, "metrics": m, "rendition": {"bitrate_kbps": 2400}},
            {"provider": "a", "target_kbps": 2500, "error": "boom"},
        ])
        self.assertEqual(rows["a"]["2500"]["sources"], 1)
        self.assertEqual(rows["a"]["2500"]["mean_vmaf"], 90)


class CloudinaryUrlTests(unittest.TestCase):
    def test_vbr_url(self):
        p = build("c", {"type": "cloudinary", "cloud_name": "demo", "video_codec": "h264"})
        self.assertEqual(p.delivery_url("vqbench/x", 2500),
                         "https://res.cloudinary.com/demo/video/upload/vc_h264,br_2500k/vqbench/x.mp4")

    def test_constant_and_quality(self):
        p = build("c", {"type": "cloudinary", "cloud_name": "demo", "bitrate_mode": "constant", "quality": "auto"})
        self.assertIn("br_1000k:constant,q_auto", p.delivery_url("x", 1000))

    def test_missing_credentials(self):
        p = build("c", {"type": "cloudinary"})
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(Exception):
                p.delivery_url("x", 1000)


class UrlTemplateTests(unittest.TestCase):
    def test_ladder_never_rounds_up(self):
        p = build("u", {"type": "url_template", "url_template": "https://e/{source_id}/{kbps}.mp4",
                        "bitrate_ladder": [800, 2000, 4000]})
        with mock.patch("vqbench.providers.url_template.download", side_effect=lambda url, dest, headers: dest) as dl:
            from pathlib import Path
            p.encode(Path("s.mp4"), "clip", 2500, Path("."))
            self.assertEqual(dl.call_args[0][0], "https://e/clip/2000.mp4")

    def test_describe_hides_headers(self):
        p = build("u", {"type": "url_template", "url_template": "x", "headers_env": {"Authorization": "TOKEN"}})
        self.assertNotIn("headers_env", json.dumps(p.describe()))


if __name__ == "__main__":
    unittest.main()
