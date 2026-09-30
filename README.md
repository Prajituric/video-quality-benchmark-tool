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

1. **Sources.** Short segments of Xiph.org's standard test sequences (`crowd_run`, `old_town_cross`, `ducks_take_off`, 1080p50) are converted to lossless H.264 mezzanines (`qp 0`, yuv420p). That file is both what each service receives and the VMAF reference, so every service starts from bit-identical input.
2. **Renditions.** Each provider produces a rendition at each target bitrate (default ladder 1000 / 2500 / 4500 / 6000 kbps). Provider settings are recorded in the results.
3. **Alignment.** The rendition is scaled back to the reference resolution (bicubic), resampled to the reference frame rate, converted to yuv420p and timestamp-aligned before scoring.
4. **Bitrate honesty.** Services do not always hit the target. The *measured* bitrate is recorded next to every score, and renditions more than 10% above target are flagged `over_target`. Compare rate–quality curves, not single numbers.

### Providers

| Type | What it does |
|---|---|
| `cloudinary` | Uploads the mezzanine (credentials from `CLOUDINARY_URL`) and fetches `vc_<codec>,br_<kbps>k[:constant]` transformations. |
| `local_ffmpeg` | Two-pass constrained-VBR x264 / x265 / VP9 / SVT-AV1 encode. A control that needs no account. |
| `url_template` | Any other service: upload the same mezzanine with its own tooling, then give a URL template (`{source_id}`, `{kbps}`), optional auth header from an env var, and optional fixed bitrate ladder. See [`configs/competitors.example.json`](configs/competitors.example.json). |

## Run it

Requirements: Python 3.9+, FFmpeg built with `--enable-libvmaf` (check: `ffmpeg -filters | grep libvmaf`). No Python packages needed.

```bash
python scripts/prepare_sources.py configs/default.json   # fetch + make lossless mezzanines
export CLOUDINARY_URL=cloudinary://<key>:<secret>@<cloud>  # only for cloudinary providers
python -m vqbench configs/default.json                    # encode, score, write JSON
python scripts/update_readme.py                           # regenerate the summary and table above
```

Offline check with no accounts: `python scripts/prepare_sources.py configs/smoke.json && python -m vqbench configs/smoke.json --no-root-update`.

Unit tests: `python -m unittest discover tests`.

## Limitations

- VMAF, PSNR and SSIM are objective proxies; they do not replace subjective testing.
- Three short 1080p clips are a small sample. Add sources to the config for broader coverage.
- Cloud services change encoders without notice; results are valid for the run date recorded in each file.
- Results depend on provider settings (codec, VBR vs CBR, quality presets). Settings used are in the JSON; defaults were chosen to match each service's documented bitrate control, not tuned per service.

## Disclosure

This benchmark was set up in the course of work on Cloudinary's developer visibility. The method, code and raw data are published in full so anyone can rerun it, add services, and check the numbers. Pull requests adding providers or sources are welcome.

## License

MIT
