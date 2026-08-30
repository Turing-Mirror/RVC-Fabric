# -*- coding: utf-8 -*-
"""tools/block_geometry.py —— 分块几何只能有一份。

这段算术原来在三个地方各写一份：`gui_v1.start_vc`、`tools/benchmark_realtime.py`，
以及将来加工流程里的离线渲染器。**三份不一致时没有任何征兆**——渲染出来的声音
听着像那么回事，只是和用户实际听到的差了半个块，照着它调出来的参数到了用户
机器上就不对。

所以这里钉两件事：

1. 数值与 `gui_v1` 原来那份公式**逐字相同**（下面 `_legacy` 是从 gui_v1 抄来的
   原式，改动任何一边都会让这条测试红）；
2. `gui_v1` 和 `benchmark_realtime` 都**确实从这一份取**，没有偷偷留一份自己的。

纯 stdlib，不需要 Runtime。
"""

from __future__ import annotations

import importlib.util
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 源文件在仓库根。`app/src-tauri/engine-payload/` 是 prepare_engine_payload.py
# 每次构建重新生成的副本，且被 gitignore —— 改那边等于没改。
SRC = ROOT

# 按文件路径加载，**不动 sys.path**。
#
# 早先这里是 `sys.path.insert(0, tools/)`，结果整个 discover 跑下来 sys.path
# 里多了一条 tools/，让 test_separate_worker 那条「setup 之前 pymss_core
# 应当找不到」的断言红了 —— 一条测试改坏了另一条测试的环境。
_spec = importlib.util.spec_from_file_location(
    "_block_geometry_under_test", os.path.join(SRC, "tools", "block_geometry.py")
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
geometry, zc_of = _mod.geometry, _mod.zc_of


def _legacy(sr: int, block_time: float, crossfade_time: float, extra_time: float) -> dict:
    """gui_v1.start_vc 原来那份公式，逐字照抄（round 用 numpy 的等价行为）。"""
    zc = sr // 100
    block_frame = int(round(block_time * sr / zc)) * zc
    block_frame_16k = 160 * block_frame // zc
    crossfade_frame = int(round(crossfade_time * sr / zc)) * zc
    sola_buffer_frame = min(crossfade_frame, 4 * zc)
    sola_search_frame = zc
    extra_frame = int(round(extra_time * sr / zc)) * zc
    input_frames = extra_frame + crossfade_frame + sola_search_frame + block_frame
    return {
        "zc": zc,
        "block_frame": block_frame,
        "block_frame_16k": block_frame_16k,
        "crossfade_frame": crossfade_frame,
        "sola_buffer_frame": sola_buffer_frame,
        "sola_search_frame": sola_search_frame,
        "extra_frame": extra_frame,
        "input_frames": input_frames,
        "input_res_len": 160 * input_frames // zc,
        "skip_head": extra_frame // zc,
        "return_length": (block_frame + sola_buffer_frame + sola_search_frame) // zc,
    }


class BlockGeometryTests(unittest.TestCase):
    def test_matches_the_original_formula_everywhere(self):
        """遍历真实会出现的组合，一个键都不许差。"""
        checked = 0
        for sr in (32000, 40000, 44100, 48000):
            for block_time in (0.10, 0.15, 0.18, 0.25, 0.30, 0.40):
                for crossfade in (0.02, 0.05, 0.08, 0.15):
                    for extra in (0.5, 1.0, 2.5, 5.0):
                        got = geometry(sr, block_time, crossfade, extra)
                        want = _legacy(sr, block_time, crossfade, extra)
                        self.assertEqual(got, want, f"{sr} {block_time} {crossfade} {extra}")
                        checked += 1
        self.assertGreater(checked, 300)

    def test_lengths_stay_aligned_to_zc(self):
        """对齐一旦破了，16k 侧的换算就不再是整数，块会一点一点错位。"""
        for sr in (32000, 40000, 44100, 48000):
            g = geometry(sr, 0.25, 0.05, 2.5)
            self.assertEqual(g["zc"], zc_of(sr))
            self.assertEqual(g["block_frame"] % g["zc"], 0)
            self.assertEqual(g["crossfade_frame"] % g["zc"], 0)
            self.assertEqual(g["extra_frame"] % g["zc"], 0)
            self.assertEqual(g["block_frame_16k"] % 160, 0)

    def test_sola_buffer_is_capped(self):
        """交叉淡化拉得再长，SOLA 的对齐窗最多 4 个 zc。"""
        g = geometry(48000, 0.25, 1.0, 2.5)
        self.assertEqual(g["sola_buffer_frame"], 4 * g["zc"])
        g = geometry(48000, 0.25, 0.02, 2.5)
        self.assertEqual(g["sola_buffer_frame"], g["crossfade_frame"])

    def test_zero_and_negative_times_do_not_explode(self):
        """坏配置不该让开流直接崩，长度归零即可。"""
        g = geometry(48000, 0.25, 0.0, 0.0)
        self.assertEqual(g["crossfade_frame"], 0)
        self.assertEqual(g["extra_frame"], 0)
        self.assertEqual(g["skip_head"], 0)
        g = geometry(48000, 0.25, -1.0, -1.0)
        self.assertEqual(g["crossfade_frame"], 0)
        self.assertEqual(g["extra_frame"], 0)
        with self.assertRaises(ValueError):
            geometry(0, 0.25, 0.05, 2.5)

    def test_rounding_is_nearest_not_toward_zero(self):
        """int() 是向零取整，每块都短一点，累积起来就是输出比输入慢一截。"""
        # 44100 上 0.25 秒 = 25.0 个 zc，正好；换个不整除的值才看得出差别。
        sr, zc = 44100, 441
        self.assertEqual(geometry(sr, 0.117, 0.05, 2.5)["block_frame"], round(0.117 * sr / zc) * zc)
        self.assertNotEqual(int(0.117 * sr / zc) * zc, round(0.117 * sr / zc) * zc)

    def test_both_call_sites_use_the_shared_module(self):
        """谁都不许再留一份自己的公式。"""
        with open(os.path.join(SRC, "gui_v1.py"), encoding="utf-8") as f:
            gui = f.read()
        with open(os.path.join(SRC, "tools", "benchmark_realtime.py"), encoding="utf-8") as f:
            bench = f.read()

        self.assertIn("from tools.block_geometry import geometry", gui)
        self.assertIn("from block_geometry import geometry", bench)

        # gui_v1 里不该再出现 `min(self.crossfade_frame, 4 * self.zc)` 这种
        # 自己算的痕迹（注释里提到不算）。
        code = "\n".join(
            line for line in gui.splitlines() if not line.lstrip().startswith("#")
        )
        self.assertNotIn("min(self.crossfade_frame, 4 * self.zc)", code)
        # gui_v1 里有两处开流（RVC 与无模型 DSP），两处都必须接过来。
        self.assertEqual(
            code.count("from tools.block_geometry import geometry"),
            2,
            "gui_v1 有两处开流，两处都要用共享几何",
        )
        self.assertIsNone(
            re.search(r"self\.block_frame\s*=\s*\(\s*\n\s*int\(", code),
            "gui_v1 又自己算 block_frame 了",
        )


if __name__ == "__main__":
    unittest.main()
