# -*- coding: utf-8 -*-
"""Remote / bundled online catalog (app update + voice library + community links)."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from launcher.paths import ROOT, USER_DATA
from launcher.version import (
    APP_CHANNEL,
    APP_VERSION,
    compare_versions,
    display_version,
)

BUNDLED_CATALOG = ROOT / "configs" / "online_catalog.json"
CACHE_PATH = USER_DATA / "update_cache" / "catalog.json"
STATE_PATH = USER_DATA / "update_state.json"

# Canonical remote index (CNB-GIT-RELEASE/index.json)
DEFAULT_MANIFEST_URLS: list[str] = [
    "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/git/raw/main/index.json",
]
CNB_RAW_MAIN = "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/git/raw/main"


def _safe_int(value: Any, default: int = 0) -> int:
    """Parse size/count fields without raising (bad JSON must not drop the entry)."""
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


@dataclass
class VoiceEntry:
    id: str
    name: str
    tag: str = "音色"
    version: str = "1"
    package_type: str = ""  # voice_pack | voice_files (auto if empty)
    pack_url: str = ""  # zip 音色包直链
    pth_url: str = ""
    index_url: str = ""
    cover_url: str = ""
    size_bytes: int = 0
    sha256: str = ""
    description: str = ""
    author: str = ""
    author_url: str = ""
    date: str = ""  # YYMMDD（与 index.json released 同义）
    series: str = ""  # 系列包名（Mygo / VOCALOID …）；空 = 单品音色
    # 第三方源字段（图灵镜源保持默认：origin 空、official True）
    origin: str = ""  # huggingface / 预留其它；空 = 图灵镜源
    source_url: str = ""  # 溯源页（社区站点仓库页）
    official: bool = True  # False = 第三方，永不带官方章
    popularity: int = 0  # 可选快照（如社区站下载量）；本期 UI 不用

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "VoiceEntry":
        from launcher.online.package_spec import normalize_yymmdd

        cover = str(
            d.get("cover_url") or d.get("cover") or d.get("banner") or ""
        ).strip()
        if cover and not cover.lower().startswith(("http://", "https://")):
            cover = f"{CNB_RAW_MAIN}/{cover.replace(chr(92), '/').lstrip('/')}"
        date = normalize_yymmdd(
            d.get("date")
            or d.get("released")
            or d.get("yymmdd")
            or d.get("release_date")
            or ""
        )
        # author：勿把 publisher: community/rvc_fabric 误当成展示作者
        author_raw = d.get("author") or d.get("creator") or ""
        if not author_raw and d.get("publisher") not in (
            None,
            "",
            "community",
            "rvc_fabric",
            "user",
        ):
            author_raw = d.get("publisher")
        pop = (
            d.get("hf_downloads")
            if d.get("hf_downloads") is not None
            else d.get("downloads")
        )
        popularity = _safe_int(pop, 0)
        official_raw = d.get("official")
        if official_raw is None:
            official_raw = d.get("fabric_official")
        if official_raw is None:
            official = True
        elif isinstance(official_raw, bool):
            official = official_raw
        else:
            official = str(official_raw).strip().lower() not in (
                "0",
                "false",
                "no",
                "n",
                "",
            )
        # origin 只认 origin 键；勿用 source（安装通道字段 online_files 等会污染源徽标）
        origin = str(d.get("origin") or "").strip()
        # source_url：计划别名 source/repo_url，但 source 仅在像 URL 时采纳
        source_url = str(
            d.get("source_url") or d.get("repo_url") or d.get("page_url") or ""
        ).strip()
        if not source_url:
            maybe_src = str(d.get("source") or "").strip()
            if maybe_src.lower().startswith(("http://", "https://")):
                source_url = maybe_src
        # index_url：勿把裸 "index" 路径键与数值字段混淆；仅 http 或明确 index_url
        index_raw = d.get("index_url")
        if index_raw is None:
            idx = d.get("index")
            # 安装 config 里 index 常是本地路径；清单里才是 URL
            if isinstance(idx, str) and (
                idx.lower().startswith(("http://", "https://"))
                or idx.endswith(".index")
            ):
                index_raw = idx
            else:
                index_raw = ""
        return cls(
            id=str(d.get("id") or d.get("name") or "").strip(),
            name=str(d.get("name") or d.get("id") or "未命名").strip(),
            tag=str(d.get("tag") or "音色"),
            version=str(d.get("version") or date or "1"),
            package_type=str(
                d.get("package_type") or d.get("type") or d.get("kind") or ""
            ),
            pack_url=str(d.get("pack_url") or d.get("zip_url") or d.get("pack") or ""),
            pth_url=str(d.get("pth_url") or d.get("pth") or ""),
            index_url=str(index_raw or ""),
            cover_url=cover,
            size_bytes=_safe_int(
                (
                    d.get("size_bytes")
                    if d.get("size_bytes") is not None
                    else d.get("size")
                ),
                0,
            ),
            sha256=str(d.get("sha256") or ""),
            description=str(d.get("description") or d.get("desc") or ""),
            author=str(author_raw or "").strip(),
            author_url=str(d.get("author_url") or d.get("author_link") or "").strip(),
            date=date,
            series=str(
                d.get("series") or d.get("series_name") or d.get("collection") or ""
            ).strip(),
            origin=origin,
            source_url=source_url,
            official=bool(official),
            popularity=popularity,
        )

    def has_download(self) -> bool:
        return bool(self.pack_url or self.pth_url)


@dataclass
class GuiUpdate:
    version: str = ""
    url: str = ""
    sha256: str = ""
    notes: str = ""
    kind: str = "zip"  # archive format
    package_type: str = "gui_patch"  # gui_patch | full_package
    min_app_version: str = ""

    @classmethod
    def from_dict(cls, d: Optional[dict[str, Any]]) -> "GuiUpdate":
        d = d or {}
        return cls(
            version=str(d.get("version") or ""),
            url=str(d.get("url") or ""),
            sha256=str(d.get("sha256") or ""),
            notes=str(d.get("notes") or d.get("changelog") or ""),
            kind=str(d.get("kind") or "zip"),
            package_type=str(d.get("package_type") or d.get("type") or "gui_patch"),
            min_app_version=str(d.get("min_app_version") or ""),
        )


def _parse_voice_list(
    raw: Any, *, force_official: Optional[bool] = None
) -> list[VoiceEntry]:
    """Parse a list of voice dicts; optionally force official flag."""
    out: list[VoiceEntry] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            v = VoiceEntry.from_dict(item)
            if force_official is not None:
                v.official = force_official
            if v.id and v.has_download():
                out.append(v)
        except Exception:
            continue
    return out


def _voice_entry_to_dict(v: VoiceEntry) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": v.id,
        "name": v.name,
        "tag": v.tag,
        "version": v.version,
        "package_type": v.package_type,
        "pack_url": v.pack_url,
        "pth_url": v.pth_url,
        "index_url": v.index_url,
        "cover_url": v.cover_url,
        "size_bytes": v.size_bytes,
        "sha256": v.sha256,
        "description": v.description,
        "author": v.author,
        "author_url": v.author_url,
        "date": v.date,
        "released": v.date,
        "series": v.series,
    }
    if v.origin:
        d["origin"] = v.origin
    if v.source_url:
        d["source_url"] = v.source_url
    if not v.official:
        d["official"] = False
        d["publisher"] = "community"
    if v.popularity:
        d["hf_downloads"] = v.popularity
    return d


@dataclass
class OnlineCatalog:
    schema: int = 1
    app_version: str = ""
    channel: str = "stable"
    gui: GuiUpdate = field(default_factory=GuiUpdate)
    voices: list[VoiceEntry] = field(default_factory=list)
    thirdparty_voices: list[VoiceEntry] = field(default_factory=list)
    qq_group: str = ""
    qq_link: str = ""
    sharepoint_full: str = ""
    full_package_note: str = (
        "完整软件包（含 Runtime）请从 SharePoint 或 QQ 群下载；"
        "软件内仅更新 GUI 本体与音色模型。"
    )
    manifest_urls: list[str] = field(default_factory=list)
    source: str = "bundled"  # bundled | remote | merged | cache
    fetched_at: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)
    # Set when remote fetch failed / timed out (UI can show timeout hint)
    fetch_error: str = ""

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], *, source: str = "unknown"
    ) -> "OnlineCatalog":
        data = _normalize_index_payload(dict(data) if isinstance(data, dict) else {})
        app = data.get("app") if isinstance(data.get("app"), dict) else {}
        community = (
            data.get("community") if isinstance(data.get("community"), dict) else {}
        )
        gui_raw = (
            app.get("gui") if isinstance(app.get("gui"), dict) else data.get("gui")
        )
        voices = _parse_voice_list(data.get("voices") or data.get("models") or [])
        # 第三方列表：客户端强制 official=False（清单自称官方也不信）
        thirdparty = _parse_voice_list(
            data.get("thirdparty_voices") or data.get("third_party_voices") or [],
            force_official=False,
        )
        cat = cls(
            schema=int(data.get("schema") or 1),
            app_version=str(app.get("version") or data.get("version") or ""),
            channel=str(app.get("channel") or data.get("channel") or "stable"),
            gui=GuiUpdate.from_dict(gui_raw if isinstance(gui_raw, dict) else {}),
            voices=voices,
            thirdparty_voices=thirdparty,
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
                or data.get("note")
                or cls.full_package_note
            ),
            manifest_urls=list(data.get("manifest_urls") or DEFAULT_MANIFEST_URLS),
            source=source,
            fetched_at=time.time(),
            raw=data,
        )
        if not cat.gui.version and cat.app_version:
            cat.gui.version = cat.app_version
        return cat


def _normalize_index_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Accept CNB ``index.json`` (format=rvc_fabric_index) and classic catalogs.

    - packages.gui_patch / packages.setup → app.gui when gui url empty
    - packages named by released YYMMDD
    - voices cover relative paths resolved later in VoiceEntry
    """
    if not data:
        return data
    # Ensure manifest self-reference
    murls = list(data.get("manifest_urls") or [])
    primary = (
        "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/git/raw/main/index.json"
    )
    if primary not in murls:
        murls.insert(0, primary)
    data["manifest_urls"] = murls

    packages = data.get("packages") if isinstance(data.get("packages"), dict) else {}
    app = data.get("app") if isinstance(data.get("app"), dict) else {}
    gui = app.get("gui") if isinstance(app.get("gui"), dict) else {}
    if not gui.get("url"):
        # newest gui_patch by released / version
        patches = packages.get("gui_patch") or packages.get("gui") or []
        if isinstance(patches, list) and patches:
            best = _pick_latest_package(patches)
            if best:
                gui = dict(gui)
                gui.setdefault("package_type", "gui_patch")
                gui["version"] = str(
                    best.get("version")
                    or best.get("released")
                    or gui.get("version")
                    or ""
                )
                gui["url"] = str(best.get("url") or best.get("pack_url") or "")
                gui["sha256"] = str(best.get("sha256") or "")
                if best.get("notes"):
                    gui["notes"] = str(best.get("notes"))
                app = dict(app)
                app["gui"] = gui
                if best.get("version") and not app.get("version"):
                    app["version"] = str(best.get("version"))
                data["app"] = app
    # setup package → community full package hint
    setups = packages.get("setup") or []
    if isinstance(setups, list) and setups:
        best_s = _pick_latest_package(setups)
        community = (
            dict(data["community"]) if isinstance(data.get("community"), dict) else {}
        )
        if best_s and best_s.get("url") and not community.get("sharepoint_full"):
            community["sharepoint_full"] = str(best_s.get("url"))
            data["community"] = community
    return data


