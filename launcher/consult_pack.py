# -*- coding: utf-8 -*-
"""Consult pack (.zip) — paid tuning intake without gating knobs.

Users already self-tune and freely share ``.tmvp`` profiles. A *consult pack*
is an optional bundle for the team: environment + performance snapshot +
original / converted voice samples + profile + model identity (and optionally
model weight files). The product stays fully open; this path only packages
what support needs to tune for someone.

Pure stdlib (no Tk / torch) so packing is unit-tested offline.
"""

from __future__ import annotations

import json
import os
import platform
import re
import sys
import time
import zipfile
from typing import Any, Optional

from launcher import profiles as P

CONSULT_SCHEMA_VERSION = 1
CONSULT_KIND = "consult_pack"
CONSULT_DIRNAME = "consult_packs"
_KEEP_BUNDLES = 10

# Audio the user attaches (copied in; names normalized inside the zip).
AUDIO_EXTS = frozenset({".wav", ".mp3", ".flac", ".ogg", ".m4a"})

_FABRIC_SOURCES = frozenset({"online_pack", "online_files"})
# 社区/第三方安装通道 — 一律不当作 RVC Fabric 官方音色
_THIRDPARTY_SOURCES = frozenset(
    {"thirdparty_pack", "thirdparty_files", "community", "user_import"}
)
# Written into official packs / config.json so clients can recognize without network.
FABRIC_PUBLISHER = "rvc_fabric"
_FABRIC_PUBLISHER_ALIASES = frozenset(
    {
        "rvc_fabric",
        "rvc-fabric",
        "rvcf",
        "turing_mirror",
        "turing-mirror",
        "turingmirror",
    }
)

_README = """RVC Fabric 咨询包
================

把本 zip 发给团队即可（QQ / 邮件 / 网盘均可）。

包内内容
--------
- manifest.json     角色名、模型身份、是否含模型文件、档案说明
- env.json          本机环境摘要（系统 / Python / GPU 等）
- profile.tmvp      当前配置档案（音高、效果链、性能等）
- model_meta.json   音色身份信息（官方库有 online_id，便于团队定位）
- samples/          你的原声 + 变声后效果对照
- perf/             若有本机性能记录，会附带最新一份
- models/           仅当你勾选「包含模型文件」时才有 .pth / .index

说明
----
- 软件参数始终可自行调节与导入导出配置档案；咨询包只是方便团队帮你调参。
- 官方库音色默认只写身份信息，不必上传大模型文件。
- 本包不会自动上传，只保存在本机 User_Data/consult_packs/。
"""


class ConsultPackError(ValueError):
    """User-facing packing error (missing sample, missing model file, …)."""


