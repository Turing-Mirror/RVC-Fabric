# -*- coding: utf-8 -*-
"""静音块跳过推理时，音高历史必须照常往前滚。

`cache_pitch` / `cache_pitchf` 只在 `RVC.infer` 内部滚动。壳为了省显卡会跳过
整块静音不调 `infer`，那样这段历史就冻在用户上一次说话的结尾上 —— 他停顿两秒
再开口，模型拿到的是两秒前的音高轨迹，却被当成「紧挨着现在」，起音处对不上，
听感就是每句话前几个字发糊。

这里不碰 torch：真跑一遍 RVC 要先加载模型。验的是两件事 ——
切片算术对不对，以及壳里那条跳过分支到底有没有调 `skip_block`。
"""

from __future__ import annotations

import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import numpy as np
except Exception:  # pragma: no cover - numpy 是 Runtime 的一部分
    np = None


def _roll_silence(cache, shift):
    """`RVC.skip_block` 的切片算术，用 numpy 复刻一份。

    两边必须逐字一致：这里改了而 rtrvc.py 没改，测试就白跑了。
    """
    if shift <= 0:
        return cache
    if shift >= cache.shape[0]:
        cache[:] = 0
        return cache
    cache[:-shift] = cache[shift:].copy()
    cache[-shift:] = 0
    return cache


@unittest.skipIf(np is None, "numpy 不在")
class RollArithmeticTests(unittest.TestCase):
    def test_history_moves_left_and_silence_fills_the_tail(self):
        cache = np.arange(1, 11, dtype=np.int64)
        _roll_silence(cache, 3)
        # 前面的历史整体左移，腾出来的尾部是清音
        np.testing.assert_array_equal(cache, [4, 5, 6, 7, 8, 9, 10, 0, 0, 0])

    def test_a_long_silence_eventually_clears_the_whole_history(self):
        # 这正是我们要的语义：静音够久，模型就该认为「前面什么都没有」，
        # 而不是攥着几秒前那句话的收尾。
        cache = np.arange(1, 11, dtype=np.int64)
        for _ in range(4):
            _roll_silence(cache, 3)
        self.assertTrue(bool((cache == 0).all()), cache)

    def test_an_oversized_shift_clears_instead_of_erroring(self):
        # block 比缓冲还长时 cache[:-shift] 会退化成空切片，静默地什么都不做。
        # 那种「不报错但也没生效」比崩掉更难查，所以单独钉一根。
        cache = np.arange(1, 6, dtype=np.int64)
        _roll_silence(cache, 99)
        self.assertTrue(bool((cache == 0).all()), cache)

    def test_a_zero_shift_leaves_history_untouched(self):
        cache = np.arange(1, 6, dtype=np.int64)
        before = cache.copy()
        _roll_silence(cache, 0)
        np.testing.assert_array_equal(cache, before)


class WiringTests(unittest.TestCase):
    """算术对了但没人调，等于没修。"""

    def test_the_silent_branch_advances_the_pitch_cache(self):
        with open(os.path.join(ROOT, "gui_v1.py"), encoding="utf-8") as fh:
            src = fh.read()
        # 跳过分支的标志是那句 peak 判据；skip_block 必须紧跟在它后面出现。
        i = src.find("if peak < 2e-5:")
        self.assertGreater(i, 0, "静音跳过分支不见了，判据是不是改了？")
        window = src[i : i + 1200]
        self.assertIn(
            "skip_block",
            window,
            "静音块跳过了 infer 却没推进音高历史 —— 每句话开头会发糊",
        )

    def test_rtrvc_exposes_skip_block(self):
        path = os.path.join(ROOT, "infer", "lib", "rtrvc.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        self.assertTrue(
            re.search(r"^\s*def skip_block\(", src, re.M),
            "rtrvc.RVC.skip_block 不见了",
        )
        # 尾部必须填 0（清音）。填成别的值会在起音处插进一段假音高。
        m = re.search(r"def skip_block\(.*?\n(?=\s*def )", src, re.S)
        self.assertIsNotNone(m)
        body = m.group(0)
        self.assertIn("self.cache_pitch[-shift:] = 0", body)
        self.assertIn("self.cache_pitchf[-shift:] = 0", body)


if __name__ == "__main__":
    unittest.main()
