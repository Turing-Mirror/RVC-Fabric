# -*- coding: utf-8 -*-
"""Shell release changelog feed — Tk-free core.

Source of truth on the maintainer side: ``catalog-src/changelog.yaml`` →
CNB root ``changelog.json`` (via ``scripts/build_catalog.py``).

Client contract:

- Independent of ``index.json`` and ``plaza.json`` (fetch failure never
  blocks the main app or plaza news).
- Stable versions only: ``X.Y.Z`` / ``X.Y.Z-hotfixN`` (see launcher.version).
- Sorted newest-first by ``compare_versions``.
- Shell-import safe: no numpy/torch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from launcher.online.catalog import CNB_RAW_MAIN
from launcher.paths import USER_DATA
from launcher.version import (
    compare_versions,
    display_version,
    is_stable_shell_version,
)

CHANGELOG_FEED_URL = f"{CNB_RAW_MAIN}/changelog.json"
CACHE_PATH = USER_DATA / "update_cache" / "changelog.json"


@dataclass
class ChangelogEntry:
    version: str
    date: str = ""  # YYMMDD
    title: str = ""
    highlights: list[str] = field(default_factory=list)
    body: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def display_title(self) -> str:
        t = (self.title or "").strip()
        if t:
            return t
        return display_version(self.version)

    @property
    def summary(self) -> str:
        """One short block for the plaza teaser card."""
        if self.highlights:
            return "\n".join(f"· {h}" for h in self.highlights if str(h).strip())
        body = (self.body or "").strip()
        if len(body) > 220:
            return body[:220] + "……"
        return body

    @property
    def detail_text(self) -> str:
        """Full text for the changelog detail page."""
        parts: list[str] = []
        if self.highlights:
            parts.append("\n".join(f"· {h}" for h in self.highlights if str(h).strip()))
        body = (self.body or "").strip()
        if body:
            parts.append(body)
        return "\n\n".join(p for p in parts if p).strip()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Optional["ChangelogEntry"]:
        if not isinstance(d, dict):
            return None
        version = str(d.get("version") or d.get("ver") or "").strip()
        if not version or not is_stable_shell_version(version):
            return None
        from launcher.online.package_spec import normalize_yymmdd

        hl_raw = d.get("highlights") or d.get("bullets") or []
        highlights: list[str] = []
        if isinstance(hl_raw, str) and hl_raw.strip():
            highlights = [hl_raw.strip()]
        elif isinstance(hl_raw, list):
            for x in hl_raw:
                s = str(x or "").strip()
                if s:
                    highlights.append(s)
        body = str(d.get("body") or d.get("notes") or d.get("text") or "").strip()
        if not body and not highlights:
            return None
        title = str(d.get("title") or "").strip()
        return cls(
            version=version,
            date=normalize_yymmdd(d.get("date") or d.get("released") or "") or "",
            title=title,
            highlights=highlights,
            body=body,
            raw=dict(d),
        )


def parse_changelog(data: Any) -> list[ChangelogEntry]:
    """Parse changelog payload (dict with ``entries`` or a bare list)."""
    if isinstance(data, dict):
        rows = data.get("entries") or data.get("items") or []
    elif isinstance(data, list):
        rows = data
    else:
        return []
    out: list[ChangelogEntry] = []
    seen: set[str] = set()
    for row in rows:
        try:
            ent = ChangelogEntry.from_dict(row) if isinstance(row, dict) else None
        except Exception:
            ent = None
        if ent is None or ent.version in seen:
            continue
        seen.add(ent.version)
        out.append(ent)
    return sort_entries(out)


def sort_entries(entries: Iterable[ChangelogEntry]) -> list[ChangelogEntry]:
    """Newest Full version first; date as weak tie-break."""
    from functools import cmp_to_key

    def _cmp(a: ChangelogEntry, b: ChangelogEntry) -> int:
        c = compare_versions(a.version, b.version)
        if c != 0:
            return -c  # newest first
        da, db = a.date or "", b.date or ""
        if da != db:
            return (da < db) - (da > db)  # newer date first
        return 0

    return sorted(list(entries), key=cmp_to_key(_cmp))


def latest_entry(entries: Iterable[ChangelogEntry]) -> Optional[ChangelogEntry]:
    rows = sort_entries(entries)
    return rows[0] if rows else None


def notes_from_entry(entry: ChangelogEntry) -> str:
    """Text for catalog ``gui.notes`` (single-source from changelog)."""
    body = (entry.body or "").strip()
    if body:
        return body
    if entry.highlights:
        return "；".join(str(h).strip() for h in entry.highlights if str(h).strip())
    return ""


def feed_stamp(entries: Iterable[ChangelogEntry]) -> str:
    """Render invalidation stamp covering all visible fields."""
    parts: list[str] = []
    for e in entries:
        parts.append(
            "|".join(
                [
                    e.version,
                    e.date,
                    e.title,
                    "\n".join(e.highlights),
                    e.body[:80],
                ]
            )
        )
    return "\x1f".join(parts)


def load_cached_changelog() -> list[ChangelogEntry]:
    try:
        if not CACHE_PATH.is_file():
            return []
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return parse_changelog(data)
    except Exception:
        return []


def save_cache(payload: Any) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, (dict, list)):
            text = json.dumps(payload, ensure_ascii=False, indent=2)
        else:
            text = str(payload)
        CACHE_PATH.write_text(text + "\n", encoding="utf-8")
    except Exception:
        pass


def fetch_changelog(
    *,
    url: str = "",
    timeout: float = 12.0,
) -> tuple[list[ChangelogEntry], str]:
    """Fetch remote changelog; fall back to disk cache.

    Returns (entries, source) where source is ``remote`` | ``cache`` | ``none``.
    Never raises.
    """
    feed_url = (url or CHANGELOG_FEED_URL).strip()
    try:
        from launcher.online.downloader import fetch_bytes_simple

        raw = fetch_bytes_simple(feed_url, timeout=timeout)
        data = json.loads(raw.decode("utf-8"))
        entries = parse_changelog(data)
        if entries:
            save_cache(data if isinstance(data, (dict, list)) else {"entries": []})
            return entries, "remote"
        # Empty remote still overwrites? Keep cache if remote empty list intentional
        save_cache(data if isinstance(data, (dict, list)) else {"schema": 1, "entries": []})
        return entries, "remote"
    except Exception:
        pass
    cached = load_cached_changelog()
    if cached:
        return cached, "cache"
    return [], "none"
