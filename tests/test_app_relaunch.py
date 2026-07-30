# -*- coding: utf-8 -*-
"""Unit tests for delayed relaunch helpers (no process spawn)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.app_relaunch import delayed_start_cmd


class DelayedStartCmdTests(unittest.TestCase):
    def test_cmd_quotes_path_and_delays(self):
        argv = delayed_start_cmd(Path(r"C:\App\变声器.exe"), delay_s=1.5)
        self.assertEqual(argv[0], "cmd.exe")
        self.assertEqual(argv[1], "/c")
        self.assertIn("ping 127.0.0.1", argv[2])
        self.assertIn(r'start "" "C:\App\变声器.exe"', argv[2])


if __name__ == "__main__":
    unittest.main()
