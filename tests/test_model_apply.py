# -*- coding: utf-8 -*-
"""模型应用契约（model_apply / model_active / model_selected）的 worker 侧测试。

gui_v1 顶层要 import torch/sounddevice，整文件不可入测。这里用 AST 把
`_emit_model_apply` / `_drain_model_events` / `_worker_swap_model` /
`_preload_pending_model` / `_install_ready_model` / `_apply_pending_model` /
`_worker_drop_model` 真编出来跑 —— 执行的是仓库里的真实函数体，不是抄写。

轻量替身：self 用 SimpleNamespace，模型用带 net_g/tgt_sr 的假对象，音频
线程的「装上」就是直接调 _install_ready_model。status.json 写到临时目录。
"""

import ast
import json
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import worker_protocol as wp  # noqa: E402

METHODS = (
    "_emit_model_apply",
    "_queue_status_hint",
    "_drain_model_events",
    "_worker_swap_model",
    "_preload_pending_model",
    "_install_ready_model",
    "_apply_pending_model",
    "_worker_drop_model",
)


def _extract(names):
    tree = ast.parse((ROOT / "gui_v1.py").read_text(encoding="utf-8"))
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in names:
            found[node.name] = node
    missing = [n for n in names if n not in found]
    if missing:
        raise AssertionError(f"gui_v1.py 里找不到方法：{missing}")
    mod = ast.fix_missing_locations(
        ast.Module(body=[found[n] for n in names], type_ignores=[])
    )
    ns = {}
    exec(compile(mod, str(ROOT / "gui_v1.py"), "exec"), ns)
    return ns


FNS = _extract(METHODS)


class _FakeRvc:
    """够用的假模型：swap 逻辑只读 net_g / tgt_sr / f0_repair /
    change_index_rate。"""

    def __init__(self, tag):
        self.net_g = object()
        self.tgt_sr = 48000
        self.tag = tag
        self.f0_repair = False
        self.index_rates = []

    def change_index_rate(self, rate):
        self.index_rates.append(rate)


def _bad_rvc(*_a, **_k):
    return _BadRvc()


class _BadRvc:
    net_g = None
    tgt_sr = 0


class FakeSelf(types.SimpleNamespace):
    pass


def _make_self(tmp):
    pth_a = tmp / "a.pth"
    pth_a.write_bytes(b"x")
    pth_b = tmp / "b.pth"
    pth_b.write_bytes(b"x")
    idx_b = tmp / "b.index"
    idx_b.write_bytes(b"x")
    gui = types.SimpleNamespace(
        pth_path=str(pth_a),
        index_path="",
        index_rate=0.0,
        sr_type="sr_device",
        samplerate=48000,
        pitch=0,
        formant=0.0,
        n_cpu=4,
    )
    attached = []

    def _attach(new, pth, idx, rate):
        attached.append((new.tag, pth, idx, rate))
        self.rvc = new
        gui.pth_path = pth
        gui.index_path = idx
        gui.index_rate = rate

    self = FakeSelf(
        gui_config=gui,
        config=types.SimpleNamespace(dml=False),
        rvc=_FakeRvc("old"),
        resampler2=None,
        dsp_only=False,
        function="vc",
        sola_buffer=types.SimpleNamespace(zero_=lambda: None),
        _pending_model=None,
        _pending_model_lock=threading.Lock(),
        _swap_ready=None,
        _swap_busy=False,
        _swap_progress=0,
        _swap_loader=None,
        _model_swap_error="",
        _model_events=[],
        _status_hints=[],
        _model_apply=None,
        _model_active=None,
        _model_selected={"pth_path": "", "index_path": ""},
        _attach_rvc=_attach,
        _worker_write_status=lambda **_f: None,
        _ckpt_tgt_sr=lambda _p: 48000,
        _rebuild_voice_chain=lambda: None,
        _swap_in_flight=lambda: False,
        # swap 内部会 spawn 一个 daemon 线程调 _preload_pending_model；测试里
        # 手动驱动真函数，替身只吞掉这个线程入口，保证确定性。
        _preload_pending_model=lambda _job: None,
        _on_swap_progress=lambda *a, **k: None,
        _worker_start=lambda **_k: None,
    )
    # _emit_model_apply / _queue_status_hint 走真实函数体（其它方法经 self. 调）。
    self._emit_model_apply = types.MethodType(FNS["_emit_model_apply"], self)
    self._queue_status_hint = types.MethodType(FNS["_queue_status_hint"], self)
    self._attached = attached
    return self


