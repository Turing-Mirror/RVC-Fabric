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

    def test_write_status_keeps_progress(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            with mock.patch.object(rp, "CONTROL_DIR", td_path), mock.patch.object(
                rp, "STATUS_PATH", td_path / "status.json"
            ):
                rp.write_status(
                    state="starting",
                    message_code="vc.warmup",
                    message="正在预热引擎（首次较慢）…",
                    progress=78,
                )
                data = json.loads(
                    (td_path / "status.json").read_text(encoding="utf-8")
                )
                self.assertEqual(data["progress"], 78)
                self.assertEqual(data["message_code"], "vc.warmup")
                rp.write_status(state="running", progress=100, message_code="vc.running")
                data = json.loads(
                    (td_path / "status.json").read_text(encoding="utf-8")
                )
                self.assertEqual(data["progress"], 100)
                self.assertEqual(data["message_code"], "vc.running")


class MsgCodeTests(unittest.TestCase):
    def test_new_load_codes_have_zh_fallback(self):
        from tools import msg_codes as mc

        for code in (
            mc.ENGINE_IMPORTING,
            mc.VC_LOADING_INDEX,
            mc.VC_LOADING_HUBERT,
            mc.VC_LOADING_NET,
            mc.VC_WARMUP,
            mc.VC_OPENING_STREAM,
            mc.VC_SWAPPING,
            mc.VC_SWAP_FAILED,
        ):
            text = mc.fallback_message(code)
            self.assertTrue(text and text != code, code)
            self.assertNotIn("{", text)

    def test_locale_packs_have_load_keys(self):
        root = ROOT / "app" / "i18n" / "locales"
        keys = (
            ("dock", "switching"),
            ("msg", "engine", "importing"),
            ("msg", "vc", "swapping"),
            ("msg", "vc", "warmup"),
            ("msg", "vc", "opening_stream"),
            ("msg", "vc", "swap_failed"),
        )
        for path in sorted(root.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for parts in keys:
                cur = data
                for p in parts:
                    self.assertIn(p, cur, f"{path.name} missing {'.'.join(parts)}")
                    cur = cur[p]
                self.assertIsInstance(cur, str)
                self.assertTrue(cur.strip(), f"{path.name} empty {'.'.join(parts)}")


if __name__ == "__main__":
    unittest.main()
