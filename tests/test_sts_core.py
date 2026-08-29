# -*- coding: utf-8 -*-
"""离线转换共用内核的单测（不需要 GPU / 模型权重 / torch）。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.sts_core import (  # noqa: E402
    ConversionCancelled,
    StsProgress,
    convert_one,
    convert_one_with_cpu_fallback,
    friendly_error,
    is_dml_backend_error,
    is_dml_runtime_failure,
    move_models_to_cpu,
    normalize_format,
    run_batch,
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


# ---------------------------------------------------------------------------
# DirectML 兜底
# ---------------------------------------------------------------------------

# 用户诊断包（26.8.20，AMD 核显）里的两条原文，一字未改。
DML_GRAD_MULTIPLY_TB = """Traceback (most recent call last):
  File "D:\\RVC Fabric\\infer\\modules\\vc\\modules.py", line 206, in vc_single
    audio_opt = self.pipeline.pipeline(
  File "D:\\RVC Fabric\\Runtime\\lib\\site-packages\\fairseq\\modules\\grad_multiply.py", line 13, in forward
    res = x.new(x)
RuntimeError: new(): expected key in DispatchKeySet(CPU, CUDA, HIP, XLA, MPS, IPU, XPU, HPU, Lazy, Meta) but got: PrivateUse1"""

DML_TORCHCREPE_TB = """Traceback (most recent call last):
  File "D:\\RVC Fabric\\Runtime\\lib\\site-packages\\torchcrepe\\load.py", line 30, in model
    torch.load(file, map_location=device))
RuntimeError: don't know how to restore data location of torch.storage.UntypedStorage (tagged with privateuseone:0)"""


class DmlErrorTextTests(unittest.TestCase):
    def test_recognizes_both_real_errors(self):
        self.assertTrue(is_dml_backend_error(DML_GRAD_MULTIPLY_TB))
        self.assertTrue(is_dml_backend_error(DML_TORCHCREPE_TB))

    def test_oom_is_not_a_dml_error(self):
        self.assertFalse(is_dml_backend_error("CUDA out of memory. Tried to allocate 2.00 GiB"))
        self.assertFalse(is_dml_backend_error(""))

    def test_friendly_error_collapses_the_wall_of_traceback(self):
        # 截图里用户看到的是几十行 D:\RVC Fabric\... 的路径，什么也说明不了。
        msg = friendly_error(DML_GRAD_MULTIPLY_TB)
        self.assertNotIn("site-packages", msg)
        self.assertIn("DirectML", msg)
        self.assertIn("TM_USE_DML=0", msg)
        self.assertIn("PrivateUse1", msg)  # 原始报错那一行还留着

    def test_friendly_error_stays_detectable(self):
        # run_batch 判断要不要退 CPU 时看的是 friendly_error 之后的文本，
        # 这条链断了兜底就永远不触发。
        self.assertTrue(is_dml_backend_error(friendly_error(DML_GRAD_MULTIPLY_TB)))

    def test_unknown_traceback_headline_is_the_last_line(self):
        # 规格书 1.3 兜底：认不出的错误也必须把正文收成最后一行，不能让界面
        # 第一行停在 Traceback (most recent call last):。
        tb = (
            "Traceback (most recent call last):\n"
            '  File "foo.py", line 1, in <module>\n'
            "ValueError: bad wav header"
        )
        msg = friendly_error(tb)
        self.assertTrue(msg.startswith("ValueError: bad wav header"))
        self.assertIn("Traceback", msg)
        self.assertIn("foo.py", msg)


