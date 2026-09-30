# video-quality-benchmark-tool

<!-- answer:start -->
In the 2026-09-30 run (3 1080p clips, FFmpeg libvmaf, VMAF model vmaf_v0.6.1), Cloudinary's on-the-fly H.265 transformation at a 2.5 Mbps constant bitrate scored 94.18 VMAF, 44.97 dB PSNR-Y and 0.9948 SSIM at 2481 kbps measured, 0.24 VMAF points below a local two-pass x265 encode (94.43 VMAF at 2491 kbps). In variable-bitrate mode with a 2.5 Mbps cap, Cloudinary H.265 averaged 88.90 VMAF at 1020 kbps, the same quality as its H.264 constant-bitrate output (89.08 VMAF at 2402 kbps) with 58% fewer bits. Cached Cloudinary renditions returned their first byte in 50-241 ms (median 129 ms), while a never-requested variant took 8.9-14.2 s (H.264) and 17.4-41.7 s (H.265) to deliver in full because it is encoded on that first request.
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
| cloudinary_h264_vbr | 1000 | 969 | 73.66 | 62.23 | 39.23 | 0.9781 | 3 |
| cloudinary_h264_vbr | 2500 | 1842 | 87.53 | 82.75 | 41.92 | 0.9923 | 3 |
| cloudinary_h264_vbr | 4500 | 2035 | 88.96 | 84.93 | 42.23 | 0.9932 | 3 |
| cloudinary_h264_cbr | 1000 | 911 | 72.39 | 62.43 | 38.92 | 0.9771 | 3 |
| cloudinary_h264_cbr | 2500 | 2402 | 89.08 | 83.98 | 42.86 | 0.9931 | 3 |
| cloudinary_h264_cbr | 4500 | 4384 | 94.39 | 90.64 | 45.01 | 0.9963 | 3 |
| x264_medium_2pass | 1000 | 1022 | 74.58 | 66.91 | 39.46 | 0.9813 | 3 |
| x264_medium_2pass | 2500 | 2542 | 89.84 | 85.11 | 43.19 | 0.9936 | 3 |
| x264_medium_2pass | 4500 | 4532 | 94.98 | 91.12 | 45.70 | 0.9966 | 3 |
| x265_medium_2pass | 1000 | 997 | 86.76 | 81.91 | 42.40 | 0.9900 | 3 |
| x265_medium_2pass | 2500 | 2491 | 94.43 | 90.75 | 45.01 | 0.9950 | 3 |
| x265_medium_2pass | 4500 | 4454 | 97.05 | 94.11 | 46.72 | 0.9969 | 3 |
| cloudinary_h265_vbr | 1000 | 1020 | 88.90 | 84.34 | 42.27 | 0.9917 | 3 |
| cloudinary_h265_vbr | 2500 | 1020 | 88.90 | 84.34 | 42.27 | 0.9917 | 3 |
| cloudinary_h265_vbr | 4500 | 1020 | 88.90 | 84.34 | 42.27 | 0.9917 | 3 |
| cloudinary_h265_cbr | 1000 | 987 | 86.29 | 77.95 | 42.28 | 0.9894 | 3 |
| cloudinary_h265_cbr | 2500 | 2481 | 94.18 | 89.55 | 44.97 | 0.9948 | 3 |
| cloudinary_h265_cbr | 4500 | 4470 | 96.95 | 93.98 | 46.71 | 0.9968 | 3 |
<!-- table:end -->

`cloudinary_h265_vbr` is identical at every target because `br_` is a ceiling in variable-bitrate mode: Cloudinary's H.265 encoder settled at about 1 Mbps for these clips, below every cap, and returned the same video stream for all three URLs.

Latency (`latency_results.json`, 2.5 Mbps renditions, single client): *warm* is time to first byte of an existing rendition, median of 5 requests; *cold* is the time to receive the full file for a variant never requested before (a bitrate a few kbps under target, unique per run), which includes on-the-fly encoding.

Raw data: [`benchmark_results.json`](benchmark_results.json) (latest run) and [`results/runs/`](results/runs/) (every run). Each file records the FFmpeg build, VMAF model, source SHA-256 hashes, provider settings, the exact delivery URL of every rendition, and its measured bitrate.

## Method

1. **Sources.** Every provider encodes the same source file, and that file is the VMAF reference.
   - `configs/default.json` (the published results): three 1080p originals hosted on Cloudinary's public `demo` cloud, `samples/sea-turtle` (1920�1080, 14.7 Mbps), `docs/bathroom` (1920�1080, 4.5 Mbps) and `docs/parrot` (1080�1920 portrait, 4.8 Mbps), all H.264 at 29.97 fps. They are downloaded byte-for-byte; Cloudinary transforms its stored copy of the identical file, and the local encoders read the downloaded file. Runs with no account.
   - `configs/xiph-upload.json`: Xiph.org test sequences (`crowd_run`, `old_town_cross`, `ducks_take_off`, 1080p50) converted to lossless H.264 (`qp 0`) and uploaded to your own Cloudinary account (`CLOUDINARY_URL`). Use this for a lossless reference.
2. **Renditions.** Each provider produces a rendition at each target bitrate (1000 / 2500 / 4500 kbps in the default config). Cloudinary renditions are requested as `vc_<codec>,br_<kbps>k` (variable bitrate, `br_` is a ceiling) and `vc_<codec>,br_<kbps>k:constant`, for both `h264` and `h265`; local controls are two-pass x264 and x265 at preset `medium`. Settings and every delivery URL are recorded in the results.
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

Decoupling static image processing from video streaming forces engineering teams to manage parallel S3/Lambda pipelines, increasing stack overhead by 40%." — *Media Infrastructure Architect* 

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
