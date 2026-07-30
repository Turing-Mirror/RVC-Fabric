# -*- coding: utf-8 -*-
"""Product shell version (GUI / launcher) and comparison helpers.

Not the RVC engine train version. Not Runtime / engine-core / voice pack versions.

Stable full versions (APP_VERSION / catalog gui.version)::

    X.Y.Z              formal baseline
    X.Y.Z-hotfixN      post-release OTA hotfixes (N >= 1)

See ``docs/在线更新与音色库.md`` § 壳层版本号规范.
"""

from __future__ import annotations

import re
from typing import NamedTuple, Optional

APP_VERSION: str = "1.2.3-hotfix2"
APP_CHANNEL: str = "stable"

# After this many hotfixes on one base, prefer shipping X.Y.(Z+1).
HOTFIX_SUGGEST_THRESHOLD: int = 5

# Stable channel Full: X.Y.Z or X.Y.Z-hotfixN (N >= 1). No -part / -build in the string.
_STABLE_FULL_RE = re.compile(
    r"^\s*(\d+)\.(\d+)\.(\d+)(?:-hotfix(\d+))?\s*$",
    re.IGNORECASE,
)
_HOTFIX_TAIL_RE = re.compile(r"-hotfix(\d+)\s*$", re.IGNORECASE)
_PART_TAIL_RE = re.compile(r"-part(\d+)\s*$", re.IGNORECASE)


class VersionParts(NamedTuple):
    """Parsed shell-ish version for ordering."""

    base: tuple[int, ...]
    kind: str  # "part" | "release" | "hotfix" | "other"
    rev: int


def parse_version(v: str) -> VersionParts:
    """Parse a version string for compare_versions.

    Known suffixes (case-insensitive, at end only)::

        -partN     historical prerelease — same base ranks **below** bare X.Y.Z
        -hotfixN   post-release OTA — same base ranks **above** bare X.Y.Z

    ``build`` is **not** a version suffix (use tm_package ``build_id`` metadata).
    """
    s = str(v or "").strip()
    if not s:
        return VersionParts((0,), "release", 0)

    hotfix_m = _HOTFIX_TAIL_RE.search(s)
    part_m = _PART_TAIL_RE.search(s)

    if hotfix_m and (part_m is None or hotfix_m.start() >= part_m.start()):
        base_s = s[: hotfix_m.start()]
        kind = "hotfix"
        rev = int(hotfix_m.group(1))
    elif part_m:
        base_s = s[: part_m.start()]
        kind = "part"
        rev = int(part_m.group(1))
    else:
        base_s = s
        kind = "release"
        rev = 0

    base_digits = [int(x) for x in re.findall(r"\d+", base_s)] or [0]

    # Unknown letter suffixes (e.g. 1.0.0-rc1): fall back to all digits in full string.
    if kind == "release" and re.search(r"[A-Za-z_]", base_s):
        all_digits = [int(x) for x in re.findall(r"\d+", s)] or [0]
        return VersionParts(tuple(all_digits), "other", 0)

    return VersionParts(tuple(base_digits), kind, rev)


def compare_versions(a: str, b: str) -> int:
    """Return -1 if a<b, 0 if equal, 1 if a>b.

    Ordering (same numeric base)::

        X.Y.Z-partN  <  X.Y.Z  <  X.Y.Z-hotfix1  <  X.Y.Z-hotfix2  <  X.Y.(Z+1)

    **Legacy -partN trap** (old digit-only clients): ``1.1.2-part1`` looked newer
    than ``1.1.2``. Do not ship new ``-partN`` on stable. Unstick with a higher
    pure base (e.g. ``1.1.4``). Hotfixes use ``-hotfixN`` so digit-only clients
    still see ``1.2.3-hotfix1`` > ``1.2.3``.
    """
    pa, pb = parse_version(a), parse_version(b)
    n = max(len(pa.base), len(pb.base))
    ba = pa.base + (0,) * (n - len(pa.base))
    bb = pb.base + (0,) * (n - len(pb.base))
    if ba < bb:
        return -1
    if ba > bb:
        return 1

    # Same base: part < release/other < hotfix; then rev ascending.
    rank = {"part": 0, "release": 1, "other": 1, "hotfix": 2}
    ra = rank.get(pa.kind, 1)
    rb = rank.get(pb.kind, 1)
    if ra < rb:
        return -1
    if ra > rb:
        return 1
    if pa.rev < pb.rev:
        return -1
    if pa.rev > pb.rev:
        return 1
    return 0


def base_version(v: str) -> str:
    """Marketing / title base ``X.Y.Z`` (first three numeric base components)."""
    p = parse_version(v)
    d = list(p.base[:3]) if p.base else [0]
    while len(d) < 3:
        d.append(0)
    return f"{d[0]}.{d[1]}.{d[2]}"


def hotfix_revision(v: str) -> int:
    """Hotfix N, or 0 if not a hotfix full version."""
    p = parse_version(v)
    return p.rev if p.kind == "hotfix" else 0


def display_version(v: str) -> str:
    """Human-facing Chinese label: ``1.2.3`` or ``1.2.3 热修2``."""
    p = parse_version(v)
    base = base_version(v)
    if p.kind == "hotfix" and p.rev > 0:
        return f"{base} 热修{p.rev}"
    if p.kind == "part" and p.rev > 0:
        return f"{base} 预发布{p.rev}"
    return base


def is_stable_shell_version(v: str) -> bool:
    """True if ``v`` is allowed as stable APP_VERSION / catalog gui.version."""
    m = _STABLE_FULL_RE.match(str(v or ""))
    if not m:
        return False
    if m.group(4) is not None and int(m.group(4)) < 1:
        return False
    return True


def validate_stable_shell_version(v: str) -> str:
    """Normalize a stable full version or raise ValueError."""
    raw = str(v or "").strip()
    m = _STABLE_FULL_RE.match(raw)
    if not m:
        raise ValueError(
            f"稳定通道版本必须是 X.Y.Z 或 X.Y.Z-hotfixN（N≥1），收到: {raw!r}。"
            "不要使用 -partN / -buildN；build 请写入 tm_package.build_id。"
        )
    x, y, z = int(m.group(1)), int(m.group(2)), int(m.group(3))
    hf = m.group(4)
    if hf is not None:
        n = int(hf)
        if n < 1:
            raise ValueError("hotfix 序号 N 必须 ≥ 1")
        return f"{x}.{y}.{z}-hotfix{n}"
    return f"{x}.{y}.{z}"


def should_suggest_base_bump(v: str) -> bool:
    """True when hotfix count on this base reached the soft threshold."""
    return hotfix_revision(v) >= HOTFIX_SUGGEST_THRESHOLD


def next_hotfix_version(v: str) -> str:
    """Suggest next Full after ``v`` (for tooling / docs examples)."""
    p = parse_version(v)
    base = base_version(v)
    if p.kind == "hotfix":
        return f"{base}-hotfix{p.rev + 1}"
    return f"{base}-hotfix1"
