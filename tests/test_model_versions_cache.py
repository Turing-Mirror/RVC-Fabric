"""Execute the real idle-cache/prewarm handlers without opening audio or loading torch."""
import ast
import json
import os
import tempfile
import threading
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import mock_open, patch

ROOT = Path(__file__).resolve().parents[1]


class ModelVersionCacheTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((ROOT / "gui_v1.py").read_text(encoding="utf-8"))
        methods = {"_cmd_prewarm", "_worker_invalidate_model"}
        nodes = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in methods]
        self.jobs, self.status = [], []
        jobs = self.jobs

        class Thread:
            def __init__(self, target, **kwargs):
                self.target = target

            def start(self):
                jobs.append(self.target)

        self.ns = dict(os=os, json=json, flag_vc=False, inp_q=None, opt_q=None,
                       printt=lambda *a: None, traceback=traceback,
                       threading=SimpleNamespace(Thread=Thread),
                       torch=SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)),
                       rvc_for_realtime=SimpleNamespace(RVC=lambda *a: SimpleNamespace(tgt_sr=48000, net_g=object())))
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / "gui_v1.py"), "exec"), self.ns)
        self.worker = SimpleNamespace(
            _pending_model_lock=threading.Lock(), _pending_model=object(), _swap_ready=object(), _swap_busy=True,
            _prewarmed=object(), rvc=object(), resampler2=object(), config=SimpleNamespace(),
            gui_config=SimpleNamespace(n_cpu=2, pth_path="voice.pth", index_path="keep.index"),
            _worker_write_status=lambda **data: self.status.append(data),
        )

    def test_invalidation_drops_old_weights_and_acknowledges_without_changing_selection(self):
        self.ns["_worker_invalidate_model"](self.worker, 12)
        for key in ("rvc", "_prewarmed", "resampler2", "_pending_model", "_swap_ready"):
            self.assertIsNone(getattr(self.worker, key))
        self.assertEqual(self.worker.gui_config.pth_path, "voice.pth")
        self.assertEqual(self.worker.gui_config.index_path, "keep.index")
        self.assertEqual(self.status, [{"model_active": None, "model_cache_seq": 12}])

    def test_preload_that_finishes_after_invalidation_cannot_restore_old_weights(self):
        with tempfile.TemporaryDirectory() as td:
            model = Path(td) / "voice.pth"
            model.write_bytes(b"old")
            saved = json.dumps({"pth_path": str(model), "index_path": "keep.index"})
            self.worker._prewarmed = None
            with patch("builtins.open", mock_open(read_data=saved)):
                self.ns["_cmd_prewarm"](self.worker)
                self.assertTrue(self.worker._prewarm_busy)
                self.ns["_worker_invalidate_model"](self.worker, 13)
                model.write_bytes(b"new")
                self.jobs.pop(0)()
                self.assertIsNone(self.worker._prewarmed)
                self.assertFalse(self.worker._prewarm_busy)
                self.ns["_cmd_prewarm"](self.worker)
                self.jobs.pop(0)()
                self.assertIsNotNone(self.worker._prewarmed)
                self.assertEqual(self.worker._prewarmed.pth_path_str, str(model))


if __name__ == "__main__":
    unittest.main()