class DmlRuntimeFailureTests(unittest.TestCase):
    """26.8.29/113756：空消息的 RuntimeError 也得算 DirectML 后端失败。

    torch-directml 撞显存/后端失败时抛一个字都没有的 RuntimeError，关键词
    匹配（privateuse1/directml…）永远接不住，用户只能看到一墙 traceback。
    """

    def _vc(self, device):
        return SimpleNamespace(pipeline=SimpleNamespace(device=device))

    def test_bare_runtime_error_on_dml_device(self):
        vc = self._vc("privateuseone:0")
        self.assertTrue(is_dml_runtime_failure(RuntimeError(), vc))

    def test_wrapped_bare_error_from_convert_one(self):
        # convert_one 会把底层异常包成 RuntimeError(friendly 文本) 再抛；
        # 空 RuntimeError 包完 str 就是 "RuntimeError"。
        vc = self._vc("privateuseone:0")
        self.assertTrue(is_dml_runtime_failure(RuntimeError("RuntimeError"), vc))

    def test_message_runtime_error_on_dml_is_not(self):
        # 带消息但没关键词的失败多半是坏文件，退 CPU 也一样炸，不陪跑。
        vc = self._vc("privateuseone:0")
        self.assertFalse(is_dml_runtime_failure(RuntimeError("boom"), vc))

    def test_bare_runtime_error_on_cuda_is_not(self):
        # CUDA / CPU 上的 RuntimeError 是真 bug，拖去 CPU 重试只会更糊涂。
        vc = self._vc("cuda:0")
        self.assertFalse(is_dml_runtime_failure(RuntimeError(), vc))

    def test_other_exception_on_dml_is_not(self):
        vc = self._vc("privateuseone:0")
        self.assertFalse(is_dml_runtime_failure(ValueError("bad wav"), vc))

    def test_marker_text_wins_regardless_of_device(self):
        vc = self._vc("cuda:0")
        self.assertTrue(is_dml_runtime_failure(DML_GRAD_MULTIPLY_TB, vc))

    def test_friendly_text_of_bare_error_on_dml(self):
        # 热路径闸门拿到的是 friendly_error 之后的文本：空 RuntimeError
        # 过完只剩一行光秃秃的 "RuntimeError"。
        text = friendly_error(RuntimeError())
        self.assertEqual(text, "RuntimeError")
        self.assertTrue(is_dml_runtime_failure(text, self._vc("privateuseone:0")))
        self.assertFalse(is_dml_runtime_failure(text, self._vc("cuda:0")))


class FakeModel:
    def __init__(self, device="privateuseone:0"):
        self.device = device
        self.half = True

    def float(self):
        self.half = False
        return self

    def to(self, device):
        self.device = str(device)
        return self


class FakePipeline:
    def __init__(self, device="privateuseone:0"):
        self.device = device
        self.is_half = True
        self.model_rmvpe = object()


class FakeVC:
    def __init__(self):
        self.net_g = FakeModel()
        self.hubert_model = FakeModel()
        self.pipeline = FakePipeline()
        self.config = SimpleNamespace(device="privateuseone:0", is_half=True)


class MoveToCpuTests(unittest.TestCase):
    def test_moves_everything_and_drops_rmvpe(self):
        vc = FakeVC()
        self.assertTrue(move_models_to_cpu(vc))
        self.assertEqual(vc.net_g.device, "cpu")
        self.assertEqual(vc.hubert_model.device, "cpu")
        self.assertFalse(vc.net_g.half)
        self.assertEqual(vc.pipeline.device, "cpu")
        self.assertFalse(vc.pipeline.is_half)
        # rmvpe 在 privateuseone 上是 onnxruntime 的 DML EP，必须扔掉重建
        self.assertFalse(hasattr(vc.pipeline, "model_rmvpe"))
        self.assertEqual(vc.config.device, "cpu")

    def test_hubert_fail_leaves_net_g_on_original_device(self):
        vc = FakeVC()

        class Boom(FakeModel):
            def to(self, device):
                raise RuntimeError("oom moving hubert")

        vc.hubert_model = Boom()
        self.assertFalse(move_models_to_cpu(vc))
        self.assertEqual(vc.net_g.device, "privateuseone:0")
        self.assertEqual(vc.pipeline.device, "privateuseone:0")
        self.assertTrue(hasattr(vc.pipeline, "model_rmvpe"))


class FakeWavfile:
    """scipy.io.wavfile 的替身，只要能落个文件。"""

    @staticmethod
    def write(path, sr, audio):
        Path(path).write_bytes(b"RIFF-fake")


class DmlFailingVC(FakeVC):
    """在显卡上必炸、挪到 CPU 就好——就是用户那台机器的行为。"""

    def __init__(self):
        super().__init__()
        self.calls = 0

    def vc_single(self, *a, progress_cb=None, **kw):
        self.calls += 1
        if str(self.pipeline.device) != "cpu":
            raise RuntimeError(DML_GRAD_MULTIPLY_TB)
        if progress_cb:
            progress_cb("infer", 1.0)
        return "ok", (16000, b"\x00\x00")


