# -*- coding: utf-8 -*-
"""E-03 唯一后端策略：TM_ACCEL 显式值 > TM_USE_DML / --dml > auto。

`_resolve_accel` 只读环境变量，不实例化 Config，不碰 torch 探测，
所以可以安全单测。device_config 的「显式 cpu 不再探测 CUDA」分支由
集成验收覆盖。
"""

import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class ResolveAccel(unittest.TestCase):
    def _resolve(self, cli_dml=False):
        from configs.config import Config

        # Config 被 singleton_variable 包成了函数，__wrapped__ 才是原类。
        return Config.__wrapped__._resolve_accel(cli_dml)

    def test_explicit_values_win(self):
        env = {"TM_ACCEL": "cpu", "TM_USE_DML": "1"}
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(self._resolve(cli_dml=True), "cpu")

    def test_aliases_normalize(self):
        for raw, want in [
            ("directml", "dml"),
            ("amd", "dml"),
            ("intel", "dml"),
            ("nvidia", "cuda"),
            ("CUDA", "cuda"),
        ]:
            with patch.dict(os.environ, {"TM_ACCEL": raw}, clear=False):
                self.assertEqual(self._resolve(), want, raw)

    def test_legacy_dml_force_used_only_without_explicit_choice(self):
        with patch.dict(os.environ, {"TM_USE_DML": "1"}, clear=False):
            os.environ.pop("TM_ACCEL", None)
            self.assertEqual(self._resolve(), "dml")
        with patch.dict(os.environ, {"TM_ACCEL": "cuda", "TM_USE_DML": "1"}):
            self.assertEqual(self._resolve(), "cuda")

    def test_cli_dml_falls_under_legacy(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TM_ACCEL", None)
            os.environ.pop("TM_USE_DML", None)
            self.assertEqual(self._resolve(cli_dml=True), "dml")
            self.assertEqual(self._resolve(cli_dml=False), "auto")

    def test_garbage_value_is_auto(self):
        with patch.dict(os.environ, {"TM_ACCEL": "vulkan"}, clear=False):
            os.environ.pop("TM_USE_DML", None)
            self.assertEqual(self._resolve(), "auto")


if __name__ == "__main__":
    unittest.main()
