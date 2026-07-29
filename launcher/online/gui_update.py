# -*- coding: utf-8 -*-
"""Apply GUI updates with package-type awareness.

- **gui_patch** (增量): download zip → merge allowlist into product root
- **full_package** (全量): download optional / open link only — **never** merge Runtime
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Callable, Optional

from launcher.online.catalog import GuiUpdate, OnlineCatalog, compare_versions
from launcher.online.downloader import DownloadError, download_file, open_in_browser
from launcher.online.package_spec import (
    PKG_FULL,
    PKG_GUI_PATCH,
    TM_PACKAGE_JSON,
    detect_zip_package_type,
    full_package_policy_help,
    gui_member_allowed,
    normalize_package_type,
    read_zip_tm_package,
)
from launcher.paths import ROOT, USER_DATA
from launcher.version import APP_VERSION

ProgressCb = Callable[[str, int, int], None]


def check_gui_update(catalog: OnlineCatalog, local_version: str = "") -> dict:
    """Return status for UI: available, package_type, action, …"""
    local = (local_version or APP_VERSION).strip()
    remote = (catalog.gui.version or catalog.app_version or "").strip()
    url = (catalog.gui.url or "").strip()
    pkg_type = normalize_package_type(
        catalog.gui.package_type or PKG_GUI_PATCH, default=PKG_GUI_PATCH
    )
    newer = bool(remote and compare_versions(local, remote) < 0)
    # full_package may still show as "available" for notice, but action differs
    available = bool(url and remote and newer)
    if pkg_type == PKG_FULL:
        action = "external"  # open link / download to folder, do not apply
    else:
        action = "apply_patch"

    return {
        "available": available,
        "local": local,
        "remote": remote or "—",
        "notes": catalog.gui.notes or "",
        "url": url,
        "sha256": catalog.gui.sha256 or "",
        "package_type": pkg_type,
        "action": action,
        "min_app_version": catalog.gui.min_app_version or "",
    }


def apply_gui_patch_zip(
    zip_path: Path,
    *,
    root: Optional[Path] = None,
    enforce_type: bool = True,
) -> dict:
    """Merge a **gui_patch** zip into product root.

    Returns dict: written, package_type, meta, skipped_blocked.
    Raises DownloadError if zip is full_package or has nothing allowed.
    """
    root = Path(root or ROOT)
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        raise DownloadError(f"找不到更新包：{zip_path}")

    detected = detect_zip_package_type(zip_path)
    meta = read_zip_tm_package(zip_path)
    declared = normalize_package_type(
        str(meta.get("package_type") or meta.get("type") or meta.get("kind") or ""),
        default=detected,
    )
    pkg_type = declared if meta else detected

    if enforce_type and pkg_type == PKG_FULL:
        raise DownloadError(
            "该文件被识别为【全量发行包】，不能在软件内覆盖安装。\n"
            + full_package_policy_help()
        )

    if enforce_type and pkg_type not in (PKG_GUI_PATCH,):
        # voice packs should not go through this function
        if pkg_type.startswith("voice"):
            raise DownloadError(
                "该 zip 是音色包，请走「音色库」下载安装，不要当作 GUI 更新应用。"
            )

    # min_app_version check
    min_v = str(meta.get("min_app_version") or "").strip()
    if min_v and compare_versions(APP_VERSION, min_v) < 0:
        raise DownloadError(
            f"此增量包要求软件版本 ≥ {min_v}，当前为 {APP_VERSION}。"
            "请先安装中间版本或下载全量包。"
        )

    from launcher.online.safe_zip import UnsafeZipError, assert_path_under_root

    root = Path(root).resolve()
    written: list[str] = []
    skipped: list[str] = []

    # Two-phase apply (review #9): extract fully to staging, then commit with
    # per-file backups so a mid-write failure can restore the previous tree.
    stage_root = USER_DATA / "update_cache" / "gui_stage"
    stage_root.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f"patch_{int(time.time())}_",
            dir=str(stage_root),
        )
    )
    staged: list[tuple[str, Path]] = []  # (rel posix, staged file)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = list(zf.infolist())
            prefix = _common_strip_prefix([m.filename for m in members])

            for info in members:
                raw = info.filename.replace("\\", "/")
                if prefix and raw.startswith(prefix):
                    raw_body = raw[len(prefix) :]
                else:
                    raw_body = raw
                rel = gui_member_allowed(raw_body)
                if not rel:
                    if not raw.endswith("/") and TM_PACKAGE_JSON not in raw:
                        skipped.append(raw)
                    continue
                dest_check = root / rel
                try:
                    assert_path_under_root(dest_check, root)
                except UnsafeZipError:
                    skipped.append(raw)
                    continue
                staged_path = stage / rel
                staged_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with zf.open(info, "r") as src, open(staged_path, "wb") as out:
                        shutil.copyfileobj(src, out)
                except OSError as e:
                    raise DownloadError(
                        f"增量包解压到暂存区失败（磁盘满或权限不足）：{e}"
                    ) from e
                staged.append((rel, staged_path))

        if not staged:
            raise DownloadError(
                "增量包中没有可应用的文件。\n"
                "请确认 zip 内路径为 launcher/、configs/、tools/ 等白名单，"
                "且未误打成全量 Runtime 包。"
            )

        # Backup then commit each file
        backup_dir = stage / "_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backups: list[tuple[Path, Path | None]] = []  # (dest, backup or None)
        try:
            for rel, staged_path in staged:
                dest = root / rel
                bak: Path | None = None
                if dest.is_file():
                    bak = backup_dir / rel
                    bak.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dest, bak)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(staged_path, dest)
                backups.append((dest, bak))
                written.append(rel)
        except Exception as e:
            # Rollback committed files
            for dest, bak in reversed(backups):
                try:
                    if bak is not None and bak.is_file():
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(bak, dest)
                    elif dest.is_file() and bak is None:
                        # Newly added file — remove
                        try:
                            dest.unlink()
                        except OSError:
                            pass
                except OSError:
                    pass
            raise DownloadError(
                f"应用增量包失败，已尝试回滚已写入文件：{e}"
            ) from e
    finally:
        try:
            shutil.rmtree(stage, ignore_errors=True)
        except Exception:
            pass

    # Write version stamp if package declares version
    ver = str(meta.get("version") or "").strip()
    if ver:
        try:
            state_path = USER_DATA / "update_state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state = {}
            if state_path.is_file():
                try:
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                except Exception:
                    state = {}
            state["last_gui_patch_version"] = ver
            state["last_gui_patch_files"] = written[:50]
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    return {
        "written": written,
        "skipped_blocked": skipped[:30],
        "package_type": PKG_GUI_PATCH,
        "meta": meta,
        "version": ver,
    }


# Back-compat name
def apply_gui_zip(zip_path: Path, *, root: Optional[Path] = None) -> list[str]:
    return list(apply_gui_patch_zip(zip_path, root=root)["written"])


def _common_strip_prefix(names: list[str]) -> str:
    """If all files are under one folder Foo/, strip Foo/ (except tm_package at root)."""
    cleaned = []
    for n in names:
        n = n.replace("\\", "/")
        if not n or n.endswith("/"):
            continue
        cleaned.append(n)
    if not cleaned:
        return ""
    tops = {n.split("/")[0] for n in cleaned if "/" in n}
    if len(tops) != 1:
        return ""
    top = next(iter(tops))
    # don't strip if top is an allowed root dir name
    if top.lower() in (
        "launcher",
        "configs",
        "docs",
        "i18n",
        "scripts",
        "tools",
        "tests",
        "runtime",
        "user_data",
        "assets",
    ):
        return ""
    # all multi-segment paths must start with top/
    for n in cleaned:
        if n == TM_PACKAGE_JSON:
            continue
        if not n.startswith(top + "/"):
            return ""
    return top + "/"


def download_and_apply_gui(
    gui: GuiUpdate,
    *,
    root: Optional[Path] = None,
    progress: Optional[ProgressCb] = None,
    require_sha256: bool = True,
) -> dict:
    """Download by catalog entry; route by package_type.

    require_sha256: default True for supply-chain safety (electron-updater style).
    """
    if not gui.url:
        raise DownloadError("没有 GUI 更新地址")

    # Catalog min_app_version gate on the download path (review #10)
    min_v = str(getattr(gui, "min_app_version", None) or "").strip()
    if min_v and compare_versions(APP_VERSION, min_v) < 0:
        raise DownloadError(
            f"此增量包要求软件版本 ≥ {min_v}，当前为 {APP_VERSION}。"
            "请先安装中间版本或下载全量包。"
        )

    pkg_type = normalize_package_type(gui.package_type or PKG_GUI_PATCH)

    if pkg_type == PKG_FULL:
        # Never apply: open browser or download to cache with instruction
        open_in_browser(gui.url)
        return {
            "package_type": PKG_FULL,
            "action": "external_opened",
            "written": [],
            "message": "已打开全量包下载链接。请下载后解压到新目录使用，勿在软件内覆盖 Runtime。",
        }

    sha = (gui.sha256 or "").strip()
    if require_sha256 and not sha:
        raise DownloadError(
            "清单未提供 gui.sha256，已拒绝应用增量包（供应链安全）。\n"
            "请运营在 online_catalog 填写校验和，或用 scripts/pack_gui_patch.py 生成后登记。"
        )

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
        expected_sha256=sha,
    )

    # Re-detect after download (catalog may be wrong)
    detected = detect_zip_package_type(dest)
    if detected == PKG_FULL or pkg_type == PKG_FULL:
        raise DownloadError(
            "下载到的文件是【全量包】标记/结构，已中止自动安装。\n"
            f"文件保存在：{dest}\n"
            + full_package_policy_help()
        )

    if progress:
        progress("apply", 0, 1)
    result = apply_gui_patch_zip(dest, root=root, enforce_type=True)
    if progress:
        progress("apply", 1, 1)
    result["action"] = "applied_patch"
    result["zip_path"] = str(dest)
    return result


def handle_full_package_url(url: str, *, download_to_cache: bool = False) -> dict:
    """Policy entry for full packages: open browser; optional save only."""
    url = (url or "").strip()
    if not url:
        raise DownloadError("未配置全量包地址")
    if download_to_cache:
        cache = USER_DATA / "update_cache" / "full_packages"
        cache.mkdir(parents=True, exist_ok=True)
        dest = cache / "full_package_download.bin"
        download_file(url, dest)
        return {
            "package_type": PKG_FULL,
            "action": "downloaded_only",
            "path": str(dest),
            "message": "全量包已下载到缓存目录，请手动解压到新文件夹后使用，勿覆盖当前 Runtime。",
        }
    open_in_browser(url)
    return {
        "package_type": PKG_FULL,
        "action": "external_opened",
        "message": "已在浏览器打开全量包链接。",
    }
