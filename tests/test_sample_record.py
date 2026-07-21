# -*- coding: utf-8 -*-
"""launcher.sample_record — device pick + wav write (no live mic required)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher.sample_record import resolve_device_name, write_wav_int16


class SampleRecordTests(unittest.TestCase):
    def test_resolve_dry_uses_cfg_input(self):
        name = resolve_device_name(
            "dry", {"sg_input_device": "My Mic", "input_device": "Legacy"}
        )
        self.assertEqual(name, "My Mic")

    def test_resolve_wet_explicit_override(self):
        name = resolve_device_name(
            "wet",
            {
                "sg_input_device": "My Mic",
                "consult_wet_device": "CABLE Output (VB-Audio Virtual Cable)",
            },
        )
        self.assertIn("CABLE", name)

    def test_write_wav_int16(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "t.wav")
            write_wav_int16(path, [0.0, 0.5, -0.5, 0.0] * 100, 16000)
            self.assertTrue(os.path.isfile(path))
            with wave.open(path, "rb") as wf:
                self.assertEqual(wf.getnchannels(), 1)
                self.assertEqual(wf.getsampwidth(), 2)
                self.assertEqual(wf.getframerate(), 16000)
                self.assertGreater(wf.getnframes(), 0)


if __name__ == "__main__":
    unittest.main()
