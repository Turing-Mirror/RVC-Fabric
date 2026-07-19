# -*- coding: utf-8 -*-
"""Remote / bundled online catalog (app update + voice library + community links)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from launcher.paths import ROOT, USER_DATA
from launcher.version import APP_CHANNEL, APP_VERSION

BUNDLED_CATALOG = ROOT / "configs" / "online_catalog.json"
CACHE_PATH = USER_DATA / "update_cache" / "catalog.json"
STATE_PATH = USER_DATA / "update_state.json"

# Default remote (publisher can override in app_config / online_catalog.json)
# Prefer a public raw JSON or SharePoint-hosted catalog URL.
DEFAULT_MANIFEST_URLS: list[str] = []


@dataclass
class VoiceEntry:
    id: str
    name: str
    tag: str = "音色"
    version: str = "1"
    pth_url: str = ""
    index_url: str = ""
    cover_url: str = ""
    size_bytes: int = 0
    sha256: str = ""
    description: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "VoiceEntry":
        return cls(
            id=str(d.get("id") or d.get("name") or "").strip(),
            name=str(d.get("name") or d.get("id") or "未命名").strip(),
            tag=str(d.get("tag") or "音色"),
            version=str(d.get("version") or "1"),
            pth_url=str(d.get("pth_url") or d.get("pth") or d.get("url") or ""),
            index_url=str(d.get("index_url") or d.get("index") or ""),
            cover_url=str(d.get("cover_url") or d.get("cover") or ""),
            size_bytes=int(d.get("size_bytes") or d.get("size") or 0),
            sha256=str(d.get("sha256") or ""),
            description=str(d.get("description") or d.get("desc") or ""),
        )


@dataclass
class GuiUpdate:
    version: str = ""
    url: str = ""
    sha256: str = ""
    notes: str = ""
    kind: str = "zip"  # zip of relative paths under package root

    @classmethod
    def from_dict(cls, d: Optional[dict[str, Any]]) -> "GuiUpdate":
        d = d or {}
        return cls(
            version=str(d.get("version") or ""),
            url=str(d.get("url") or ""),
            sha256=str(d.get("sha256") or ""),
            notes=str(d.get("notes") or d.get("changelog") or ""),
            kind=str(d.get("kind") or "zip"),
        )


@dataclass
class OnlineCatalog:
    schema: int = 1
    app_version: str = ""
    channel: str = "stable"
    gui: GuiUpdate = field(default_factory=GuiUpdate)
    voices: list[VoiceEntry] = field(default_factory=list)
    qq_group: str = ""
    qq_link: str = ""
    sharepoint_full: str = ""
    full_package_note: str = (
        "完整软件包（含 Runtime）请从 SharePoint 或 QQ 群下载；"
        "软件内仅更新 GUI 本体与音色模型。"
    )
    manifest_urls: list[str] = field(default_factory=list)
    source: str = "bundled"  # bundled | remote | merged
    fetched_at: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str = "unknown") -> "OnlineCatalog":
        app = data.get("app") if isinstance(data.get("app"), dict) else {}
        community = (
            data.get("community") if isinstance(data.get("community"), dict) else {}
        )
        gui_raw = app.get("gui") if isinstance(app.get("gui"), dict) else data.get("gui")
        voices_raw = data.get("voices") or data.get("models") or []
        voices: list[VoiceEntry] = []
        if isinstance(voices_raw, list):
            for item in voices_raw:
                if isinstance(item, dict):
                    try:
                        v = VoiceEntry.from_dict(item)
                        if v.id and v.pth_url:
                            voices.append(v)
                    except Exception:
                        continue
        cat = cls(
            schema=int(data.get("schema") or 1),
            app_version=str(app.get("version") or data.get("version") or ""),
            channel=str(app.get("channel") or data.get("channel") or "stable"),
            gui=GuiUpdate.from_dict(gui_raw if isinstance(gui_raw, dict) else {}),
            voices=voices,
            qq_group=str(community.get("qq_group") or data.get("qq_group") or ""),
            qq_link=str(community.get("qq_link") or data.get("qq_link") or ""),
            sharepoint_full=str(
                community.get("sharepoint_full")
                or community.get("full_package")
                or data.get("sharepoint_full")
                or ""
            ),
            full_package_note=str(
                community.get("note")
                or data.get("full_package_note")
                or cls.full_package_note
            ),
            manifest_urls=list(data.get("manifest_urls") or []),
            source=source,
            fetched_at=time.time(),
            raw=data,
        )
        if not cat.gui.version and cat.app_version:
            cat.gui.version = cat.app_version
        return cat


def load_bundled_catalog() -> OnlineCatalog:
    if BUNDLED_CATALOG.is_file():
        try:
            data = json.loads(BUNDLED_CATALOG.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return OnlineCatalog.from_dict(data, source="bundled")
        except Exception:
            pass
    return OnlineCatalog(
        source="bundled",
        full_package_note=(
            "尚未配置在线清单。请编辑 configs/online_catalog.json，"
            "或在设置中填写清单 URL。"
        ),
    )


def load_cached_catalog() -> Optional[OnlineCatalog]:
    if not CACHE_PATH.is_file():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return OnlineCatalog.from_dict(data, source="cache")
    except Exception:
        return None
    return None


def save_catalog_cache(cat: OnlineCatalog) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = cat.raw if cat.raw else _catalog_to_dict(cat)
    CACHE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _catalog_to_dict(cat: OnlineCatalog) -> dict[str, Any]:
    return {
        "schema": cat.schema,
        "app": {
            "version": cat.app_version or cat.gui.version,
            "channel": cat.channel,
            "gui": {
                "version": cat.gui.version,
                "url": cat.gui.url,
                "sha256": cat.gui.sha256,
                "notes": cat.gui.notes,
                "kind": cat.gui.kind,
            },
        },
        "community": {
            "qq_group": cat.qq_group,
            "qq_link": cat.qq_link,
            "sharepoint_full": cat.sharepoint_full,
            "note": cat.full_package_note,
        },
        "voices": [
            {
                "id": v.id,
                "name": v.name,
                "tag": v.tag,
                "version": v.version,
                "pth_url": v.pth_url,
                "index_url": v.index_url,
                "cover_url": v.cover_url,
                "size_bytes": v.size_bytes,
                "sha256": v.sha256,
                "description": v.description,
            }
            for v in cat.voices
        ],
        "manifest_urls": cat.manifest_urls,
    }


def merge_catalogs(base: OnlineCatalog, remote: OnlineCatalog) -> OnlineCatalog:
    """Remote wins for fields that are non-empty; keep base voices if remote empty."""
    out = OnlineCatalog.from_dict(_catalog_to_dict(base), source="merged")
    if remote.app_version:
        out.app_version = remote.app_version
    if remote.gui.url or remote.gui.version:
        out.gui = remote.gui
    if remote.voices:
        out.voices = remote.voices
    if remote.qq_group:
        out.qq_group = remote.qq_group
    if remote.qq_link:
        out.qq_link = remote.qq_link
    if remote.sharepoint_full:
        out.sharepoint_full = remote.sharepoint_full
    if remote.full_package_note:
        out.full_package_note = remote.full_package_note
    out.source = "merged"
    out.fetched_at = remote.fetched_at or time.time()
    out.raw = remote.raw or base.raw
    return out


def fetch_catalog(
    urls: Optional[list[str]] = None,
    *,
    timeout: int = 30,
) -> OnlineCatalog:
    """Fetch first successful remote catalog; fall back to bundled + cache."""
    from launcher.online.downloader import DownloadError, download_file

    bundled = load_bundled_catalog()
    candidates: list[str] = []
    for u in urls or []:
        u = (u or "").strip()
        if u and u not in candidates:
            candidates.append(u)
    for u in bundled.manifest_urls or DEFAULT_MANIFEST_URLS:
        u = (u or "").strip()
        if u and u not in candidates:
            candidates.append(u)

    last_err = ""
    for url in candidates:
        try:
            tmp = USER_DATA / "update_cache" / "catalog_fetch.json"
            download_file(url, tmp, timeout=timeout)
            data = json.loads(tmp.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise DownloadError("清单不是 JSON 对象")
            remote = OnlineCatalog.from_dict(data, source="remote")
            save_catalog_cache(remote)
            return merge_catalogs(bundled, remote)
        except Exception as e:
            last_err = str(e)
            continue

    cached = load_cached_catalog()
    if cached and cached.voices:
        cached.source = "cache"
        if last_err:
            cached.full_package_note = (
                f"{cached.full_package_note}\n（远程清单失败：{last_err}，使用缓存）"
            )
        return merge_catalogs(bundled, cached)

    if last_err:
        bundled.full_package_note = (
            f"{bundled.full_package_note}\n（远程拉取失败：{last_err}）"
        )
    return bundled


def local_app_version() -> str:
    return APP_VERSION


def local_channel() -> str:
    return APP_CHANNEL


def load_update_state() -> dict[str, Any]:
    if STATE_PATH.is_file():
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save_update_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def is_voice_installed(voice_id: str, models_dir: Path) -> bool:
    d = Path(models_dir) / voice_id
    if not d.is_dir():
        # also match by name folder
        return False
    return any(d.glob("*.pth"))


def compare_versions(a: str, b: str) -> int:
    """Return -1 if a<b, 0 if equal, 1 if a>b. Non-semver → string compare."""
    def parts(v: str) -> list[int]:
        out: list[int] = []
        for p in re_split(v):
            try:
                out.append(int(p))
            except ValueError:
                out.append(0)
        return out or [0]

    pa, pb = parts(a), parts(b)
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    if pa < pb:
        return -1
    if pa > pb:
        return 1
    return 0


def re_split(v: str) -> list[str]:
    import re

    return re.findall(r"\d+", v or "") or [v or "0"]
