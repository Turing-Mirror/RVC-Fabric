# -*- coding: utf-8 -*-
"""离线转换共用内核的单测（不需要 GPU / 模型权重 / torch）。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.sts_core import (  # noqa: E402
    ConversionCancelled,
    StsProgress,
    normalize_format,
    unique_dest,
)


class CancelSignalTests(unittest.TestCase):
    """取消信号必须能穿过 pipeline 里那一堆 `except Exception: pass`。

    infer/modules/vc/pipeline.py、infer/lib/rmvpe.py、infer/modules/vc/modules.py
    的进度回调全都写成 `try: progress_cb(...) except Exception: pass`。取消要是
    继承了 Exception，就会被就地吞掉，长音频点了取消得等整个文件跑完才停。
    这条测试是那个设计的守门人——谁把基类改回 Exception，这里立刻红。
    """

    def test_not_caught_by_bare_except_exception(self):
        caught = False
        try:
            try:
                raise ConversionCancelled()
            except Exception:  # noqa: BLE001 — 复刻 pipeline 里的写法
                caught = True
        except ConversionCancelled:
            pass
        self.assertFalse(caught, "ConversionCancelled 被 except Exception 吞了")

    def test_is_base_exception(self):
        self.assertTrue(issubclass(ConversionCancelled, BaseException))
        self.assertFalse(issubclass(ConversionCancelled, Exception))


class HotPathProgressTests(unittest.TestCase):
    """热路径没有模型加载阶段，进度必须从 0 起步。"""

    def _events(self, **kw):
        events: list[dict] = []
        prog = StsProgress(emit=lambda **e: events.append(e), **kw)
        return prog, events

    def test_load_end_zero_starts_first_file_at_zero(self):
        prog, events = self._events(total_files=1, f0method="rmvpe", load_end=0.0)
        prog.begin_file(1, "a.wav")
        self.assertEqual(events[-1]["pct"], 0)

    def test_load_end_zero_swallows_load_events(self):
        prog, events = self._events(total_files=1, f0method="rmvpe", load_end=0.0)
        prog.load("model", 0.5)
        prog.load("hubert", 1.0)
        self.assertEqual(events, [], "热路径不该发加载进度")

    def test_cold_path_still_reserves_load_band(self):
        prog, events = self._events(total_files=1, f0method="rmvpe")
        prog.begin_file(1, "a.wav")
        # 冷路径默认留 12% 给加载，第一个文件从那儿开始
        self.assertEqual(events[-1]["pct"], 12)

    def test_reaches_100_either_way(self):
        for load_end in (0.0, None):
            kw = {"total_files": 2, "f0method": "rmvpe"}
            if load_end is not None:
                kw["load_end"] = load_end
            prog, events = self._events(**kw)
            prog.begin_file(1, "a.wav")
            prog.file_done(1, "a.wav", ok=True)
            prog.begin_file(2, "b.wav")
            prog.file_done(2, "b.wav", ok=True)
            self.assertEqual(events[-1]["pct"], 100)
            self.assertEqual(events[-1]["ok"], 2)


class UniqueDestTests(unittest.TestCase):
    def test_preserves_subdir_and_dedupes(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            first = unique_dest(out, Path("A/vocal.wav"), "vocal")
            self.assertEqual(first.parent.name, "A")
            self.assertEqual(first.name, "vocal_rvc.wav")
            first.write_bytes(b"x")
            second = unique_dest(out, Path("A/vocal.wav"), "vocal")
            self.assertEqual(second.name, "vocal_rvc_1.wav")

    def test_flat_input_lands_in_root(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            got = unique_dest(out, Path("a.wav"), "a")
            self.assertEqual(got.parent, out)

    def test_export_format_changes_suffix(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            got = unique_dest(out, Path("a.wav"), "a", "flac")
            self.assertEqual(got.name, "a_rvc.flac")
            self.assertEqual(normalize_format("MP3"), "mp3")
            self.assertEqual(normalize_format("aac"), "wav")


class CudnnBenchmarkGateTests(unittest.TestCase):
    """短任务开 cudnn.benchmark 是净亏：调优跑完活也干完了。"""

    def setUp(self):
        import os

        self._old = os.environ.pop("TM_CUDNN_BENCHMARK", None)

    def tearDown(self):
        import os

        os.environ.pop("TM_CUDNN_BENCHMARK", None)
        if self._old is not None:
            os.environ["TM_CUDNN_BENCHMARK"] = self._old

    def test_short_single_file_is_off(self):
        from infer.lib.torch_runtime import want_cudnn_benchmark

        self.assertFalse(want_cudnn_benchmark(total_seconds=5.0, total_files=1))

    def test_long_single_file_is_on(self):
        from infer.lib.torch_runtime import want_cudnn_benchmark

        self.assertTrue(want_cudnn_benchmark(total_seconds=300.0, total_files=1))

    def test_batch_is_on_regardless_of_length(self):
        from infer.lib.torch_runtime import want_cudnn_benchmark

        self.assertTrue(want_cudnn_benchmark(total_seconds=6.0, total_files=8))

    def test_env_override_both_ways(self):
        import os

        from infer.lib.torch_runtime import want_cudnn_benchmark

        os.environ["TM_CUDNN_BENCHMARK"] = "1"
        self.assertTrue(want_cudnn_benchmark(total_seconds=1.0, total_files=1))
        os.environ["TM_CUDNN_BENCHMARK"] = "0"
        self.assertFalse(want_cudnn_benchmark(total_seconds=9999.0, total_files=99))

    def test_no_args_defaults_to_off(self):
        from infer.lib.torch_runtime import want_cudnn_benchmark

        self.assertFalse(want_cudnn_benchmark())


if __name__ == "__main__":
    unittest.main()