class CpuFallbackTests(unittest.TestCase):
    """DirectML 撞上算子缺口时，冷路径要能自己退到 CPU 把文件转出来。"""

    def setUp(self):
        # run_batch 里 `from scipy.io import wavfile`，开发机上没有 scipy。
        self._saved = {k: sys.modules.get(k) for k in ("scipy", "scipy.io")}
        scipy = ModuleType("scipy")
        scipy_io = ModuleType("scipy.io")
        scipy_io.wavfile = FakeWavfile
        scipy.io = scipy_io
        sys.modules["scipy"] = scipy
        sys.modules["scipy.io"] = scipy_io

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def _run(self, vc, allow_cpu_fallback=True):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.wav"
            src.write_bytes(b"RIFF-fake")
            out = Path(td) / "out"
            events: list[dict] = []
            emit = lambda **e: events.append(e)  # noqa: E731
            prog = StsProgress(1, "rmvpe", emit=emit, load_end=0.0)
            params = {
                "pitch": 0,
                "f0method": "rmvpe",
                "index_path": None,
                "index_rate": 0.75,
                "filter_radius": 3,
                "resample_sr": 0,
                "rms_mix_rate": 0.25,
                "protect": 0.33,
                "format": "wav",
                "sid": 0,
                "f0_file": None,
            }
            return run_batch(
                vc, [(src, Path("in.wav"))], out, params, prog, emit,
                allow_cpu_fallback=allow_cpu_fallback,
            ), events

    def test_retries_on_cpu_and_the_file_comes_out(self):
        vc = DmlFailingVC()
        (out_files, skipped, cancelled), events = self._run(vc)
        self.assertEqual(len(out_files), 1, skipped)
        self.assertEqual(skipped, [])
        self.assertFalse(cancelled)
        self.assertEqual(vc.calls, 2)  # 显卡一次，CPU 一次
        self.assertTrue(
            any("CPU" in str(e.get("message") or "") for e in events),
            "退 CPU 这件事得让用户看见",
        )

    def test_hot_path_never_touches_the_resident_models(self):
        # 热路径的 net_g / hubert 就是实时引擎那几个对象，挪走实时变声就废了。
        vc = DmlFailingVC()
        (out_files, skipped, _), _ = self._run(vc, allow_cpu_fallback=False)
        self.assertEqual(out_files, [])
        self.assertEqual(len(skipped), 1)
        self.assertEqual(vc.calls, 1)
        self.assertEqual(vc.pipeline.device, "privateuseone:0")
        self.assertEqual(vc.net_g.device, "privateuseone:0")
        self.assertTrue(is_dml_backend_error(skipped[0]["reason"]))

    def test_a_non_runtime_failure_is_not_retried(self):
        # DML 设备上只有 RuntimeError（含空报错）才给 CPU 机会；别的类型
        # 是真 bug / 真坏文件，退 CPU 也一样炸，别拖着整批慢慢陪跑。
        class Broken(FakeVC):
            def __init__(self):
                super().__init__()
                self.calls = 0

            def vc_single(self, *a, progress_cb=None, **kw):
                self.calls += 1
                raise ValueError("找不到音频文件")

        vc = Broken()
        (out_files, skipped, _), _ = self._run(vc)
        self.assertEqual(out_files, [])
        self.assertEqual(vc.calls, 1)
        self.assertEqual(vc.pipeline.device, "privateuseone:0")

    def test_bare_runtime_error_retries_on_cpu(self):
        # 26.8.29/113756：torch-directml 撞显存/后端失败抛的是空消息的
        # RuntimeError，关键词匹配接不住，用户只能看到一墙 traceback。
        # 现在得跟带字样的报错一样退 CPU 把文件转出来。

        class BareDmlFailure(DmlFailingVC):
            def vc_single(self, *a, progress_cb=None, **kw):
                self.calls += 1
                if str(self.pipeline.device) != "cpu":
                    raise RuntimeError()  # 一个字都没有
                if progress_cb:
                    progress_cb("infer", 1.0)
                return "ok", (16000, b"\x00\x00")

        vc = BareDmlFailure()
        (out_files, skipped, _), _ = self._run(vc)
        self.assertEqual(len(out_files), 1, skipped)
        self.assertEqual(vc.calls, 2)

    def _single(self, vc, allow_cpu_fallback=True):
        """TTS / infer_cli 那条单文件入口。"""
        notes: list[str] = []
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.wav"
            src.write_bytes(b"RIFF-fake")
            dest = Path(td) / "out.wav"
            used = convert_one_with_cpu_fallback(
                vc,
                src,
                dest,
                pitch=0,
                f0method="rmvpe",
                index_path=None,
                index_rate=0.75,
                filter_radius=3,
                resample_sr=0,
                rms_mix_rate=1.0,
                protect=0.33,
                on_stage=lambda *_a, **_k: None,
                wavfile=FakeWavfile,
                fmt="wav",
                allow_cpu_fallback=allow_cpu_fallback,
                on_fallback=lambda _e: notes.append("cpu"),
            )
            return used, dest.exists(), notes

    def test_single_file_entry_retries_on_cpu(self):
        # 26.8.21 TTS 日志：SAPI 成功、infer_cli 在 GradMultiply 上炸。
        # 这条入口以前没有 CPU 兜底，现在必须跟 STS 批量同一份行为。
        vc = DmlFailingVC()
        used, exists, notes = self._single(vc)
        self.assertTrue(used)
        self.assertTrue(exists)
        self.assertEqual(notes, ["cpu"])
        self.assertEqual(vc.calls, 2)
        self.assertEqual(vc.pipeline.device, "cpu")

    def test_single_file_entry_does_not_move_models_when_disabled(self):
        vc = DmlFailingVC()
        with self.assertRaises(RuntimeError) as caught:
            self._single(vc, allow_cpu_fallback=False)
        self.assertTrue(is_dml_backend_error(caught.exception))
        self.assertEqual(vc.calls, 1)
        self.assertEqual(vc.pipeline.device, "privateuseone:0")


