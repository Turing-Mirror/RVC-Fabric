# -*- coding: utf-8 -*-
"""One-click diagnostics bundle.

Packs the files support actually needs into a single zip under
``User_Data/diagnostics/`` so a user can send one file instead of hunting
through folders:

  * ``User_Data/logs/``          — newest log files
  * ``User_Data/perf_reports/``  — newest local perf reports
  * ``User_Data/runtime_control/status.json`` / ``worker.pid``
  * ``User_Data/app_config.json``, ``User_Data/update_state.json``
  * ``configs/inuse/config.json``, ``package_meta.json``
  * ``env.json``                 — python/torch/platform summary (generated)

Local-only; nothing is uploaded. Run from the repo/package root::

    Runtime\\python.exe tools\\collect_diagnostics.py

Pure stdlib so it works even when the ML stack is broken (which is exactly
when support needs it).
"""

from __future__ import annotations

import json
import os
import platform
import sys
import time
import zipfile

_MAX_FILE_BYTES = 8 * 1024 * 1024  # skip anything bigger (runaway logs)
_MAX_PER_DIR = 10  # newest N files per collected directory
# perf reports are ~1 KB each and are exactly what the team optimizes from —
# bundle every kept sample (perf_report keeps 30, bench keeps 10)
_MAX_PERF_REPORTS = 40
_KEEP_BUNDLES = 10


def _newest_files(dir_path: str, limit: int = _MAX_PER_DIR) -> list[str]:
    try:
        names = [
            os.path.join(dir_path, n)
            for n in os.listdir(dir_path)
            if os.path.isfile(os.path.join(dir_path, n))
        ]
    except OSError:
        return []
    names.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return names[:limit]


def gather_files(root: str) -> list[tuple[str, str]]:
    """(arcname, abs_path) pairs for everything worth bundling that exists."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(path: str) -> None:
        if not os.path.isfile(path):
            return
        try:
            size = os.path.getsize(path)
        except OSError:
            return
        arc = os.path.relpath(path, root).replace(os.sep, "/")
        # the explicit list below overlaps with the newest-N directory sweep;
        # duplicate arcnames make ZipFile warn and bloat the bundle
        if arc in seen:
            return
        # Oversized logs: keep a tail so field diags never silently drop
        # realtime_worker.log (review #21)
        if size > _MAX_FILE_BYTES:
            try:
                with open(path, "rb") as f:
                    f.seek(-_MAX_FILE_BYTES, os.SEEK_END)
                    tail = f.read()
                # Drop partial first line so tail is readable
                nl = tail.find(b"\n")
                if 0 <= nl < 4096:
                    tail = tail[nl + 1 :]
                tail_path = path + ".diag_tail"
                with open(tail_path, "wb") as f:
                    f.write(tail)
                seen.add(arc)
                out.append((arc + ".tail", tail_path))
            except OSError:
                return
            return
        seen.add(arc)
        out.append((arc, path))

    for rel_dir, limit in (
        ("User_Data/logs", _MAX_PER_DIR),
        ("User_Data/perf_reports", _MAX_PERF_REPORTS),
    ):
        for p in _newest_files(os.path.join(root, rel_dir), limit):
            add(p)
    for rel in (
        "User_Data/runtime_control/status.json",
        "User_Data/runtime_control/worker.pid",
        "User_Data/runtime_control/gpu_probe.json",
        "User_Data/app_config.json",
        "User_Data/update_state.json",
        "User_Data/logs/runtime_integrity_last.json",
        "User_Data/logs/install_health.log",
        "User_Data/logs/gpu_probe.log",
        "configs/inuse/config.json",
        "package_meta.json",
    ):
        add(os.path.join(root, rel))
    return out


def _cpu_name() -> str:
    """Human CPU model name; registry first (Windows), platform fallback."""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        ) as k:
            name, _ = winreg.QueryValueEx(k, "ProcessorNameString")
            if name:
                return str(name).strip()
    except Exception:
        pass
    return platform.processor() or ""


def _total_ram_gb() -> float | None:
    """Physical RAM in GB via GlobalMemoryStatusEx; None off-Windows/on error."""
    try:
        import ctypes

        class _MemStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_uint32),
                ("dwMemoryLoad", ctypes.c_uint32),
                ("ullTotalPhys", ctypes.c_uint64),
                ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64),
                ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64),
                ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64),
            ]

        st = _MemStatus()
        st.dwLength = ctypes.sizeof(st)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return round(st.ullTotalPhys / (1024**3), 1)
    except Exception:
        pass
    return None


def env_summary(root: str) -> dict:
    """Machine + stack snapshot — the per-machine sample the team optimizes
    from, so it should identify the hardware class (CPU/RAM/OS/GPU), not just
    the Python stack."""
    info = {
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu": _cpu_name(),
        "cpu_count": os.cpu_count() or 0,
        "root": os.path.abspath(root),
        "root_ascii": all(ord(c) < 128 for c in os.path.abspath(root)),
    }
    ram = _total_ram_gb()
    if ram is not None:
        info["ram_total_gb"] = ram
    try:
        win_ver = "-".join(x for x in platform.win32_ver() if x)
        if win_ver:
            info["windows"] = win_ver
    except Exception:
        pass
    try:
        import torch  # optional: broken ML stack must not break diagnostics

        info["torch"] = str(torch.__version__)
        info["cuda_available"] = bool(torch.cuda.is_available())
        if info["cuda_available"]:
            info["gpu"] = torch.cuda.get_device_name(0)
    except Exception as e:
        info["torch"] = "unavailable: %s" % e
    return info


def collect(root: str = ".", out_dir: str | None = None) -> str:
    """Build the bundle; returns the zip path."""
    if out_dir is None:
        out_dir = os.path.join(root, "User_Data", "diagnostics")
    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, time.strftime("diag_%Y%m%d_%H%M%S.zip"))
    files = gather_files(root)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "env.json", json.dumps(env_summary(root), ensure_ascii=False, indent=2)
        )
        for arcname, path in files:
            try:
                zf.write(path, arcname)
            except OSError:
                continue
    _prune(out_dir)
    return zip_path


def _prune(dir_path: str, keep: int = _KEEP_BUNDLES) -> None:
    try:
        names = sorted(
            n
            for n in os.listdir(dir_path)
            if n.startswith("diag_") and n.endswith(".zip")
        )
        for n in names[:-keep]:
            os.remove(os.path.join(dir_path, n))
    except OSError:
        pass


def main() -> int:
    path = collect(os.getcwd())
    print("诊断包已生成: %s" % path)
    print("请将该 zip 文件发送给团队/客服。内容仅包含日志与配置，不含音频或音色模型。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
