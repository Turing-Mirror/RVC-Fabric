# -*- coding: utf-8 -*-
"""Safe zip extraction — reject zip-slip (../, absolute paths).

Used by voice packs and any future archive installers.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Iterable, Optional


class UnsafeZipError(ValueError):
    """Archive member would escape the destination directory."""


def _safe_member_path(base: Path, member_name: str) -> Path:
    """Return dest path under base, or raise UnsafeZipError."""
    # Normalize zip member (forward slashes, no drive)
    name = (member_name or "").replace("\\", "/").lstrip("/")
    if not name or name.endswith("/"):
        return base  # directory entry — caller may skip
    if name.startswith("../") or "/../" in f"/{name}/" or name == "..":
        raise UnsafeZipError(f"zip member escapes base: {member_name!r}")
    # Reject absolute-like Windows paths inside zip
    if len(name) >= 2 and name[1] == ":":
        raise UnsafeZipError(f"zip member absolute path: {member_name!r}")
    dest = (base / name).resolve()
    base_r = base.resolve()
    try:
        dest.relative_to(base_r)
    except ValueError as e:
        raise UnsafeZipError(f"zip member escapes base: {member_name!r}") from e
    return dest


def safe_extract_zip(
    zip_path: Path,
    dest_dir: Path,
    *,
    members: Optional[Iterable[str]] = None,
) -> list[str]:
    """Extract zip into dest_dir with path sanitization. Returns written relative paths."""
    zip_path = Path(zip_path)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = list(members) if members is not None else zf.namelist()
        for name in names:
            info = zf.getinfo(name)
            # skip pure directory markers after sanitize
            rel = name.replace("\\", "/").lstrip("/")
            if not rel or rel.endswith("/"):
                continue
            dest = _safe_member_path(dest_dir, name)
            if info.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(dest, "wb") as out:
                out.write(src.read())
            try:
                written.append(str(dest.relative_to(dest_dir.resolve())))
            except ValueError:
                written.append(dest.name)
    return written


def assert_path_under_root(path: Path, root: Path) -> Path:
    """Ensure path resolves under root; raise UnsafeZipError otherwise."""
    p = Path(path).resolve()
    r = Path(root).resolve()
    try:
        p.relative_to(r)
    except ValueError as e:
        raise UnsafeZipError(f"path escapes root: {path}") from e
    return p
