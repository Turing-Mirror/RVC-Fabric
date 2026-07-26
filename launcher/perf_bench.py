# -*- coding: utf-8 -*-
"""Quick offline performance test driven from the shell (diagnostics helper).

The frozen shell has no torch/numpy, so the actual measurement runs inside the
embedded Runtime via ``tools/benchmark_realtime.py``. This module only builds
the command line from the user's *actual* realtime settings, launches it with
a cleaned environment, and drops the JSON result into
``User_Data/perf_reports/bench_*.json`` — right next to the session perf
reports, so diagnostics bundles pick it up automatically.

Tk-free and subprocess-injectable so it stays unit-testable on hosts without
the ML stack.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

# harvest needs gui_v1's multiprocess worker pool — not benchable offline
_BENCH_F0 = frozenset({"fcpe", "rmvpe", "pm", "crepe"})
_FALLBACK_F0 = "fcpe"

# ~15-45 s of measured blocks on mid GPUs — enough samples for a stable p95
QUICK_N_BLOCKS = 60
# model load + first-block warmup can take minutes on a cold HDD
BENCH_TIMEOUT_S = 600
_KEEP_BENCH = 10


def bench_python(root: Path | str) -> str | None:
    """Runtime python(w) under *root*, or None when no Runtime is provisioned.

    Mirrors launcher.paths._runtime_bases but stays relative to the given root
    so it is testable; deliberately never falls back to the host interpreter —
    a host python without torch would just fail late and slower.
    """
    root = Path(root)
    bases = (
        root / "Runtime",
        root / "runtime",
        root / "RVCMAX" / "RVCMAX_Nvidia_xiaoyuan" / "Runtime",
    )
    for base in bases:
        for name in ("pythonw.exe", "python.exe"):
            p = base / name
            if p.is_file():
                return str(p)
    return None


def bench_ready(root: Path | str, pth: str) -> tuple[bool, str]:
    """(ok, reason-if-not) — can a quick benchmark run right now?"""
    root = Path(root)
    if bench_python(root) is None:
        return False, "Runtime 未就绪（请先在启动器补全运行环境）"
    if not (root / "tools" / "benchmark_realtime.py").is_file():
        return False, "缺少性能测试脚本 tools/benchmark_realtime.py"
    if not pth or not Path(pth).is_file():
        return False, "未找到当前音色的模型文件"
    return True, ""


def bench_f0method(cfg_f0: str) -> str:
    f0 = (cfg_f0 or "").strip().lower()
    return f0 if f0 in _BENCH_F0 else _FALLBACK_F0


def build_bench_command(
    python_exe: str,
    root: Path | str,
    pth: str,
    index_path: str,
    cfg: dict | None,
    out_json: Path | str,
    n_blocks: int = QUICK_N_BLOCKS,
) -> list[str]:
    """Benchmark argv mirroring the user's realtime settings (block/f0/index)."""
    cfg = cfg or {}
    cmd = [
        str(python_exe),
        str(Path(root) / "tools" / "benchmark_realtime.py"),
        "--pth",
        str(pth),
        "--f0method",
        bench_f0method(str(cfg.get("f0method") or "")),
        "--block-time",
        str(float(cfg.get("block_time") or 0.25)),
        "--crossfade-time",
        str(float(cfg.get("crossfade_length") or 0.05)),
        "--extra-time",
        str(float(cfg.get("extra_time") or 2.5)),
        "--n-blocks",
        str(int(n_blocks)),
        "--json-out",
        str(out_json),
    ]
    try:
        rate = float(cfg.get("index_rate") or 0.0)
    except (TypeError, ValueError):
        rate = 0.0
    if index_path and rate > 0 and Path(index_path).is_file():
        cmd += ["--index", str(index_path), "--index-rate", str(rate)]
    return cmd


def run_benchmark(
    root: Path | str,
    pth: str,
    index_path: str = "",
    cfg: dict | None = None,
    *,
    n_blocks: int = QUICK_N_BLOCKS,
    timeout_s: float = BENCH_TIMEOUT_S,
    popen=None,
) -> dict:
    """Run one quick benchmark; never raises.

    Returns ``{"ok": bool, "json_path": str, "summary": dict, "error": str}``.
    ``popen`` is injectable for tests; the default launches Runtime python with
    the cleaned worker environment and tees output to logs/perf_bench.log.
    """
    root = Path(root)

    def fail(msg: str) -> dict:
        return {"ok": False, "json_path": "", "summary": {}, "error": msg}

    ok, why = bench_ready(root, pth)
    if not ok:
        return fail(why)
    py = bench_python(root)
    out_dir = root / "User_Data" / "perf_reports"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return fail("无法创建 perf_reports 目录：%s" % e)
    out_json = out_dir / time.strftime("bench_%Y%m%d_%H%M%S.json")
    cmd = build_bench_command(py, root, pth, index_path, cfg, out_json, n_blocks)

    try:
        if popen is None:
            from launcher.paths import USER_LOGS
            from launcher.win_util import _env_for_runtime_python, run_gui_process

            proc = run_gui_process(
                cmd,
                cwd=root,
                env=_env_for_runtime_python(),
                log_path=USER_LOGS / "perf_bench.log",
                hide_console=True,
            )
        else:
            proc = popen(cmd)
    except Exception as e:
        return fail("性能测试进程启动失败：%s" % e)

    try:
        code = proc.wait(timeout=timeout_s)
    except Exception as e:
        try:
            proc.kill()
        except Exception:
            pass
        if isinstance(e, (subprocess.TimeoutExpired, TimeoutError)):
            return fail("性能测试超时（超过 %d 秒），已跳过" % int(timeout_s))
        return fail("性能测试等待失败：%s" % e)

    if code != 0 or not out_json.is_file():
        return fail("性能测试未完成（详见 User_Data/logs/perf_bench.log）")
    try:
        data = json.loads(out_json.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    summary = data.get("summary") if isinstance(data, dict) else None
    _prune(out_dir)
    return {
        "ok": True,
        "json_path": str(out_json),
        "summary": dict(summary or {}),
        "error": "",
    }


def format_bench_summary(summary: dict) -> str:
    """One-line human summary for dialogs; '' when there is nothing to show."""
    if not summary:
        return ""
    try:
        return "均值 %.0fms · p95 %.0fms · RTF %.2f" % (
            float(summary.get("mean_ms") or 0.0),
            float(summary.get("p95_ms") or 0.0),
            float(summary.get("rtf") or 0.0),
        )
    except (TypeError, ValueError):
        return ""


def _prune(dir_path: Path, keep: int = _KEEP_BENCH) -> None:
    try:
        names = sorted(
            p
            for p in dir_path.iterdir()
            if p.name.startswith("bench_") and p.suffix == ".json"
        )
        for p in names[:-keep]:
            p.unlink()
    except OSError:
        pass
