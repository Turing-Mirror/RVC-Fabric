# -*- coding: utf-8 -*-
"""原生监听接管：壳在本地输出上播麦克风时，worker 不得再开自己的监听流，
否则用户会听到两份自己的声音。"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _func(src: str, name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"找不到函数 {name}")


def _first_open_line(fn: ast.FunctionDef) -> int:
    lines = [
        n.lineno
        for n in ast.walk(fn)
        if isinstance(n, ast.Attribute) and n.attr in ("OutputStream", "query_devices")
    ]
    return min(lines) if lines else 10**9


def _guard_line(fn: ast.FunctionDef, flag: str) -> int:
    for n in ast.walk(fn):
        if isinstance(n, ast.If) and flag in ast.dump(n.test):
            if any(isinstance(s, ast.Return) for s in n.body):
                return n.lineno
    raise AssertionError(f"{fn.name} 缺少 {flag} 的提前返回")


class WorkersDeferMonitorToShell(unittest.TestCase):
    def test_gui_v1_checks_flag_before_opening(self):
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        fn = _func(src, "_open_monitor_stream")
        self.assertLess(_guard_line(fn, "_pcm_bridge_monitor"), _first_open_line(fn))
        self.assertIn("pcm_bridge_monitor", src)

    def test_dsp_worker_checks_flag_before_opening(self):
        src = (ROOT / "tools" / "dsp_worker.py").read_text(encoding="utf-8")
        fn = _func(src, "_open_monitor")
        self.assertLess(_guard_line(fn, "shell_monitor"), _first_open_line(fn))
        start = _func(src, "start_vc")
        self.assertIn("pcm_bridge_monitor", ast.dump(start))

    def test_shell_sends_the_flag(self):
        src = (ROOT / "app" / "src-tauri" / "src" / "worker.rs").read_text(encoding="utf-8")
        self.assertIn('"pcm_bridge_monitor"', src)


if __name__ == "__main__":
    unittest.main()
