"""Bounded float32 microphone producer for the native voice-output mixer.

The mapping is created by the shell. This process only attaches and publishes
complete frames; it never opens an output audio device.
"""

import ctypes
import math
import os
import struct
from multiprocessing.shared_memory import SharedMemory

import numpy as np


MAGIC = b"FABPCM01"
VERSION = 1
HEADER_BYTES = 64
WRITE_FRAME_OFFSET = 32
READ_FRAME_OFFSET = 40


def _load_counter(buffer, offset):
    if os.name != "nt":
        return struct.unpack_from("<Q", buffer, offset)[0]
    ptr = ctypes.addressof(ctypes.c_char.from_buffer(buffer, offset))
    fn = ctypes.windll.kernel32.InterlockedCompareExchange64
    fn.argtypes = (ctypes.c_void_p, ctypes.c_longlong, ctypes.c_longlong)
    fn.restype = ctypes.c_longlong
    return fn(ptr, 0, 0)


def _store_counter(buffer, offset, value):
    if os.name != "nt":
        struct.pack_into("<Q", buffer, offset, value)
        return
    ptr = ctypes.addressof(ctypes.c_char.from_buffer(buffer, offset))
    fn = ctypes.windll.kernel32.InterlockedExchange64
    fn.argtypes = (ctypes.c_void_p, ctypes.c_longlong)
    fn.restype = ctypes.c_longlong
    fn(ptr, value)


class PcmBridgeWriter:
    def __init__(self, name, epoch):
        self.shm = SharedMemory(name=name, create=False)
        try:
            buffer = self.shm.buf
            if len(buffer) < HEADER_BYTES or bytes(buffer[:8]) != MAGIC:
                raise ValueError("invalid_pcm_bridge_magic")
            version, capacity, sample_rate = struct.unpack_from("<III", buffer, 8)
            channels = struct.unpack_from("<H", buffer, 20)[0]
            actual_epoch = struct.unpack_from("<Q", buffer, 24)[0]
            if version != VERSION or not capacity or not sample_rate or not channels:
                raise ValueError("invalid_pcm_bridge_header")
            if actual_epoch != epoch:
                raise ValueError("invalid_pcm_bridge_epoch")
            required = HEADER_BYTES + capacity * channels * 4
            if required > len(buffer):
                raise ValueError("pcm_bridge_buffer_too_small")
            self.capacity = capacity
            self.sample_rate = sample_rate
            self.channels = channels
            self.epoch = epoch
        except Exception:
            self.shm.close()
            raise

    def close(self):
        self.shm.close()

    def publish(self, samples, source_rate):
        """Return False on a full ring or stale epoch; never block inference."""
        if struct.unpack_from("<Q", self.shm.buf, 24)[0] != self.epoch:
            return False
        if source_rate <= 0:
            raise ValueError("invalid_pcm_source_rate")
        pcm = np.asarray(samples, dtype=np.float32)
        if pcm.ndim == 1:
            pcm = pcm.reshape(-1, 1)
        if pcm.ndim != 2 or pcm.shape[1] == 0:
            raise ValueError("invalid_pcm_source_channels")
        if pcm.shape[1] != self.channels:
            if self.channels == 1:
                pcm = pcm.mean(axis=1, keepdims=True)
            elif pcm.shape[1] == 1:
                pcm = np.repeat(pcm, self.channels, axis=1)
            else:
                raise ValueError("unsupported_pcm_channel_conversion")
        if source_rate != self.sample_rate:
            from scipy.signal import resample_poly

            divisor = math.gcd(source_rate, self.sample_rate)
            pcm = resample_poly(
                pcm, self.sample_rate // divisor, source_rate // divisor, axis=0
            )
        pcm = np.ascontiguousarray(pcm, dtype="<f4")
        frames = int(pcm.shape[0])
        if frames == 0:
            return True
        if frames > self.capacity:
            raise ValueError("pcm_bridge_block_too_large")
        read = _load_counter(self.shm.buf, READ_FRAME_OFFSET)
        write = _load_counter(self.shm.buf, WRITE_FRAME_OFFSET)
        if write < read or write - read > self.capacity:
            raise ValueError("invalid_pcm_bridge_cursor")
        if frames > self.capacity - (write - read):
            return False
        start = write % self.capacity
        first = min(frames, self.capacity - start)
        frame_bytes = self.channels * 4
        raw = pcm.tobytes()
        data = self.shm.buf
        first_offset = HEADER_BYTES + start * frame_bytes
        data[first_offset:first_offset + first * frame_bytes] = raw[:first * frame_bytes]
        if first < frames:
            tail = (frames - first) * frame_bytes
            data[HEADER_BYTES:HEADER_BYTES + tail] = raw[first * frame_bytes:]
        _store_counter(data, WRITE_FRAME_OFFSET, write + frames)
        return True
