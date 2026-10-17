"""Unit tests for STS worker helpers (no GPU / model weights required)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from contextlib import ExitStack, nullcontext
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.sts_worker import (  # noqa: E402
    StsProgress,
    _ensure_rvc_env,
    _friendly_error,
    _is_oom,
    _normalize_f0method,
    collect_inputs,
    file_weights,
)


class FriendlyErrorTests(unittest.TestCase):
    def test_cuda_oom_traceback_to_chinese(self):
        tb = (
            "torch.cuda.OutOfMemoryError: CUDA out of memory. "
            "Tried to allocate 2.75 GiB (GPU 0; 3.00 GiB total capacity)"
        )
        msg = _friendly_error(tb)
        self.assertIn("显存不够", msg)
        self.assertIn("harvest", msg)

    def test_exception_instance(self):
        msg = _friendly_error(RuntimeError("CUDA out of memory"))
        self.assertIn("显存不够", msg)

    def test_passthrough_plain(self):
        self.assertEqual(_friendly_error("找不到音色模型"), "找不到音色模型")

    def test_idempotent_on_friendly(self):
        once = _friendly_error("CUDA out of memory")
        self.assertEqual(_friendly_error(once), once)


class CollectInputsTests(unittest.TestCase):
    def test_single_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.wav"
            p.write_bytes(b"x")
            got = collect_inputs(str(p))
            self.assertEqual(len(got), 1)
            self.assertEqual(got[0][1], Path("a.wav"))

    def test_folder_preserves_relative_tree(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "A").mkdir()
            (root / "B").mkdir()
            (root / "A" / "vocal.wav").write_bytes(b"1")
            (root / "B" / "vocal.wav").write_bytes(b"2")
            (root / "skip.txt").write_bytes(b"no")
            got = collect_inputs(str(root))
            rels = sorted(str(r).replace("\\", "/") for _, r in got)
            self.assertEqual(rels, ["A/vocal.wav", "B/vocal.wav"])

    def test_missing_returns_empty(self):
        self.assertEqual(collect_inputs(r"Z:\no\such\path\sts_test"), [])


class EnsureRvcEnvTests(unittest.TestCase):
    def test_sets_index_root_default(self):
        old = os.environ.pop("index_root", None)
        try:
            _ensure_rvc_env()
            self.assertTrue(os.environ.get("index_root"))
            self.assertTrue(os.path.isabs(os.environ["index_root"]))
            self.assertEqual(os.environ.get("TM_VOICE_ROOT"), str(ROOT))
        finally:
            if old is not None:
                os.environ["index_root"] = old
            else:
                os.environ.pop("index_root", None)


class StsProgressTests(unittest.TestCase):
    def test_single_file_stages_increase(self):
        events = []

        def capture(**kw):
            events.append(kw)

        p = StsProgress(1, "rmvpe", emit=capture)
        p.load("config", 1.0)
        p.load("model", 1.0)
        p.begin_file(1, "a.wav")
        p.stage("read", 1.0)
        p.stage("f0", 0.0)
        p.stage("f0", 1.0)
        p.stage("infer", 0.5)
        p.stage("write", 1.0)
        p.file_done(1, "a.wav", ok=True)

        pcts = [e["pct"] for e in events if "pct" in e]
        self.assertTrue(pcts)
        # 单调不减，单文件结束应到 100
        self.assertEqual(pcts, sorted(pcts))
        self.assertEqual(pcts[-1], 100)
        # 音高步骤文案要带算法名，用户才知道卡在哪
        f0_msgs = [e["message"] for e in events if e.get("step") == "f0"]
        self.assertTrue(any("rmvpe" in m for m in f0_msgs))

    def test_multi_file_second_starts_after_first_half(self):
        events = []

        def capture(**kw):
            events.append(kw)

        p = StsProgress(2, "harvest", emit=capture)
        p.load("model", 1.0)
        p.begin_file(1, "a.wav")
        p.file_done(1, "a.wav", ok=True)
        p.begin_file(2, "b.wav")

        second_start = next(
            e for e in events if e.get("step") == "file_start" and "b.wav" in e["message"]
        )
        # 等权两文件：加载 12% + 第一个文件约 44% → 第二文件起点约 56%
        self.assertGreaterEqual(second_start["pct"], 50)
        self.assertLess(second_start["pct"], 65)
        self.assertEqual(second_start.get("ok"), 1)
        self.assertEqual(second_start.get("current"), 2)

    def test_size_weighted_big_file_gets_more_span(self):
        events = []

        def capture(**kw):
            events.append(kw)

            # 小文件 1、大文件 9 → 大文件约占文件段 90%
        p = StsProgress(2, "rmvpe", weights=[1, 9], emit=capture)
        p.begin_file(1, "tiny.wav")
        p.file_done(1, "tiny.wav", ok=True)
        p.begin_file(2, "huge.wav")
        p.file_done(2, "huge.wav", ok=True)

        tiny_done = next(e for e in events if e.get("step") == "file_done" and "tiny" in e["message"])
        huge_start = next(
            e for e in events if e.get("step") == "file_start" and "huge" in e["message"]
        )
        # tiny 结束后 pct 应明显小于半程（加载 12 + 0.1*88 ≈ 21）
        self.assertLess(tiny_done["pct"], 30)
        self.assertEqual(huge_start["pct"], tiny_done["pct"])
        self.assertEqual(events[-1]["pct"], 100)
        self.assertEqual(events[-1].get("ok"), 2)

    def test_file_weights_from_sizes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = root / "a.wav"
            b = root / "b.wav"
            a.write_bytes(b"x" * 100)
            b.write_bytes(b"y" * 900)
            w = file_weights([a, b])
            self.assertEqual(w[0], 100.0)
            self.assertEqual(w[1], 900.0)

    def test_f0_and_infer_report_percent_in_message(self):
        events = []

        def capture(**kw):
            events.append(kw)

        p = StsProgress(1, "rmvpe", emit=capture)
        p.load("model", 1.0)
        p.begin_file(1, "song.wav")
        p.stage("f0", 0.0)
        p.stage("f0", 0.33)
        p.stage("f0", 0.67)
        p.stage("infer", 0.0)
        p.stage("infer", 0.4)
        p.stage("infer", 0.9)

        f0 = [e for e in events if e.get("step") == "f0"]
        inf = [e for e in events if e.get("step") == "infer"]
        self.assertTrue(any("33%" in e["message"] for e in f0))
        self.assertTrue(any("40%" in e["message"] for e in inf))
        # 同阶段百分比应往上走
        f0_pcts = [e["pct"] for e in f0]
        self.assertEqual(f0_pcts, sorted(f0_pcts))


class NormalizeF0Tests(unittest.TestCase):
    def test_fcpe_maps_to_rmvpe(self):
        m, note = _normalize_f0method("fcpe")
        self.assertEqual(m, "rmvpe")
        self.assertTrue(note)

    def test_known_passthrough(self):
        for name in ("rmvpe", "harvest", "pm", "crepe"):
            m, note = _normalize_f0method(name)
            self.assertEqual(m, name)
            self.assertIsNone(note)

    def test_is_oom(self):
        self.assertTrue(_is_oom("CUDA out of memory"))
        self.assertTrue(_is_oom("显存不够（CUDA OOM）"))
        self.assertFalse(_is_oom("file not found"))


class TorchRuntimeTests(unittest.TestCase):
    def test_rmvpe_chunk_cpu_default(self):
        from infer.lib.torch_runtime import rmvpe_max_mel_frames

        self.assertEqual(rmvpe_max_mel_frames(False, "cpu"), 1024)
        self.assertEqual(rmvpe_max_mel_frames(True, "cpu"), 1024)

    def test_rmvpe_chunk_env_override_aligned(self):
        from infer.lib.torch_runtime import rmvpe_max_mel_frames

        old = os.environ.get("TM_RMVPE_MAX_FRAMES")
        try:
            os.environ["TM_RMVPE_MAX_FRAMES"] = "500"
            n = rmvpe_max_mel_frames(False, "cpu")
            self.assertEqual(n % 32, 0)
            self.assertLessEqual(n, 500)
            self.assertGreaterEqual(n, 256)
        finally:
            if old is None:
                os.environ.pop("TM_RMVPE_MAX_FRAMES", None)
            else:
                os.environ["TM_RMVPE_MAX_FRAMES"] = old

    def test_empty_cache_if_needed_no_cuda_returns_false(self):
        from infer.lib.torch_runtime import empty_cache_if_needed

        # 无 GPU 或不可用时不应抛异常。
        self.assertFalse(empty_cache_if_needed(min_free_mb=1))

    def test_tune_for_inference_is_safe(self):
        from infer.lib.torch_runtime import inference_context, tune_for_inference

        tune_for_inference()
        with inference_context():
            pass

    def test_inference_context_lets_errors_out(self):
        """块里抛的异常必须原样出来。

        以前 try 把 yield 一起包了，异常被 `except Exception: pass` 吞掉，生成器
        接着第二次 yield，contextlib 换抛一句 "generator didn't stop after
        throw()"。用户看到的报错跟真实原因毫无关系。
        """
        from infer.lib.torch_runtime import inference_context

        with self.assertRaises(ValueError):
            with inference_context():
                raise ValueError("boom")

    def test_no_inference_mode_anywhere(self):
        """`torch.inference_mode()` 在本仓库里一处都不许有。

        它建出来的张量带 inference 标记，出了块再用就抛
        "Cannot set version_counter for inference tensor"。而离线转换会在块里
        懒加载 RMVPE（`mel_basis` 是 register_buffer），26.8.18 有用户因此
        整批转换失败。省下的那点记账开销不值这个。
        """
        import re

        root = Path(__file__).resolve().parent.parent
        # 只扫源码目录：app/src-tauri 下面有构建时拷进去的副本，虚拟环境里还有
        # torch 自己，扫到它们只会得到一堆噪音。
        pat = re.compile(r"(with|return|=)\s+torch\.inference_mode\s*\(")
        hits = []
        for sub in ("infer", "tools", "configs"):
            base = root / sub
            if not base.is_dir():
                continue
            for path in base.rglob("*.py"):
                text = path.read_text(encoding="utf-8", errors="ignore")
                for i, line in enumerate(text.splitlines(), 1):
                    if pat.search(line):
                        hits.append(f"{path.relative_to(root)}:{i}")
        self.assertEqual(hits, [], "改回 no_grad：" + ", ".join(hits))

    def test_tune_thread_knobs_applied_once(self):
        """第二次 tune 不得再调 set_num_interop_threads。

        Config() 之后 interop 线程池已启动，再调用会在 torch 2.0 Windows 上
        原生崩溃（0xC0000409，exit -1073740791），try/except 拦不住。
        """
        import sys
        import types

        from infer.lib import torch_runtime as tr

        class FakeTorch(types.ModuleType):
            def __init__(self):
                super().__init__("torch")
                self._grad = True
                self.thread_calls = 0
                self.interop_calls = 0

            def set_grad_enabled(self, v):
                self._grad = v

            def set_num_threads(self, n):
                self.thread_calls += 1

            def set_num_interop_threads(self, n):
                self.interop_calls += 1

            class cuda:
                @staticmethod
                def is_available():
                    return False

        fake = FakeTorch()
        old = sys.modules.get("torch")
        saved = tr._THREADS_TUNED
        try:
            sys.modules["torch"] = fake
            tr._THREADS_TUNED = False
            tr.tune_for_inference()
            tr.tune_for_inference()
            self.assertEqual(fake.interop_calls, 1)
            self.assertEqual(fake.thread_calls, 1)
        finally:
            tr._THREADS_TUNED = saved
            if old is None:
                sys.modules.pop("torch", None)
            else:
                sys.modules["torch"] = old


class ManifestWorkerTests(unittest.TestCase):
    def setUp(self):
        import tools.sts_worker as worker

        self.worker = worker
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.src = self.root / "a.wav"
        self.src.write_bytes(b"RIFF-fake")
        self.models = {name: self.root / f"{name}.pth" for name in ("A", "B", "bad")}
        for model in self.models.values():
            model.touch()
        self.events, self.loads, self.converted = [], [], []
        self.side_loads = {"hubert": 0, "rmvpe": 0}
        fixture = self

        class VC:
            pipeline = None
            hubert_model = None

            def get_vc(self, model):
                fixture.loads.append(model)
                if model == str(fixture.models["bad"]) or not Path(model).is_file():
                    raise RuntimeError("模型损坏")
                self.model = model
                self.pipeline = SimpleNamespace(device="cpu", is_half=False)

        self.engine = worker._Engine()
        self.engine.config = SimpleNamespace(device="cpu", is_half=False)
        self.engine.vc = VC()

        def preload(vc, config, f0method, prog):
            if vc.hubert_model is None:
                self.side_loads["hubert"] += 1
                vc.hubert_model = object()
            if not hasattr(vc.pipeline, "model_rmvpe"):
                self.side_loads["rmvpe"] += 1
                vc.pipeline.model_rmvpe = object()

        def convert(vc, src, dest, **kwargs):
            self.converted.append((vc.model, str(src), kwargs["pitch"], kwargs["index_path"]))
            dest.write_bytes(b"audio")

        for name, value in (
            ("_ensure_rvc_env", None), ("_preflight_engine", None), ("_new_timer", None),
            ("_tune_torch", None), ("cuda_empty_cache", None),
        ):
            self.stack.enter_context(patch.object(worker, name, return_value=value))
        self.stack.enter_context(patch.object(worker, "emit", side_effect=lambda **e: self.events.append(e)))
        self.stack.enter_context(patch.object(worker, "preload_side_models", side_effect=preload))
        self.stack.enter_context(patch("tools.sts_core.convert_one", side_effect=convert))
        self.stack.enter_context(patch.dict(os.environ, {"TM_VOICE_ROOT": str(self.root)}))
        scipy = ModuleType("scipy")
        scipy_io = ModuleType("scipy.io")
        scipy.io = scipy_io
        scipy_io.wavfile = SimpleNamespace()
        self.stack.enter_context(patch.dict(sys.modules, {"scipy": scipy, "scipy.io": scipy_io}))

    def request(self, manifest):
        return dict(output=str(self.root / "out"), model=str(self.models["A"]), pitch=7, manifest=manifest)

    def item(self, model=None, tag="", **extra):
        entry = dict(src=str(self.src), rel="source/a.wav", tag=tag, **extra)
        if model:
            entry["model"] = str(self.models[model])
        return entry

    def test_model_order_reloads_only_on_changes_and_keeps_side_models(self):
        manifest = [self.item(tag="A1", pitch=0), self.item(tag="A2"), self.item("B", "B1", pitch=-4),
                    self.item("B", "B2", pitch=None), self.item("A", "A3")]
        rc = self.worker.run_request(self.engine, self.request(manifest))
        self.assertEqual(rc, 0)
        self.assertEqual(self.loads, [str(self.models[m]) for m in ("A", "B", "A")])
        self.assertEqual([c[0] for c in self.converted], [str(self.models[m]) for m in ("A", "A", "B", "B", "A")])
        self.assertEqual([c[2] for c in self.converted], [0, 7, -4, 7, 7])
        self.assertEqual(self.side_loads, {"hubert": 1, "rmvpe": 1})
        done = self.events[-1]
        self.assertEqual(done["phase"], "done")
        self.assertEqual(done["total"], len(manifest))
        self.assertEqual([r["tag"] for r in done["results"]], [e["tag"] for e in manifest])
        self.assertEqual([r["dest"] for r in done["results"]], done["files"])
        progress = [e["done"] for e in self.events if "done" in e]
        self.assertEqual(progress, sorted(progress))
        # 后续请求继续复用当前 A，换音色时也只重装 net_g。
        self.assertEqual(self.worker.run_request(self.engine, self.request([self.item()])), 0)
        self.assertEqual(self.loads, [str(self.models[m]) for m in ("A", "B", "A")])
        self.assertEqual(self.side_loads, {"hubert": 1, "rmvpe": 1})

    def test_failed_model_is_skipped_once_and_later_models_continue_in_order(self):
        manifest = [self.item("bad", "bad1"), self.item(tag="A1"), self.item("bad", "bad2"),
                    self.item("B", "B1"), self.item("B", "B2")]
        self.assertEqual(self.worker.run_request(self.engine, self.request(manifest)), 0)
        self.assertEqual(self.loads, [str(self.models[m]) for m in ("bad", "A", "B")])
        self.assertEqual([c[0] for c in self.converted], [str(self.models[m]) for m in ("A", "B", "B")])
        done = self.events[-1]
        self.assertEqual(done["total"], 5)
        self.assertEqual((done["ok"], done["skip"]), (3, 2))
        self.assertEqual([r["tag"] for r in done["results"]], ["A1", "B1", "B2"])
        self.assertEqual([r["tag"] for r in done["skipped"]], ["bad1", "bad2"])
        skips = [e for e in self.events if e["phase"] == "skip"]
        self.assertEqual([e["done"] for e in skips], [1, 3])
        self.assertEqual([e["tag"] for e in skips], ["bad1", "bad2"])
        for skipped in done["skipped"]:
            self.assertIn(str(self.models["bad"]), skipped["reason"])
            self.assertIn("模型损坏", skipped["reason"])

    def test_failed_default_model_does_not_abort_other_voices(self):
        req = self.request([self.item(tag="bad1"), self.item("A", "A"), self.item(tag="bad2")])
        req["model"] = str(self.models["bad"])
        self.assertEqual(self.worker.run_request(self.engine, req), 0)
        self.assertEqual(self.loads, [str(self.models[m]) for m in ("bad", "A")])
        self.assertEqual([r["tag"] for r in self.events[-1]["results"]], ["A"])

    def test_load_failure_after_success_does_not_lose_shared_models(self):
        manifest = [self.item(tag="A1"), self.item("bad", "bad1"), self.item(tag="A2"),
                    self.item("B", "B1"), self.item("bad", "bad2"), self.item("B", "B2")]
        self.assertEqual(self.worker.run_request(self.engine, self.request(manifest)), 0)
        self.assertEqual(self.loads, [str(self.models[m]) for m in ("A", "bad", "A", "B")])
        self.assertEqual(self.side_loads, {"hubert": 1, "rmvpe": 1})
        self.assertEqual([r["tag"] for r in self.events[-1]["results"]], ["A1", "A2", "B1", "B2"])

    def test_old_manifest_and_input_requests_keep_default_parameters(self):
        request_index = self.root / "request.index"
        request_index.touch()
        for manifest in ([{"src": str(self.src), "rel": "source/a.wav"}], None):
            with self.subTest(manifest=manifest):
                req = self.request(manifest)
                req.update(input=str(self.src), index=str(request_index))
                self.assertEqual(self.worker.run_request(self.engine, req), 0)
                done = self.events[-1]
                self.assertEqual(done["skipped"], [])
                self.assertEqual(Path(done["files"][0]).name, "a_rvc.wav")
                self.assertEqual(done["results"], [{"src": str(self.src), "dest": done["files"][0], "tag": ""}])
                self.assertEqual(self.converted[-1][2:], (7, str(request_index)))

    def test_conversion_timing_excludes_model_switches(self):
        from tools.sts_perf import StsTimer

        clock = [0.0]
        get_vc = self.engine.vc.get_vc

        def load(model):
            clock[0] += 2.0
            get_vc(model)

        def convert(vc, src, dest, **kwargs):
            clock[0] += 3.0
            dest.write_bytes(b"audio")

        with patch("tools.sts_worker.time.monotonic", side_effect=lambda: clock[0]):
            timer = StsTimer()
            with patch.object(self.worker, "_new_timer", return_value=timer), patch.object(
                self.worker, "_save_timing",
            ), patch.object(self.engine.vc, "get_vc", side_effect=load), patch(
                "tools.sts_core.convert_one", side_effect=convert,
            ):
                self.assertEqual(self.worker.run_request(self.engine, self.request([
                    self.item(tag="A1"), self.item(tag="A2"), self.item("B", "B1"),
                ])), 0)
            timing = timer.summary()
        self.assertEqual(timing["total_s"], 13.0)
        self.assertEqual(timing["stages_s"]["model"], 4.0)
        self.assertEqual(timing["stages_s"]["convert"], 9.0)

    def test_hot_handler_honors_entry_pitch_tag_and_results(self):
        # 只提取真实处理函数，避免导入 gui_v1 时加载 GUI、torch 和音频设备。
        import ast
        import traceback

        tree = ast.parse((ROOT / "gui_v1.py").read_text(encoding="utf-8"))
        handler = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_worker_convert")
        module = ast.Module(body=[handler], type_ignores=[])
        namespace = dict(os=os, traceback=traceback, flag_vc=False, printt=lambda *a: None,
                         _sts_stage=lambda *a: nullcontext())
        exec(compile(module, str(ROOT / "gui_v1.py"), "exec"), namespace)
        self.engine.vc.get_vc(str(self.models["A"]))
        resident = SimpleNamespace(
            config=self.engine.config, gui_config=SimpleNamespace(index_path=""),
            _sts_emit=lambda **e: self.events.append(e), _sts_timer=lambda: None,
            _sts_resident_vc=lambda *a: (self.engine.vc, ""), _sts_cancelled=lambda: False,
        )
        cuda_graph = ModuleType("tools.cuda_graph")
        cuda_graph.clear_cuda_graph_cache = lambda *a: None
        manifest = [self.item(tag="A/B", pitch=0), self.item(tag="down", pitch=-3), self.item(tag="default", pitch=None),
                    {"src": str(self.root / "gone.wav"), "tag": "missing"}]
        with patch.dict(sys.modules, {"tools.cuda_graph": cuda_graph}):
            namespace["_worker_convert"](resident, self.request(manifest))
        done = self.events[-1]
        self.assertEqual(done["phase"], "done")
        self.assertEqual([c[2] for c in self.converted], [0, -3, 7])
        self.assertEqual([r["tag"] for r in done["results"]], ["A/B", "down", "default"])
        self.assertEqual([r["dest"] for r in done["results"]], done["files"])
        self.assertEqual(Path(done["files"][0]).name, "a_A_B.wav")
        self.assertEqual(done["skipped"][0]["tag"], "missing")
        self.assertEqual(next(e for e in self.events if e["phase"] == "skip")["tag"], "missing")


class ResidentLoopTests(unittest.TestCase):
    """常驻模式的协议：一行一个请求，每批收尾补一行 idle。

    这里不碰 torch —— 请求全都在装模型之前就被判掉（模型文件不存在），
    走的是同一套「解析请求 → 报错 → 收尾」路径，协议部分完全一致。
    """

    def _run(self, argv, stdin_text):
        import io
        import json as _json

        import tools.sts_worker as w

        old_in, old_out = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = io.StringIO(stdin_text), io.StringIO()
        try:
            rc = w.main(argv)
            raw = sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout = old_in, old_out
        lines = [_json.loads(x) for x in raw.splitlines() if x.strip().startswith("{")]
        return rc, lines

    def _req(self, tmp, name):
        import json as _json

        path = Path(tmp) / name
        path.write_text(
            _json.dumps({"input": "a.wav", "output": tmp, "model": str(Path(tmp) / "nope.pth")}),
            encoding="utf-8",
        )
        return str(path)

    def test_one_shot_has_no_idle_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, lines = self._run(["sts_worker.py", self._req(tmp, "r1.json")], "")
            self.assertEqual(rc, 2)
            self.assertEqual([x["phase"] for x in lines], ["error"])

    def test_resident_serves_three_requests_then_stops_at_eof(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self._req(tmp, "r1.json")
            more = f"{self._req(tmp, 'r2.json')}\n\n{self._req(tmp, 'r3.json')}\n"
            rc, lines = self._run(["sts_worker.py", first, "--resident"], more)
            self.assertEqual(rc, 0)
            phases = [x["phase"] for x in lines]
            # 三条请求，每条一个 error 一个 idle；中间那行空行被忽略。
            self.assertEqual(phases, ["error", "idle", "error", "idle", "error", "idle"])

    def test_resident_stops_on_exit_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self._req(tmp, "r1.json")
            rest = f"exit\n{self._req(tmp, 'r2.json')}\n"
            rc, lines = self._run(["sts_worker.py", first, "--resident"], rest)
            self.assertEqual(rc, 0)
            # exit 之后那条请求不该再跑。
            self.assertEqual([x["phase"] for x in lines], ["error", "idle"])

    def test_unreadable_request_does_not_kill_the_resident(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("{ this is not json", encoding="utf-8")
            rest = f"{bad}\n{self._req(tmp, 'r2.json')}\n"
            rc, lines = self._run(["sts_worker.py", self._req(tmp, "r1.json"), "--resident"], rest)
            self.assertEqual(rc, 0)
            self.assertEqual(
                [x["phase"] for x in lines],
                ["error", "idle", "error", "idle", "error", "idle"],
            )


if __name__ == "__main__":
    unittest.main()

