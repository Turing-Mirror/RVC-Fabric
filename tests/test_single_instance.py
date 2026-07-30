# -*- coding: utf-8 -*-
"""single_instance: non-frozen always allows multi instance."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.single_instance import acquire_single_instance


class SingleInstanceTests(unittest.TestCase):
    def test_dev_always_allows(self):
        # Non-frozen: never block multiple processes
        self.assertTrue(acquire_single_instance(kind="voice"))
        self.assertTrue(acquire_single_instance(kind="bootstrap"))

    def test_frozen_same_process_reentry_ok(self):
        """shell_entry then main() both call acquire — must not self-block."""
        if sys.platform != "win32":
            self.skipTest("Windows mutex only")
        with mock.patch("launcher.single_instance._is_frozen", return_value=True):
            with mock.patch(
                "launcher.single_instance._MUTEX_VOICE",
                "Local\\RVCFabric_TestMutex_Reentry",
            ):
                import launcher.single_instance as si

                si._held_mutex = None
                self.assertTrue(si.acquire_single_instance(kind="voice"))
                # Second call in the same process must succeed (held handle)
                self.assertTrue(si.acquire_single_instance(kind="voice"))
                self.assertIsNotNone(si._held_mutex)
                # cleanup so other tests / re-runs do not leak the name
                try:
                    import ctypes

                    if si._held_mutex:
                        ctypes.windll.kernel32.CloseHandle(si._held_mutex)
                except Exception:
                    pass
                si._held_mutex = None

    def test_frozen_second_process_denied(self):
        if sys.platform != "win32":
            self.skipTest("Windows mutex only")
        with mock.patch("launcher.single_instance._is_frozen", return_value=True):
            with mock.patch(
                "launcher.single_instance._MUTEX_VOICE",
                "Local\\RVCFabric_TestMutex_Peer",
            ):
                import launcher.single_instance as si

                si._held_mutex = None
                self.assertTrue(si.acquire_single_instance(kind="voice"))
                held = si._held_mutex
                # Simulate a peer process: clear process-local hold, then
                # CreateMutex on the same name should report already exists.
                si._held_mutex = None
                self.assertFalse(si.acquire_single_instance(kind="voice"))
                try:
                    import ctypes

                    if held:
                        ctypes.windll.kernel32.CloseHandle(held)
                except Exception:
                    pass
                si._held_mutex = None


if __name__ == "__main__":
    unittest.main()
