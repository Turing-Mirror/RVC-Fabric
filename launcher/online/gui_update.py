# -*- coding: utf-8 -*-
"""Apply GUI/shell zip updates (not full Runtime packages).

Zip layout: relative paths under package root, e.g.::

    launcher/main_app.py
    launcher/theme.py
    configs/online_catalog.json

Blocked prefixes protect Runtime, user data, and large engine weights.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Callable, Optional

from launcher.online.catalog import GuiUpdate, OnlineCatalog, compare_versions
from launcher.online.downloader import DownloadError, download_file
from launcher.paths import ROOT, USER_DATA
from launcher.version import APP_VERSION

ProgressCb = Callable[[str, int, int], None]

# Paths that must never be overwritten by an in-app GUI patch
BLOCKED_PREFIXES = (
    "runtime/",
    "user_data/",
    "userdata/",
    "rvcmax/",
    "dist/",
    "build/",
    "assets/pretrained/",
    "assets/pretrained_v2/",
    "assets/uvr5_weights/",
    "assets/hubert/",
    "assets/rmvpe/",
    "assets/weights/",
    "vbcable/",
    ".git/",
)

ALLOWED_PREFIXES = (
    "launcher/",
    "configs/",
    "docs/",
    "i18n/",
    "scripts/",
    "tools/",
)

ALLOWED_ROOT_FILES = frozenset(
    {
        "gui_v1.py",
        "infer-web.py",
        "readme.md",
        "package_meta.json",
        "version.txt",
    }
)


def check_gui_update(catalog: OnlineCatalog, local_version: str = "") -> dict:
    """Return status dict: available, local, remote, notes, url."""
    local = (local_version or APP_VERSION).strip()
    remote = (catalog.gui.version or catalog.app_version or "").strip()
    url = (catalog.gui.url or "").strip()
    available = bool(url and remote and compare_versions(local, remote) < 0)
    return {
        "available": available,
        "local": local,
        "remote": remote or "—",
        "notes": catalog.gui.notes or "",
        "url": url,
        "sha256": catalog.gui.sha256 or "",
    }


def _safe_member(name: str) -> Optional[str]:
    """Normalize zip member; return None if blocked."""
    n = name.replace("\\", "/").lstrip("/")
    if not n or n.endswith("/"):
        return None
    if ".." in n.split("/"):
        return None
    low = n.lower()
    for b in BLOCKED_PREFIXES:
        if low.startswith(b):
            return None
    # allowlisted prefixes or root files
    if any(low.startswith(p) for p in ALLOWED_PREFIXES):
        return n
    base = Path(n).name.lower()
    if "/" not in n.rstrip("/") and base in ALLOWED_ROOT_FILES:
        return n
    return None


def apply_gui_zip(
    zip_path: Path,
    *,
    root: Optional[Path] = None,
) -> list[str]:
    """Extract allowed files from zip into package root. Returns written paths."""
    root = Path(root or ROOT)
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        raise DownloadError(f"找不到更新包：{zip_path}")
    written: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            rel = _safe_member(info.filename)
            if not rel:
                continue
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            written.append(rel)
    if not written:
        raise DownloadError(
            "更新包中没有可应用的文件（可能被安全策略拦截，或 zip 结构不正确）"
        )
    return written


def download_and_apply_gui(
    gui: GuiUpdate,
    *,
    root: Optional[Path] = None,
    progress: Optional[ProgressCb] = None,
) -> list[str]:
    if not gui.url:
        raise DownloadError("没有 GUI 更新地址")
    cache = USER_DATA / "update_cache" / "gui"
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / f"gui_{gui.version or 'patch'}.zip"

    def _p(done: int, total: int) -> None:
        if progress:
            progress("download", done, total)

    download_file(
        gui.url,
        dest,
        progress=_p,
        expected_sha256=gui.sha256 or "",
    )
    if progress:
        progress("apply", 0, 1)
    written = apply_gui_zip(dest, root=root)
    if progress:
        progress("apply", 1, 1)
    return written
