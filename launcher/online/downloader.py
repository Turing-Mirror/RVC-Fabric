# -*- coding: utf-8 -*-
"""HTTP downloader for GitHub raw/release and SharePoint/OneDrive share links.

Full Runtime packages are intentionally NOT applied in-app — only file downloads
for GUI patches and voice models. SharePoint public share links are resolved via
redirect + download.aspx / download=1 heuristics (no Microsoft Graph auth).
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, unquote, urlparse, urlunparse

ProgressCb = Callable[[int, int], None]  # done_bytes, total_bytes (0 if unknown)

CHUNK = 1 << 16  # 64 KiB
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36 TuringMirrorVoice/1.0"
)


class DownloadError(RuntimeError):
    pass


def _session():
    try:
        import requests
    except ImportError as e:
        raise DownloadError("需要 requests 库（Runtime 或主机 Python 请安装 requests）") from e
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": DEFAULT_UA,
            "Accept": "*/*",
        }
    )
    return s


def is_sharepoint_or_onedrive(url: str) -> bool:
    u = (url or "").lower()
    return any(
        h in u
        for h in (
            "sharepoint.com",
            "1drv.ms",
            "onedrive.live.com",
            "onedrive.com",
        )
    )


def is_github_url(url: str) -> bool:
    u = (url or "").lower()
    return "github.com" in u or "githubusercontent.com" in u


def normalize_github_url(url: str) -> str:
    """blob → raw; keep releases/download and raw as-is."""
    u = (url or "").strip()
    if not u:
        return u
    # https://github.com/org/repo/blob/branch/path → raw
    m = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.*)$",
        u,
        re.I,
    )
    if m:
        org, repo, branch, path = m.groups()
        return f"https://raw.githubusercontent.com/{org}/{repo}/{branch}/{path}"
    return u


def resolve_download_url(url: str, session=None) -> str:
    """Turn a share/page URL into a streamable download URL when possible."""
    u = (url or "").strip()
    if not u:
        raise DownloadError("空下载地址")
    u = normalize_github_url(u)

    # Already force-download
    if "download=1" in u or "download.aspx" in u.lower():
        return u
    if is_github_url(u) or not is_sharepoint_or_onedrive(u):
        return u

    # SharePoint / OneDrive public share: follow redirects, rewrite to download.aspx
    close = False
    if session is None:
        session = _session()
        close = True
    try:
        # Prefer append download=1 first (works for many :u: :b: shares)
        if "download=1" not in u:
            joiner = "&" if "?" in u else "?"
            candidate = f"{u}{joiner}download=1"
        else:
            candidate = u

        r = session.get(candidate, allow_redirects=True, stream=True, timeout=60)
        final = r.url
        # Peek content-type: if HTML, try download.aspx rewrite
        ctype = (r.headers.get("Content-Type") or "").lower()
        r.close()

        if "text/html" not in ctype and r.status_code < 400:
            return final

        # Rewrite onedrive.aspx?id= → download.aspx?SourceUrl=
        if "onedrive.aspx" in final.lower():
            new_url = final.replace("onedrive.aspx", "download.aspx").replace(
                "?id=", "?SourceUrl="
            )
            return new_url

        parsed = urlparse(final)
        qs = parse_qs(parsed.query)
        # UniqueId / sourcedoc style
        if "sourcedoc" in qs or "UniqueId" in qs:
            uid = (qs.get("UniqueId") or qs.get("sourcedoc") or [""])[0]
            base = f"{parsed.scheme}://{parsed.netloc}"
            # Prefer layouts download
            return f"{base}/_layouts/15/download.aspx?UniqueId={unquote(uid)}"

        # Fallback: original + download=1
        return candidate
    except DownloadError:
        raise
    except Exception as e:
        raise DownloadError(f"解析 SharePoint/OneDrive 链接失败: {e}") from e
    finally:
        if close:
            try:
                session.close()
            except Exception:
                pass


def download_file(
    url: str,
    dest: Path,
    *,
    progress: Optional[ProgressCb] = None,
    retries: int = 3,
    timeout: int = 120,
    expected_sha256: str = "",
) -> Path:
    """Download url → dest (atomic .part rename). Returns dest."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    session = _session()
    last_err: Exception | None = None

    try:
        resolved = resolve_download_url(url, session=session)
        for attempt in range(1, retries + 1):
            try:
                with session.get(
                    resolved, stream=True, allow_redirects=True, timeout=timeout
                ) as r:
                    r.raise_for_status()
                    total = int(r.headers.get("content-length") or 0)
                    ctype = (r.headers.get("Content-Type") or "").lower()
                    if "text/html" in ctype and total < 500_000:
                        # likely an error / login page
                        snippet = r.content[:200].decode("utf-8", errors="ignore")
                        raise DownloadError(
                            "服务器返回了网页而不是文件（链接可能需要登录或已失效）。"
                            f" Content-Type={ctype} 预览={snippet[:80]!r}"
                        )
                    done = 0
                    with open(tmp, "wb") as f:
                        for chunk in r.iter_content(chunk_size=CHUNK):
                            if not chunk:
                                continue
                            f.write(chunk)
                            done += len(chunk)
                            if progress:
                                try:
                                    progress(done, total)
                                except Exception:
                                    pass
                    if total and done < total * 0.98:
                        raise DownloadError(
                            f"下载不完整：{done}/{total} bytes"
                        )
                if expected_sha256:
                    _verify_sha256(tmp, expected_sha256)
                if dest.is_file():
                    try:
                        dest.unlink()
                    except OSError:
                        pass
                tmp.replace(dest)
                if progress:
                    try:
                        progress(dest.stat().st_size, dest.stat().st_size)
                    except Exception:
                        pass
                return dest
            except Exception as e:
                last_err = e
                try:
                    if tmp.is_file():
                        tmp.unlink()
                except OSError:
                    pass
                if attempt < retries:
                    time.sleep(1.2 * attempt)
        raise DownloadError(str(last_err) if last_err else "下载失败")
    finally:
        try:
            session.close()
        except Exception:
            pass


def _verify_sha256(path: Path, expect: str) -> None:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    got = h.hexdigest().lower()
    exp = expect.strip().lower()
    if got != exp:
        raise DownloadError(f"SHA256 不匹配：期望 {exp[:12]}… 实际 {got[:12]}…")


def open_in_browser(url: str) -> None:
    import webbrowser

    if url:
        webbrowser.open(url)
