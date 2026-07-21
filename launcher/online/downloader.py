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
    "Chrome/122.0.0.0 Safari/537.36 RVCFabric/1.0"
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


def is_cnb_url(url: str) -> bool:
    u = (url or "").lower()
    return "cnb.cool" in u


def parse_cnb_org_repo(url: str) -> Optional[tuple[str, str]]:
    """Return (org, repo) from a cnb.cool URL, or None."""
    m = re.match(r"https?://cnb\.cool/([^/]+)/([^/]+)", (url or "").strip(), re.I)
    if not m:
        return None
    return m.group(1), m.group(2)


def cnb_lfs_object_url(org: str, repo: str, oid_sha256: str) -> str:
    """CNB public LFS object download (file body by content hash).

    Form confirmed working with GET (HEAD may 404)::

        https://cnb.cool/<org>/<repo>/-/lfs/<sha256>
    """
    oid = re.sub(r"[^0-9a-fA-F]", "", (oid_sha256 or "").strip())
    if len(oid) != 64:
        raise DownloadError("CNB LFS oid 必须是 64 位 hex sha256")
    return f"https://cnb.cool/{org}/{repo}/-/lfs/{oid.lower()}"


def normalize_cnb_url(url: str) -> str:
    """Normalize CNB browser URLs; prefer LFS object URLs for binaries.

    Working downloads::

      * small files: ``…/-/git/raw/<branch>/<path>``
      * Git LFS blobs: ``…/-/lfs/<sha256>``  (content hash = oid)

    ``/-/blob/...`` is an HTML page — rewritten to git/raw (may still be an
    LFS pointer; caller should upgrade via sha256 or pointer parse).
    """
    u = (url or "").strip()
    if not u or not is_cnb_url(u):
        return u
    # Already LFS object or raw — keep
    if "/-/lfs/" in u:
        return u.split("?", 1)[0]
    if "/-/git/raw/" in u:
        return u.split("?", 1)[0]
    # blob page → raw (path form; LFS still needs /-/lfs/<oid>)
    m = re.match(
        r"https?://cnb\.cool/([^/]+)/([^/]+)/-/blob/([^/]+)/(.*)$",
        u,
        re.I,
    )
    if m:
        org, repo, branch, path = m.groups()
        path = path.split("?", 1)[0]
        return f"https://cnb.cool/{org}/{repo}/-/git/raw/{branch}/{path}"
    m = re.match(
        r"https?://cnb\.cool/([^/]+)/([^/]+)/-/raw/([^/]+)/(.*)$",
        u,
        re.I,
    )
    if m:
        org, repo, branch, path = m.groups()
        path = path.split("?", 1)[0]
        return f"https://cnb.cool/{org}/{repo}/-/git/raw/{branch}/{path}"
    return u


def prefer_cnb_lfs_url(url: str, sha256: str = "") -> str:
    """If URL is CNB and sha256 known, use ``/-/lfs/<sha256>`` for real bytes."""
    u = normalize_cnb_url(url)
    oid = re.sub(r"[^0-9a-fA-F]", "", (sha256 or "").strip())
    if not is_cnb_url(u) or len(oid) != 64:
        return u
    if "/-/lfs/" in u:
        return u
    parsed = parse_cnb_org_repo(u)
    if not parsed:
        return u
    org, repo = parsed
    return cnb_lfs_object_url(org, repo, oid)


def is_git_lfs_pointer_bytes(data: bytes) -> bool:
    """True when body is a Git LFS pointer text, not the real object."""
    if not data or len(data) > 1024:
        return False
    head = data.lstrip()[:80]
    return head.startswith(b"version https://git-lfs.github.com/spec/")


def parse_git_lfs_pointer_oid(data: bytes) -> str:
    """Extract sha256 oid from LFS pointer text; empty if not a pointer."""
    if not is_git_lfs_pointer_bytes(data):
        return ""
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("oid sha256:"):
            return line.split(":", 1)[-1].strip().lower()
        if line.startswith("oid "):
            # oid sha256:xxxx
            parts = line.split()
            if len(parts) >= 2 and "sha256:" in parts[1]:
                return parts[1].split("sha256:", 1)[-1].strip().lower()
    return ""


def resolve_download_url(url: str, session=None) -> str:
    """Turn a share/page URL into a streamable download URL when possible."""
    u = (url or "").strip()
    if not u:
        raise DownloadError("空下载地址")
    u = normalize_github_url(u)
    u = normalize_cnb_url(u)

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
        # Prefer CNB LFS object URL when content hash is known (real zip/tar bytes).
        resolved = prefer_cnb_lfs_url(
            resolve_download_url(url, session=session), expected_sha256
        )
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
                    first = b""
                    with open(tmp, "wb") as f:
                        for chunk in r.iter_content(chunk_size=CHUNK):
                            if not chunk:
                                continue
                            if len(first) < 200:
                                first += chunk[: 200 - len(first)]
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
                    # git/raw of LFS files returns pointer text — upgrade to /-/lfs/<oid>
                    body_head = first
                    if done < 1024 and tmp.is_file():
                        try:
                            body_head = tmp.read_bytes()[:512]
                        except OSError:
                            pass
                    if is_git_lfs_pointer_bytes(body_head):
                        oid = parse_git_lfs_pointer_oid(body_head)
                        pr = parse_cnb_org_repo(resolved)
                        if oid and pr and "/-/lfs/" not in resolved:
                            resolved = cnb_lfs_object_url(pr[0], pr[1], oid)
                            try:
                                tmp.unlink()
                            except OSError:
                                pass
                            # Retry same attempt slot with LFS object URL
                            with session.get(
                                resolved,
                                stream=True,
                                allow_redirects=True,
                                timeout=timeout,
                            ) as r2:
                                r2.raise_for_status()
                                total2 = int(r2.headers.get("content-length") or 0)
                                done = 0
                                first2 = b""
                                with open(tmp, "wb") as f:
                                    for chunk in r2.iter_content(chunk_size=CHUNK):
                                        if not chunk:
                                            continue
                                        if len(first2) < 200:
                                            first2 += chunk[: 200 - len(first2)]
                                        f.write(chunk)
                                        done += len(chunk)
                                        if progress:
                                            try:
                                                progress(done, total2)
                                            except Exception:
                                                pass
                                if is_git_lfs_pointer_bytes(first2):
                                    raise DownloadError(
                                        "CNB LFS 对象地址仍返回指针，无法取得实体文件。"
                                    )
                                if total2 and done < total2 * 0.98:
                                    raise DownloadError(
                                        f"下载不完整：{done}/{total2} bytes"
                                    )
                        else:
                            raise DownloadError(
                                "下载到的是 Git LFS 指针而不是真实文件。\n"
                                "请在 catalog 中使用 CNB 直链：…/-/lfs/<sha256> "
                                "（内容哈希，与 sha256 字段相同）。"
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
