"""Phone PCM adapter for the existing realtime worker; no soundcard is opened."""
import socket
import struct
import threading
from multiprocessing import Value, Event
from multiprocessing.shared_memory import SharedMemory
import numpy as np

RATE = 48000

def exact(stream, count):
    data = bytearray(count)
    view = memoryview(data)
    offset = 0
    while offset < count:
        read = stream.recv_into(view[offset:])
        if not read:
            raise ConnectionError("mobile_disconnected")
        offset += read
    return data

class MobileAudioIo:
    def __init__(self, endpoint, block_size):
        self.block_size = int(block_size)
        self.buf_shape = (self.block_size * 2, 1)
        self.in_mem = self.out_mem = None
        self.in_ptr, self.out_ptr, self.play_ptr = (Value('i', 0) for _ in range(3))
        self.in_evt, self.stop_evt = Event(), Event()
        self.error = None
        self.socket = socket.create_connection(('127.0.0.1', int(endpoint['port'])), timeout=10)
        try:
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.socket.settimeout(5)
            self.socket.sendall((endpoint['token'] + '\n').encode('ascii'))
            self.in_mem = SharedMemory(create=True, size=self.block_size * 8)
            self.out_mem = SharedMemory(create=True, size=self.block_size * 8)
        except Exception:
            self.socket.close()
            self.close()
            raise
        self.thread = threading.Thread(target=self.run, name='fabric-mobile-input', daemon=True)
        self.write_lock = threading.Lock()

    def get_in_mem_name(self): return self.in_mem.name
    def get_out_mem_name(self): return self.out_mem.name
    def get_np_shape(self): return self.buf_shape
    def get_np_dtype(self): return np.float32
    def get_ptrs_and_events(self): return self.in_ptr, self.out_ptr, self.play_ptr, self.in_evt, self.stop_evt
    def get_latency(self): return -1.0
    def start(self): self.thread.start()
    def is_alive(self): return self.thread.is_alive()
    def join(self, timeout=None):
        self.thread.join(timeout)
        if not self.thread.is_alive():
            self.close()
    def close(self):
        for memory in (self.in_mem, self.out_mem):
            if memory is None: continue
            try: memory.close()
            except (BufferError, OSError): pass
            try: memory.unlink()
            except FileNotFoundError: pass
    def terminate(self):
        self.stop_evt.set()
        try: self.socket.shutdown(socket.SHUT_RDWR)
        except OSError: pass
        self.socket.close()
        self.in_evt.set()
    kill = terminate

    def run(self):
        view = np.ndarray(self.buf_shape, dtype=np.float32, buffer=self.in_mem.buf)
        view.fill(0)
        position = 0
        try:
            while not self.stop_evt.is_set():
                raw = exact(self.socket, self.block_size * 2)
                view[position:position+self.block_size, 0] = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768
                self.in_ptr.value = position
                self.in_evt.set()
                position = (position+self.block_size) % len(view)
        except (OSError, ConnectionError) as exc:
            if not self.stop_evt.is_set(): self.error = str(exc)
        finally:
            self.stop_evt.set()
            self.in_evt.set()
            self.socket.close()
            del view

    def publish(self, samples):
        if self.stop_evt.is_set(): return
        data = np.asarray(samples, dtype=np.float32)
        if data.ndim > 1: data = data.mean(axis=1)
        pcm = (np.clip(np.nan_to_num(data), -1, 1) * 32767).astype('<i2').tobytes()
        with self.write_lock:
            self.socket.sendall(struct.pack('!I', len(pcm)) + pcm)
