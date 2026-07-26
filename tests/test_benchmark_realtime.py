# -*- coding: utf-8 -*-
"""tools/benchmark_realtime.py — geometry must mirror gui_v1.start_vc exactly.

Requires numpy (Runtime stack). Without it the module soft-skips under BOTH
runners — gate on the actual dependency, not on pytest being importable:
pytest.importorskip raises pytest's own Skipped, which unittest discover
reports as an error, so a host with pytest but no numpy would go red.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_HAS_NUMPY = importlib.util.find_spec("numpy") is not None


@unittest.skipUnless(_HAS_NUMPY, "numpy (Runtime stack) not installed")
class BenchmarkRealtimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import numpy

        cls.np = numpy
        from tools.benchmark_realtime import (
            block_geometry,
            build_parser,
            stage_stats,
            synth_input,
        )

        cls.block_geometry = staticmethod(block_geometry)
        cls.build_parser = staticmethod(build_parser)
        cls.stage_stats = staticmethod(stage_stats)
        cls.synth_input = staticmethod(synth_input)

    def test_geometry_40k_default_params(self):
        g = self.block_geometry(
            sr=40000, block_time=0.25, crossfade_time=0.05, extra_time=2.5
        )
        self.assertEqual(g["zc"], 400)
        self.assertEqual(g["block_frame"], 10000)
        self.assertEqual(g["block_frame_16k"], 4000)
        self.assertEqual(g["crossfade_frame"], 2000)
        self.assertEqual(g["sola_buffer_frame"], 1600)  # capped at 4*zc
        self.assertEqual(g["sola_search_frame"], 400)
        self.assertEqual(g["extra_frame"], 100000)
        self.assertEqual(g["input_frames"], 112400)
        self.assertEqual(g["input_res_len"], 44960)
        self.assertEqual(g["skip_head"], 250)
        self.assertEqual(g["return_length"], 30)

    def test_geometry_48k_16k_domain_invariant(self):
        g40 = self.block_geometry(
            sr=40000, block_time=0.25, crossfade_time=0.05, extra_time=2.5
        )
        g48 = self.block_geometry(
            sr=48000, block_time=0.25, crossfade_time=0.05, extra_time=2.5
        )
        self.assertEqual(g48["block_frame_16k"], g40["block_frame_16k"])
        self.assertEqual(g40["block_frame_16k"], 4000)
        self.assertEqual(g48["input_res_len"], g40["input_res_len"])
        self.assertEqual(g40["input_res_len"], 44960)
        self.assertEqual(g48["skip_head"], g40["skip_head"])
        self.assertEqual(g48["return_length"], g40["return_length"])

    def test_geometry_block_frames_are_zc_multiples(self):
        for sr in (32000, 40000, 48000):
            for bt in (0.1, 0.25, 0.5):
                g = self.block_geometry(
                    sr=sr, block_time=bt, crossfade_time=0.05, extra_time=2.5
                )
                self.assertEqual(g["block_frame"] % g["zc"], 0)
                self.assertEqual(g["extra_frame"] % g["zc"], 0)
                self.assertEqual(g["block_frame_16k"] % 160, 0)

    def test_parser_defaults_and_required_pth(self):
        p = self.build_parser()
        args = p.parse_args(["--pth", "x.pth"])
        self.assertEqual(args.f0method, "fcpe")
        self.assertEqual(args.block_time, 0.25)
        self.assertEqual(args.n_blocks, 200)
        self.assertEqual(args.warmup, 10)
        self.assertEqual(args.index, "")
        self.assertIs(args.sync_stages, False)
        self.assertEqual(args.json_out, "")
        with self.assertRaises(SystemExit):
            p.parse_args([])

    def test_stage_stats_aggregation(self):
        rows = [
            (0.010, 0.001, 0.020, 0.015),
            (0.012, 0.001, 0.022, 0.017),
            (0.011, 0.001, 0.021, 0.016),
        ]
        st = self.stage_stats(rows)
        self.assertEqual(set(st), {"fea", "index", "f0", "model"})
        self.assertEqual(st["fea"]["mean_ms"], 11.0)
        self.assertEqual(st["f0"]["mean_ms"], 21.0)
        self.assertGreaterEqual(st["model"]["p95_ms"], st["model"]["mean_ms"])
        self.assertEqual(self.stage_stats([]), {})

    def test_synth_input_is_sane(self):
        np = self.np
        sig = self.synth_input(16000)
        self.assertEqual(sig.shape, (16000,))
        self.assertEqual(sig.dtype, np.float32)
        self.assertLessEqual(np.max(np.abs(sig)), 1.0)
        self.assertGreater(np.max(np.abs(sig)), 0.1)  # actually voiced, not silence


if __name__ == "__main__":
    unittest.main()
