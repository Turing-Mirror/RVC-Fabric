# -*- coding: utf-8 -*-
"""广场 content feed (news / notices / sponsor cards) — Tk-free core.

Feed 与发版清单解耦：``plaza.json`` 独立于 ``index.json``，运营改内容不发版。
由 ``scripts/build_catalog.py`` 从 ``catalog-src/plaza.yaml`` 编译并回环校验。

客户端契约（向前兼容的关键）：

- 未知 ``type`` / 未知字段静默忽略——新增卡片类型只需新 feed + 新客户端，
  旧客户端不炸不乱。
- 图片仅允许 CNB 仓内相对路径或 cnb.cool https 直链（供应链可控，不给
  外部图床/跟踪像素开口）。图片落盘缓存 ``update_cache/plaza_covers/``。
- 点击 / 展示统一收敛在 :func:`on_card_clicked` / :func:`mark_seen` ——
  未来若上曝光统计，只动这两个函数；上报端点必须硬编码在代码里，
  feed 永远无权指定任何上报 URL（防 feed 被劫持后驱动装机量发请求）。
- 广告可识别：``ad`` / ``sponsor`` 类型强制可关闭，UI 侧必须带「广告」角标。
- 关闭语义：按 ``id`` 永久关闭（存 ``app_config``）；运营想重新曝光就换新 id。

Shell-import 安全：本模块只用标准库 + launcher 纯逻辑模块，绝不引入
numpy / torch 依赖链（PyInstaller 壳没有这些，顶层导入会闪退）。
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from launcher.online.catalog import CNB_RAW_MAIN, compare_versions
from launcher.paths import USER_DATA
from launcher.version import APP_VERSION

# 独立于 index.json：广场内容更新不触发/不依赖发版清单
PLAZA_FEED_URL = f"{CNB_RAW_MAIN}/plaza.json"
CACHE_PATH = USER_DATA / "update_cache" / "plaza.json"
IMAGE_CACHE_DIR = USER_DATA / "update_cache" / "plaza_covers"

# 渲染器认识的卡片类型；不在此列的条目整条忽略（向前兼容开口）
KNOWN_TYPES = ("news", "notice", "banner", "ad", "sponsor")
AD_TYPES = ("ad", "sponsor")

PLACEMENT_PLAZA = "plaza"
PLACEMENT_MODELS = "models_page"

# 已读 / 已关闭列表的上限——防 cfg 无限膨胀
_CFG_LIST_CAP = 200

_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


@dataclass
class PlazaItem:
    id: str
    type: str = "news"  # news | notice | banner | ad | sponsor
    title: str = ""
    body: str = ""
    image_url: str = ""  # resolved https URL (CNB only) or ""
    url: str = ""  # click-through；仅 http/https
    action_label: str = ""
    date: str = ""  # YYMMDD
    priority: int = 0
    pinned: bool = False
    dismissible: bool = False  # ad/sponsor 强制 True
    placements: list[str] = field(default_factory=lambda: [PLACEMENT_PLAZA])
    start: str = ""  # 投放窗口 YYMMDD（含当天）；空 = 不限
    end: str = ""
    min_app_version: str = ""
    max_app_version: str = ""
    sponsor: str = ""  # 广告主名；非空 → UI 必须显示「广告」角标
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_ad(self) -> bool:
        return self.type in AD_TYPES or bool(self.sponsor)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Optional["PlazaItem"]:
        """Tolerant parse; None when the entry is unusable (no id/title)."""
        if not isinstance(d, dict):
            return None
        item_id = str(d.get("id") or "").strip()
        title = str(d.get("title") or "").strip()
        if not item_id or not title:
            return None
        from launcher.online.package_spec import normalize_yymmdd

        typ = str(d.get("type") or d.get("kind") or "news").strip().lower()
        placements = d.get("placements") or d.get("placement") or [PLACEMENT_PLAZA]
        if isinstance(placements, str):
            placements = [placements]
        if not isinstance(placements, list):
            placements = [PLACEMENT_PLAZA]
        placements = [str(p).strip() for p in placements if str(p).strip()]
        if not placements:
            placements = [PLACEMENT_PLAZA]
        try:
            priority = int(d.get("priority") or d.get("weight") or 0)
        except (TypeError, ValueError):
            priority = 0
        dismissible = bool(d.get("dismissible", False))
        sponsor = str(d.get("sponsor") or d.get("advertiser") or "").strip()
        if typ in AD_TYPES or sponsor:
            # 广告必须可关闭——产品承诺，feed 无权关掉这个开关
            dismissible = True
        return cls(
            id=item_id,
            type=typ,
            title=title,
            body=str(d.get("body") or d.get("text") or d.get("desc") or "").strip(),
            image_url=_resolve_image_url(
                str(d.get("image") or d.get("image_url") or d.get("cover") or "")
            ),
            url=_safe_link(str(d.get("url") or d.get("link") or "")),
            action_label=str(d.get("action_label") or d.get("action") or "").strip(),
            date=normalize_yymmdd(d.get("date") or d.get("released") or ""),
            priority=priority,
            pinned=bool(d.get("pinned", False)),
            dismissible=dismissible,
            placements=placements,
            start=normalize_yymmdd(d.get("start") or ""),
            end=normalize_yymmdd(d.get("end") or ""),
            min_app_version=str(d.get("min_app_version") or "").strip(),
            max_app_version=str(d.get("max_app_version") or "").strip(),
            sponsor=sponsor,
            raw=dict(d),
        )


def _safe_link(url: str) -> str:
    """Click-through URLs are http/https only; anything else is dropped."""
    u = (url or "").strip()
    if u.lower().startswith(("http://", "https://")):
        return u
    return ""


def _resolve_image_url(image: str) -> str:
    """CNB-only image policy: relative path → raw URL; foreign hosts dropped."""
    s = (image or "").strip()
    if not s:
        return ""
    if s.lower().startswith(("http://", "https://")):
        try:
            from urllib.parse import urlparse

            host = (urlparse(s).hostname or "").lower()
        except Exception:
            return ""
        if host == "cnb.cool" or host.endswith(".cnb.cool"):
            return s
        return ""  # 外部图床不允许——供应链可控
    return f"{CNB_RAW_MAIN}/{s.replace(chr(92), '/').lstrip('/')}"


def parse_feed(data: Any) -> list[PlazaItem]:
    """Parse a plaza feed payload (dict with ``items`` or a bare list)."""
    if isinstance(data, dict):
        rows = data.get("items") or []
    elif isinstance(data, list):
        rows = data
    else:
        return []
    out: list[PlazaItem] = []
    seen: set[str] = set()
    for row in rows:
        try:
            item = PlazaItem.from_dict(row)
        except Exception:
            item = None
        if item is None or item.id in seen:
            continue
        seen.add(item.id)
        out.append(item)
    return out


def today_yymmdd() -> str:
    return time.strftime("%y%m%d", time.localtime())


def visible_items(
    items: Iterable[PlazaItem],
    placement: str = PLACEMENT_PLAZA,
    *,
    app_version: str = "",
    today: str = "",
    dismissed: Iterable[str] = (),
) -> list[PlazaItem]:
    """Filter + order for one placement.

    未知类型剔除；投放窗口按本地日期（YYMMDD 字符串比较）；版本门槛用
    compare_versions（含 -partN 语义）；已关闭 id 只对 dismissible 条目生效。
    排序：pinned 置顶 → priority 降序 → date 新在前 → id 升序（确定性）。
    """
    ver = app_version or APP_VERSION
    day = today or today_yymmdd()
    hidden = set(dismissed or ())
    out: list[PlazaItem] = []
    for it in items:
        if it.type not in KNOWN_TYPES:
            continue
        if placement not in it.placements:
            continue
        if it.start and day < it.start:
            continue
        if it.end and day > it.end:
            continue
        try:
            if it.min_app_version and compare_versions(ver, it.min_app_version) < 0:
                continue
            if it.max_app_version and compare_versions(ver, it.max_app_version) > 0:
                continue
        except Exception:
            pass
        if it.dismissible and it.id in hidden:
            continue
        out.append(it)
    out.sort(key=lambda i: (not i.pinned, -i.priority, _date_desc(i.date), i.id))
    return out


def _date_desc(date: str) -> str:
    """Sort helper: newest date first inside an ascending tuple sort."""
    if not date:
        return "999999"  # undated sinks below any real date
    # YYMMDD digits map 0↔9 so lexicographic asc == date desc
    return "".join(chr(ord("9") - ord(c) + ord("0")) for c in date)


def pick_models_banner(
    items: Iterable[PlazaItem],
    *,
    app_version: str = "",
    today: str = "",
    dismissed: Iterable[str] = (),
) -> Optional[PlazaItem]:
    """模型页横幅：至多一条，且必须可关闭（不可关闭的条目没资格上模型页）。"""
    for it in visible_items(
        items,
        PLACEMENT_MODELS,
        app_version=app_version,
        today=today,
        dismissed=dismissed,
    ):
        if it.dismissible:
            return it
    return None


def unread_ids(
    items: Iterable[PlazaItem],
    seen: Iterable[str],
    *,
    app_version: str = "",
    today: str = "",
    dismissed: Iterable[str] = (),
) -> list[str]:
    """广场页当前可见、且未读的 id（驱动导航「广场·新」角标）。"""
    seen_set = set(seen or ())
    return [
        it.id
        for it in visible_items(
            items,
            PLACEMENT_PLAZA,
            app_version=app_version,
            today=today,
            dismissed=dismissed,
        )
        if it.id not in seen_set
    ]


def feed_stamp(items: Iterable[PlazaItem]) -> tuple:
    """Equality snapshot of feed content — render-snapshot short-circuiting.

    必须覆盖所有影响渲染的字段：漏掉任何一个（如 body/url/type），运营
    原地修改该字段后客户端的快照短路就会把新内容当旧内容，整会话陈旧。
    """
    return tuple(
        sorted(
            (
                i.id,
                i.type,
                i.title,
                i.body,
                i.image_url,
                i.url,
                i.action_label,
                i.date,
                i.priority,
                i.pinned,
                i.dismissible,
                i.sponsor,
                tuple(i.placements),
            )
            for i in items
        )
    )


# ------------------------------------------------------------------ feed IO


def load_cached_feed() -> list[PlazaItem]:
    if not CACHE_PATH.is_file():
        return []
    try:
        return parse_feed(json.loads(CACHE_PATH.read_text(encoding="utf-8")))
    except Exception:
        return []


def fetch_feed(*, timeout: int = 20, url: str = "") -> tuple[list[PlazaItem], str]:
    """Fetch remote feed; fall back to disk cache. Returns (items, source).

    source: "remote" | "cache" | "none"。网络失败绝不抛——广场挂了不能
    影响主流程。必须在后台线程调用（会做网络 IO）。
    """
    from launcher.online.downloader import download_file

    tmp = CACHE_PATH.parent / "plaza_fetch.json"
    try:
        download_file(url or PLAZA_FEED_URL, tmp, timeout=timeout, retries=1)
        data = json.loads(tmp.read_text(encoding="utf-8"))
        items = parse_feed(data)
        try:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            CACHE_PATH.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
        return items, "remote"
    except Exception:
        cached = load_cached_feed()
        return (cached, "cache") if cached else ([], "none")


# ------------------------------------------------------------------ images


def image_cache_path(image_url: str) -> Path:
    """Stable on-disk path for a feed image (URL-keyed, extension kept)."""
    ext = Path(image_url.split("?")[0]).suffix.lower()
    if ext not in _IMAGE_EXTS:
        ext = ".jpg"
    digest = hashlib.sha1(image_url.encode("utf-8")).hexdigest()[:20]
    return IMAGE_CACHE_DIR / f"{digest}{ext}"


def ensure_image_cached(image_url: str, *, timeout: int = 20) -> Optional[Path]:
    """Download-once disk cache. Returns local path or None. Thread-only."""
    u = (image_url or "").strip()
    if not u:
        return None
    dest = image_cache_path(u)
    try:
        if dest.is_file() and dest.stat().st_size > 0:
            return dest
    except OSError:
        pass
    try:
        from launcher.online.downloader import download_file

        download_file(u, dest, timeout=timeout, retries=1)
        return dest if dest.is_file() and dest.stat().st_size > 0 else None
    except Exception:
        return None


# ------------------------------------------------------------ user actions
#
# 展示与点击的唯一入口。未来如需曝光统计（beacon），只改这里：
# 端点硬编码、payload 仅 {campaign_id, event}、每会话每条一次、
# fire-and-forget 不重试、设置页可关——feed 无权指定任何上报参数。


def on_card_clicked(item: PlazaItem) -> bool:
    """Open the card's link in the default browser. Returns success."""
    u = _safe_link(item.url)
    if not u:
        return False
    try:
        import webbrowser

        webbrowser.open(u)
        return True
    except Exception:
        return False


def seen_ids(cfg: dict) -> list[str]:
    v = cfg.get("plaza_seen_ids")
    return [str(x) for x in v] if isinstance(v, list) else []


def dismissed_ids(cfg: dict) -> list[str]:
    v = cfg.get("plaza_dismissed")
    return [str(x) for x in v] if isinstance(v, list) else []


def mark_seen(cfg: dict, ids: Iterable[str]) -> bool:
    """Merge ids into cfg['plaza_seen_ids'] (capped). True when changed."""
    cur = seen_ids(cfg)
    merged = list(cur)
    for i in ids or ():
        s = str(i)
        if s and s not in merged:
            merged.append(s)
    merged = merged[-_CFG_LIST_CAP:]
    if merged == cur:
        return False
    cfg["plaza_seen_ids"] = merged
    return True


def dismiss(cfg: dict, item_id: str) -> bool:
    """永久关闭一条（按 id）。True when newly dismissed."""
    s = str(item_id or "").strip()
    if not s:
        return False
    cur = dismissed_ids(cfg)
    if s in cur:
        return False
    cfg["plaza_dismissed"] = (cur + [s])[-_CFG_LIST_CAP:]
    return True
