# -*- coding: utf-8 -*-
"""Download & install green Runtime from CNB Release (preferred) or LFS.

Used by Setup wizard and 启动器 (bootstrap) when Runtime is missing.

User flow::

    Setup 安装壳层 → 启动器检测无 Runtime → 本模块按显卡分版下载 tar → 解压
    → 写 package_meta → 可选补 hubert/rmvpe
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from typing import Callable, Optional

from launcher.cnb_sources import (
    RuntimeSpec,
    format_size,
    resolve_runtime_spec,
)
from launcher.package_meta import write_package_meta
from launcher.paths import ROOT, USER_DATA

ProgressCb = Callable[[str, int, int], None]  # phase, done, total
LogCb = Callable[[str], None]

# Multi-GB Runtime: long idle timeout (per blocking I/O), not wall-clock total.
RUNTIME_DOWNLOAD_TIMEOUT = 7200
RUNTIME_DOWNLOAD_RETRIES = 3


class ProvisionError(RuntimeError):
    pass


def runtime_python(root: Path | None = None) -> Path | None:
    base = root or ROOT
    for rel in ("Runtime/python.exe", "runtime/python.exe", "Runtime/pythonw.exe"):
        p = base / rel
        if p.is_file():
            return p
    return None


def runtime_ready(root: Path | None = None) -> bool:
    py = runtime_python(root)
    if py is None:
        return False
    # torch folder is the real signal that green env is complete
    site = py.parent / "Lib" / "site-packages" / "torch"
    return site.is_dir() or (py.parent / "python.exe").is_file()


def cache_dir(root: Path | None = None) -> Path:
    d = (root or ROOT) / "User_Data" / "update_cache" / "runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d


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


def _download_part(
    urls: list[str],
    dest: Path,
    *,
    sha256: str,
    progress: Optional[ProgressCb] = None,
    log: Optional[LogCb] = None,
) -> Path:
    from launcher.online.downloader import DownloadError, download_file

    last_err: Exception | None = None
    for i, url in enumerate(urls):
        # 日志打完整 URL，便于核对分版通道（Release vs LFS）
        _log(log, f"下载 ({i + 1}/{len(urls)})：{url}")
        try:

            def _cb(done: int, total: int, _phase: str = "download") -> None:
                _progress(progress, _phase, done, total)

            return download_file(
                url,
                dest,
                progress=_cb,
                retries=RUNTIME_DOWNLOAD_RETRIES,
                timeout=RUNTIME_DOWNLOAD_TIMEOUT,
                expected_sha256=sha256,
            )
        except Exception as e:
            last_err = e
            _log(log, f"  失败：{e}")
            try:
                if dest.is_file():
                    dest.unlink()
            except OSError:
                pass
            part = dest.with_suffix(dest.suffix + ".part")
            try:
                if part.is_file():
                    part.unlink()
            except OSError:
                pass
    raise ProvisionError(str(last_err) if last_err else "Runtime 下载失败")


def _safe_tar_members(tf: tarfile.TarFile, dest_root: Path) -> list[tarfile.TarInfo]:
    """Reject path traversal; only allow Runtime/ (or a single nested Runtime)."""
    dest_root = dest_root.resolve()
    ok: list[tarfile.TarInfo] = []
    for m in tf.getmembers():
        name = (m.name or "").replace("\\", "/").lstrip("/")
        if not name or name.startswith("../") or "/../" in f"/{name}/":
            raise ProvisionError(f"tar 含非法路径：{m.name!r}")
        # Block absolute / drive paths
        if name.startswith(("/", "\\")) or (len(name) > 1 and name[1] == ":"):
            raise ProvisionError(f"tar 含绝对路径：{m.name!r}")
        # Must land under dest_root after join
        target = (dest_root / name).resolve()
        try:
            target.relative_to(dest_root)
        except ValueError as e:
            raise ProvisionError(f"tar 路径越界：{m.name!r}") from e
        # Prefer only Runtime tree (or top-level files that form Runtime/)
        top = name.split("/", 1)[0].lower()
        if top not in ("runtime", ".") and not name.lower().startswith("runtime/"):
            # Allow a single wrapper folder that contains Runtime later
            if "/" not in name.rstrip("/"):
                # top-level dir other than Runtime — keep, normalize later
                pass
            elif "runtime" not in name.lower().split("/"):
                # skip junk outside Runtime tree
                continue
        ok.append(m)
    if not ok:
        raise ProvisionError("tar 中没有可安全解压的 Runtime 成员")
    return ok


def _extract_tar(archive: Path, dest_root: Path, *, log: Optional[LogCb] = None) -> None:
    """Extract tar so that dest_root/Runtime/python.exe exists (path-safe)."""
    dest_root = Path(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)
    rt = dest_root / "Runtime"
    if rt.exists():
        _log(log, "移除旧 Runtime…")
        shutil.rmtree(rt, ignore_errors=True)

    staging = dest_root / "User_Data" / "update_cache" / "runtime_extract"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    _log(log, f"解压 {archive.name} …")
    # Always extract via Python tarfile with path checks (OS tar has no easy filter)
    try:
        with tarfile.open(archive, "r:*") as tf:
            members = _safe_tar_members(tf, staging)
            try:
                tf.extractall(path=staging, members=members, filter="data")  # type: ignore[call-arg]
            except TypeError:
                tf.extractall(path=staging, members=members)
    except ProvisionError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(staging, ignore_errors=True)
        raise ProvisionError(f"tar 解压失败：{e}") from e

    # Normalize: staging/Runtime or staging/**/python.exe → dest_root/Runtime
    candidate_rt = staging / "Runtime"
    if not (candidate_rt / "python.exe").is_file():
        nested = list(staging.glob("**/python.exe"))
        for cand in nested:
            parent = cand.parent
            if parent.name.lower() == "runtime" or (
                parent / "Lib" / "site-packages"
            ).is_dir():
                candidate_rt = parent
                break
    if not (candidate_rt / "python.exe").is_file():
        shutil.rmtree(staging, ignore_errors=True)
        raise ProvisionError(
            "解压后未找到 Runtime\\python.exe。请检查 tar 是否完整或重试。"
        )

    final_rt = dest_root / "Runtime"
    if final_rt.exists():
        shutil.rmtree(final_rt, ignore_errors=True)
    try:
        shutil.move(str(candidate_rt), str(final_rt))
    except Exception as e:
        shutil.rmtree(staging, ignore_errors=True)
        raise ProvisionError(f"移动 Runtime 失败：{e}") from e
    shutil.rmtree(staging, ignore_errors=True)

    if not (final_rt / "python.exe").is_file():
        raise ProvisionError(
            "解压后未找到 Runtime\\python.exe。请检查 tar 是否完整或重试。"
        )


def provision_runtime(
    variant: str,
    *,
    root: Path | None = None,
    progress: Optional[ProgressCb] = None,
    log: Optional[LogCb] = None,
    keep_archive: bool = False,
    prefer_remote_catalog: bool = True,
    download_core_models: bool = True,
    force: bool = False,
) -> tuple[bool, str]:
    """Download Runtime for *variant* into *root*/Runtime.

    Returns (ok, message).
    """
    base = Path(root or ROOT)
    var = (variant or "nvidia").strip().lower()
    if var not in ("nvidia", "amd", "nvidia50"):
        var = "nvidia"

    if runtime_ready(base) and not force:
        try:
            write_package_meta(base, var)
        except Exception:
            pass
        return True, "Runtime 已就绪，跳过下载。"

    if force and (base / "Runtime").exists():
        _log(log, "强制重装：移除现有 Runtime…")
        try:
            shutil.rmtree(base / "Runtime", ignore_errors=True)
        except Exception as e:
            _log(log, f"移除旧 Runtime 时：{e}")

    try:
        spec: RuntimeSpec = resolve_runtime_spec(
            var, prefer_remote=prefer_remote_catalog
        )
    except Exception as e:
        return False, f"解析 Runtime 清单失败：{e}"

    part = spec.primary
    if not part.urls:
        return False, "清单中没有可用的 Runtime 下载地址。"

    _log(
        log,
        f"准备下载 {spec.label} Runtime "
        f"v{spec.version or '?'}（约 {format_size(spec.size_bytes or part.size_bytes)}）",
    )
    _progress(progress, "prepare", 0, part.size_bytes or 1)

    cache = cache_dir(base)
    dest_file = cache / (part.name or f"runtime-{var}.tar")

    # Resume: reuse verified cache
    if dest_file.is_file() and part.sha256:
        try:
            from launcher.online.downloader import _verify_sha256

            _verify_sha256(dest_file, part.sha256)
            _log(log, f"使用本地缓存：{dest_file.name}")
        except Exception:
            try:
                dest_file.unlink()
            except OSError:
                pass

    if not dest_file.is_file():
        try:
            _download_part(
                part.urls,
                dest_file,
                sha256=part.sha256,
                progress=progress,
                log=log,
            )
        except ProvisionError as e:
            return False, str(e)
        except Exception as e:
            return False, f"下载失败：{e}"

    try:
        _progress(progress, "extract", 0, 1)
        _extract_tar(dest_file, base, log=log)
        _progress(progress, "extract", 1, 1)
    except ProvisionError as e:
        return False, str(e)
    except Exception as e:
        return False, f"解压失败：{e}"

    try:
        write_package_meta(
            base,
            var,
            label=spec.label,
            runtime_version=spec.version,
            runtime_source="cnb_release",
            provisioned_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        _log(log, f"已写入 package_meta.json（variant={var}）")
    except Exception as e:
        _log(log, f"写 package_meta 跳过：{e}")

    # Seed accel default
    try:
        from launcher.config_store import load_config, save_config
        from launcher.package_meta import VARIANT_DEFAULTS

        cfg = load_config()
        accel = VARIANT_DEFAULTS.get(var, {}).get("accel_default") or "auto"
        if not cfg.get("accel_backend") or cfg.get("accel_backend") == "auto":
            cfg["accel_backend"] = accel
            save_config(cfg)
    except Exception:
        pass

    if download_core_models:
        try:
            from launcher.engine_core import ensure_engine_core, engine_core_ready

            if engine_core_ready(base):
                _log(log, "引擎资源（engine-core）已就绪")
            else:
                _log(log, "补全 engine-core（Hubert / RMVPE / ffmpeg）…")
                _progress(progress, "models", 0, 1)
                ok_m, msg_m = ensure_engine_core(
                    root=base, progress=progress, log=log
                )
                _log(log, msg_m)
                _progress(progress, "models", 1, 1)
                if not ok_m:
                    _log(log, f"引擎资源未完全成功（可稍后在启动器重试）：{msg_m}")
        except Exception as e:
            _log(log, f"引擎资源补全跳过：{e}")

    if not keep_archive:
        try:
            # Keep multi-GB cache only if user wants; default delete to free disk
            if dest_file.is_file() and dest_file.stat().st_size > 500_000_000:
                dest_file.unlink()
                _log(log, "已删除 Runtime 安装包缓存以节省空间")
        except OSError:
            pass

    if not runtime_ready(base):
        return False, "安装结束但 Runtime 仍不可用，请重试或检查磁盘空间。"

    return True, f"{spec.label} 运行环境已安装完成。"


def ensure_runtime(
    *,
    variant: str | None = None,
    root: Path | None = None,
    progress: Optional[ProgressCb] = None,
    log: Optional[LogCb] = None,
    force: bool = False,
) -> tuple[bool, str]:
    """Ensure Runtime exists; download if missing (or force=True)."""
    base = Path(root or ROOT)
    if runtime_ready(base) and not force:
        return True, "Runtime 已就绪。"

    var = variant
    if not var:
        try:
            from launcher.package_meta import load_package_meta

            var = str(load_package_meta(base).get("variant") or "nvidia")
        except Exception:
            var = "nvidia"
    return provision_runtime(
        var,
        root=base,
        progress=progress,
        log=log,
        download_core_models=True,
        force=force,
    )