class OomRetryShrinksWindowsTests(unittest.TestCase):
    """CUDA OOM 重试必须真的把合成窗改小，否则第二轮还是同一段 30s infer。"""

    def setUp(self):
        import os

        self._old_frames = os.environ.pop("TM_RMVPE_MAX_FRAMES", None)
        self._old_xmax = os.environ.pop("TM_VC_X_MAX", None)

    def tearDown(self):
        import os

        os.environ.pop("TM_RMVPE_MAX_FRAMES", None)
        os.environ.pop("TM_VC_X_MAX", None)
        if self._old_frames is not None:
            os.environ["TM_RMVPE_MAX_FRAMES"] = self._old_frames
        if self._old_xmax is not None:
            os.environ["TM_VC_X_MAX"] = self._old_xmax

    def test_first_oom_calls_pipeline_shrink_then_succeeds(self):
        import os

        class FakeWavfile:
            @staticmethod
            def write(path, sr, audio):
                Path(path).write_bytes(b"RIFF")

        class Pipe:
            def __init__(self):
                self.shrunk = 0

            def shrink_windows(self):
                self.shrunk += 1

        class Vc:
            def __init__(self):
                self.pipeline = Pipe()
                self.calls = 0

            def vc_single(self, *a, **k):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")
                return "ok", (16000, [0, 0, 0])

        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.wav"
            dest = Path(td) / "out.wav"
            src.write_bytes(b"x")
            vc = Vc()
            convert_one(
                vc,
                src,
                dest,
                pitch=0,
                f0method="rmvpe",
                index_path=None,
                index_rate=0.75,
                filter_radius=3,
                resample_sr=0,
                rms_mix_rate=1.0,
                protect=0.33,
                on_stage=lambda *_a, **_k: None,
                wavfile=FakeWavfile,
                fmt="wav",
            )
            self.assertEqual(vc.calls, 2)
            self.assertEqual(vc.pipeline.shrunk, 1)
            self.assertEqual(os.environ.get("TM_VC_X_MAX"), "4")
            self.assertEqual(os.environ.get("TM_RMVPE_MAX_FRAMES"), "512")
            self.assertTrue(dest.is_file())


if __name__ == "__main__":
    unittest.main()
