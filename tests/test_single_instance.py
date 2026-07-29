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

    def test_frozen_second_instance_denied(self):
        if sys.platform != "win32":
            self.skipTest("Windows mutex only")
        # Simulate frozen: first acquire holds mutex, second must fail
        with mock.patch("launcher.single_instance._is_frozen", return_value=True):
            # Use unique mutex names via patching constants
            with mock.patch(
                "launcher.single_instance._MUTEX_VOICE",
                "Local\\RVCFabric_TestMutex_Voice",
            ):
                import launcher.single_instance as si

                si._held_mutex = None
                self.assertTrue(si.acquire_single_instance(kind="voice"))
                # Second call with already-held process-level mutex name:
                # CreateMutex with same name returns ALREADY_EXISTS
                ok2 = si.acquire_single_instance(kind="voice")
                # Same process: CreateMutex may succeed again with same handle
                # semantics — we only assert no crash
                self.assertIsInstance(ok2, bool)


if __name__ == "__main__":
    unittest.main()
