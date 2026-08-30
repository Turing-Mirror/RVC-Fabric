# -*- coding: utf-8 -*-
"""Offline benchmark for the realtime conversion hot path (RVC.infer).

Feeds a rolling 16 kHz buffer through the exact tensor path gui_v1 drives
(hubert -> optional index -> f0 -> net_g) without touching audio devices,
and reports per-block wall time against the block-time budget.

Run inside the product Runtime, from the repo root::

    Runtime\\python.exe tools\\benchmark_realtime.py --pth assets\\weights\\voice.pth
    Runtime\\python.exe tools\\benchmark_realtime.py --pth ... --index logs\\added_x.index --f0method rmvpe

A/B a change: check out each revision, run with identical args, compare reports.

Notes:
  * harvest needs gui_v1's multiprocess worker pool and is not supported here;
    use fcpe / rmvpe / pm / crepe.
  * Realtime headroom rule of thumb: p95 should stay under ~80% of block time.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

now_dir = os.getcwd()
sys.path.append(now_dir)
sys.path.append(os.path.join(now_dir, "tools"))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Benchmark the realtime RVC.infer hot path (no audio devices)."
    )
    p.add_argument("--pth", required=True, help="voice model .pth")
    p.add_argument("--index", default="", help="optional added_*.index feature bank")
    p.add_argument(
        "--index-rate",
        type=float,
        default=0.0,
        help="index blend rate; forced to 0.5 when --index is given without a rate",
    )
    p.add_argument(
        "--f0method",
        default="fcpe",
        choices=["fcpe", "rmvpe", "pm", "crepe"],
        help="pitch extractor (harvest unsupported here)",
    )
    p.add_argument("--pitch", type=int, default=0, help="f0 up key in semitones")
    p.add_argument("--formant", type=float, default=0.0, help="formant shift")
    p.add_argument("--block-time", type=float, default=0.25, help="seconds per block")
    p.add_argument("--crossfade-time", type=float, default=0.05)
    p.add_argument("--extra-time", type=float, default=2.5)
    p.add_argument(
        "--wav", default="", help="input wav; synthetic voiced tone when omitted"
    )
    p.add_argument("--n-blocks", type=int, default=200, help="measured blocks")
    p.add_argument("--warmup", type=int, default=10, help="unmeasured warmup blocks")
    p.add_argument(
        "--sync-stages",
        action="store_true",
        help="synchronize the device between stages so the engine's per-stage "
        "'Spent time' log is truthful (end-to-end gets slightly slower)",
    )
    p.add_argument(
        "--json-out", default="", help="also write the full results to this JSON file"
    )
    return p


def stage_stats(stage_rows) -> dict:
    """Aggregate per-block (fea, index, f0, model) second tuples into ms stats."""
    if not stage_rows:
        return {}
    arr = np.asarray(stage_rows, dtype=np.float64) * 1000.0
    out = {}
    for i, name in enumerate(("fea", "index", "f0", "model")):
        col = arr[:, i]
        out[name] = {
            "mean_ms": round(float(col.mean()), 2),
            "p95_ms": round(float(np.percentile(col, 95)), 2),
        }
    return out


def block_geometry(
    sr: int, block_time: float, crossfade_time: float, extra_time: float
) -> dict:
    """Frame layout for one stream.

    Delegates to ``tools/block_geometry.py`` so this benchmark, ``gui_v1`` and
    the offline renderer can never drift apart. They must agree exactly: half a
    block of difference is inaudible on its own, but it makes every parameter
    tuned here wrong on the user's machine.
    """
    from block_geometry import geometry

    return geometry(sr, block_time, crossfade_time, extra_time)


def synth_input(n_samples: int) -> np.ndarray:
    """Voiced-ish 16 kHz test signal: gliding sawtooth + light breath noise."""
    t = np.arange(n_samples, dtype=np.float64) / 16000.0
    f0 = 130.0 * 2 ** (0.5 * np.sin(2 * np.pi * 0.25 * t))  # ~92..184 Hz glide
    phase = 2 * np.pi * np.cumsum(f0) / 16000.0
    saw = 2.0 * ((phase / (2 * np.pi)) % 1.0) - 1.0
    noise = np.random.default_rng(0).standard_normal(n_samples)
    return (0.35 * saw + 0.02 * noise).astype(np.float32)


def load_source(path: str, total_needed: int) -> np.ndarray:
    if not path:
        return synth_input(total_needed)
    import librosa

    src, _ = librosa.load(path, sr=16000, mono=True)
    if len(src) == 0:
        raise SystemExit("empty wav: %s" % path)
    if len(src) < total_needed:
        src = np.tile(src, int(np.ceil(total_needed / len(src))))
    return src[:total_needed].astype(np.float32)


def main() -> int:
    args = build_parser().parse_args()
    if args.index and args.index_rate <= 0:
        args.index_rate = 0.5
        print("[bench] --index given without rate, using index_rate=0.5")

    import torch
    from multiprocessing import Queue

    from configs.config import Config
    from infer.lib.rtrvc import RVC

    config = Config()
    rvc = RVC(
        args.pitch,
        args.formant,
        args.pth,
        args.index,
        args.index_rate if args.index else 0.0,
        1,
        Queue(),
        Queue(),
        config,
    )
    if getattr(rvc, "net_g", None) is None:
        raise SystemExit("[bench] model failed to load — see traceback above")
    rvc.bench_sync = bool(args.sync_stages)

    geo = block_geometry(rvc.tgt_sr, args.block_time, args.crossfade_time, args.extra_time)
    total = args.warmup + args.n_blocks
    src = load_source(args.wav, geo["block_frame_16k"] * total)

    device = config.device
    use_cuda_sync = torch.cuda.is_available() and "cuda" in str(device)
    input_wav_res = torch.zeros(geo["input_res_len"], device=device, dtype=torch.float32)

    times: list[float] = []
    stage_rows: list[tuple] = []
    bf16k = geo["block_frame_16k"]
    for i in range(total):
        chunk = torch.from_numpy(src[i * bf16k : (i + 1) * bf16k]).to(device)
        input_wav_res[:-bf16k] = input_wav_res[bf16k:].clone()
        input_wav_res[-bf16k:] = chunk
        if use_cuda_sync:
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        out = rvc.infer(
            input_wav_res, bf16k, geo["skip_head"], geo["return_length"], args.f0method
        )
        # touching the result forces device completion on cuda / dml / cpu alike
        _ = float(out[-1].item())
        if use_cuda_sync:
            torch.cuda.synchronize()
        if i >= args.warmup:
            times.append(time.perf_counter() - t0)
            st = getattr(rvc, "last_stage_times", None)
            if st is not None:
                stage_rows.append(st)

    arr = np.asarray(times) * 1000.0
    block_ms = args.block_time * 1000.0
    p50, p95 = np.percentile(arr, [50, 95])
    rtf = float(arr.mean()) / block_ms
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "-"
    print("=" * 64)
    print("[bench] torch=%s gpu=%s" % (torch.__version__, gpu))
    print(
        "[bench] device=%s half=%s | model sr=%d v=%s f0=%s | f0method=%s index_rate=%.2f"
        % (
            device,
            config.is_half,
            rvc.tgt_sr,
            getattr(rvc, "version", "?"),
            getattr(rvc, "if_f0", "?"),
            args.f0method,
            args.index_rate if args.index else 0.0,
        )
    )
    print(
        "[bench] block=%.0fms n=%d | mean=%.1f p50=%.1f p95=%.1f max=%.1f ms | RTF=%.2f"
        % (block_ms, len(arr), arr.mean(), p50, p95, arr.max(), rtf)
    )
    st = stage_stats(stage_rows) if args.sync_stages else {}
    if st:
        print(
            "[bench] stages: "
            + " | ".join(
                "%s mean=%.1f p95=%.1f" % (k, v["mean_ms"], v["p95_ms"])
                for k, v in st.items()
            )
        )
    budget = 0.8 * block_ms
    if p95 <= budget:
        print("[bench] OK: p95 within 80%% of block budget (%.0fms)" % budget)
    else:
        print(
            "[bench] OVER BUDGET: p95 %.1fms > %.0fms — expect glitches; "
            "raise block-time or use a faster f0method/device" % (p95, budget)
        )
    if args.json_out:
        payload = {
            "env": {
                "torch": str(torch.__version__),
                "gpu": gpu,
                "device": str(device),
                "half": bool(config.is_half),
            },
            "run": {
                "model": os.path.basename(args.pth),
                "model_sr": int(rvc.tgt_sr),
                "version": str(getattr(rvc, "version", "?")),
                "f0method": args.f0method,
                "index_rate": args.index_rate if args.index else 0.0,
                "block_time": args.block_time,
                "sync_stages": bool(args.sync_stages),
                "n_blocks": len(arr),
            },
            "summary": {
                "mean_ms": round(float(arr.mean()), 2),
                "p50_ms": round(float(p50), 2),
                "p95_ms": round(float(p95), 2),
                "max_ms": round(float(arr.max()), 2),
                "rtf": round(rtf, 3),
            },
            "stages": st or None,
        }
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print("[bench] json written: %s" % args.json_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
