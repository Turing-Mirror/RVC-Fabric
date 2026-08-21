# -*- coding: utf-8 -*-
"""Fullscreen/Game Mode must not silently throttle realtime audio."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.win_realtime import (  # noqa: E402
    begin_timer_period,
    boost_current_process,
    boost_current_thread_audio,
    end_timer_period,
)


class WinRealtimeTests(unittest.TestCase):
    def test_boost_does_not_raise(self):
        boost_current_process()
        boost_current_process(high=True)
        boost_current_thread_audio()
        token = begin_timer_period()
        end_timer_period(token)

    def test_worker_calls_boost_before_torch(self):
        src = (ROOT / "tools" / "realtime_worker.py").read_text(encoding="utf-8")
        main = src[src.index("def main") :]
        self.assertIn("boost_current_process(high=True)", main)
        self.assertLess(
            main.index("boost_current_process"),
            main.index("runpy"),
        )

    def test_dsp_worker_calls_boost(self):
        src = (ROOT / "tools" / "dsp_worker.py").read_text(encoding="utf-8")
        self.assertIn("boost_current_process", src)

    def test_audio_io_boosts_process_and_callback(self):
        src = (ROOT / "tools" / "audio_io_process.py").read_text(encoding="utf-8")
        run = src[src.index("def run") :]
        self.assertIn("boost_current_process(high=True)", run)
        self.assertIn("boost_current_thread_audio()", run)
        self.assertIn("begin_timer_period", run)
        self.assertIn("end_timer_period", run)

    def test_shell_boosts_spawned_worker(self):
        rust = (ROOT / "app" / "src-tauri" / "src" / "worker.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn("win_realtime::boost_child", rust)
        lib = (ROOT / "app" / "src-tauri" / "src" / "lib.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn("win_realtime::boost_current", lib)
        self.assertTrue(
            (ROOT / "app" / "src-tauri" / "src" / "win_realtime.rs").is_file()
        )

    def test_gpu_scheduling_is_high(self):
        src = (ROOT / "tools" / "win_realtime.py").read_text(encoding="utf-8")
        self.assertIn("D3DKMTSetProcessSchedulingPriorityClass(handle, 4)", src)


if __name__ == "__main__":
    unittest.main()