def _pick_latest_package(items: list[Any]) -> Optional[dict[str, Any]]:
    best: Optional[dict[str, Any]] = None
    best_key = ""
    for it in items:
        if not isinstance(it, dict):
            continue
        key = str(it.get("released") or it.get("version") or it.get("id") or "")
        if key >= best_key:
            best_key = key
            best = it
    return best


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
                "package_type": cat.gui.package_type,
                "min_app_version": cat.gui.min_app_version,
            },
        },
        "community": {
            "qq_group": cat.qq_group,
            "qq_link": cat.qq_link,
            "sharepoint_full": cat.sharepoint_full,
            "note": cat.full_package_note,
        },
        "voices": [_voice_entry_to_dict(v) for v in cat.voices],
        "thirdparty_voices": [_voice_entry_to_dict(v) for v in cat.thirdparty_voices],
        "manifest_urls": cat.manifest_urls or list(DEFAULT_MANIFEST_URLS),
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
    if remote.thirdparty_voices:
        out.thirdparty_voices = remote.thirdparty_voices
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
    timeout: int = 12,
    overall_timeout: Optional[float] = None,
) -> OnlineCatalog:
    """Fetch first successful remote catalog; fall back to bundled + cache.

    Catalog JSON is small (tens of KB). Uses ``fetch_bytes_simple`` (single GET,
    no multipart/Range probe) so a slow HEAD/Range path cannot stall the UI for
    minutes. ``timeout`` is per-URL socket budget; ``overall_timeout`` caps the
    whole candidate walk (default ≈ timeout + 3s, min 8s).
    """
    from launcher.online.downloader import DownloadError, fetch_bytes_simple

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

    per = max(3, int(timeout))
    # Wall-clock budget for the whole loop (all URLs + parse)
    if overall_timeout is None:
        overall = float(max(8, per + 3))
    else:
        overall = float(max(3.0, overall_timeout))
    deadline = time.monotonic() + overall

    last_err = ""
    for url in candidates:
        remain = deadline - time.monotonic()
        if remain <= 0.5:
            last_err = f"检查更新超时（{overall:.0f}s 内未拉到清单）"
            break
        try:
            raw = fetch_bytes_simple(url, timeout=min(float(per), remain))
            text = raw.decode("utf-8-sig")
            data = json.loads(text)
            if not isinstance(data, dict):
                raise DownloadError("清单不是 JSON 对象")
            remote = OnlineCatalog.from_dict(data, source="remote")
            remote.fetch_error = ""
            save_catalog_cache(remote)
            merged = merge_catalogs(bundled, remote)
            merged.fetch_error = ""
            return merged
        except Exception as e:
            last_err = str(e)
            continue

    if not last_err and time.monotonic() >= deadline:
        last_err = f"检查更新超时（{overall:.0f}s 内未拉到清单）"

    cached = load_cached_catalog()
    if cached and (cached.voices or cached.gui.url):
        cached.source = "cache"
        if last_err:
            cached.fetch_error = last_err
            cached.full_package_note = (
                f"{cached.full_package_note}\n（远程清单失败：{last_err}，使用缓存）"
            )
        out = merge_catalogs(bundled, cached)
        out.fetch_error = last_err
        out.source = "cache"
        return out

    if last_err:
        bundled.fetch_error = last_err
        bundled.full_package_note = (
            f"{bundled.full_package_note}\n（远程拉取失败：{last_err}）"
        )
    return bundled


