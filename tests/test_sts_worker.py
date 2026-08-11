"""Unit tests for STS worker helpers (no GPU / model weights required)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.sts_worker import (  # noqa: E402
    StsProgress,
    _ensure_rvc_env,
    _friendly_error,
    collect_inputs,
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

        import tools.sts_worker as sw

        old = sw.emit
        sw.emit = capture
        try:
            p = StsProgress(1, "rmvpe")
            p.load("config", 1.0)
            p.load("model", 1.0)
            p.begin_file(1, "a.wav")
            p.stage("read", 1.0)
            p.stage("f0", 0.0)
            p.stage("f0", 1.0)
            p.stage("infer", 0.5)
            p.stage("write", 1.0)
            p.file_done(1, "a.wav", ok=True)
        finally:
            sw.emit = old

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

        import tools.sts_worker as sw

        old = sw.emit
        sw.emit = capture
        try:
            p = StsProgress(2, "harvest")
            p.load("model", 1.0)
            p.begin_file(1, "a.wav")
            p.file_done(1, "a.wav", ok=True)
            p.begin_file(2, "b.wav")
        finally:
            sw.emit = old

        second_start = next(e for e in events if e.get("step") == "file_start" and "b.wav" in e["message"])
        # 第二个文件起点应在 50% 附近（10% 加载 + 45% 第一个文件）
        self.assertGreaterEqual(second_start["pct"], 50)
        self.assertLess(second_start["pct"], 60)

    def test_f0_and_infer_report_percent_in_message(self):
        events = []

        def capture(**kw):
            events.append(kw)

        import tools.sts_worker as sw

        old = sw.emit
        sw.emit = capture
        try:
            p = StsProgress(1, "rmvpe")
            p.load("model", 1.0)
            p.begin_file(1, "song.wav")
            p.stage("f0", 0.0)
            p.stage("f0", 0.33)
            p.stage("f0", 0.67)
            p.stage("infer", 0.0)
            p.stage("infer", 0.4)
            p.stage("infer", 0.9)
        finally:
            sw.emit = old

        f0 = [e for e in events if e.get("step") == "f0"]
        inf = [e for e in events if e.get("step") == "infer"]
        self.assertTrue(any("33%" in e["message"] for e in f0))
        self.assertTrue(any("40%" in e["message"] for e in inf))
        # 同阶段百分比应往上走
        f0_pcts = [e["pct"] for e in f0]
        self.assertEqual(f0_pcts, sorted(f0_pcts))


if __name__ == "__main__":
    unittest.main()
