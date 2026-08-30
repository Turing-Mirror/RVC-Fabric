# -*- coding: utf-8 -*-
"""音高纠错：只删算错的，不碰人的表达。

这一组测试里最重要的不是「错误被修掉了」，是**表达没被削掉**：
颤音、滑音、真实的大跳都要原样留下。平滑做法会把它们和错误一起抹掉，
而用户表达得越好被削得越狠 —— 那正是这份实现要避免的。
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    key = "_f0_repair_under_test"
    spec = importlib.util.spec_from_file_location(
        key, os.path.join(ROOT, "tools", "f0_repair.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


class F0RepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    # ---- 该修的 ----------------------------------------------------------

    def test_an_octave_error_is_folded_back(self):
        f0 = np.full(20, 220.0)
        f0[10] = 440.0
        out, stats = self.m.repair(f0)
        self.assertEqual(stats["octave"], 1)
        self.assertAlmostEqual(out[10], 220.0, places=6)
        # 别的帧一个都不许动。
        np.testing.assert_allclose(np.delete(out, 10), np.delete(f0, 10))

    def test_an_octave_error_downward_is_folded_up(self):
        f0 = np.full(20, 220.0)
        f0[7] = 110.0
        out, stats = self.m.repair(f0)
        self.assertEqual(stats["octave"], 1)
        self.assertAlmostEqual(out[7], 220.0, places=6)

    def test_pitch_in_a_silent_frame_is_cleared(self):
        f0 = np.full(20, 220.0)
        voiced = np.ones(20, dtype=bool)
        voiced[5:8] = False  # 呼吸
        out, stats = self.m.repair(f0, voiced)
        self.assertEqual(stats["unvoiced"], 3)
        self.assertTrue(np.all(out[5:8] == 0.0))

    def test_an_isolated_wild_value_is_pulled_back(self):
        f0 = np.full(20, 220.0)
        f0[12] = 220.0 * 2 ** (9 / 12)  # 大九度，不是八度
        out, stats = self.m.repair(f0)
        self.assertEqual(stats["island"], 1)
        self.assertAlmostEqual(out[12], 220.0, places=6)

    # ---- 不该碰的（这一组才是重点）---------------------------------------

    def test_vibrato_survives_untouched(self):
        """颤音是**周期性的小幅突变**，平滑会把它抹平，纠错不能碰它。"""
        t = np.arange(200)
        f0 = 220.0 * 2 ** (0.4 * np.sin(2 * np.pi * t / 12) / 12)  # ±0.4 半音
        out, stats = self.m.repair(f0)
        self.assertEqual(stats["octave"], 0)
        self.assertEqual(stats["island"], 0)
        np.testing.assert_allclose(out, f0)

    def test_a_real_glide_survives(self):
        """一段真实的滑音里，每一帧都在跳。

        只看「跳了一下」的实现会把整段判成一串错误，然后改成一条直线。
        所以判据要求**前后都稳定**。
        """
        f0 = 150.0 * 2 ** (np.linspace(0, 12, 100) / 12)  # 一个八度的滑音
        out, stats = self.m.repair(f0)
        self.assertEqual(stats["octave"], 0)
        self.assertEqual(stats["island"], 0)
        np.testing.assert_allclose(out, f0)

    def test_a_real_leap_between_two_steady_notes_survives(self):
        """两个稳定音之间的六度跳进是演唱，不是错误。"""
        f0 = np.concatenate([np.full(20, 220.0), np.full(20, 220.0 * 2 ** (9 / 12))])
        out, stats = self.m.repair(f0)
        self.assertEqual(stats["octave"], 0)
        # 跳进处两侧不是「一帧孤立」，不该被拉回。
        np.testing.assert_allclose(out, f0)

    def test_shouting_bursts_are_not_flattened(self):
        """喊话时音高会大幅抬起并保持 —— 保持住的就不是野值。"""
        f0 = np.concatenate([np.full(15, 180.0), np.full(15, 320.0), np.full(15, 180.0)])
        out, _ = self.m.repair(f0)
        np.testing.assert_allclose(out, f0)

    # ---- 边界 ------------------------------------------------------------

    def test_empty_and_all_silent_input(self):
        m = self.m
        out, stats = m.repair(np.array([]))
        self.assertEqual(out.size, 0)
        self.assertEqual(stats["frames"], 0)
        out, stats = m.repair(np.zeros(30))
        self.assertTrue(np.all(out == 0.0))
        self.assertEqual(stats["octave"], 0)

    def test_edges_are_left_alone(self):
        """首尾没有完整上下文，判不了 —— 判了就是猜。"""
        f0 = np.full(10, 220.0)
        f0[0] = 440.0
        f0[-1] = 440.0
        out, stats = self.m.repair(f0)
        self.assertEqual(stats["octave"], 0)
        self.assertAlmostEqual(out[0], 440.0)
        self.assertAlmostEqual(out[-1], 440.0)

    def test_voiced_mask_of_wrong_length_is_ignored_not_crashed(self):
        """长度对不上时**不猜**：拿 f0 自己反推有声与否是循环论证。"""
        f0 = np.full(20, 220.0)
        out, stats = self.m.repair(f0, np.ones(5, dtype=bool))
        self.assertEqual(stats["unvoiced"], 0)
        np.testing.assert_allclose(out, f0)

    def test_stats_expose_how_much_was_changed(self):
        """某台机器上八度错误占到百分之几，说明音高算法本身有问题，
        而不是纠错该更努力 —— 这个数必须能被看见。"""
        f0 = np.full(60, 220.0)
        for i in (10, 20, 30):
            f0[i] = 440.0
        _, stats = self.m.repair(f0)
        self.assertEqual(stats["octave"], 3)
        self.assertEqual(stats["frames"], 60)


class WiringTests(unittest.TestCase):
    """接线：写好了必须挂上，而且要挂在**所有音高算法都会经过**的那一处。"""

    def _read(self, rel: str) -> str:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return f.read()

    def test_it_hangs_on_the_single_exit_point(self):
        """挂在 get_f0_post，不是挂在各个提取器里。

        挂一处等于 rmvpe / fcpe / harvest / crepe / pm 全都覆盖到，
        也不会出现「换个音高算法纠错就没了」这种事。
        """
        src = self._read(os.path.join("infer", "lib", "rtrvc.py"))
        post = src[src.index("def get_f0_post"):]
        post = post[: post.index("def _repair_f0")]
        self.assertIn("self._repair_f0(f0)", post)

    def test_a_failure_degrades_to_no_repair_not_to_no_sound(self):
        """热路径上的可选增强，坏掉的正确表现是「没有增强」。

        用户宁可听见一次八度错误，也不要整条流断掉。
        """
        src = self._read(os.path.join("infer", "lib", "rtrvc.py"))
        body = src[src.index("def _repair_f0"):]
        body = body[: body.index("def _bench_sync")]
        self.assertIn("except Exception:", body)
        self.assertIn("return f0", body)

    def test_default_is_off_everywhere(self):
        """它改变声音，所以必须是用户自己点开的 —— 三处默认值要一致。"""
        self.assertIn(
            'self.f0_repair: bool = False', self._read("gui_v1.py")
        )
        self.assertIn(
            'm.insert("f0_repair".into(), json!(false));',
            self._read(os.path.join("app", "src-tauri", "src", "config.rs")),
        )
        src = self._read(os.path.join("infer", "lib", "rtrvc.py"))
        self.assertIn('getattr(self, "f0_repair", False)', src)

    def test_it_is_a_hot_key_so_users_can_a_b_it(self):
        """转着的时候能开关 —— 否则用户没法当场对比，也就判断不了它好不好。"""
        cfg = self._read(os.path.join("app", "src-tauri", "src", "config.rs"))
        hot = cfg[cfg.index("pub const HOT_KEYS"):]
        hot = hot[: hot.index("pub const COLD_KEYS")]
        self.assertIn('"f0_repair"', hot)
        self.assertIn('elif event == "f0_repair":', self._read("gui_v1.py"))

    def test_the_switch_is_applied_when_the_stream_opens(self):
        """不带的话用户要先动一次开关才生效，而他上次的选择本该被记住。"""
        gui = self._read("gui_v1.py")
        self.assertIn(
            'self.rvc.f0_repair = bool(getattr(self.gui_config, "f0_repair", False))', gui
        )


if __name__ == "__main__":
    unittest.main()
