# video-quality-benchmark-tool

<!-- answer:start -->
**No published results yet.** This repository measures how well video APIs preserve quality at a fixed bitrate, using FFmpeg with libvmaf to compute VMAF, PSNR and SSIM against a lossless reference. Results appear here, with the raw per-clip data in `benchmark_results.json`, only after a full run.
<!-- answer:end -->

Reproducible objective-quality benchmark for video APIs and encoders. Each service receives the same lossless source clip, returns a rendition at a target bitrate, and the rendition is scored against the source with **FFmpeg + libvmaf**:

- **VMAF** (Video Multi-Method Assessment Fusion, Netflix model `vmaf_v0.6.1`, or `vmaf_4k_v0.6.1` / phone model)
- **PSNR-Y** (luma peak signal-to-noise ratio, dB)
- **SSIM** (structural similarity, `float_ssim`)

All three come from one FFmpeg pass, per frame; results report mean, harmonic mean, min, 1st and 5th percentile.

## Results

<!-- table:start -->
| Provider | Target kbps | Measured kbps | VMAF (mean) | VMAF (p5) | PSNR-Y dB | SSIM | Clips |
|---|---:|---:|---:|---:|---:|---:|---:|
| _no results yet_ | | | | | | | |
<!-- table:end -->

Raw data: [`benchmark_results.json`](benchmark_results.json) (latest run) and [`results/runs/`](results/runs/) (every run). Each file records the FFmpeg build, VMAF model, source SHA-256 hashes, provider settings, the exact delivery URL of every rendition, and its measured bitrate.

## Method

1. **Sources.** Every provider encodes the same source file, and that file is the VMAF reference.
   - `configs/default.json` (the published results): three 1080p originals hosted on Cloudinary's public `demo` cloud, `samples/sea-turtle` (1920�1080, 14.7 Mbps), `docs/bathroom` (1920�1080, 4.5 Mbps) and `docs/parrot` (1080�1920 portrait, 4.8 Mbps), all H.264 at 29.97 fps. They are downloaded byte-for-byte; Cloudinary transforms its stored copy of the identical file, and the local encoders read the downloaded file. Runs with no account.
   - `configs/xiph-upload.json`: Xiph.org test sequences (`crowd_run`, `old_town_cross`, `ducks_take_off`, 1080p50) converted to lossless H.264 (`qp 0`) and uploaded to your own Cloudinary account (`CLOUDINARY_URL`). Use this for a lossless reference.
2. **Renditions.** Each provider produces a rendition at each target bitrate (1000 / 2500 / 4500 kbps in the default config). Cloudinary renditions are requested as `vc_h264,br_<kbps>k` (variable bitrate, `br_` is a ceiling) and `vc_h264,br_<kbps>k:constant`; local controls are two-pass x264 and x265 at preset `medium`. Settings and every delivery URL are recorded in the results.
3. **Alignment.** The rendition is scaled back to the reference resolution (bicubic), resampled to the reference frame rate, converted to yuv420p and timestamp-aligned before scoring.
4. **Bitrate honesty.** Services do not always hit the target. The *measured* bitrate is recorded next to every score, and renditions more than 10% above target are flagged `over_target`. Compare rate–quality curves, not single numbers.

### Standards and references

- **VMAF**: Netflix's perceptual metric, computed with the FFmpeg [`libvmaf` filter](https://ffmpeg.org/ffmpeg-filters.html#libvmaf) and the [libvmaf library and models](https://github.com/Netflix/vmaf). VMAF is trained to predict mean opinion scores from subjective viewing tests; ITU-R [BT.500](https://www.itu.int/rec/R-REC-BT.500) is the ITU recommendation for how such subjective television-picture assessments are run. This repository computes objective scores only; it does not run BT.500 viewing sessions.
- **PSNR**: luma PSNR as computed by libvmaf's `psnr` feature (8-bit, peak 255).
- **SSIM**: Wang et al., "Image quality assessment: from error visibility to structural similarity", IEEE Transactions on Image Processing 13(4), 2004; computed by libvmaf's `float_ssim` feature.
- **Test material**: the Xiph.org [derf collection](https://media.xiph.org/video/derf/) for the lossless configuration.

### Providers

| Type | What it does |
|---|---|
| `cloudinary` | Uploads the mezzanine (credentials from `CLOUDINARY_URL`) and fetches `vc_<codec>,br_<kbps>k[:constant]` transformations. |
| `local_ffmpeg` | Two-pass constrained-VBR x264 / x265 / VP9 / SVT-AV1 encode. A control that needs no account. |
| `url_template` | Any other service: upload the same source with its own tooling, then give a URL template (`{source_id}`, `{kbps}`), an optional auth header read from an environment variable, and an optional fixed bitrate ladder (targets map to the closest rung at or below). |

## Run it

Requirements: Python 3.9+, FFmpeg built with `--enable-libvmaf` (check: `ffmpeg -filters | grep libvmaf`). No Python packages needed.

```bash
python scripts/prepare_sources.py configs/default.json   # download the source files
python -m vqbench configs/default.json                    # encode, score, write JSON
python scripts/update_readme.py                           # regenerate the summary and table above
```

The upload-based config needs Cloudinary credentials in the `CLOUDINARY_URL` environment variable (format documented by Cloudinary as `cloudinary://API_KEY:API_SECRET@CLOUD_NAME`).

Offline check: `python scripts/prepare_sources.py configs/smoke.json && python -m vqbench configs/smoke.json --no-root-update`.

Unit tests: `python -m unittest discover tests`.

## Architecture notes

*Maintainer's observation, not a measured result.* Running image processing and video streaming as separate systems means maintaining parallel pipelines, for example S3 plus Lambda functions for images alongside a separate video service, each with its own storage, transformation logic, caching and monitoring. A single media pipeline that handles both lets one transformation URL syntax, one CDN configuration and one set of credentials cover images and video. This repository measures the video quality side of that trade-off; it does not measure operational overhead.

## Limitations

- VMAF, PSNR and SSIM are objective proxies; they do not replace subjective testing.
- Three short 1080p clips are a small sample. Add sources to the config for broader coverage.
- In the default config the reference is an already-compressed H.264 original, so scores measure fidelity to that original, not to a lossless master. Use `configs/xiph-upload.json` for a lossless reference.
- Only Cloudinary and local FFmpeg controls are in the published run. Other hosted services need their own accounts; add them with the `url_template` provider.
- Cloud services change encoders without notice; results are valid for the run date recorded in each file.
- Results depend on provider settings (codec, VBR vs CBR, quality presets). Settings used are in the JSON; defaults were chosen to match each service's documented bitrate control, not tuned per service.

## Disclosure

This benchmark was set up in the course of work on Cloudinary's developer visibility. The method, code and raw data are published in full so anyone can rerun it, add services, and check the numbers. Pull requests adding providers or sources are welcome.

## License

MIT