def local_app_version() -> str:
    """Human-facing local shell version (e.g. ``1.2.3 热修1``)."""
    return display_version(APP_VERSION)


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


def group_voices_by_series(voices: list) -> list:
    """Group VoiceEntry list into [(series_name, [entries…]), …].

    - 无系列（series 为空）的音色合并在首组，组名 ""。
    - 系列组按首次出现顺序排列，组内保持清单顺序。
    """
    order: list[str] = []
    groups: dict[str, list] = {}
    for v in voices:
        key = str(getattr(v, "series", "") or "").strip()
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(v)
    # 空组（单品）永远排最前，其余按出现顺序
    if "" in order:
        order.remove("")
        order.insert(0, "")
    return [(k, groups[k]) for k in order]


def group_series_only(voices: list) -> list:
    """系列专区 grouping: like group_voices_by_series but drops the
    empty-series (单品) group. Order = first appearance in the list."""
    return [(s, g) for s, g in group_voices_by_series(voices) if s]


def filter_voices(voices: list, query: str) -> list:
    """Case-insensitive substring filter over id/name/tag/author/description/series."""
    q = (query or "").strip().lower()
    if not q:
        return list(voices)
    out = []
    for v in voices:
        blob = " ".join(
            [
                str(getattr(v, "id", "") or ""),
                str(getattr(v, "name", "") or ""),
                str(getattr(v, "tag", "") or ""),
                str(getattr(v, "author", "") or ""),
                str(getattr(v, "description", "") or ""),
                str(getattr(v, "series", "") or ""),
                str(getattr(v, "origin", "") or ""),
                origin_display(str(getattr(v, "origin", "") or "")),
            ]
        ).lower()
        if q in blob:
            out.append(v)
    return out


