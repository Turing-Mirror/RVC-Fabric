"""Download RVC pretrained weights from Hugging Face.

Scopes (product-oriented)::

  core      — hubert + rmvpe (+ rmvpe.onnx if available)  [daily realtime VC]
  training  — assets/pretrained + pretrained_v2            [train your own voice]
  uvr       — UVR / demucs-style separation weights        [WebUI stem split]
  all       — everything (legacy full download)

Improvements over the original script:
- Skip files that already exist and are non-empty
- Simple progress logging and retries
- Clear exit code on failure
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

RVC_DOWNLOAD_LINK = "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/"

BASE_DIR = Path(__file__).resolve().parent.parent

MAX_RETRIES = 3
CHUNK_SIZE = 1 << 20  # 1 MiB

PRETRAIN_NAMES = [
    "D32k.pth",
    "D40k.pth",
    "D48k.pth",
    "G32k.pth",
    "G40k.pth",
    "G48k.pth",
    "f0D32k.pth",
    "f0D40k.pth",
    "f0D48k.pth",
    "f0G32k.pth",
    "f0G40k.pth",
    "f0G48k.pth",
]

UVR_NAMES = [
    "HP2-%E4%BA%BA%E5%A3%B0vocals%2B%E9%9D%9E%E4%BA%BA%E5%A3%B0instrumentals.pth",
    "HP2_all_vocals.pth",
    "HP3_all_vocals.pth",
    "HP5-%E4%B8%BB%E6%97%8B%E5%BE%8B%E4%BA%BA%E5%A3%B0vocals%2B%E5%85%B6%E4%BB%96instrumentals.pth",
    "HP5_only_main_vocal.pth",
    "VR-DeEchoAggressive.pth",
    "VR-DeEchoDeReverb.pth",
    "VR-DeEchoNormal.pth",
]


def dl_model(link: str, model_name: str, dir_name: Path, retries: int = MAX_RETRIES) -> None:
    dest = dir_name / model_name
    if dest.is_file() and dest.stat().st_size > 0:
        print(f"  skip (exists): {dest}")
        return

    url = f"{link}{model_name}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            print(f"  downloading ({attempt}/{retries}): {model_name}")
            with requests.get(url, stream=True, timeout=120) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length") or 0)
                done = 0
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                        if not chunk:
                            continue
                        f.write(chunk)
                        done += len(chunk)
                        if total:
                            pct = done * 100 // total
                            print(f"\r    {pct:3d}% ({done}/{total} bytes)", end="")
                if total:
                    print()
            tmp.replace(dest)
            print(f"  saved: {dest}")
            return
        except Exception as e:
            last_err = e
            print(f"  failed: {e}")
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            if attempt < retries:
                time.sleep(2 * attempt)
    raise RuntimeError(f"failed to download {model_name}: {last_err}")


def download_core() -> None:
    print("=== scope=core (daily realtime VC) ===")
    print("Downloading hubert_base.pt...")
    dl_model(RVC_DOWNLOAD_LINK, "hubert_base.pt", BASE_DIR / "assets/hubert")
    print("Downloading rmvpe.pt...")
    dl_model(RVC_DOWNLOAD_LINK, "rmvpe.pt", BASE_DIR / "assets/rmvpe")
    # Optional ONNX for DirectML F0 — ignore hard failure
    try:
        print("Downloading rmvpe.onnx (optional, AMD/DML)...")
        dl_model(RVC_DOWNLOAD_LINK, "rmvpe.onnx", BASE_DIR / "assets/rmvpe")
    except Exception as e:
        print(f"  rmvpe.onnx skip/fail (optional): {e}")


def download_training() -> None:
    print("=== scope=training (train your own voice) ===")
    rvc_models_dir = BASE_DIR / "assets/pretrained"
    print("Downloading pretrained models v1:")
    for model in PRETRAIN_NAMES:
        dl_model(RVC_DOWNLOAD_LINK + "pretrained/", model, rvc_models_dir)

    rvc_models_dir = BASE_DIR / "assets/pretrained_v2"
    print("Downloading pretrained models v2:")
    for model in PRETRAIN_NAMES:
        dl_model(RVC_DOWNLOAD_LINK + "pretrained_v2/", model, rvc_models_dir)


def download_uvr() -> None:
    print("=== scope=uvr (stem separation) ===")
    try:
        print("Downloading vocals.onnx...")
        dl_model(
            RVC_DOWNLOAD_LINK + "uvr5_weights/onnx_dereverb_By_FoxJoy/",
            "vocals.onnx",
            BASE_DIR / "assets/uvr5_weights/onnx_dereverb_By_FoxJoy",
        )
    except Exception as e:
        print(f"  vocals.onnx skip/fail: {e}")

    print("Downloading uvr5_weights:")
    rvc_models_dir = BASE_DIR / "assets/uvr5_weights"
    for model in UVR_NAMES:
        dl_model(RVC_DOWNLOAD_LINK + "uvr5_weights/", model, rvc_models_dir)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Download RVC model weights from Hugging Face")
    ap.add_argument(
        "--scope",
        choices=("core", "training", "uvr", "all"),
        default="core",
        help="core=daily VC; training=bottom models; uvr=separation; all=legacy full set",
    )
    args = ap.parse_args(argv)
    scope = args.scope

    try:
        if scope in ("core", "all"):
            download_core()
        if scope in ("training", "all"):
            download_training()
        if scope in ("uvr", "all"):
            download_uvr()
        print(f"Done (scope={scope}).")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
