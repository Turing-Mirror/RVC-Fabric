# -*- coding: utf-8 -*-
"""tools/sts_core.py 的降质回退阶梯。

这条阶梯只处理「根本出不来结果」，**不处理「慢」**：慢就让它慢，用户等得起，
而「多慢算慢」没有客观门限，误判的代价是把他特意选的高质量选项改掉。

纯 stdlib，不需要 Runtime —— 阶梯本身是判断逻辑，不碰 torch。
"""

from __future__ import annotations

import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    """只取 sts_core 里那几个纯函数，不触发它对 torch 的惰性导入。

    按文件路径加载，**不动 sys.path** —— 往 sys.path 里塞 tools/ 会让
    test_separate_worker 那条「setup 之前 pymss_core 应当找不到」的断言红掉。
    """
    spec = importlib.util.spec_from_file_location(
        "_sts_core_under_test", os.path.join(ROOT, "tools", "sts_core.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FallbackLadderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def test_ladder_goes_from_good_to_bad_and_ends_on_cpu(self):
        ladder = self.m.FALLBACK_LADDER
        self.assertGreaterEqual(len(ladder), 2)
        # 最后一档必须是 CPU：它是唯一「一定跑得动」的那档。
        # 措辞跟随产品里既有的说法（「已改用 CPU 重试」），
        # 同一件事不该在两处有两种叫法。
        self.assertEqual(ladder[-1], "CPU")
        # 名字直接显示给用户，不能是代号。
        for name in ladder:
            self.assertNotIn("_", name)
            self.assertTrue(name.strip())

    def test_out_of_memory_steps_down_one_rung_at_a_time(self):
        """显存不足先省显存，再不行才退处理器 —— 别一步跳到最慢那档。"""
        m = self.m
        oom = "CUDA out of memory. Tried to allocate 2.00 GiB"
        self.assertTrue(m.is_oom(oom))
        self.assertEqual(m.next_rung(0, oom), 1)
        self.assertEqual(m.next_rung(1, oom), 2)
        # 已经在最后一档，无处可退。
        self.assertIsNone(m.next_rung(2, oom))

    def test_a_backend_gap_goes_straight_to_cpu(self):
        """后端缺算子时中间那档还是同一个后端，退了也是白退。"""
        m = self.m
        dml = "Could not run 'aten::_fft_r2c' with arguments from the 'PrivateUse1' backend"
        self.assertTrue(m.is_dml_backend_error(dml))
        last = len(m.FALLBACK_LADDER) - 1
        self.assertEqual(m.next_rung(0, dml), last)
        self.assertEqual(m.next_rung(1, dml), last)
        self.assertIsNone(m.next_rung(last, dml))

    def test_being_slow_is_not_a_reason_to_degrade(self):
        """慢不是「无法使用」。这条是整条阶梯的边界。"""
        m = self.m
        for reason in (
            "转换用了 92 秒",
            "推理较慢",
            "Output underrun",
            "",
            "文件读取失败",
            "ffmpeg: No such file or directory",
        ):
            self.assertIsNone(m.next_rung(0, reason), f"{reason!r} 不该触发降质")

    def test_rung_names_never_go_out_of_range(self):
        """退档时崩掉比名字不准糟得多。"""
        m = self.m
        last = m.FALLBACK_LADDER[-1]
        self.assertEqual(m.ladder_rung(99), last)
        self.assertEqual(m.ladder_rung(-5), m.FALLBACK_LADDER[0])

    def test_the_message_code_exists_and_says_which_rung(self):
        """降质是自动的，但不能是无声的。"""
        spec = importlib.util.spec_from_file_location(
            "_msg_codes_under_test", os.path.join(ROOT, "tools", "msg_codes.py")
        )
        codes = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(codes)
        self.assertEqual(codes.STS_DEGRADED, "sts.degraded")
        text = codes.fallback_message(
            codes.STS_DEGRADED, {"why": "显存不足", "rung": "CPU"}
        )
        # 用户要能从这句话里读出两件事：为什么退、退到了哪。
        self.assertIn("显存不足", text)
        self.assertIn("CPU", text)


    def test_a_message_failure_never_breaks_the_conversion(self):
        """报告用的消息，绝不能把它要报告的那件事搞砸。

        第一版是直接 `from msg_codes import ...`，在 tools/ 不在 sys.path 的
        场景下抛 ImportError，整次转换跟着失败 —— 用户丢的是转换结果，
        换来的是一句他本来也看得懂的提示。
        """
        m = self.m
        got = m._degraded_fields("显存不足", "CPU")
        self.assertEqual(got["message_code"], "sts.degraded")
        self.assertIn("显存不足", got["message"])
        self.assertIn("CPU", got["message"])

        # 把 msg_codes 变成不可导入，仍然要拿到一条完整消息。
        import builtins

        real = builtins.__import__

        def boom(name, *a, **kw):
            if name == "msg_codes":
                raise ImportError("simulated")
            return real(name, *a, **kw)

        builtins.__import__ = boom
        try:
            got = m._degraded_fields("显卡后端不支持这一步", "CPU")
        finally:
            builtins.__import__ = real
        self.assertEqual(got["message_code"], "sts.degraded")
        self.assertIn("CPU", got["message"])


if __name__ == "__main__":
    unittest.main()
