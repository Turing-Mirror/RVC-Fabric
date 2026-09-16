# -*- coding: utf-8 -*-
"""gui_v1._rms_db_frames —— librosa.feature.rms + amplitude_to_db 的等价替换。

E-02 把噪声门每块两次的 librosa 调用换成直接 numpy 实现（实测每块省约
60µs）。替换的前提是数值逐位一致，包括容易漏掉的两个细节：

1. ``center=True`` 的零填充（frame_length//2 两边）；
2. ``amplitude_to_db`` 的 ``top_db=80`` 相对最大值裁剪——不裁的话静音帧
   的 dB 会到 -100，阈值比较结果和原来不同。

任何一边改动都会让本文件红。需要 Runtime（librosa）。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import numpy as np
    import librosa

    from gui_v1 import _rms_db_frames

    _HAS_DEPS = True
except Exception:
    _HAS_DEPS = False


def _reference(y, frame_length, hop_length):
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)
    return librosa.amplitude_to_db(rms, ref=1.0)[0]


@unittest.skipUnless(_HAS_DEPS, "需要 Runtime（numpy/librosa）")
class TestRmsDbFrames(unittest.TestCase):
    def test_random_signal_matches_librosa(self):
        rng = np.random.RandomState(0)
        for length in (4800, 11025, 48000):
            y = rng.randn(length).astype(np.float32)
            zc = length // 16
            got = _rms_db_frames(y, 4 * zc, zc)
            want = _reference(y, 4 * zc, zc)
            self.assertEqual(got.shape, want.shape)
            np.testing.assert_allclose(got, want, atol=1e-5, rtol=0)

    def test_silence_hits_top_db_clip(self):
        # 前段纯静音：不实现 top_db 裁剪会得到 -100 以下，阈值判定失真。
        y = np.concatenate(
            [np.zeros(2048, dtype=np.float32), np.random.RandomState(1).randn(8192).astype(np.float32)]
        )
        got = _rms_db_frames(y, 1024, 256)
        want = _reference(y, 1024, 256)
        np.testing.assert_allclose(got, want, atol=1e-5, rtol=0)
        self.assertGreater(got.min(), -81.0)

    def test_short_input_matches_librosa(self):
        # 零填充保证即使输入短于 frame_length 也至少有一帧，与 librosa 一致。
        got = _rms_db_frames(np.zeros(32, dtype=np.float32), 1024, 256)
        want = _reference(np.zeros(32, dtype=np.float32), 1024, 256)
        self.assertEqual(got.shape, want.shape)
        np.testing.assert_allclose(got, want, atol=1e-5, rtol=0)

    def test_gate_blocks_match_reference(self):
        # 端到端：rms_buffer 前缀 + 丢前两帧 + 逐帧阈值零化，整条等价。
        rng = np.random.RandomState(2)
        zc = 256
        prev = rng.randn(4 * zc).astype(np.float32)
        block = rng.randn(8 * zc).astype(np.float32)
        merged = np.append(prev, block)
        th = -40.0

        ref_rms = librosa.feature.rms(y=merged, frame_length=4 * zc, hop_length=zc)[:, 2:]
        ref_db = librosa.amplitude_to_db(ref_rms, ref=1.0)[0] < th
        got_db = _rms_db_frames(merged, 4 * zc, zc)[2:] < th
        self.assertTrue((ref_db == got_db).all())


if __name__ == "__main__":
    unittest.main()
