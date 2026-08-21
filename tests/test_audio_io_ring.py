# -*- coding: utf-8 -*-
"""Underrun must play silence, not loop the last syllable (diag 26.8.21/1)."""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parents[1]
_HAS_NUMPY = importlib.util.find_spec("numpy") is not None


@unittest.skipUnless(_HAS_NUMPY, "numpy (Runtime stack) not installed")
class AudioIoRingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import types
        import numpy

        cls.np = numpy
        if importlib.util.find_spec("sounddevice") is None:
            sys.modules["sounddevice"] = types.ModuleType("sounddevice")
        from tools.audio_io_process import copy_and_consume_ring

        cls.copy_and_consume_ring = staticmethod(copy_and_consume_ring)

    def test_consume_zeros_played_region(self):
        np = self.np
        ring = np.arange(8, dtype=np.float32).reshape(8, 1)
        out = np.zeros((3, 1), dtype=np.float32)
        nxt = self.copy_and_consume_ring(ring, 0, 3, out)
        self.assertEqual(nxt, 3)
        self.assertTrue(np.allclose(out.reshape(-1), [0, 1, 2]))
        self.assertTrue(np.allclose(ring[:3], 0))
        self.assertTrue(np.allclose(ring[3:].reshape(-1), [3, 4, 5, 6, 7]))

    def test_wrap_around_zeros_both_sides(self):
        np = self.np
        ring = np.arange(8, dtype=np.float32).reshape(8, 1)
        out = np.zeros((4, 1), dtype=np.float32)
        nxt = self.copy_and_consume_ring(ring, 6, 4, out)
        self.assertEqual(nxt, 2)
        self.assertTrue(np.allclose(out.reshape(-1), [6, 7, 0, 1]))
        self.assertTrue(np.allclose(ring[6:], 0))
        self.assertTrue(np.allclose(ring[:2], 0))
        self.assertTrue(np.allclose(ring[2:6].reshape(-1), [2, 3, 4, 5]))

    def test_second_pass_is_silence(self):
        np = self.np
        ring = np.ones((8, 1), dtype=np.float32)
        out = np.zeros((8, 1), dtype=np.float32)
        self.copy_and_consume_ring(ring, 0, 8, out)
        self.assertTrue(np.allclose(out, 1))
        out2 = np.ones((8, 1), dtype=np.float32)
        self.copy_and_consume_ring(ring, 0, 8, out2)
        self.assertTrue(np.allclose(out2, 0))


class GuiV1HotPathTests(unittest.TestCase):
    def test_quiet_block_skips_gpu_before_torchgate(self):
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        infer = src[src.index("def audio_infer") : src.index("def update_devices")]
        peak_at = infer.index("peak = float(np.max")
        tg_at = infer.index("self.tg(")
        silent_at = infer.index("_emit_silence")
        spent_skip = infer.index("_pitch_skip_blocks")
        self.assertLess(peak_at, tg_at)
        self.assertLess(silent_at, tg_at)
        self.assertLess(spent_skip, tg_at)
        self.assertIn("feat16 = feat16.to(self.config.device)", infer)
        self.assertIn("infer_wav = infer_wav.to(io_dev)", infer)
        start = src[src.index("def start_vc") : src.index("def _on_rvc_progress")]
        self.assertIn("_io_device", start)
        io_src = (ROOT / "tools" / "audio_io_process.py").read_text(encoding="utf-8")
        self.assertIn("copy_and_consume_ring(", io_src[io_src.index("def output_callback") :])


if __name__ == "__main__":
    unittest.main()
