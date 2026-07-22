# -*- coding: utf-8 -*-
"""Multi-connection HTTP Range download (aria2 / Motrix style).

- Probe Accept-Ranges + Content-Length
- Split into N segments, ThreadPoolExecutor + Range GET
- Single preallocated .part file with seek writes
- Resume via sidecar .part.meta.json
- Progress throttled (~100ms)

Falls back to single-connection when the server rejects Range.
"""

from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional  # noqa: F401 — Callable used in signatures
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ProgressCb = Callable[[int, int], None]

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36 RVCFabric/1.0"
)

MIN_MULTIPART_BYTES = 16 * 1024 * 1024  # 16 MiB
MAX_CONNECTIONS = 32
CHUNK = 1 << 16  # 64 KiB
PROGRESS_INTERVAL = 0.1
SEGMENT_RETRIES = 3
META_SUFFIX = ".meta.json"


class MultipartError(RuntimeError):
    pass


def auto_connections(size: int) -> int:
    """Choose connection count from file size (capped)."""
    if size <= 0:
        return 1
    if size < MIN_MULTIPART_BYTES:
        return 1
    if size < 64 * 1024 * 1024:
        return 8
    n = 16
    return min(MAX_CONNECTIONS, max(1, n))


def plan_segments(total: int, n_conn: int) -> list[tuple[int, int]]:
    """Inclusive (start, end) byte ranges covering [0, total)."""
    if total <= 0:
        return []
    n = max(1, min(int(n_conn), total))
    # Avoid tiny last shards: at least ~1MB per segment when large
    if total >= MIN_MULTIPART_BYTES:
        max_n = max(1, total // (1 * 1024 * 1024))
        n = min(n, max_n)
    n = max(1, n)
    base = total // n
    rem = total % n
    segs: list[tuple[int, int]] = []
    pos = 0
    for i in range(n):
        length = base + (1 if i < rem else 0)
        if length <= 0:
            continue
        start = pos
        end = pos + length - 1
        segs.append((start, end))
        pos = end + 1
    return segs


def meta_path(part: Path) -> Path:
    return Path(str(part) + META_SUFFIX)


def load_meta(part: Path) -> Optional[dict]:
    p = meta_path(part)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def save_meta(part: Path, data: dict) -> None:
    p = meta_path(part)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def clear_meta(part: Path) -> None:
    p = meta_path(part)
    try:
        if p.is_file():
            p.unlink()
    except OSError:
        pass


def _headers_base() -> dict[str, str]:
    return {"User-Agent": DEFAULT_UA, "Accept": "*/*"}


def probe_ranges(
    url: str,
    *,
    timeout: int = 60,
    session=None,
) -> tuple[bool, int]:
    """Return (accept_ranges, total_size). total may be 0 if unknown."""
    # Prefer HEAD
    total = 0
    accept = False
    try:
        if session is not None:
            r = session.head(url, allow_redirects=True, timeout=timeout)
            if r.status_code < 400:
                ar = (r.headers.get("Accept-Ranges") or "").lower()
                accept = "bytes" in ar
                total = int(r.headers.get("Content-Length") or 0)
                if total > 0:
                    # Confirm with a tiny range if Accept-Ranges missing but size known
                    if not accept:
                        accept = _probe_partial(url, timeout=timeout, session=session)
                    return accept, total
        else:
            req = Request(url, headers=_headers_base(), method="HEAD")
            with urlopen(req, timeout=timeout) as resp:
                ar = (resp.headers.get("Accept-Ranges") or "").lower()
                accept = "bytes" in ar
                total = int(resp.headers.get("Content-Length") or 0)
                if total > 0:
                    if not accept:
                        accept = _probe_partial(url, timeout=timeout, session=None)
                    return accept, total
    except Exception:
        pass

    # Fallback: GET Range 0-0
    return _probe_partial_with_size(url, timeout=timeout, session=session)


def _probe_partial(url: str, *, timeout: int, session) -> bool:
    try:
        if session is not None:
            r = session.get(
                url,
                headers={"Range": "bytes=0-0"},
                stream=True,
                allow_redirects=True,
                timeout=timeout,
            )
            ok = r.status_code == 206
            r.close()
            return ok
        req = Request(
            url,
            headers={**_headers_base(), "Range": "bytes=0-0"},
            method="GET",
        )
        with urlopen(req, timeout=timeout) as resp:
            return getattr(resp, "status", 200) == 206 or resp.getcode() == 206
    except Exception:
        return False


def _probe_partial_with_size(
    url: str, *, timeout: int, session
) -> tuple[bool, int]:
    try:
        if session is not None:
            r = session.get(
                url,
                headers={"Range": "bytes=0-0"},
                stream=True,
                allow_redirects=True,
                timeout=timeout,
            )
            code = r.status_code
            cr = r.headers.get("Content-Range") or ""
            total = 0
            if "/" in cr:
                try:
                    total = int(cr.rsplit("/", 1)[-1])
                except ValueError:
                    total = int(r.headers.get("Content-Length") or 0)
            else:
                total = int(r.headers.get("Content-Length") or 0)
            r.close()
            return code == 206, total
        req = Request(
            url,
            headers={**_headers_base(), "Range": "bytes=0-0"},
            method="GET",
        )
        with urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            cr = resp.headers.get("Content-Range") or ""
            total = 0
            if "/" in cr:
                try:
                    total = int(cr.rsplit("/", 1)[-1])
                except ValueError:
                    total = int(resp.headers.get("Content-Length") or 0)
            else:
                total = int(resp.headers.get("Content-Length") or 0)
            return code == 206, total
    except Exception:
        return False, 0


def _preallocate(path: Path, total: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Sparse-ish: seek to end-1 and write one byte (Windows ok for our sizes)
    with open(path, "wb") as f:
        if total > 0:
            f.seek(total - 1)
            f.write(b"\0")
        else:
            f.truncate(0)


class _ProgressAgg:
    """Absolute progress from per-segment done[] — safe across segment retries."""

    def __init__(self, total: int, seg_done: list[int], cb: Optional[ProgressCb]):
        self.total = total
        self.seg_done = seg_done
        self.cb = cb
        self._lock = threading.Lock()
        self._last_t = 0.0

    def notify(self) -> None:
        with self._lock:
            now = time.monotonic()
            if self.cb and (now - self._last_t >= PROGRESS_INTERVAL):
                self._last_t = now
                d = sum(self.seg_done)
                try:
                    self.cb(d, self.total)
                except Exception:
                    pass

    def flush(self) -> None:
        with self._lock:
            if self.cb:
                try:
                    self.cb(sum(self.seg_done), self.total)
                except Exception:
                    pass


def _download_range_requests(
    session,
    url: str,
    start: int,
    end: int,
    part: Path,
    *,
    already: int,
    timeout: int,
    on_bytes: Callable[[int], None],
    stop: threading.Event,
) -> int:
    """Write bytes [start+already, end] into part. Returns total done in segment (from start)."""
    abs_start = start + already
    if abs_start > end:
        return already
    headers = {"Range": f"bytes={abs_start}-{end}"}
    written = 0
    with session.get(
        url,
        headers=headers,
        stream=True,
        allow_redirects=True,
        timeout=timeout,
    ) as r:
        if r.status_code not in (200, 206):
            raise MultipartError(f"HTTP {r.status_code} for Range {abs_start}-{end}")
        if r.status_code == 200 and abs_start > 0:
            raise MultipartError("服务器忽略 Range，回落单连接")
        with open(part, "r+b") as f:
            f.seek(abs_start)
            for chunk in r.iter_content(chunk_size=CHUNK):
                if stop.is_set():
                    raise MultipartError("下载已取消")
                if not chunk:
                    continue
                f.write(chunk)
                written += len(chunk)
                on_bytes(already + written)
    need = end - abs_start + 1
    if written < need * 0.98:
        raise MultipartError(
            f"分段不完整：{abs_start}-{end} 得到 {written}/{need}"
        )
    return already + written


def _download_range_urllib(
    url: str,
    start: int,
    end: int,
    part: Path,
    *,
    already: int,
    timeout: int,
    on_bytes: Callable[[int], None],
    stop: threading.Event,
) -> int:
    abs_start = start + already
    if abs_start > end:
        return already
    req = Request(
        url,
        headers={**_headers_base(), "Range": f"bytes={abs_start}-{end}"},
        method="GET",
    )
    written = 0
    try:
        resp = urlopen(req, timeout=timeout)
    except HTTPError as e:
        raise MultipartError(f"HTTP {e.code}: {e.reason}") from e
    except URLError as e:
        raise MultipartError(f"网络错误：{e.reason}") from e
    try:
        code = resp.getcode()
        if code not in (200, 206):
            raise MultipartError(f"HTTP {code} for Range {abs_start}-{end}")
        if code == 200 and abs_start > 0:
            raise MultipartError("服务器忽略 Range，回落单连接")
        with open(part, "r+b") as f:
            f.seek(abs_start)
            while True:
                if stop.is_set():
                    raise MultipartError("下载已取消")
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                f.write(chunk)
                written += len(chunk)
                on_bytes(already + written)
    finally:
        try:
            resp.close()
        except Exception:
            pass
    need = end - abs_start + 1
    if written < need * 0.98:
        raise MultipartError(
            f"分段不完整：{abs_start}-{end} 得到 {written}/{need}"
        )
    return already + written


def download_multipart(
    url: str,
    dest: Path,
    *,
    progress: Optional[ProgressCb] = None,
    timeout: int = 600,
    expected_sha256: str = "",
    connections: Optional[int] = None,
    resume: bool = True,
    session=None,
    total_hint: int = 0,
) -> Path:
    """Multi-connection download to dest. Raises MultipartError on hard failure."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")

    accept, total = probe_ranges(url, timeout=min(timeout, 120), session=session)
    if total_hint > 0 and total <= 0:
        total = total_hint
    if total <= 0:
        raise MultipartError("无法取得 Content-Length，无法分片")
    if not accept:
        raise MultipartError("服务器不支持 Range")

    n = connections if connections is not None else auto_connections(total)
    n = max(1, min(int(n), MAX_CONNECTIONS))
    if n <= 1 or total < MIN_MULTIPART_BYTES:
        raise MultipartError("文件过小或连接数=1，使用单连接")

    segs = plan_segments(total, n)
    # Resume meta
    seg_done = [0] * len(segs)
    meta = load_meta(part) if resume else None
    if (
        resume
        and meta
        and int(meta.get("total") or 0) == total
        and str(meta.get("url") or "") == url
        and (
            not expected_sha256
            or str(meta.get("sha256") or "").lower()
            == expected_sha256.strip().lower()
        )
        and part.is_file()
        and part.stat().st_size == total
    ):
        raw_segs = meta.get("segments") or []
        if isinstance(raw_segs, list) and len(raw_segs) == len(segs):
            for i, s in enumerate(raw_segs):
                try:
                    want_s, want_e = segs[i]
                    if int(s.get("start")) == want_s and int(s.get("end")) == want_e:
                        d = int(s.get("done") or 0)
                        seg_done[i] = max(0, min(d, want_e - want_s + 1))
                except Exception:
                    seg_done[i] = 0
    else:
        # Fresh or incompatible meta
        clear_meta(part)
        if part.is_file():
            try:
                part.unlink()
            except OSError:
                pass
        _preallocate(part, total)
        seg_done = [0] * len(segs)

    agg = _ProgressAgg(total, seg_done, progress)
    agg.flush()

    stop = threading.Event()
    meta_lock = threading.Lock()
    done_lock = threading.Lock()

    def _persist() -> None:
        data = {
            "url": url,
            "sha256": (expected_sha256 or "").strip().lower(),
            "total": total,
            "connections": n,
            "segments": [
                {"start": segs[i][0], "end": segs[i][1], "done": seg_done[i]}
                for i in range(len(segs))
            ],
        }
        try:
            save_meta(part, data)
        except Exception:
            pass

    _persist()

    def _one(i: int) -> None:
        start, end = segs[i]
        need = end - start + 1
        last_err: Exception | None = None

        def on_bytes(done_in_seg: int) -> None:
            with done_lock:
                seg_done[i] = max(seg_done[i], min(done_in_seg, need))
            agg.notify()

        for attempt in range(1, SEGMENT_RETRIES + 1):
            if stop.is_set():
                raise MultipartError("下载已取消")
            with done_lock:
                already = seg_done[i]
            if already >= need:
                return
            try:
                if session is not None:
                    got = _download_range_requests(
                        session,
                        url,
                        start,
                        end,
                        part,
                        already=already,
                        timeout=timeout,
                        on_bytes=on_bytes,
                        stop=stop,
                    )
                else:
                    got = _download_range_urllib(
                        url,
                        start,
                        end,
                        part,
                        already=already,
                        timeout=timeout,
                        on_bytes=on_bytes,
                        stop=stop,
                    )
                with done_lock:
                    seg_done[i] = max(seg_done[i], got)
                with meta_lock:
                    _persist()
                if seg_done[i] >= need:
                    return
            except Exception as e:
                last_err = e
                with meta_lock:
                    _persist()
                time.sleep(0.6 * attempt)
        stop.set()
        raise MultipartError(str(last_err) if last_err else f"分段 {i} 失败")

    try:
        with ThreadPoolExecutor(max_workers=n) as ex:
            futs = [ex.submit(_one, i) for i in range(len(segs))]
            for fut in as_completed(futs):
                fut.result()
    except Exception:
        stop.set()
        with meta_lock:
            _persist()
        raise

    agg.flush()

    if expected_sha256:
        _verify_sha256_local(part, expected_sha256)

    if dest.is_file():
        try:
            dest.unlink()
        except OSError:
            pass
    part.replace(dest)
    clear_meta(part)
    if progress:
        try:
            progress(total, total)
        except Exception:
            pass
    return dest


def _verify_sha256_local(path: Path, expect: str) -> None:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    got = h.hexdigest().lower()
    exp = expect.strip().lower()
    if got != exp:
        raise MultipartError(f"SHA256 不匹配：期望 {exp[:12]}… 实际 {got[:12]}…")


def download_single_resumable(
    url: str,
    dest: Path,
    *,
    progress: Optional[ProgressCb] = None,
    timeout: int = 600,
    expected_sha256: str = "",
    session=None,
    resume: bool = True,
) -> Path:
    """Single-connection download with optional Range resume into .part."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")

    accept, total = probe_ranges(url, timeout=min(timeout, 120), session=session)
    already = 0
    if resume and part.is_file():
        try:
            already = part.stat().st_size
        except OSError:
            already = 0
        if total and already > total:
            already = 0
            try:
                part.unlink()
            except OSError:
                pass
        if total and already == total and expected_sha256:
            try:
                _verify_sha256_local(part, expected_sha256)
                if dest.is_file():
                    dest.unlink()
                part.replace(dest)
                if progress:
                    progress(total, total)
                return dest
            except Exception:
                already = 0
                try:
                    part.unlink()
                except OSError:
                    pass

    mode = "ab" if already > 0 and accept else "wb"
    if mode == "wb" and part.is_file():
        try:
            part.unlink()
        except OSError:
            pass
        already = 0

    headers = _headers_base()
    if already > 0 and accept:
        headers["Range"] = f"bytes={already}-"

    done = [already]
    last_t = [0.0]

    def _prog(n_add: int = 0) -> None:
        if n_add:
            done[0] += n_add
        if not progress:
            return
        now = time.monotonic()
        if now - last_t[0] < PROGRESS_INTERVAL and n_add:
            return
        last_t[0] = now
        try:
            progress(done[0], total or 0)
        except Exception:
            pass

    _prog(0)

    if session is not None:
        with session.get(
            url, headers=headers, stream=True, allow_redirects=True, timeout=timeout
        ) as r:
            if already > 0 and r.status_code == 200:
                already = 0
                done[0] = 0
                mode = "wb"
            elif r.status_code not in (200, 206):
                raise MultipartError(f"HTTP {r.status_code}")
            if not total:
                total = int(r.headers.get("Content-Length") or 0)
                if r.status_code == 206:
                    cr = r.headers.get("Content-Range") or ""
                    if "/" in cr:
                        try:
                            total = int(cr.rsplit("/", 1)[-1])
                        except ValueError:
                            pass
            with open(part, mode) as f:
                for chunk in r.iter_content(chunk_size=CHUNK):
                    if not chunk:
                        continue
                    f.write(chunk)
                    _prog(len(chunk))
    else:
        req = Request(url, headers=headers, method="GET")
        try:
            resp = urlopen(req, timeout=timeout)
        except HTTPError as e:
            raise MultipartError(f"HTTP {e.code}: {e.reason}") from e
        except URLError as e:
            raise MultipartError(f"网络错误：{e.reason}") from e
        try:
            code = resp.getcode()
            if already > 0 and code == 200:
                already = 0
                done[0] = 0
                mode = "wb"
            if not total:
                total = int(resp.headers.get("Content-Length") or 0)
                cr = resp.headers.get("Content-Range") or ""
                if "/" in cr:
                    try:
                        total = int(cr.rsplit("/", 1)[-1])
                    except ValueError:
                        pass
            with open(part, mode) as f:
                while True:
                    chunk = resp.read(CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    _prog(len(chunk))
        finally:
            try:
                resp.close()
            except Exception:
                pass

    if progress:
        try:
            progress(done[0], total or done[0])
        except Exception:
            pass
    final_size = part.stat().st_size
    if total and final_size < total * 0.98:
        raise MultipartError(f"下载不完整：{final_size}/{total}")

    if expected_sha256:
        _verify_sha256_local(part, expected_sha256)

    if dest.is_file():
        try:
            dest.unlink()
        except OSError:
            pass
    part.replace(dest)
    clear_meta(part)
    if progress:
        try:
            progress(final_size, final_size if not total else total)
        except Exception:
            pass
    return dest
