# -*- coding: utf-8 -*-
"""「这次改动没有改变声音」这条铁律。

## 它挡的是什么

用户说「更新完之后声音变了」，今天我们**没法自证**。日志里没有这件事，
诊断包里也没有 —— 只能凭印象争论。

有了这条测试，答案就变成两种之一：

* 测试是绿的 → 「这次一个字节都没动声音」，然后去查真正的原因
  （驱动更新了、他自己动过参数、麦克风换了）；
* 测试是红的 → 我们确实动了，而且当场知道动在哪。

## 它盖住谁

**只盖不该改变声音的那一类改动**：调度、缓冲、线程、CUDA Graph、设备选择、
拼接的实现细节。这些改完输出必须逐位相同。

**不盖会改变声音的那一类**：音高纠错、检索率浮动这些是加法，它们本来就要改
声音，所以它们有各自的开关，而且默认关。这条测试跑在**开关全关**的状态下。

## 为什么用固定波形而不是真实录音

真实录音要几十 MB 进仓库，而且每次跑都要读盘。合成一段确定性的波形，
种子写死，任何机器上生成的都是同一串数 —— 比对才有意义。

## 需要 Runtime 的那一半

真正跑一遍模型要 torch 和音色权重，那是**发版机器上的事**（见
`REALTIME_BASELINE` 说明）。没有 Runtime 的机器上，这份测试仍然会检查
「链路的形状有没有被改动」这一部分 —— 那部分是纯逻辑，人人都能跑。
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HAS_TORCH = importlib.util.find_spec("torch") is not None


def _load(rel: str, key: str):
    spec = importlib.util.spec_from_file_location(key, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


def fixed_signal(n: int = 48000) -> np.ndarray:
    """一段确定性的测试波形。

    带滑动基频的锯齿 + 一点呼吸噪声：既有明确的音高（音高纠错那一路会看它），
    也有宽频成分（拼接和降噪那一路会看它）。种子写死，任何机器上都一样。
    """
    t = np.arange(n, dtype=np.float64) / 16000.0
    f0 = 130.0 * 2 ** (0.5 * np.sin(2 * np.pi * 0.25 * t))
    phase = 2 * np.pi * np.cumsum(f0) / 16000.0
    saw = 2.0 * ((phase / (2 * np.pi)) % 1.0) - 1.0
    noise = np.random.default_rng(0).standard_normal(n)
    return (0.35 * saw + 0.02 * noise).astype(np.float32)


def digest(audio: np.ndarray) -> str:
    """波形的指纹。逐位比对用这个，比存一整段参考音频省事得多。"""
    return hashlib.sha256(np.asarray(audio, dtype=np.float32).tobytes()).hexdigest()


class FixtureTests(unittest.TestCase):
    """测试素材本身必须是确定性的，否则后面全部无从谈起。"""

    def test_the_signal_is_reproducible(self):
        self.assertEqual(digest(fixed_signal()), digest(fixed_signal()))

    def test_the_signal_has_both_pitch_and_broadband_content(self):
        a = fixed_signal()
        self.assertGreater(float(np.std(a)), 0.05)
        self.assertLess(float(np.max(np.abs(a))), 1.0)


class ShapeTests(unittest.TestCase):
    """链路的形状：不需要 Runtime 就能查的那一部分。

    这些断言盯的是「有没有人在不该改变声音的地方动了会改变声音的东西」。
    """

    def _read(self, rel: str) -> str:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return f.read()

    def test_every_sound_changing_addition_is_behind_a_switch(self):
        """修正层的每一项都必须能单独关掉，而且默认关。

        做成一整块开关的话，某个角色上出问题用户就只能全关，
        前面几项的收益一起没了。
        """
        cfg = self._read(os.path.join("app", "src-tauri", "src", "config.rs"))
        # 目前只有音高纠错一项。加新项时这张表要跟着长 ——
        # 而这条断言会在忘记加默认值时红。
        for key in ("f0_repair",):
            self.assertIn(f'm.insert("{key}".into(), json!(false));', cfg,
                          f"{key} 必须有一个默认关的开关")

    def test_the_geometry_has_exactly_one_source(self):
        """块几何变了，声音就变了 —— 而它一度在三个地方各有一份。"""
        gui = self._read("gui_v1.py")
        code = "\n".join(l for l in gui.splitlines() if not l.lstrip().startswith("#"))
        self.assertNotIn("min(self.crossfade_frame, 4 * self.zc)", code)
        self.assertEqual(code.count("from tools.block_geometry import geometry"), 2)

    def test_the_repair_hook_defaults_to_off_in_the_engine(self):
        """壳里默认关还不够 —— 引擎侧自己也要默认关。

        两处只要有一处默认开，一份没有这个键的旧配置就会让声音变了。
        """
        rt = self._read(os.path.join("infer", "lib", "rtrvc.py"))
        self.assertIn('getattr(self, "f0_repair", False)', rt)
        self.assertIn("self.f0_repair: bool = False", self._read("gui_v1.py"))


@unittest.skipUnless(_HAS_TORCH, "需要 Runtime（torch）")
class RealtimeBaselineTests(unittest.TestCase):
    """真正跑一遍模型再比对指纹。

    只在有 Runtime 的机器上跑 —— 也就是发版机器和开发机。
    要用它，先设 `RVC_BASELINE_PTH` 指向一个固定的音色权重，
    再把第一次跑出来的指纹填进 `RVC_BASELINE_DIGEST`。

    指纹变了就说明这次改动动了声音。**这时候要做的不是更新指纹**，
    而是先回答「为什么会变」；确认是有意为之（比如换了默认参数）之后，
    再连同那次改动一起更新它。
    """

    def test_the_hot_path_output_is_unchanged(self):
        pth = os.environ.get("RVC_BASELINE_PTH", "")
        want = os.environ.get("RVC_BASELINE_DIGEST", "")
        if not pth or not want:
            self.skipTest("未设 RVC_BASELINE_PTH / RVC_BASELINE_DIGEST")

        sys.path.insert(0, ROOT)
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import torch  # noqa: F401
        from multiprocessing import Queue

        from block_geometry import geometry
        from configs.config import Config
        from infer.lib.rtrvc import RVC

        config = Config()
        rvc = RVC(0, 0.0, pth, "", 0.0, 1, Queue(), Queue(), config)
        self.assertIsNotNone(getattr(rvc, "net_g", None), "模型加载失败")
        # 修正层全部关掉 —— 这条测试比的是「不该变的那部分」。
        rvc.f0_repair = False

        geo = geometry(rvc.tgt_sr, 0.25, 0.05, 2.5)
        n = geo["block_frame_16k"]
        src = fixed_signal(n * 12)
        buf = torch.zeros(geo["input_res_len"], device=rvc.device, dtype=torch.float32)
        out = []
        for i in range(12):
            chunk = torch.from_numpy(src[i * n:(i + 1) * n]).to(rvc.device)
            buf[:-n] = buf[n:].clone()
            buf[-n:] = chunk
            y = rvc.infer(buf, n, geo["skip_head"], geo["return_length"], "rmvpe")
            out.append(y.detach().float().cpu().numpy())
        got = digest(np.concatenate(out))
        self.assertEqual(
            got,
            want,
            "热路径的输出变了。先回答「为什么会变」，确认是有意为之之后，"
            "再连同那次改动一起更新 RVC_BASELINE_DIGEST —— 不要先改指纹。",
        )


if __name__ == "__main__":
    unittest.main()