# --------------------------------------------------------------------------
# json helpers
# --------------------------------------------------------------------------
def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json_str(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# model identity (combine pack mark + install source + catalog id match)
# --------------------------------------------------------------------------
def _truthy_flag(v: Any) -> bool:
    if v is True:
        return True
    if isinstance(v, (int, float)) and v == 1:
        return True
    s = str(v or "").strip().lower()
    return s in ("1", "true", "yes", "y", "official", "fabric")


def has_fabric_publisher_mark(side: Optional[dict]) -> bool:
    """JSON marks written by official pack / install (works offline)."""
    if not isinstance(side, dict):
        return False
    if _truthy_flag(side.get("fabric_official")) or _truthy_flag(
        side.get("is_rvc_fabric")
    ):
        return True
    pub = str(side.get("publisher") or side.get("provider") or "").strip().lower()
    return pub in _FABRIC_PUBLISHER_ALIASES


def load_fabric_catalog_ids() -> set[str]:
    """Voice ids from bundled + cached online catalog (CNB/Git remote after fetch).

    Matching a local ``online_id`` against this set is the second recognition
    path (list compare). Empty when catalog not configured yet.
    """
    ids: set[str] = set()
    try:
        from launcher.online.catalog import (
            load_bundled_catalog,
            load_cached_catalog,
        )

        for cat in (load_bundled_catalog(), load_cached_catalog()):
            if cat is None:
                continue
            for v in cat.voices or []:
                vid = str(getattr(v, "id", "") or "").strip()
                if vid and not vid.startswith("example-"):
                    ids.add(vid)
    except Exception:
        pass
    return ids


def _explicitly_not_official(side: dict) -> bool:
    """fabric_official 显式为假，或 publisher=community → 绝不当官方。"""
    fo = side.get("fabric_official")
    if fo is False:
        return True
    if isinstance(fo, (int, float)) and fo == 0:
        return True
    if str(fo or "").strip().lower() in ("0", "false", "no", "n"):
        return True
    pub = str(side.get("publisher") or side.get("provider") or "").strip().lower()
    if pub in ("community", "thirdparty", "third_party", "user"):
        return True
    src = str(side.get("source") or "").strip().lower()
    if src in _THIRDPARTY_SOURCES or src.startswith("thirdparty"):
        return True
    return False


def fabric_match_reasons(
    side: Optional[dict],
    *,
    catalog_ids: Optional[set[str]] = None,
) -> list[str]:
    """Why we treat this sidecar as Fabric official (may be empty = not official).

    人话：只有图灵镜源装的官方音色才算官方。社区音色即使写了 online_id，
    只要盖了「非官方」章或来自第三方通道，就绝不算官方。
    """
    if not isinstance(side, dict):
        return []
    # 一票否决：显式非官方 / 社区通道
    if _explicitly_not_official(side):
        return []
    reasons: list[str] = []
    if has_fabric_publisher_mark(side):
        reasons.append("publisher_mark")
    src = str(side.get("source") or "").strip().lower()
    if src in _FABRIC_SOURCES:
        reasons.append("install_source")
    oid = str(side.get("online_id") or "").strip()
    if oid:
        ids = catalog_ids if catalog_ids is not None else load_fabric_catalog_ids()
        if oid in ids:
            reasons.append("catalog_id_match")
        # 注意：仅有 online_id、不在官方清单里 → 不算官方（防第三方 tp-* 误判）
    return reasons


def is_fabric_model(
    side: Optional[dict],
    *,
    catalog_ids: Optional[set[str]] = None,
) -> bool:
    """True when the voice is treated as RVC Fabric official for consult packs.

    Recognition (any one is enough, unless explicitly non-official)::

      1. config.json mark: publisher=rvc_fabric | fabric_official=true
      2. installed from 图灵镜源: source online_pack|online_files
      3. online_id listed in official catalog voices[] (bundled + cache)

    Veto: fabric_official=false / publisher=community / thirdparty_* source.

    Official → consult pack defaults to *metadata only* (no large pth).
    """
    return bool(fabric_match_reasons(side, catalog_ids=catalog_ids))


def default_include_model_files(side: Optional[dict]) -> bool:
    """Fabric catalog voices default to metadata only; others also default off
    (user must opt in — large files + privacy)."""
    return False


def _find_pth(model_dir: str) -> Optional[str]:
    try:
        names = [n for n in os.listdir(model_dir) if n.lower().endswith(".pth")]
    except OSError:
        return None
    if not names:
        return None
    names.sort()
    return os.path.join(model_dir, names[0])


def _resolve_index_path(model_dir: str, side: dict) -> str:
    idx = str(side.get("index") or "").strip()
    if idx and os.path.isfile(idx):
        return idx
    try:
        for n in sorted(os.listdir(model_dir)):
            if n.lower().endswith(".index"):
                return os.path.join(model_dir, n)
    except OSError:
        pass
    return ""


def build_model_meta(model_dir: str, side: Optional[dict] = None) -> dict:
    """Identity record always written into the pack (never omitted)."""
    model_dir = os.path.abspath(str(model_dir))
    side = (
        side
        if isinstance(side, dict)
        else _read_json(os.path.join(model_dir, "config.json"))
    )
    pth = _find_pth(model_dir)
    file_name = str(side.get("file") or "")
    if not file_name and pth:
        file_name = os.path.basename(pth)
    index_path = _resolve_index_path(model_dir, side)
    reasons = fabric_match_reasons(side)
    return {
        "display_name": str(side.get("name") or os.path.basename(model_dir)),
        "folder_name": os.path.basename(model_dir),
        "file": file_name,
        "index_file": os.path.basename(index_path) if index_path else "",
        "index_path_present": bool(index_path),
        "source": str(side.get("source") or ""),
        "online_id": str(side.get("online_id") or ""),
        "publisher": str(side.get("publisher") or ""),
        "fabric_official": has_fabric_publisher_mark(side)
        or bool(side.get("fabric_official")),
        "tag": str(side.get("tag") or ""),
        "is_fabric_catalog": bool(reasons),
        "fabric_match": reasons,
        "model_dir_name": os.path.basename(model_dir),
    }


# --------------------------------------------------------------------------
# profile resolution
# --------------------------------------------------------------------------
def resolve_profile(
    model_dir: str,
    cfg: Optional[dict] = None,
    *,
    character_name: str = "",
) -> tuple[dict, str]:
    """Return (profile_dict, from_tag) where from_tag is 'active' | 'snapshot'."""
    model_dir = str(model_dir)
    active = P.resolve_active_profile(model_dir)
    if active is not None and not P.is_empty_profile(active):
        return active, "active"
    side = _read_json(os.path.join(model_dir, "config.json"))
    name = character_name or str(side.get("name") or os.path.basename(model_dir))
    snap_name = f"{name}-咨询快照"
    # Prefer live cfg; fall back to sidecar voice keys only
    base = dict(cfg or {})
    if not any(base.get(k) not in (None, "") for k in P.VOICE_KEYS):
        for k in P.VOICE_KEYS:
            if side.get(k) not in (None, ""):
                base[k] = side[k]
    prof = P.config_to_profile(
        base,
        snap_name,
        source="self",
        for_model=str(side.get("name") or name),
    )
    return prof, "snapshot"


# --------------------------------------------------------------------------
# env / perf (optional extras)
# --------------------------------------------------------------------------
def env_summary(root: str) -> dict:
    """Same spirit as tools.collect_diagnostics.env_summary (stdlib-safe)."""
    try:
        from tools.collect_diagnostics import env_summary as _env

        return _env(root)
    except Exception:
        pass
    info: dict[str, Any] = {
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "root": os.path.abspath(root),
        "root_ascii": all(ord(c) < 128 for c in os.path.abspath(root)),
    }
    try:
        import torch  # optional

        info["torch"] = str(torch.__version__)
        info["cuda_available"] = bool(torch.cuda.is_available())
        if info["cuda_available"]:
            info["gpu"] = torch.cuda.get_device_name(0)
    except Exception as e:
        info["torch"] = "unavailable: %s" % e
    return info


def _latest_perf_path(root: str) -> Optional[str]:
    d = os.path.join(root, "User_Data", "perf_reports")
    try:
        names = [
            n for n in os.listdir(d) if n.startswith("perf_") and n.endswith(".json")
        ]
    except OSError:
        return None
    if not names:
        return None
    names.sort(
        key=lambda n: os.path.getmtime(os.path.join(d, n)),
        reverse=True,
    )
    return os.path.join(d, names[0])


# --------------------------------------------------------------------------
# sample validation
# --------------------------------------------------------------------------
def _audio_ext(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext not in AUDIO_EXTS:
        raise ConsultPackError(
            "音频格式不支持：%s（请用 wav / mp3 / flac / ogg / m4a）" % ext
        )
    return ext


def _require_audio_file(path: str, label: str) -> str:
    path = os.path.abspath(str(path or ""))
    if not path or not os.path.isfile(path):
        raise ConsultPackError("请选择有效的%s文件。" % label)
    try:
        if os.path.getsize(path) <= 0:
            raise ConsultPackError("%s文件是空的。" % label)
    except OSError as e:
        raise ConsultPackError("无法读取%s：%s" % (label, e)) from e
    _audio_ext(path)
    return path


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------
def build_manifest(
    *,
    character_name: str,
    notes: str,
    model_meta: dict,
    include_model_files: bool,
    dry_arc: str,
    wet_arc: str,
    profile: dict,
    profile_from: str,
    app_version: str = "",
) -> dict:
    return {
        "schema_version": CONSULT_SCHEMA_VERSION,
        "kind": CONSULT_KIND,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "character_name": (character_name or "").strip()[:80] or "未命名角色",
        "notes": (notes or "").strip()[:2000],
        "model": {
            "display_name": model_meta.get("display_name") or "",
            "folder_name": model_meta.get("folder_name") or "",
            "file": model_meta.get("file") or "",
            "index_file": model_meta.get("index_file") or "",
            "source": model_meta.get("source") or "",
            "online_id": model_meta.get("online_id") or "",
            "publisher": model_meta.get("publisher") or "",
            "is_fabric_catalog": bool(model_meta.get("is_fabric_catalog")),
            "fabric_match": list(model_meta.get("fabric_match") or []),
            "tag": model_meta.get("tag") or "",
        },
        "include_model_files": bool(include_model_files),
        "samples": {"dry": dry_arc, "wet": wet_arc},
        "profile": {
            "id": str(profile.get("id") or ""),
            "name": str(profile.get("name") or ""),
            "from": profile_from,
        },
        "app_version": str(app_version or ""),
    }


# --------------------------------------------------------------------------
# pack
# --------------------------------------------------------------------------
def consult_out_dir(root: str) -> str:
    return os.path.join(root, "User_Data", CONSULT_DIRNAME)


def _model_files_to_include(model_dir: str, side: dict) -> list[tuple[str, str]]:
    """(arcname, abs_path) for pth + index under models/."""
    out: list[tuple[str, str]] = []
    pth = _find_pth(model_dir)
    if not pth or not os.path.isfile(pth):
        raise ConsultPackError("已勾选包含模型文件，但目录里找不到 .pth。")
    out.append(("models/" + os.path.basename(pth), pth))
    idx = _resolve_index_path(model_dir, side)
    if idx and os.path.isfile(idx):
        out.append(("models/" + os.path.basename(idx), idx))
    return out


def estimate_model_files_bytes(model_dir: str) -> int:
    """Rough size for UI confirm dialogs; 0 if no pth."""
    side = _read_json(os.path.join(model_dir, "config.json"))
    total = 0
    pth = _find_pth(model_dir)
    if pth and os.path.isfile(pth):
        try:
            total += os.path.getsize(pth)
        except OSError:
            pass
    idx = _resolve_index_path(model_dir, side)
    if idx and os.path.isfile(idx):
        try:
            total += os.path.getsize(idx)
        except OSError:
            pass
    return total


def pack_consult_zip(
    root: str,
    *,
    model_dir: str,
    character_name: str,
    dry_path: str,
    wet_path: str,
    include_model_files: bool = False,
    notes: str = "",
    cfg: Optional[dict] = None,
    app_version: str = "",
    out_dir: Optional[str] = None,
) -> str:
    """Build the consult zip; returns absolute path.

    Raises ConsultPackError on user-correctable problems.
    """
    root = os.path.abspath(str(root))
    model_dir = os.path.abspath(str(model_dir))
    if not os.path.isdir(model_dir):
        raise ConsultPackError("音色目录不存在。")

    dry = _require_audio_file(dry_path, "原声")
    wet = _require_audio_file(wet_path, "变声后效果")
    if os.path.normcase(dry) == os.path.normcase(wet):
        raise ConsultPackError("原声和变声后效果请使用两段不同的音频。")

    side = _read_json(os.path.join(model_dir, "config.json"))
    model_meta = build_model_meta(model_dir, side)
    prof, profile_from = resolve_profile(model_dir, cfg, character_name=character_name)
    dry_ext = _audio_ext(dry)
    wet_ext = _audio_ext(wet)
    dry_arc = "samples/dry_original" + dry_ext
    wet_arc = "samples/wet_converted" + wet_ext

    manifest = build_manifest(
        character_name=character_name,
        notes=notes,
        model_meta=model_meta,
        include_model_files=bool(include_model_files),
        dry_arc=dry_arc,
        wet_arc=wet_arc,
        profile=prof,
        profile_from=profile_from,
        app_version=app_version,
    )

    if out_dir is None:
        out_dir = consult_out_dir(root)
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    safe_char = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", manifest["character_name"])[:40]
    zip_name = "consult_%s_%s.zip" % (stamp, safe_char or "pack")
    zip_path = os.path.join(out_dir, zip_name)
    tmp_path = zip_path + ".tmp"

    extra_files: list[tuple[str, str]] = [(dry_arc, dry), (wet_arc, wet)]
    if include_model_files:
        extra_files.extend(_model_files_to_include(model_dir, side))

    perf = _latest_perf_path(root)
    if perf:
        extra_files.append(("perf/" + os.path.basename(perf), perf))

    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("README.txt", _README)
            zf.writestr("manifest.json", _write_json_str(manifest))
            zf.writestr("env.json", _write_json_str(env_summary(root)))
            zf.writestr("model_meta.json", _write_json_str(model_meta))
            zf.writestr("profile.tmvp", _write_json_str(prof))
            for arc, path in extra_files:
                try:
                    zf.write(path, arcname=arc)
                except OSError as e:
                    raise ConsultPackError("写入 %s 失败：%s" % (arc, e)) from e
        os.replace(tmp_path, zip_path)
    except ConsultPackError:
        try:
            if os.path.isfile(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise
    except Exception as e:
        try:
            if os.path.isfile(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise ConsultPackError("打包失败：%s" % e) from e

    _prune(out_dir)
    return zip_path


def _prune(dir_path: str, keep: int = _KEEP_BUNDLES) -> None:
    try:
        names = sorted(
            n
            for n in os.listdir(dir_path)
            if n.startswith("consult_") and n.endswith(".zip")
        )
        for n in names[:-keep]:
            try:
                os.remove(os.path.join(dir_path, n))
            except OSError:
                pass
    except OSError:
        pass