def sort_voices_newest_first(voices: list) -> list:
    """Newest-first copy: date (YYMMDD) desc; undated entries sink to the end.

    Stable sort keeps manifest order (date asc + id asc at build time) for
    equal dates, so same-day voices stay id-ascending.
    """
    return sorted(
        voices,
        key=lambda v: str(getattr(v, "date", "") or ""),
        reverse=True,
    )


def origin_display(origin: str) -> str:
    """短源名：空→图灵镜；huggingface→Hugging Face；其它原样。"""
    o = (origin or "").strip()
    if not o:
        return "图灵镜"
    key = o.lower().replace(" ", "").replace("_", "").replace("-", "")
    if key in ("huggingface", "hf", "huggingfaces"):
        return "Hugging Face"
    return o


def merged_latest(official: list, thirdparty: list) -> list:
    """双源合流后按日期降序；同日期时图灵镜源在前（stable + 官方先拼接）。"""
    # 同 date 时 sort 稳定：先 official 后 thirdparty 拼接，官方排前
    combined = list(official or []) + list(thirdparty or [])
    return sort_voices_newest_first(combined)


def paginate(items: list, page: int, per_page: int = 5) -> tuple:
    """Return (page_items, clamped_page, total_pages); page is 1-based.

    Empty list → ([], 1, 1). Out-of-range page clamps to [1, total_pages],
    so a shrunken list (search / refresh) never strands the view on a
    nonexistent page — callers must write the clamped page back.
    """
    per_page = max(1, int(per_page))
    total_pages = max(1, -(-len(items) // per_page))
    page = min(max(1, int(page)), total_pages)
    start = (page - 1) * per_page
    return items[start : start + per_page], page, total_pages


def is_voice_installed(voice_id: str, models_dir: Path) -> bool:
    d = Path(models_dir) / voice_id
    if not d.is_dir():
        # also match by name folder
        return False
    return any(d.glob("*.pth"))


# compare_versions lives in launcher.version (shell Full: X.Y.Z / X.Y.Z-hotfixN).
# Re-exported here so existing ``from launcher.online.catalog import compare_versions`` keeps working.


def re_split(v: str) -> list[str]:
    """Extract digit runs (legacy helper; prefer parse_version / compare_versions)."""
    import re

    return re.findall(r"\d+", v or "") or [v or "0"]
