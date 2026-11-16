"""Exercise framed PCM and shutdown with a real loopback connection."""
import socket
import struct
import threading
import unittest
from unittest.mock import patch
from multiprocessing.shared_memory import SharedMemory

import numpy as np
from tools.mobile_audio import MobileAudioIo, exact


class MobileAudioTest(unittest.TestCase):
    def test_partial_initialization_releases_shared_memory(self):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        memory = SharedMemory(create=True, size=7680)
        name = memory.name
        try:
            with patch('tools.mobile_audio.SharedMemory', side_effect=[memory, OSError('allocation failed')]):
                with self.assertRaises(OSError):
                    MobileAudioIo({'port': listener.getsockname()[1], 'token': 'x'}, 960)
            with self.assertRaises(FileNotFoundError):
                SharedMemory(name=name)
            peer, _ = listener.accept()
            peer.settimeout(2)
            self.assertEqual(exact(peer, 2), b'x\n')
            self.assertEqual(peer.recv(1), b'')
            peer.close()
        finally:
            memory.close()
            try: memory.unlink()
            except FileNotFoundError: pass
            listener.close()

    def test_fragmented_input_output_and_disconnect(self):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        adapter = MobileAudioIo({'port': listener.getsockname()[1], 'token': 'test'}, 960)
        peer, _ = listener.accept()
        peer.settimeout(2)
        self.assertEqual(exact(peer, 5), b'test\n')
        adapter.start()
        try:
            samples = np.arange(960, dtype='<i2')
            raw = samples.tobytes()
            for chunk in (raw[:17], raw[17:827], raw[827:]):
                peer.sendall(chunk)
            self.assertTrue(adapter.in_evt.wait(2))
            view = np.ndarray(adapter.buf_shape, dtype=np.float32, buffer=adapter.in_mem.buf)
            np.testing.assert_allclose(view[:960, 0], samples / 32768)
            del view
            adapter.publish(np.array([-.5, 0, .5, np.nan], dtype=np.float32))
            length = struct.unpack('!I', exact(peer, 4))[0]
            self.assertEqual(length, 8)
            np.testing.assert_array_equal(np.frombuffer(exact(peer, length), dtype='<i2'), [-16383, 0, 16383, 0])
            peer.close()
            adapter.join(2)
            self.assertFalse(adapter.is_alive())
            self.assertIsNotNone(adapter.error)
        finally:
            adapter.terminate()
            adapter.join(2)
            peer.close()
            listener.close()

    def test_stop_unblocks_incomplete_input(self):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        adapter = MobileAudioIo({'port': listener.getsockname()[1], 'token': 'x'}, 960)
        peer, _ = listener.accept()
        adapter.start()
        peer.sendall(b'\0')
        adapter.terminate()
        adapter.join(2)
        self.assertFalse(adapter.is_alive())
        self.assertIsNone(adapter.error)
        peer.close()
        listener.close()


if __name__ == '__main__':
    unittest.main()
