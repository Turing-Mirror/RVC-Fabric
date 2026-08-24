# -*- coding: utf-8 -*-
"""Live delay metric — numbers from diag_20260824_194728.

That pack: MME, block_time=0.25, sr=44100, device_lat=0.091s,
delay_ms formula=431, real_delay_ms leftover=794, infer ~0–76ms,
logged q=11285–20922 (wrap garbage from out_ptr-play).
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.delay_metric import ema, frames_until_block_start, live_delay_sec


class DelayMetricTests(unittest.TestCase):
    # 26.8.24 pack
    SR = 44100
    BLOCK = 0.25
    BF = 11025  # 0.25 * 44100
    BUF = 22050  # double buffer
    DEV = 0.091

    def test_play_inside_written_block_is_zero_wait(self):
        # out_ptr=0, play=5000: already hearing this block
        self.assertEqual(frames_until_block_start(0, 5000, self.BF, self.BUF), 0)
        # just written at playhead (underrun path)
        self.assertEqual(frames_until_block_start(0, 0, self.BF, self.BUF), 0)

    def test_play_in_previous_half_counts_leftover_only(self):
        # last write started at 11025; play still in [0, 11025)
        self.assertEqual(
            frames_until_block_start(self.BF, 0, self.BF, self.BUF), self.BF
        )
        self.assertEqual(
            frames_until_block_start(self.BF, 5512, self.BF, self.BUF),
            self.BF - 5512,
        )

    def test_diag_wrap_values_are_not_a_full_extra_block(self):
        # Logged q was (out_ptr - play) % buf. 11285/20922 look like
        # "play is inside the written block" (into < block), wait=0.
        for delta in (11285, 12120, 14282, 18343, 20922):
            # Reconstruct: delta = (out - play) % buf. Pick out=0, play = buf-delta
            play = (self.BUF - delta) % self.BUF
            wait = frames_until_block_start(0, play, self.BF, self.BUF)
            self.assertEqual(wait, 0, msg="delta=%s play=%s wait=%s" % (delta, play, wait))

    def test_healthy_live_delay_near_old_formula_not_794(self):
        # Voice, keeping up: wait=0 (already playing last write) + infer ~70ms
        live = live_delay_sec(device=self.DEV, block=self.BLOCK, queued=0.0, infer=0.070)
        ms = live * 1000
        self.assertGreater(ms, 350)
        self.assertLess(ms, 480)  # old formula 431; must not be ~794
        # One leftover output block still playing
        live2 = live_delay_sec(
            device=self.DEV, block=self.BLOCK, queued=self.BLOCK / 2, infer=0.070
        )
        self.assertGreater(live2 * 1000, ms)
        self.assertLess(live2 * 1000, 650)

    def test_infer_spike_raises_reading(self):
        steady = live_delay_sec(device=self.DEV, block=self.BLOCK, queued=0.0, infer=0.070)
        spike = live_delay_sec(device=self.DEV, block=self.BLOCK, queued=0.0, infer=0.380)
        self.assertGreater(spike - steady, 0.25)

    def test_ema_ignores_nothing_on_first_sample(self):
        self.assertAlmostEqual(ema(0.0, 0.070), 0.070)
        nxt = ema(0.070, 0.380)
        self.assertGreater(nxt, 0.070)
        self.assertLess(nxt, 0.380)


if __name__ == "__main__":
    unittest.main()
