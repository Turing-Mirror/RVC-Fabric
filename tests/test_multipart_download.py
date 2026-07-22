# -*- coding: utf-8 -*-
"""Tests for multi-connection download + resume helpers."""

from __future__ import annotations

import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from launcher.online.multipart import (
    auto_connections,
    download_multipart,
    download_single_resumable,
    plan_segments,
    probe_ranges,
)


def test_auto_connections_tiers():
    assert auto_connections(1024) == 1
    assert auto_connections(20 * 1024 * 1024) == 8
    assert auto_connections(100 * 1024 * 1024) == 16
    assert auto_connections(8 * 1024 ** 3) == 16


def test_plan_segments_cover():
    segs = plan_segments(1000, 4)
    assert segs
    assert segs[0][0] == 0
    assert segs[-1][1] == 999
    covered = sum(e - s + 1 for s, e in segs)
    assert covered == 1000


class _RangeHandler(BaseHTTPRequestHandler):
    DATA = b""

    def log_message(self, fmt, *args):  # quiet
        return

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(self.DATA)))
        self.end_headers()

    def do_GET(self):
        data = self.DATA
        rng = self.headers.get("Range") or self.headers.get("range")
        if rng and rng.startswith("bytes="):
            spec = rng.split("=", 1)[1].strip()
            if "-" in spec:
                a, b = spec.split("-", 1)
                start = int(a) if a else 0
                end = int(b) if b else (len(data) - 1)
                end = min(end, len(data) - 1)
                start = max(0, start)
                chunk = data[start : end + 1]
                self.send_response(206)
                self.send_header(
                    "Content-Range", f"bytes {start}-{end}/{len(data)}"
                )
                self.send_header("Content-Length", str(len(chunk)))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                self.wfile.write(chunk)
                return
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture()
def range_server(tmp_path):
    # 20 MiB so multipart triggers (MIN is 16 MiB)
    payload = (b"RVC-FABRIC-TEST-" * 4096)  # 64 KiB pattern
    data = (payload * ((20 * 1024 * 1024 // len(payload)) + 1))[: 20 * 1024 * 1024]
    sha = hashlib.sha256(data).hexdigest()

    class H(_RangeHandler):
        DATA = data

    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    url = f"http://127.0.0.1:{port}/file.bin"
    yield url, data, sha, tmp_path
    server.shutdown()


def test_probe_ranges(range_server):
    url, data, sha, _ = range_server
    accept, total = probe_ranges(url, timeout=5, session=None)
    assert accept is True
    assert total == len(data)


def test_multipart_download(range_server):
    url, data, sha, tmp = range_server
    dest = tmp / "out.bin"
    progress_hits = []

    def prog(done, total):
        progress_hits.append((done, total))

    out = download_multipart(
        url,
        dest,
        progress=prog,
        timeout=30,
        expected_sha256=sha,
        connections=4,
        resume=False,
        session=None,
    )
    assert out.is_file()
    assert out.read_bytes() == data
    assert progress_hits
    assert progress_hits[-1][0] >= len(data) * 0.9


def test_single_resume(range_server):
    url, data, sha, tmp = range_server
    dest = tmp / "resume.bin"
    part = dest.with_suffix(dest.suffix + ".part")
    # pre-write first 1MB
    part.write_bytes(data[: 1 * 1024 * 1024])
    out = download_single_resumable(
        url,
        dest,
        timeout=30,
        expected_sha256=sha,
        resume=True,
        session=None,
    )
    assert out.read_bytes() == data