class ModelApplyContractTest(unittest.TestCase):
    """跑真实函数体；每一个 case 一个干净替身 + 独立临时 status。"""

    @classmethod
    def setUpClass(cls):
        cls.fns = _extract(METHODS)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tm-model-apply-"))
        self.control = self.tmp / "runtime_control"
        self.control.mkdir(parents=True)
        self._saved = (wp.CONTROL_DIR, wp.STATUS_PATH)
        wp.CONTROL_DIR = self.control
        wp.STATUS_PATH = self.control / "status.json"
        self.g = types.SimpleNamespace(
            flag_vc=True,
            rvc_for_realtime=types.SimpleNamespace(RVC=lambda *a, **k: _FakeRvc("new")),
            inp_q=None,
            opt_q=None,
            os=__import__("os"),
            sys=sys,
            threading=threading,
            traceback=__import__("traceback"),
            printt=lambda *a, **k: None,
            _msg=lambda *a, **k: {},
            VC_SWAPPING="vc.swapping",
            VC_RUNNING="vc.running",
            VC_SWAP_FAILED="vc.swap_failed",
            VC_LOADING_NET="vc.loading_net",
        )
        # 让抽出来的函数看见这些全局名。
        for name in METHODS:
            fn = self.fns[name]
            for k, v in self.g.__dict__.items():
                fn.__globals__[k] = v

    def tearDown(self):
        wp.CONTROL_DIR, wp.STATUS_PATH = self._saved
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _swap(self, self_obj, *a, **k):
        return self.fns["_worker_swap_model"](self_obj, *a, **k)

    def _preload(self, self_obj, job):
        return self.fns["_preload_pending_model"](self_obj, job)

    def _install(self, self_obj):
        return self.fns["_install_ready_model"](self_obj)

    def _apply_dml(self, self_obj):
        return self.fns["_apply_pending_model"](self_obj)

    def _drop(self, self_obj, seq=0):
        return self.fns["_worker_drop_model"](self_obj, seq=seq)

    def _drain(self, self_obj):
        return self.fns["_drain_model_events"](self_obj)

    def _status(self):
        if not wp.STATUS_PATH.is_file():
            return {}
        return json.loads(wp.STATUS_PATH.read_text(encoding="utf-8"))

    def test_swap_publishes_loading_then_committed_with_full_identity(self):
        s = _make_self(self.tmp)
        self._swap(s, str(self.tmp / "b.pth"), str(self.tmp / "b.index"), 0.5, seq=42)
        self._drain(s)
        st = self._status()
        self.assertEqual(
            st["model_selected"],
            {"pth_path": str(self.tmp / "b.pth"), "index_path": str(self.tmp / "b.index")},
        )
        self.assertEqual(st["model_apply"]["phase"], "loading")
        self.assertEqual(st["model_apply"]["seq"], 42)

        # 后台线程读好权重：只是把 _swap_ready 摆上，还不许算 applied。
        job = s._pending_model
        self._preload(s, job)
        self.assertIsNotNone(s._swap_ready)

        # 音频线程装指针 —— committed 只能从这里来。
        self._install(s)
        self._drain(s)
        st = self._status()
        self.assertEqual(st["model_apply"]["phase"], "committed")
        self.assertEqual(st["model_apply"]["seq"], 42)
        self.assertEqual(st["model_apply"]["pth_path"], str(self.tmp / "b.pth"))
        self.assertEqual(st["model_apply"]["index_path"], str(self.tmp / "b.index"))
        self.assertEqual(
            st["model_active"],
            {"pth_path": str(self.tmp / "b.pth"), "index_path": str(self.tmp / "b.index")},
        )
        self.assertEqual(s._attached[-1][0], "new")

    def test_failed_load_keeps_the_old_active_model(self):
        s = _make_self(self.tmp)
        old = s.rvc
        self.g.rvc_for_realtime.RVC = _bad_rvc
        for name in ("_preload_pending_model",):
            self.fns[name].__globals__["rvc_for_realtime"] = self.g.rvc_for_realtime
        self._swap(s, str(self.tmp / "b.pth"), "", None, seq=7)
        self._preload(s, s._pending_model)
        self._drain(s)
        st = self._status()
        self.assertEqual(st["model_apply"]["phase"], "failed")
        self.assertEqual(st["model_apply"]["seq"], 7)
        self.assertIn("换模型失败", st["model_apply"]["error"])
        self.assertIsNone(st.get("model_active"))
        self.assertIs(s.rvc, old, "失败的加载绝不能动推理链上的旧模型")

    def test_stale_ready_pack_is_never_committed_over_a_newer_job(self):
        s = _make_self(self.tmp)
        # A 读好了等装；此刻 B 又排队进来。
        job_a = (str(self.tmp / "a2.pth"), "", 0.0, 11)
        job_b = (str(self.tmp / "b.pth"), "", 0.0, 12)
        s._pending_model = job_a
        s._swap_ready = (_FakeRvc("stale-A"), job_a[0], job_a[1], job_a[2], job_a[3])
        s._pending_model = job_b
        self._install(s)
        self._drain(s)
        self.assertEqual(s._attached, [], "被新请求顶掉的包不许装上")
        st = self._status()
        self.assertNotEqual(
            (st.get("model_apply") or {}).get("seq"),
            11,
            "作废的加载不许产出 committed 记录",
        )

    def test_idle_swap_marks_selected_without_apply_record(self):
        s = _make_self(self.tmp)
        self.fns["_worker_swap_model"].__globals__["flag_vc"] = False
        self._swap(s, str(self.tmp / "b.pth"), "", None, seq=5)
        self._drain(s)
        st = self._status()
        self.assertEqual(st["model_selected"]["pth_path"], str(self.tmp / "b.pth"))
        self.assertIsNone(st.get("model_apply"), "没在跑时没有可提交的指针")
        self.assertEqual(s.gui_config.pth_path, str(self.tmp / "b.pth"))

    def test_same_model_request_commits_immediately(self):
        s = _make_self(self.tmp)
        self._swap(s, s.gui_config.pth_path, "", None, seq=3)
        self._drain(s)
        st = self._status()
        self.assertEqual(st["model_apply"]["phase"], "committed")
        self.assertEqual(st["model_apply"]["seq"], 3)
        self.assertEqual(
            s.rvc.index_rates, [0.0], "no-op 也要把请求的 index_rate 热推上链"
        )

    def test_same_pth_with_a_different_index_is_a_real_load(self):
        """同 pth 不同 index：链上跑的还是旧索引 —— 不许按 no-op 记
        committed，必须真加载，装完才落这条 seq 的 committed。"""
        s = _make_self(self.tmp)
        new_idx = self.tmp / "new.index"
        new_idx.write_bytes(b"x")
        s.gui_config.index_path = str(self.tmp / "old.index")
        self._swap(s, s.gui_config.pth_path, str(new_idx), 0.5, seq=9)
        self._drain(s)
        st = self._status()
        self.assertEqual(st["model_apply"]["phase"], "loading")
        self.assertEqual(st["model_apply"]["seq"], 9)
        self.assertIsNotNone(s._pending_model, "index 不同就必须真加载")
        self._preload(s, s._pending_model)
        self._install(s)
        self._drain(s)
        st = self._status()
        self.assertEqual(st["model_apply"]["phase"], "committed")
        self.assertEqual(st["model_apply"]["index_path"], str(new_idx))

    def test_same_pth_without_a_bound_chain_is_not_a_noop(self):
        """pth 对得上但推理链上没绑模型（rvc=None）：committed 是谎话，
        必须走真加载。"""
        s = _make_self(self.tmp)
        s.rvc = None
        self._swap(s, s.gui_config.pth_path, "", None, seq=10)
        self.assertIsNotNone(s._pending_model, "链上没模型就必须真加载")
        self._preload(s, s._pending_model)
        self._install(s)
        self._drain(s)
        st = self._status()
        self.assertEqual(st["model_apply"]["phase"], "committed")
        self.assertEqual(st["model_apply"]["seq"], 10)

    def test_stop_and_devices_publish_own_completion_seq(self):
        """stop_seq / devices_seq：壳只认「这条命令」的完结证据。
        _worker_stop 成功失败都要写 stop_seq；_worker_list_devices 同理。"""
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        stop = src[src.index("def _worker_stop") : src.index("def _sts_timer")]
        self.assertGreaterEqual(stop.count("stop_seq=seq"), 2)
        dev = src[src.index("def _worker_list_devices") : src.index(
            "def _worker_apply_hot"
        )]
        self.assertGreaterEqual(dev.count("devices_seq=seq"), 2)
        dsp = (ROOT / "tools" / "dsp_worker.py").read_text(encoding="utf-8")
        self.assertIn("stop_seq=seq", dsp)
        self.assertIn("devices_seq=seq", dsp)

    def test_missing_file_is_a_failed_record_not_silence(self):
        s = _make_self(self.tmp)
        self._swap(s, str(self.tmp / "gone.pth"), "", None, seq=8)
        self._drain(s)
        st = self._status()
        self.assertEqual(st["model_apply"]["phase"], "failed")
        self.assertEqual(st["model_apply"]["seq"], 8)
        self.assertTrue(st["model_apply"]["error"])

    def test_drop_model_commits_an_empty_identity(self):
        s = _make_self(self.tmp)
        self._drop(s, seq=4)
        self._drain(s)
        st = self._status()
        self.assertEqual(st["model_apply"]["phase"], "committed")
        self.assertEqual(st["model_apply"]["seq"], 4)
        self.assertIsNone(st["model_active"], "丢音色后 model_active 必须是 null")

    def test_dml_inline_path_commits_and_fails_the_same_way(self):
        s = _make_self(self.tmp)
        s.config.dml = True
        self._swap(s, str(self.tmp / "b.pth"), "", None, seq=21)
        self.assertFalse(s._swap_busy)
        self._apply_dml(s)
        self._drain(s)
        st = self._status()
        self.assertEqual(st["model_apply"]["phase"], "committed")
        self.assertEqual(st["model_apply"]["seq"], 21)

        s2 = _make_self(self.tmp)
        s2.config.dml = True
        self.g.rvc_for_realtime.RVC = _bad_rvc
        self.fns["_apply_pending_model"].__globals__["rvc_for_realtime"] = (
            self.g.rvc_for_realtime
        )
        self._swap(s2, str(self.tmp / "b.pth"), "", None, seq=22)
        self._apply_dml(s2)
        self._drain(s2)
        st = self._status()
        self.assertEqual(st["model_apply"]["phase"], "failed")
        self.assertEqual(st["model_apply"]["seq"], 22)

    def test_default_status_carries_null_model_fields(self):
        st = wp.default_status()
        for key in ("model_selected", "model_active", "model_apply"):
            self.assertIn(key, st)
            self.assertIsNone(st[key], f"{key} 默认必须是 null，清掉旧记录")

    def test_start_publishes_commit_and_failure_records(self):
        """_worker_start 的三处 emit：成功 committed、set_values 拒绝 failed、
        异常 failed —— 缺一处，DSP→RVC 的「实际选中校验」就断链。"""
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        start = src.index("def _worker_start")
        end = src.index("def _worker_stop")
        body = src[start:end]
        self.assertGreaterEqual(
            body.count('phase="committed"'),
            2,
            "vc 有音色、纯 DSP 空目标各要一笔 committed",
        )
        self.assertIn(
            'phase="selected"', body, "起来的是谁要同步进 model_selected"
        )
        self.assertGreaterEqual(
            body.count('phase="failed"'), 2, "_worker_start 要有两处 failed"
        )
        self.assertIn("start_seq", body, "应用记录必须带着发令的 seq")

    def test_attach_failure_is_failed_record_and_old_pointer_survives(self):
        """_attach_rvc 抛错：提交没发生（重采样器这类准备先做完才换指针），
        self.rvc 还是旧的；必须记 failed，不许假装旧模型还在又不留记录。"""
        s = _make_self(self.tmp)
        old = s.rvc

        def _boom(_new, _p, _i, _r):
            raise RuntimeError("resample init failed")

        s._attach_rvc = _boom
        self._swap(s, str(self.tmp / "b.pth"), "", None, seq=31)
        self._preload(s, s._pending_model)
        self.assertIsNotNone(s._swap_ready)
        self._install(s)
        self._drain(s)
        st = self._status()
        self.assertEqual(st["model_apply"]["phase"], "failed")
        self.assertEqual(st["model_apply"]["seq"], 31)
        self.assertIsNone(st.get("model_active"))
        self.assertIs(s.rvc, old, "attach 失败时指针不许换")

        # DML 内联路径同样要兜住。
        s2 = _make_self(self.tmp)
        s2.config.dml = True
        s2._attach_rvc = _boom
        self._swap(s2, str(self.tmp / "b.pth"), "", None, seq=32)
        self._apply_dml(s2)
        self._drain(s2)
        st = self._status()
        self.assertEqual(st["model_apply"]["phase"], "failed")
        self.assertEqual(st["model_apply"]["seq"], 32)

    def test_status_write_is_serialized_so_confirm_survives(self):
        """write_status 进程内串行：模型确认写和别处的普通更新交错时，
        committed 记录不能被旧快照盖掉。确定性模拟交错：两条线程各自
        连写多轮，最后盘上必须两边最后的值都在。"""
        import threading as _th

        errs = []

        def _writer(tag):
            try:
                for i in range(40):
                    wp.write_status(**{f"k_{tag}": i})
            except Exception as e:  # pragma: no cover
                errs.append(e)

        ts = [_th.Thread(target=_writer, args=(t,)) for t in ("a", "b", "c")]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(errs, [])
        st = self._status()
        for tag in ("a", "b", "c"):
            self.assertEqual(st.get(f"k_{tag}"), 39, f"{tag} 的写入被旧快照盖掉了")

        # 确认记录与普通更新交错：写完 model_apply 后再被别的线程写
        # 普通字段，确认记录必须还在。
        s = _make_self(self.tmp)
        self._swap(s, str(self.tmp / "b.pth"), "", None, seq=51)
        self._preload(s, s._pending_model)
        self._install(s)
        self._drain(s)
        wp.write_status(progress=77, state="running")
        st = self._status()
        self.assertEqual(st["model_apply"]["phase"], "committed")
        self.assertEqual(st["model_apply"]["seq"], 51)
        self.assertEqual(st["progress"], 77)


if __name__ == "__main__":
    unittest.main()
