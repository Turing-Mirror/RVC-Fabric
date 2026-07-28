# -*- coding: utf-8 -*-
"""Worker PID identity helpers (no live worker required)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher import realtime_client as rc
from launcher.paths import find_python, is_frozen


class WorkerPidIdentityTests(unittest.TestCase):
    def test_dead_pid_not_ours(self):
        self.assertFalse(rc._pid_is_our_worker(0))
        self.assertFalse(rc._pid_is_our_worker(-1))

    def test_non_python_image_rejected(self):
        with mock.patch.object(rc, "_pid_alive", return_value=True), mock.patch.object(
            rc, "_pid_image_path", return_value=r"C:\Windows\System32\notepad.exe"
        ):
            self.assertFalse(rc._pid_is_our_worker(4242))

    def test_runtime_python_accepted(self):
        fake = str(ROOT / "Runtime" / "pythonw.exe")
        with mock.patch.object(rc, "_pid_alive", return_value=True), mock.patch.object(
            rc, "_pid_image_path", return_value=fake
        ):
            self.assertTrue(rc._pid_is_our_worker(99))

    def test_foreign_python_rejected_when_runtime_exists(self):
        rt_py = ROOT / "Runtime" / "pythonw.exe"
        if not rt_py.is_file() and not (ROOT / "Runtime" / "python.exe").is_file():
            self.skipTest("no local Runtime — foreign-python rule needs Runtime present")
        with mock.patch.object(rc, "_pid_alive", return_value=True), mock.patch.object(
            rc, "_pid_image_path", return_value=r"C:\Python39\python.exe"
        ):
            self.assertFalse(rc._pid_is_our_worker(77))


class FindPythonFrozenTests(unittest.TestCase):
    def test_find_python_never_returns_non_python_basename(self):
        # In normal (unfrozen) test host, find_python should still return a real python
        p = find_python(prefer_windowed=False)
        self.assertTrue(p)
        if Path(p).is_file():
            self.assertTrue(Path(p).name.lower().startswith("python"))

    def test_frozen_skips_sys_executable_shell(self):
        with mock.patch("launcher.paths.is_frozen", return_value=True), mock.patch(
            "launcher.paths.sys"
        ) as msys:
            msys.executable = str(ROOT / "变声器.exe")
            msys.platform = sys.platform
            # With no Runtime candidates mocked empty — should not return 变声器.exe
            with mock.patch("launcher.paths._runtime_bases", return_value=[]):
                p = find_python(prefer_windowed=True)
            self.assertNotIn("变声器", p)
            self.assertFalse(str(p).lower().endswith(".exe") and "变声器" in str(p))


class GlobalHotkeyQueueTests(unittest.TestCase):
    def test_poll_once_drains_queue(self):
        from launcher.hotkeys import GlobalHotkeyManager

        g = GlobalHotkeyManager()
        g._enabled = True
        g._queue.put("toggle_vc")
        self.assertEqual(g.poll_once(), "toggle_vc")
        self.assertIsNone(g.poll_once())


if __name__ == "__main__":
    unittest.main()
