"""PCM bridge layout and bounded producer behavior without real audio hardware."""

import importlib.util
import os
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@unittest.skipUnless(importlib.util.find_spec("numpy"), "numpy is not installed")
class PcmBridgeTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        from tools import audio_pcm_bridge

        self.np = np
        self.bridge = audio_pcm_bridge
        self.buffer = bytearray(64 + 4 * 2 * 4)
        self.buffer[:8] = b"FABPCM01"
        struct.pack_into("<III", self.buffer, 8, 1, 4, 48000)
        struct.pack_into("<H", self.buffer, 20, 2)
        struct.pack_into("<Q", self.buffer, 24, 19)

        outer = self

        class FakeMemory:
            def __init__(self, name, create=False):
                self.buf = outer.buffer

            def close(self):
                pass

        self.mapping = patch.object(audio_pcm_bridge, "SharedMemory", FakeMemory)
        self.mapping.start()

    def tearDown(self):
        self.mapping.stop()

    def test_writes_interleaved_float32_and_wraps(self):
        writer = self.bridge.PcmBridgeWriter("test", 19)
        first = self.np.array([[0.1, 0.2], [0.3, 0.4]], dtype=self.np.float32)
        self.assertTrue(writer.publish(first, 48000))
        self.assertEqual(struct.unpack_from("<Q", self.buffer, 32)[0], 2)
        self.np.testing.assert_allclose(
            self.np.frombuffer(self.buffer, dtype="<f4", count=4, offset=64).reshape(2, 2),
            first,
        )
        struct.pack_into("<Q", self.buffer, 40, 2)
        second = self.np.array([[0.5, 0.6], [0.7, 0.8], [0.9, 1.0]], dtype=self.np.float32)
        self.assertTrue(writer.publish(second, 48000))
        self.assertEqual(struct.unpack_from("<Q", self.buffer, 32)[0], 5)
        self.np.testing.assert_allclose(
            self.np.frombuffer(self.buffer, dtype="<f4", count=2, offset=64),
            second[2],
        )
        writer.close()

    def test_full_ring_drops_new_audio_and_does_not_advance_cursor(self):
        writer = self.bridge.PcmBridgeWriter("test", 19)
        self.assertTrue(writer.publish(self.np.zeros((4, 2), dtype=self.np.float32), 48000))
        self.assertFalse(writer.publish(self.np.ones((1, 2), dtype=self.np.float32), 48000))
        self.assertEqual(struct.unpack_from("<Q", self.buffer, 32)[0], 4)

    def test_stale_epoch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "epoch"):
            self.bridge.PcmBridgeWriter("test", 20)
        writer = self.bridge.PcmBridgeWriter("test", 19)
        struct.pack_into("<Q", self.buffer, 24, 21)
        self.assertFalse(writer.publish(self.np.ones((1, 2), dtype=self.np.float32), 48000))


if __name__ == "__main__":
    unittest.main()
