# -*- coding: utf-8 -*-
"""Download & install engine-core from CNB (hubert / rmvpe / ffmpeg).

Setup payload is shell-only; this pack is required for realtime VC and is
identical for all GPU variants (unlike Runtime).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from launcher.paths import ROOT, USER_DATA, ensure_dirs

ProgressCb = Callable[[str, int, int], None]
LogCb = Callable[[str], None]

# ~800 MB pack: generous I/O timeout, few retries
ENGINE_CORE_DOWNLOAD_TIMEOUT = 3600
ENGINE_CORE_DOWNLOAD_RETRIES = 3

def _log(cb: Optional[LogCb], msg: str) -> None:
    if cb:
        try:
            cb(msg)
        except Exception:
            pass


def _progress(cb: Optional[ProgressCb], phase: str, done: int, total: int) -> None:
    if cb:
        try:
            cb(phase, done, total)
        except Exception:
            pass


def engine_core_paths(root: Path | None = None) -> list[tuple[Path, int]]:
    """(path, min_size) for install root (default product ROOT)."""
    base = Path(root or ROOT)
    return [
        (base / "assets" / "hubert" / "hubert_base.pt", 1_000_000),
        (base / "assets" / "rmvpe" / "rmvpe.pt", 1_000_000),
        (base / "assets" / "rmvpe" / "rmvpe.onnx", 100_000),
        (base / "ffmpeg.exe", 1_000_000),
        (base / "ffprobe.exe", 1_000_000),
    ]


def engine_core_ready(root: Path | None = None) -> bool:
    """True when hubert + both rmvpe + ffmpeg/ffprobe are present and non-tiny."""
    for path, min_sz in engine_core_paths(root):
        try:
            if not path.is_file() or path.stat().st_size < min_sz:
                return False
        except OSError:
            return False
    return True


def engine_core_missing(root: Path | None = None) -> list[str]:
    miss: list[str] = []
    for path, min_sz in engine_core_paths(root):
        try:
            if not path.is_file() or path.stat().st_size < min_sz:
                miss.append(str(path.name))
        except OSError:
            miss.append(str(path.name))
    return miss


def ensure_engine_core(
    *,
    root: Path | None = None,
    force: bool = False,
    progress: Optional[ProgressCb] = None,
    log: Optional[LogCb] = None,
) -> tuple[bool, str]:
    """Download engine-core zip from CNB and extract into install root.

    Call after Runtime is ready (or in parallel after); required before VC.
    """
    base = Path(root or ROOT)
    ensure_dirs()
    if engine_core_ready(base) and not force:
        return True, "引擎资源（Hubert / RMVPE / ffmpeg）已就绪"

    try:
        from launcher.cnb_sources import format_size, resolve_engine_core_spec
        from launcher.online.downloader import download_file
        from launcher.online.safe_zip import safe_extract_zip
    except Exception as e:
        return False, f"无法加载下载模块：{e}"

    try:
        spec = resolve_engine_core_spec(prefer_remote=True)
    except Exception as e:
        return False, f"无法解析引擎资源下载地址：{e}"

    if not spec.urls or not spec.sha256:
        return False, "CNB 清单中缺少 engine-core 下载信息"

    cache = USER_DATA / "update_cache" / "engine_core"
    if root is not None:
        cache = Path(root) / "User_Data" / "update_cache" / "engine_core"
    cache.mkdir(parents=True, exist_ok=True)
    # Catalog-controlled name → basename only (review #25)
    safe_name = Path(str(spec.name or "engine-core.zip")).name
    if not safe_name or safe_name in (".", "..") or ".." in safe_name:
        safe_name = "engine-core.zip"
    dest = cache / safe_name

    size_hint = format_size(spec.size_bytes) if spec.size_bytes else "约 800 MB"
    _log(log, f"准备下载引擎资源包 {spec.name}（{size_hint}）…")

    # Reuse verified cache
    if dest.is_file() and spec.sha256 and not force:
        try:
            from launcher.online.downloader import _verify_sha256

            _verify_sha256(dest, spec.sha256)
            _log(log, f"使用本地缓存：{dest.name}")
        except Exception:
            try:
                dest.unlink()
            except OSError:
                pass

    if not dest.is_file() or force:
        last_err: Exception | None = None
        for i, url in enumerate(spec.urls):
            _log(log, f"下载引擎资源 ({i + 1}/{len(spec.urls)})：{url}")
            try:

                def _cb(done: int, total: int, _phase: str = "engine_core") -> None:
                    _progress(progress, _phase, done, total)

                download_file(
                    url,
                    dest,
                    progress=_cb,
                    retries=ENGINE_CORE_DOWNLOAD_RETRIES,
                    timeout=ENGINE_CORE_DOWNLOAD_TIMEOUT,
                    expected_sha256=spec.sha256,
                )
                last_err = None
                break
            except Exception as e:
                last_err = e
                _log(log, f"  失败：{e}")
                # Keep .part / partial cache for resume on retry
        if last_err is not None:
            return False, f"引擎资源下载失败：{last_err}"

    _log(log, f"解压 {dest.name} → 安装目录…")
    _progress(progress, "engine_extract", 0, 1)
    try:
        written = safe_extract_zip(dest, base)
        _log(log, f"已写入 {len(written)} 个文件")
    except Exception as e:
        return False, f"引擎资源解压失败：{e}"
    _progress(progress, "engine_extract", 1, 1)

    if not engine_core_ready(base):
        miss = ", ".join(engine_core_missing(base)) or "未知"
        return False, f"解压后仍缺文件：{miss}。请重试「补全运行环境」。"

    return True, "引擎资源（Hubert / RMVPE / ffmpeg）已安装完成。"
