# -*- coding: utf-8 -*-
"""configs/inuse 里的 JSON 坏了不能再把整个 Config 拖死。

26.8.19/1：用户点了「清理缓存」之后跑性能测试，Config() 读到一个空的
inuse JSON 直接抛 JSONDecodeError —— bench、实时 worker、离线转换全都
起不来。修复是回源头重拷一份再读。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import torch  # noqa: F401

    HAS_TORCH = True
except Exception:
    HAS_TORCH = False

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "configs" / "config.py"
    spec = importlib.util.spec_from_file_location("tm_configs_config", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@unittest.skipUnless(HAS_TORCH, "configs.config imports torch")
class LoadConfigJsonTests(unittest.TestCase):
    def _stage(self, root: Path):
        mod = _load()
        for rel in mod.version_config_list:
            src = root / "configs" / rel
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_text(json.dumps({"file": rel}), encoding="utf-8")
        return mod

    def test_empty_inuse_json_is_restored_from_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mod = self._stage(root)
            bad = root / "configs" / "inuse" / "v2" / "48k.json"
            bad.parent.mkdir(parents=True, exist_ok=True)
            bad.write_text("", encoding="utf-8")

            old = os.getcwd()
            os.chdir(root)
            try:
                d = mod.Config.load_config_json()
            finally:
                os.chdir(old)

            self.assertEqual(d["v2/48k.json"], {"file": "v2/48k.json"})
            # 盘上那份也要被修好，下一次读不用再走一遍恢复。
            self.assertEqual(
                json.loads(bad.read_text(encoding="utf-8")), {"file": "v2/48k.json"}
            )

    def test_garbage_inuse_json_is_restored_from_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mod = self._stage(root)
            bad = root / "configs" / "inuse" / "v1" / "32k.json"
            bad.parent.mkdir(parents=True, exist_ok=True)
            bad.write_text("{ half of a json", encoding="utf-8")

            old = os.getcwd()
            os.chdir(root)
            try:
                d = mod.Config.load_config_json()
            finally:
                os.chdir(old)

            self.assertEqual(d["v1/32k.json"], {"file": "v1/32k.json"})


if __name__ == "__main__":
    unittest.main()
