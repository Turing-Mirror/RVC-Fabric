# -*- coding: utf-8 -*-
"""tools/audio_probe.py —— 引擎开火前踩音频枚举那颗雷的小兵。

它存在的唯一理由是「死了也不连累别人」，所以这里钉的是它的边界条件，而不是
枚举结果本身（枚举结果依赖这台机器上装了什么声卡，测不了）。
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "audio_probe.py"


class AudioProbeTests(unittest.TestCase):
    def test_it_never_pulls_in_the_heavy_stack(self):
        """探测进程必须便宜。

        它一旦 import torch，就得跟引擎一样等十几秒，而且 torch 自己也可能出事
        —— 那就分不清到底是谁死的，这个小兵也就白派了。
        """
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for heavy in ("torch", "numpy", "fairseq", "faiss", "librosa"):
            self.assertNotIn(heavy, imported, f"探测进程不该 import {heavy}")

    def test_missing_output_path_is_rejected(self):
        p = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            cwd=str(ROOT),
        )
        self.assertEqual(p.returncode, 2)

    def test_it_always_writes_a_verdict_even_when_enumeration_fails(self):
        """壳子靠退出码判定，但诊断包靠这份文件。

        这台开发机上没有 sounddevice，`probe()` 会抛 ModuleNotFoundError ——
        正是要钉住这种情况下它照样把结论写出来、并且以非 0 退出，而不是自己
        崩掉一个 traceback。
        """
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "audio_probe.json"
            p = subprocess.run(
                [sys.executable, str(SCRIPT), str(out)],
                capture_output=True,
                cwd=str(ROOT),
            )
            self.assertIn(p.returncode, (0, 1), p.stderr.decode("utf-8", "replace"))
            self.assertTrue(out.is_file(), "无论成败都要写结论文件")
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("ok", data)
            self.assertIsInstance(data["ok"], bool)
            if data["ok"]:
                self.assertEqual(p.returncode, 0)
                for key in ("hostapis", "inputs", "outputs"):
                    self.assertIn(key, data)
            else:
                self.assertEqual(p.returncode, 1)
                # 报错要留一句人能看的，但不能是整条 traceback。
                self.assertTrue(data.get("error"))
                self.assertLessEqual(len(data["error"]), 300)


if __name__ == "__main__":
    unittest.main()
