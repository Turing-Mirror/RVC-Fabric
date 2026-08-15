"""Download RVC pretrained weights from Hugging Face.

Scopes (product-oriented)::

  core      — hubert + rmvpe (+ rmvpe.onnx if available)  [daily realtime VC]
  training  — assets/pretrained + pretrained_v2            [train your own voice]
  all       — everything

人声分离用的是 PyMSS（tools/pymss，模型按需从它自己的清单下），不再有 uvr
这一档 —— 上游 RVC 已经用 PyMSS 取代了 UVR5，本产品的分离功能也一直走 PyMSS，
留着这一档只会让人下一堆没有任何代码会去读的权重。

Improvements over the original script:
- Skip only when size exceeds minimum thresholds (not size>0)
- Verify Content-Length when server provides it
- Simple progress logging and retries
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

RVC_DOWNLOAD_LINK = "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/"

BASE_DIR = Path(__file__).resolve().parent.parent

MAX_RETRIES = 3
CHUNK_SIZE = 1 << 20  # 1 MiB

# Minimum sizes to treat an existing file as valid (avoid stuck corrupt stubs)
MIN_SIZE = {
    "hubert_base.pt": 1_000_000,
    "rmvpe.pt": 1_000_000,
    "rmvpe.onnx": 100_000,
    "vocals.onnx": 100_000,
}
DEFAULT_MIN = 50_000  # generic .pth weights

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


def _min_size(model_name: str) -> int:
    return int(MIN_SIZE.get(model_name, DEFAULT_MIN))


def _is_complete(path: Path, model_name: str) -> bool:
    return path.is_file() and path.stat().st_size >= _min_size(model_name)


def dl_model(
    link: str,
    model_name: str,
    dir_name: Path,
    retries: int = MAX_RETRIES,
) -> None:
    try:
        import requests
    except ImportError as e:
        raise RuntimeError("需要 requests 库：pip install requests") from e

    dest = dir_name / model_name
    if _is_complete(dest, model_name):
        print(f"  skip (ok): {dest} ({dest.stat().st_size} bytes)")
        return
    if dest.is_file():
        print(
            f"  re-download (too small {dest.stat().st_size} < {_min_size(model_name)}): {model_name}"
        )
        try:
            dest.unlink()
        except OSError:
            pass

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
            if total and done != total:
                raise RuntimeError(
                    f"size mismatch: got {done} bytes, Content-Length {total}"
                )
            if done < _min_size(model_name):
                raise RuntimeError(
                    f"file too small: {done} < min {_min_size(model_name)}"
                )
            tmp.replace(dest)
            print(f"  saved: {dest} ({done} bytes)")
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



def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Download RVC model weights from Hugging Face")
    ap.add_argument(
        "--scope",
        choices=("core", "training", "all"),
        default="core",
        help="core=daily VC; training=bottom models; all=both",
    )
    args = ap.parse_args(argv)
    scope = args.scope

    try:
        if scope in ("core", "all"):
            download_core()
        if scope in ("training", "all"):
            download_training()
        print(f"Done (scope={scope}).")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
