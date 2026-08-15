# -*- coding: utf-8 -*-
"""ckpt_worker 不依赖 torch 的部分。"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load():
    path = ROOT / "tools" / "ckpt_worker.py"
    spec = importlib.util.spec_from_file_location("tm_ckpt_worker", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class NameTests(unittest.TestCase):
    def test_rejects_path_chars(self):
        tw = _load()
        with self.assertRaises(SystemExit):
            tw._name_ok("a/b")
        with self.assertRaises(SystemExit):
            tw._name_ok("")
        self.assertEqual(tw._name_ok("  mix_v2  "), "mix_v2")


if __name__ == "__main__":
    unittest.main()
