# -*- coding: utf-8 -*-
"""Package types, layouts, and validation for online updates.

Three product package kinds (运营/打包必须遵守)::

1. **gui_patch** (增量壳层包) — 软件内下载并合并覆盖白名单路径
2. **full_package** (全量发行包) — 含 Runtime，**禁止**软件内静默覆盖；只引导外链/下载后手动解压
3. **voice_pack** / **voice_files** (音色) — 装入 User_Data/models/<id>/

Zip 根目录可放 ``tm_package.json`` 声明类型（推荐）；也可由 catalog 字段指定。
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Optional

# --- Package type constants ---
PKG_GUI_PATCH = "gui_patch"
PKG_FULL = "full_package"
PKG_VOICE_PACK = "voice_pack"
PKG_VOICE_FILES = "voice_files"

PACKAGE_TYPES = frozenset(
    {PKG_GUI_PATCH, PKG_FULL, PKG_VOICE_PACK, PKG_VOICE_FILES}
)

# Alias map (catalog / tm_package.json 可用的别名)
TYPE_ALIASES: dict[str, str] = {
    "gui_patch": PKG_GUI_PATCH,
    "incremental": PKG_GUI_PATCH,
    "patch": PKG_GUI_PATCH,
    "delta": PKG_GUI_PATCH,
    "shell": PKG_GUI_PATCH,
    "gui": PKG_GUI_PATCH,
    "full_package": PKG_FULL,
    "full": PKG_FULL,
    "complete": PKG_FULL,
    "runtime": PKG_FULL,
    "installer": PKG_FULL,
    "voice_pack": PKG_VOICE_PACK,
    "voice_zip": PKG_VOICE_PACK,
    "model_pack": PKG_VOICE_PACK,
    "voice_files": PKG_VOICE_FILES,
    "files": PKG_VOICE_FILES,
    "loose": PKG_VOICE_FILES,
}

# Manifest filename inside zip (UTF-8 JSON)
TM_PACKAGE_JSON = "tm_package.json"

# GUI patch allow / block (relative to product root, forward slash, lower for compare)
GUI_BLOCKED_PREFIXES = (
    "runtime/",
    "user_data/",
    "userdata/",
    "rvcmax/",
    "dist/",
    "build/",
    "temp/",
    "temp_build/",
    "assets/pretrained/",
    "assets/pretrained_v2/",
    "assets/uvr5_weights/",
    "assets/hubert/",
    "assets/rmvpe/",
    "assets/weights/",
    "vbcable/",
    ".git/",
    "logs/",
)

GUI_ALLOWED_PREFIXES = (
    "launcher/",
    "configs/",
    "docs/",
    "i18n/",
    "scripts/",
    "tools/",
    "tests/",
)

GUI_ALLOWED_ROOT_FILES = frozenset(
    {
        "gui_v1.py",
        "infer-web.py",
        "readme.md",
        "package_meta.json",
        "version.txt",
        "license",
        "pyproject.toml",
        "requirements.txt",
        "openapp.vbs",
        "opensetup.vbs",
        "start.bat",
        "start_app.bat",
    }
)

# full_package: markers that mean "this zip must NOT be applied as patch"
FULL_PACKAGE_MARKERS = (
    "runtime/python.exe",
    "runtime/pythonw.exe",
    "runtime/lib/",
    "tm_voice.exe",
    "变声器.exe",
    "启动器.exe",
)

# voice pack: recognized names
VOICE_PTH_EXTS = (".pth",)
VOICE_INDEX_EXTS = (".index",)
VOICE_COVER_NAMES = ("cover.png", "cover.jpg", "cover.jpeg", "cover.webp")
VOICE_CONFIG_NAME = "config.json"

# Voice pack / installed sidecar identity fields (config.json or tm_package.json)
# Required product fields for RVC Fabric released packs:
#   name, author, author_url, date (YYMMDD), cover (local path in pack)
VOICE_META_KEYS: tuple[str, ...] = (
    "name",
    "author",
    "author_url",
    "date",
    "cover",
)


def normalize_package_type(raw: str, *, default: str = PKG_GUI_PATCH) -> str:
    s = (raw or "").strip().lower().replace("-", "_")
    if not s:
        return default
    return TYPE_ALIASES.get(s, s if s in PACKAGE_TYPES else default)


def read_zip_tm_package(zip_path: Path) -> dict[str, Any]:
    """Read tm_package.json from zip root if present."""
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        return {}
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = {n.replace("\\", "/") for n in zf.namelist()}
            # root or single top-folder
            candidates = [TM_PACKAGE_JSON]
            for n in names:
                if n.endswith("/" + TM_PACKAGE_JSON) and n.count("/") == 1:
                    candidates.append(n)
            for c in candidates:
                if c in names or c in zf.namelist():
                    try:
                        data = json.loads(zf.read(c).decode("utf-8"))
                        return data if isinstance(data, dict) else {}
                    except Exception:
                        continue
    except Exception:
        return {}
    return {}


def detect_zip_package_type(zip_path: Path) -> str:
    """Infer package type from tm_package.json or zip contents."""
    meta = read_zip_tm_package(zip_path)
    if meta.get("package_type") or meta.get("type") or meta.get("kind"):
        return normalize_package_type(
            str(meta.get("package_type") or meta.get("type") or meta.get("kind"))
        )

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = [n.replace("\\", "/").lower() for n in zf.namelist()]
    except Exception:
        return PKG_GUI_PATCH

    # Full package heuristics
    for m in FULL_PACKAGE_MARKERS:
        if any(n == m or n.endswith("/" + m) or m in n for n in names):
            return PKG_FULL
    if any(n.startswith("runtime/") for n in names):
        return PKG_FULL

    # Voice pack: has pth, no launcher/
    has_pth = any(n.endswith(".pth") for n in names)
    has_launcher = any(n.startswith("launcher/") or "/launcher/" in n for n in names)
    if has_pth and not has_launcher:
        return PKG_VOICE_PACK

    return PKG_GUI_PATCH


def gui_member_allowed(name: str) -> Optional[str]:
    """Return normalized relative path if allowed for gui_patch, else None."""
    n = name.replace("\\", "/").lstrip("/")
    if not n or n.endswith("/"):
        return None
    if ".." in n.split("/"):
        return None
    # strip single top-level folder if it's only packaging wrapper (optional later)
    low = n.lower()
    if low == TM_PACKAGE_JSON or low.endswith("/" + TM_PACKAGE_JSON):
        return None  # meta not installed into product
    for b in GUI_BLOCKED_PREFIXES:
        if low.startswith(b):
            return None
    if any(low.startswith(p) for p in GUI_ALLOWED_PREFIXES):
        return n
    base = Path(n).name.lower()
    if "/" not in n.rstrip("/") and base in GUI_ALLOWED_ROOT_FILES:
        return n
    return None


def describe_package_type(pkg_type: str) -> str:
    t = normalize_package_type(pkg_type)
    return {
        PKG_GUI_PATCH: "增量壳层包（软件内合并覆盖，不含 Runtime）",
        PKG_FULL: "全量发行包（含 Runtime；软件内不覆盖，请外链手动安装）",
        PKG_VOICE_PACK: "音色 zip 包（解压到 User_Data/models）",
        PKG_VOICE_FILES: "音色多文件直链（pth + 可选 index/cover）",
    }.get(t, t)


def normalize_yymmdd(raw: Any) -> str:
    """Normalize to YYMMDD string; empty if unusable."""
    import re

    s = str(raw or "").strip()
    if not s:
        return ""
    digits = re.sub(r"\D", "", s)
    if len(digits) == 8:  # YYYYMMDD → YYMMDD
        return digits[2:]
    if len(digits) == 6:
        return digits
    return ""


def normalize_voice_meta(data: Any) -> dict[str, str]:
    """Extract voice identity fields from pack config / tm_package / catalog.

    Canonical keys: name, author, author_url, date (YYMMDD), cover (relative path).
    """
    out: dict[str, str] = {}
    if not isinstance(data, dict):
        return out
    name = data.get("name") or data.get("title") or data.get("voice_name")
    if name not in (None, ""):
        out["name"] = str(name).strip()
    author = data.get("author") or data.get("creator") or data.get("artist")
    if author not in (None, ""):
        out["author"] = str(author).strip()
    # Do not use generic "url" — that is often the pack download link
    aurl = data.get("author_url") or data.get("author_link") or data.get("homepage")
    if aurl not in (None, ""):
        out["author_url"] = str(aurl).strip()
    date = normalize_yymmdd(
        data.get("date")
        or data.get("released")
        or data.get("yymmdd")
        or data.get("release_date")
    )
    if date:
        out["date"] = date
    cover = (
        data.get("cover")
        or data.get("cover_path")
        or data.get("cover_file")
        or data.get("cover_url")
    )
    if cover not in (None, ""):
        # Keep relative pack paths; absolute http covers stay as-is for catalog
        out["cover"] = str(cover).strip().replace("\\", "/")
    return out


def voice_meta_template(
    *,
    name: str = "",
    author: str = "",
    author_url: str = "",
    date: str = "",
    cover: str = "cover.jpg",
    **extra: Any,
) -> dict[str, Any]:
    """Minimal config.json body for a released voice pack."""
    body: dict[str, Any] = {
        "name": name or "",
        "author": author or "",
        "author_url": author_url or "",
        "date": normalize_yymmdd(date) or "",
        "cover": cover or "cover.jpg",
    }
    body.update({k: v for k, v in extra.items() if v is not None})
    return body


def voice_pack_layout_help() -> str:
    return (
        "音色包 zip 结构：\n"
        "  config.json       （必需字段见下）\n"
        "  *.pth             （必需）\n"
        "  *.index           （可选，与 .pth 同级）\n"
        "  cover.jpg|png     （封面，路径写在 config.cover）\n"
        "  tm_package.json   （可选，package_type=voice_pack）\n"
        "config.json 字段：\n"
        "  name        音色名称\n"
        "  author      作者\n"
        "  author_url  作者链接\n"
        "  date        YYMMDD\n"
        "  cover       包内封面相对路径（如 cover.jpg）\n"
        "安装后：User_Data/models/<id>/\n"
    )


def gui_patch_layout_help() -> str:
    return (
        "增量 GUI 包 zip 结构（路径相对软件根目录）：\n"
        "  tm_package.json\n"
        "  launcher/...\n"
        "  configs/...\n"
        "  tools/...\n"
        "  gui_v1.py（可选）\n"
        "禁止包含：Runtime/、User_Data/、assets/hubert|rmvpe|pretrained…、VBCABLE/\n"
    )


def full_package_policy_help() -> str:
    return (
        "全量包 = 完整发行目录或压缩包（含 Runtime、exe、资源）。\n"
        "软件内策略：仅提供下载/打开链接，不自动解压覆盖当前安装。\n"
        "用户应：下载 → 解压到新目录 → 使用新目录内启动器；或按说明覆盖。\n"
        "完整包渠道：SharePoint 直链 或 QQ 群（软件外）。\n"
    )


def tm_package_template(package_type: str, **extra: Any) -> dict[str, Any]:
    t = normalize_package_type(package_type)
    base: dict[str, Any] = {
        "schema": 1,
        "package_type": t,
        "format_version": 1,
        "name": extra.get("name") or "",
        "version": extra.get("version") or "",
        "min_app_version": extra.get("min_app_version") or "",
        "notes": extra.get("notes") or "",
    }
    if t == PKG_GUI_PATCH:
        base["applies"] = "merge_allowlist"
        base["description"] = "Incremental shell/GUI patch for in-app apply"
    elif t == PKG_FULL:
        base["applies"] = "external_only"
        base["description"] = "Full product with Runtime — do not in-app merge"
    elif t in (PKG_VOICE_PACK, PKG_VOICE_FILES):
        base["applies"] = "install_to_user_data_models"
        base["voice_id"] = extra.get("voice_id") or extra.get("id") or ""
        base["tag"] = extra.get("tag") or "音色"
        base["name"] = extra.get("name") or ""
        base["author"] = extra.get("author") or ""
        base["author_url"] = extra.get("author_url") or ""
        base["date"] = normalize_yymmdd(extra.get("date") or "") or ""
        base["cover"] = extra.get("cover") or "cover.jpg"
        # Official publisher stamp — clients read this without network
        base["publisher"] = extra.get("publisher") or "rvc_fabric"
        base["fabric_official"] = (
            True
            if extra.get("fabric_official") is None
            else bool(extra.get("fabric_official"))
        )
    base.update({k: v for k, v in extra.items() if k not in base})
    return base
