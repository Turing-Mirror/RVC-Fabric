# -*- coding: utf-8 -*-
"""实时链路和离线渲染出的是同一个声音。

调参在离线状态下按实时的方式渲染候选参数，再挑一组给用户。只有两边逐位相同，
离线挑出来的参数到用户电脑上才是同一个声音。

这里把 gui_v1 的音频回调原样取出来（`GUI` 定义在 `__main__` 块里，不能直接
import），和 `tools/realtime_block.OfflineStream` 用同一个假模型、同一段输入
各跑一遍，比较输出。假模型带内部状态，静音块推进音高历史的那一步也会反映在
输出里。

需要 Runtime（torch、torchaudio、librosa）。
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import os
import sys
import textwrap
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HAS_DEPS = all(
    importlib.util.find_spec(m) is not None
    for m in ("numpy", "torch", "torchaudio", "librosa")
)


def _gui_source() -> str:
    with open(os.path.join(ROOT, "gui_v1.py"), encoding="utf-8") as f:
        return f.read()


def _gui_methods(src: str) -> dict:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "GUI":
            return {n.name: n for n in node.body if isinstance(n, ast.FunctionDef)}
    raise AssertionError("gui_v1 里找不到 GUI 类")


#: 三组设置，覆盖：响应阈值、输入 / 输出降噪、音量包络开与关、相位声码器拼接、
#: 修音链、输入与总音量增益、模型采样率和设备采样率不同时的重采样。
CASES = {
    "defaults": {
        "I_noise_reduce": True, "rms_mix_rate": 0.25,
        "block_time": 0.1, "extra_time": 0.5, "f0method": "rmvpe",
    },
    "gate_pv_fx": {
        "threhold": -40, "O_noise_reduce": True, "rms_mix_rate": 1.0, "use_pv": True,
        "fx_enabled": True, "fx_eq_gains": [2.0, -1.0, 0.0, 1.5, -3.0],
        "in_gain_db": 3.0, "out_gain_db": -2.0,
        "block_time": 0.1, "extra_time": 0.5, "f0method": "rmvpe",
    },
    "resample_nr": {
        "sr_type": "sr_device", "rms_mix_rate": 0.5, "I_noise_reduce": True,
        "O_noise_reduce": True, "fx_enabled": True,
        "block_time": 0.12, "crossfade_length": 0.08, "extra_time": 0.7, "f0method": "rmvpe",
    },
}
TGT_SR = 40000
DEVICE_SR = 48000


@unittest.skipUnless(_HAS_DEPS, "需要 Runtime（torch / torchaudio / librosa）")
class RealtimeEqualsOfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        import numpy as np
        import torch
        import torch.nn.functional as F

        from tools import realtime_block as rb

        torch.set_grad_enabled(False)
        cls.np, cls.torch, cls.F, cls.rb = np, torch, F, rb

        src = _gui_source()
        methods = _gui_methods(src)
        ns = {
            "np": np,
            "time": __import__("time"),
            "process_block": rb.process_block,
            "flag_vc": True,
        }
        for name in ("audio_infer", "_emit_silence"):
            seg = ast.get_source_segment(src, methods[name], padded=True)
            exec(compile(textwrap.dedent(seg), "<gui_v1>", "exec"), ns)
        cls.gui_fns = {n: ns[n] for n in ("audio_infer", "_emit_silence")}

    def _fake_rvc(self):
        torch, F = self.torch, self.F

        class FakeRVC:
            def __init__(self):
                self.tgt_sr = TGT_SR
                self.device = torch.device("cpu")
                self.f0_repair = False
                self.calls = 0
                self.skipped = 0

            def infer(self, input_wav, block_frame_16k, skip_head, return_length, f0method):
                self.calls += 1
                n_out = return_length * (self.tgt_sr // 100)
                x = input_wav[-return_length * 160:].float()
                y = F.interpolate(x[None, None, :], size=n_out, mode="linear",
                                  align_corners=False)[0, 0]
                t = torch.arange(n_out, dtype=torch.float32)
                wobble = 0.01 * torch.sin(t * 0.003 * (1 + self.calls % 5) + self.skipped * 1e-4)
                return torch.tanh(1.7 * y) * 0.8 + wobble

            def skip_block(self, n):
                self.skipped += int(n)

        return FakeRVC()

    def _signal(self, sr: int):
        np = self.np
        n = int(sr * 3.0)
        t = np.arange(n, dtype=np.float64) / sr
        f0 = 130.0 * 2 ** (0.5 * np.sin(2 * np.pi * 0.25 * t))
        phase = 2 * np.pi * np.cumsum(f0) / sr
        saw = 2.0 * ((phase / (2 * np.pi)) % 1.0) - 1.0
        x = 0.35 * saw + 0.02 * np.random.default_rng(0).standard_normal(n)
        q0, q1 = int(n * 0.40), int(n * 0.55)
        x[q0:q1] = 0.0                  # 整段静音：走静音块
        x[q1:q1 + n // 20] *= 0.003     # 很轻的一段：走响应阈值
        return x.astype(np.float32)

    def _run_realtime(self, settings, signal):
        """照 start_vc 建流，再按音频回调一块一块喂。"""
        np, torch, rb = self.np, self.torch, self.rb
        s = types.SimpleNamespace()
        for name, fn in self.gui_fns.items():
            setattr(s, name, types.MethodType(fn, s))
        s.gui_config = copy.deepcopy(settings)
        s.gui_config.channels = 2
        s.rvc = self._fake_rvc()
        # start_vc：模型采样率模式下，流的采样率就是模型的采样率。
        if s.gui_config.sr_type == "sr_model":
            s.gui_config.samplerate = s.rvc.tgt_sr
        s.config = types.SimpleNamespace(device=torch.device("cpu"))
        s._dml = False
        s._io_device = torch.device("cpu")
        s.function = "vc"
        s._voice_chain = None
        s._fx_chain = None
        s.window = None
        s.last_infer_ms = 0
        s._swap_ready = None
        s._pending_model = None
        s._swap_busy = False
        s.rt_log = lambda *a: None
        out = []
        s._commit_output = lambda o, b: out.append(np.array(o, dtype=np.float32, copy=True))
        s._write_monitor = lambda o: None
        s._finish_block_timing = lambda t: None
        rb.rebuild_fx_chain(s)
        if s._fx_chain is not None:
            s._fx_chain.reset()
        rb.rebuild_voice_chain(s)
        rb.build_stream(s)

        class Evt:
            def wait(self, timeout=None):
                return True

            def clear(self):
                pass

            def is_set(self):
                return False

        bf = s.block_frame
        nblk = len(signal) // bf
        s.in_buf = signal[: nblk * bf].reshape(-1, 1)
        s.out_buf = np.zeros((2 * bf, 2), dtype=np.float32)
        s.in_evt = Evt()
        s.in_ptr = types.SimpleNamespace(value=0)
        s.out_ptr = types.SimpleNamespace(value=0)
        for i in range(nblk):
            s.in_ptr.value = i * bf
            s.audio_infer(2 * bf)
        return np.concatenate(out), s.rvc

    def _run_offline(self, settings, signal):
        torch = self.torch
        rvc = self._fake_rvc()
        st = self.rb.OfflineStream(
            rvc, copy.deepcopy(settings), types.SimpleNamespace(device=torch.device("cpu"))
        )
        n = len(signal) // st.block_frame * st.block_frame
        return st.render(signal[:n]), rvc

    def test_realtime_and_offline_are_bit_identical(self):
        np = self.np
        for name, cfg in CASES.items():
            with self.subTest(case=name):
                settings = self.rb.settings_from_config(cfg, samplerate=DEVICE_SR)
                sr = TGT_SR if settings.sr_type == "sr_model" else DEVICE_SR
                signal = self._signal(sr)
                rt, rt_rvc = self._run_realtime(settings, signal)
                off, off_rvc = self._run_offline(settings, signal)
                self.assertEqual(rt.shape, (len(off), 2))
                self.assertGreater(rt_rvc.skipped, 0, "这组输入没走到静音块")
                self.assertEqual((rt_rvc.calls, rt_rvc.skipped), (off_rvc.calls, off_rvc.skipped))
                self.assertTrue(np.array_equal(rt[:, 0], off), "实时链路和离线渲染的输出不一样")
                self.assertTrue(np.array_equal(rt[:, 1], off))


class OneCopyTests(unittest.TestCase):
    """处理只能有一份：音频回调和开流都调公共模块，不再自己写一份。"""

    def test_the_callback_and_stream_setup_use_the_shared_module(self):
        src = _gui_source()
        methods = _gui_methods(src)
        cb = ast.get_source_segment(src, methods["audio_infer"])
        self.assertIn("process_block(self, indata)", cb)
        for own_copy in ("self.rvc.infer(", "F.conv1d", "librosa.feature.rms", "self.tg("):
            self.assertNotIn(own_copy, cb, f"音频回调里又出现了自己的一份处理：{own_copy}")
        start = ast.get_source_segment(src, methods["start_vc"])
        self.assertIn("build_stream(self)", start)
        self.assertNotIn("TorchGate(", start)


if __name__ == "__main__":
    unittest.main()
