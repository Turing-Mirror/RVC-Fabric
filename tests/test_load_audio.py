# -*- coding: utf-8 -*-
"""load_audio 不能把 Popen 参数塞给 ffmpeg-python 的 run()。"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIO_PY = ROOT / "infer" / "lib" / "audio.py"


class TestLoadAudioFfmpegRun(unittest.TestCase):
    def test_run_does_not_take_creationflags(self):
        tree = ast.parse(AUDIO_PY.read_text(encoding="utf-8"))
        func = None
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "load_audio":
                func = node
                break
        self.assertIsNotNone(func, "load_audio missing")
        run_calls = 0
        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            name = ""
            if isinstance(node.func, ast.Attribute):
                name = node.func.attr
            elif isinstance(node.func, ast.Name):
                name = node.func.id
            if name != "run":
                continue
            run_calls += 1
            keys = [k.arg for k in node.keywords if k.arg]
            self.assertNotIn(
                "creationflags",
                keys,
                "ffmpeg.run() 不认 creationflags；藏黑框走 Popen 补丁",
            )
        self.assertGreaterEqual(run_calls, 1, "load_audio 应变过 ffmpeg.run")
