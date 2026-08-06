# -*- coding: utf-8 -*-
"""Unit tests for tools.worker_protocol atomic JSON writes."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from tools import worker_protocol as rp


class WriteJsonTests(unittest.TestCase):
    def test_write_json_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "status.json"
            rp._write_json(path, {"state": "idle", "pid": 1})
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["state"], "idle")
            self.assertEqual(data["pid"], 1)
            # unique temps must not be left behind
            leftovers = list(Path(td).glob("status.json.*"))
            self.assertEqual(leftovers, [])

    def test_write_json_retries_permission_error(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "status.json"
            path.write_text("{}", encoding="utf-8")
            calls = {"n": 0}
            real_replace = rp.os.replace

            def flaky_replace(src, dst):
                calls["n"] += 1
                if calls["n"] < 3:
                    raise PermissionError(
                        5, "Access is denied", src, None, dst
                    )
                return real_replace(src, dst)

            with mock.patch.object(rp.os, "replace", side_effect=flaky_replace):
                rp._write_json(path, {"state": "running", "pid": 42})
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["state"], "running")
            self.assertEqual(data["pid"], 42)
            self.assertGreaterEqual(calls["n"], 3)

    def test_write_json_falls_back_after_retries(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "status.json"

            def always_deny(src, dst):
                raise PermissionError(5, "Access is denied", src, None, dst)

            with mock.patch.object(rp.os, "replace", side_effect=always_deny):
                with mock.patch.object(rp, "_WRITE_RETRIES", 2):
                    with mock.patch.object(rp, "_WRITE_RETRY_BASE_S", 0):
                        rp._write_json(path, {"ok": True})
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(data["ok"])

    def test_concurrent_writers_no_raise(self):
        """Many threads writing the same path must not raise PermissionError."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "status.json"
            errors: list[BaseException] = []

            def worker(i: int) -> None:
                try:
                    for j in range(20):
                        rp._write_json(path, {"i": i, "j": j})
                except BaseException as e:  # noqa: BLE001 — collect any failure
                    errors.append(e)

            threads = [
                threading.Thread(target=worker, args=(i,)) for i in range(6)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)
            self.assertEqual(errors, [])
            self.assertTrue(path.is_file())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("i", data)
            self.assertIn("j", data)

    def test_write_status_clears_stale_message_code(self):
        """Boot leaves engine.starting; idle/ready must not keep that code."""
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            with mock.patch.object(rp, "CONTROL_DIR", td_path), mock.patch.object(
                rp, "STATUS_PATH", td_path / "status.json"
            ):
                rp.write_status(
                    state="starting",
                    message_code="engine.starting",
                    message="引擎进程已启动，正在加载…",
                )
                rp.write_status(state="idle", message="引擎就绪")
                data = json.loads(
                    (td_path / "status.json").read_text(encoding="utf-8")
                )
                self.assertEqual(data["state"], "idle")
                self.assertEqual(data["message"], "引擎就绪")
                self.assertEqual(data.get("message_code", ""), "")
                # Explicit code still wins when provided with the update.
                rp.write_status(
                    state="starting",
                    message_code="vc.loading_model",
                    message="正在加载音色模型…",
                )
                data = json.loads(
                    (td_path / "status.json").read_text(encoding="utf-8")
                )
                self.assertEqual(data["message_code"], "vc.loading_model")


if __name__ == "__main__":
    unittest.main()
