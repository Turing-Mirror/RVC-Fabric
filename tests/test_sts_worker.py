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


if __name__ == "__main__":
    unittest.main()
