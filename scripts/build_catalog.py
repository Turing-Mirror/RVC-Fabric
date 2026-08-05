# -*- coding: utf-8 -*-
"""CNB 在线清单编译器 — YAML 源文件 → index / snippet / bundled / plaza / changelog.

维护者只改 ``CNB-GIT-RELEASE/catalog-src/`` 下的 YAML（每音色一个文件，
只写人话字段与制品相对路径）；sha256 / size_bytes / pack_url / cover_url /
sha256_urls 全部由本脚本从本地制品自动补全。JSON 产物为**生成物，禁止手改**::

    CNB-GIT-RELEASE/index.json                          主索引（schema 2）
    CNB-GIT-RELEASE/catalog/online_catalog.snippet.json 兼容清单（schema 1）
    configs/online_catalog.json                         app 内置兜底（schema 1）
    CNB-GIT-RELEASE/plaza.json                          广场 feed（独立管线）
    CNB-GIT-RELEASE/changelog.json                      壳层更新日志（独立管线）

广场 ``catalog-src/plaza.yaml``、更新日志 ``catalog-src/changelog.yaml`` 均可选。
有 changelog 条目时：最新条写入 ``app.gui.notes``；默认仍派生 plaza release 资讯。

用法（仓库根目录，宿主 Python，需 PyYAML）::

    python scripts/build_catalog.py init            # 一次性：从线上 index.json 反向生成 YAML 源
    python scripts/build_catalog.py check           # 只校验（契约 + 回环过真实客户端解析器）
    python scripts/build_catalog.py build --diff    # 校验 + 打印语义 diff + 写出产物

锁定值语义：YAML 里的 ``sha256`` / ``size_bytes`` = 已发布的线上真值；
与本地制品不一致时**警告并以锁定值为准**（--strict 升级为错误），
防止「本地重打包未发布」把索引改成用户下不到的哈希。
新条目不写锁定值，由本地制品自动填充。

客户端契约（勿破坏）见发布仓的 docs-发布流程.md / docs-发布规则.md 与本文件 _roundtrip_check。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlsplit, urlunsplit

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    import yaml
except ImportError:  # pragma: no cover
    print(
        "ERROR: 需要 PyYAML（仅维护机需要，客户端不用）。请先: pip install pyyaml",
        file=sys.stderr,
    )
    raise SystemExit(2)

CNB_HOST = "https://cnb.cool"
CNB_ORG_REPO = "Turing-Mirror/RVC-Fabric-Releases"
CNB_REPO_URL = f"{CNB_HOST}/{CNB_ORG_REPO}"
RAW = f"{CNB_REPO_URL}/-/git/raw/main"
LFS = f"{CNB_REPO_URL}/-/lfs"
# 封面所在的 Release tag。见 cnb_cover_url() 里为什么不能用 git raw。
COVER_TAG = "covers"
MANIFEST_URLS = [
    f"{RAW}/index.json",
    f"{RAW}/catalog/online_catalog.snippet.json",
]

VALID_VARIANTS = ("nvidia", "amd", "nvidia50")
VALID_CHANNELS = ("release", "lfs")


def default_cnb_dir() -> Path:
    """发布仓工作区的位置。

    优先级：环境变量 RVCF_CNB_DIR → 与产品仓同级的 RVC-Fabric-Release →
    仓内旧位置 CNB-GIT-RELEASE。

    发布仓现在独立放在产品仓旁边，不再塞进产品仓目录里。默认值写死成仓内路径
    的话，忘记加 --cnb 就会在产品源码仓里凭空长出一个 CNB-GIT-RELEASE，两个
    仓的内容混在一起。
    """
    env = os.environ.get("RVCF_CNB_DIR")
    if env:
        return Path(env).expanduser()
    sibling = REPO.parent / "RVC-Fabric-Release"
    if (sibling / ".git").exists():
        return sibling
    return REPO / "CNB-GIT-RELEASE"


class Paths:
    """所有输入/输出路径；测试可指向 tmpdir。"""

    def __init__(self, cnb: Path | None = None, bundled: Path | None = None) -> None:
        self.cnb = Path(cnb) if cnb else default_cnb_dir()
        self.src = self.cnb / "catalog-src"
        self.index_out = self.cnb / "index.json"
        self.plaza_out = self.cnb / "plaza.json"
        self.changelog_out = self.cnb / "changelog.json"
        self.snippet_out = self.cnb / "catalog" / "online_catalog.snippet.json"
        self.bundled_out = (
            Path(bundled) if bundled else REPO / "configs" / "online_catalog.json"
        )


# --------------------------------------------------------------------- utils



# ---------------------------------------------------------------------------
# 客户端解析器（Rust）——回环校验不再 import 已退役的 Python 壳
# ---------------------------------------------------------------------------

_CHECKER_CACHE: list[Path | None] = []


def _client_checker() -> Path | None:
    """Locate (or build) app/src-tauri catalog-check."""
    if _CHECKER_CACHE:
        return _CHECKER_CACHE[0]
    app = REPO / "app" / "src-tauri"
    exe = "catalog-check.exe" if os.name == "nt" else "catalog-check"
    for profile in ("release", "debug"):
        cand = app / "target" / profile / exe
        if cand.is_file():
            _CHECKER_CACHE.append(cand)
            return cand
    try:
        subprocess.check_call(
            ["cargo", "build", "--bin", "catalog-check"],
            cwd=str(app),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        _CHECKER_CACHE.append(None)
        return None
    cand = app / "target" / "debug" / exe
    _CHECKER_CACHE.append(cand if cand.is_file() else None)
    return _CHECKER_CACHE[0]


def _client_call(args: list[str], payload: dict | None = None) -> dict | None:
    """Run the client parser; None when it is unavailable."""
    exe = _client_checker()
    if not exe:
        return None
    try:
        out = subprocess.run(
            [str(exe), *args],
            input=json.dumps(payload) if payload is not None else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        if out.returncode != 0:
            return None
        return json.loads(out.stdout or "{}")
    except Exception:
        return None


def _client_compare_versions(a: str, b: str) -> int:
    r = _client_call(["version", a, b])
    if r is None:
        # Local fallback keeps `check` usable without a Rust toolchain.
        return _fallback_compare_versions(a, b)
    return int(r.get("cmp", 0))


def _fallback_compare_versions(a: str, b: str) -> int:
    def parse(v: str):
        v = (v or "").strip()
        core, _, rest = v.partition("-")
        tag = 0
        r = rest.lower()
        if r.startswith("hotfix"):
            tag = max(1, int(r[6:] or 1))
        elif r.startswith("part"):
            tag = -max(1, int(r[4:] or 1))
        nums = [int(x) for x in core.split(".")[:3] if x.isdigit()]
        while len(nums) < 3:
            nums.append(0)
        return (tuple(nums), tag)

    try:
        pa, pb = parse(a), parse(b)
    except Exception:
        return 0
    return (pa > pb) - (pa < pb)


def _is_stable_shell_version(v: str) -> bool:
    """Stable channel: plain X.Y.Z only (hotfix / part forms are retired)."""
    parts = (v or "").strip().split(".")
    return len(parts) == 3 and all(p.isdigit() for p in parts)


def read_lfs_pointer(path: Path) -> Optional[tuple[str, int]]:
    """Git LFS 指针里的 (sha256, size)；不是指针就返回 None。

    没跑过 `git lfs pull` 的克隆里，制品文件是一个一百来字节的指针文本，
    真身在 LFS 服务器上。直接 stat / sha256 这个文件，量到的是指针自己 ——
    Setup 的体积就会被写成 133 字节发出去，客户端下完校验必然对不上。

    指针文本里本来就写着真身的 sha256 和字节数（LFS 的 oid 就是 sha256），
    所以不用把几个 GB 拉下来也能拿到正确的值。格式见
    https://github.com/git-lfs/git-lfs/blob/main/docs/spec.md
    """
    try:
        if path.stat().st_size > 512:
            return None
        head = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError):
        return None
    if not head.startswith("version https://git-lfs.github.com/spec/v1"):
        return None
    oid = ""
    size = -1
    for line in head.splitlines():
        if line.startswith("oid sha256:"):
            oid = line.split(":", 1)[1].strip().lower()
        elif line.startswith("size "):
            try:
                size = int(line.split(" ", 1)[1].strip())
            except ValueError:
                return None
    if len(oid) != 64 or size < 0:
        return None
    return oid, size


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _sidecar_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".sha256")


def local_artifact_hash(path: Path, *, refresh_sidecar: bool = True) -> str:
    """本地制品 sha256；.sha256 边车比制品新则当缓存，否则重算并回写边车。"""
    side = _sidecar_path(path)
    try:
        if side.is_file() and side.stat().st_mtime >= path.stat().st_mtime:
            head = side.read_text(encoding="utf-8", errors="replace").split()
            if head and len(head[0]) == 64:
                return head[0].lower()
    except OSError:
        pass
    digest = sha256_file(path)
    if refresh_sidecar:
        try:
            side.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
        except OSError:
            pass
    return digest


def cnb_lfs_url(sha256: str) -> str:
    oid = "".join(c for c in (sha256 or "").strip().lower() if c in "0123456789abcdef")
    return f"{LFS}/{oid}" if len(oid) == 64 else ""


def cnb_raw_url(rel_path: str) -> str:
    return f"{RAW}/{(rel_path or '').replace(chr(92), '/').lstrip('/')}"



def _attach_i18n_fields(src: dict, dst: dict, fields: list[str]) -> None:
    """Copy optional localized maps and flat aliases into compiled JSON.

    Supported shapes (all optional; Chinese primary fields stay authoritative):

      title_i18n:
        en-US: Hello
        ja-JP: こんにちは
      # or flat:
      title_en: Hello
      title_ja: こんにちは

    Array fields (highlights) use the same map of locale → list[str].
    """
    if not isinstance(src, dict) or not isinstance(dst, dict):
        return
    short_map = {
        "en": "en-US",
        "ja": "ja-JP",
        "ko": "ko-KR",
        "es": "es-ES",
        "fr": "fr-FR",
        "ru": "ru-RU",
        "zh_Hant": "zh-TW",
        "zh-Hant": "zh-TW",
        "zh_TW": "zh-TW",
        "zh-TW": "zh-TW",
    }
    for f in fields:
        map_key = f"{f}_i18n"
        bucket: dict = {}
        raw_map = src.get(map_key)
        if isinstance(raw_map, dict):
            for loc, val in raw_map.items():
                loc_s = str(loc).strip()
                if not loc_s:
                    continue
                if isinstance(val, list):
                    items = [str(x).strip() for x in val if str(x).strip()]
                    if items:
                        bucket[loc_s] = items
                else:
                    s = str(val or "").strip()
                    if s:
                        bucket[loc_s] = s
        # flat aliases: title_en / body_ja / highlights_en
        for short, full in short_map.items():
            flat = f"{f}_{short}"
            if flat not in src:
                continue
            val = src[flat]
            if isinstance(val, list):
                items = [str(x).strip() for x in val if str(x).strip()]
                if items:
                    bucket.setdefault(full, items)
            else:
                s = str(val or "").strip()
                if s:
                    bucket.setdefault(full, s)
        if bucket:
            dst[map_key] = bucket



def cnb_release_url(tag: str, name: str) -> str:
    return f"{CNB_REPO_URL}/-/releases/download/{tag}/{name}"


def cnb_cover_url(rel_path: str) -> str:
    """封面走 Release 附件，不走 git raw。

    CNB 的 git-raw 返回的响应**不带 Content-Type，却带 X-Content-Type-Options:
    nosniff**。浏览器于是既不知道这是图片、又不许自己嗅探，`<img>` 直接不渲染
    —— 「社区音色不显示封面、模型页正常」就是这么来的：模型页读的是本地文件，
    MIME 由我们自己给。

    Release 附件按扩展名给 Content-Type（实测 image/jpeg），也没有 nosniff。
    所以封面统一传到 `covers` tag 下，文件名就是 ch-banner 里的文件名。
    """
    name = (rel_path or "").replace(chr(92), "/").rsplit("/", 1)[-1]
    return cnb_release_url(COVER_TAG, name) if name else ""


def _yymmdd(raw: Any) -> str:
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(digits) == 8:
        return digits[2:]
    if len(digits) == 6:
        return digits
    return ""


def _load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: 顶层必须是映射（mapping）")
    return data


def _dump_yaml(path: Path, data: dict, header: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(
        data, allow_unicode=True, sort_keys=False, default_flow_style=False, width=100
    )
    if header:
        text = "".join(f"# {line}\n" for line in header.splitlines()) + text
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


class Report:
    """收集 errors/warnings；--strict 时 warnings 也算失败。"""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def failed(self, strict: bool) -> bool:
        return bool(self.errors or (strict and self.warnings))

    def print(self) -> None:
        for w in self.warnings:
            print(f"  [警告] {w}")
        for e in self.errors:
            print(f"  [错误] {e}")


# ---------------------------------------------------------------- artifacts


def _release_tag_of(entry: dict, rep: Report, *, who: str, channel: str) -> str:
    """条目自己的 release_tag。channel=release 却没写就是错——别退默认值。

    退默认值正是上一次出事的方式：漏传之后一路默认成 RVC-runtime，生成的
    URL 语法完全正确、指向的 tag 下却没有这个附件，`check` 看不出来，只有
    用户下载时才 404。宁可在这里拦住。
    """
    tag = str(entry.get("release_tag") or "").strip()
    if channel == "release" and not tag:
        rep.error(f"{who}: channel=release 但没写 release_tag，下载地址会指错")
    return tag or "RVC-runtime"


def _resolve_artifact(
    entry: dict,
    paths: Paths,
    rep: Report,
    *,
    who: str,
    channel: str,
    release_tag: str = "RVC-runtime",
) -> dict:
    """解析一条制品：file(相对 CNB 仓) + 可选锁定 sha256/size → name/sha256/size/urls。

    锁定值（已发布真值）优先；本地文件哈希只用于补新条目与漂移告警。
    """
    rel_file = str(entry.get("file") or "").replace("\\", "/").strip()
    pinned_sha = str(entry.get("sha256") or "").strip().lower()
    pinned_size = entry.get("size_bytes")
    name = str(entry.get("name") or (Path(rel_file).name if rel_file else "")).strip()

    local_sha = ""
    local_size: Optional[int] = None
    if rel_file:
        f = paths.cnb / rel_file
        if f.is_file():
            ptr = read_lfs_pointer(f)
            if ptr:
                # 指针即权威：它记的就是真身的 sha256 与字节数。
                local_sha, local_size = ptr
            else:
                local_sha = local_artifact_hash(f)
                local_size = f.stat().st_size
        elif not pinned_sha:
            rep.error(f"{who}: 制品不存在且无锁定 sha256: {rel_file}")
        elif channel != "release":
            # 还挂在 git/LFS 上却本地没有 —— 多半是忘了 git lfs pull，值得提醒。
            #
            # channel: release 就不提了：制品已经搬到 Release 附件，仓库里本来就
            # 没有这个文件，缺席才是常态。留着的话每条制品都要报一次，17 条警告
            # 里 16 条是它，check --strict 从此永远红着，也就没法当 CI 门禁用了。
            rep.warn(f"{who}: 本地缺制品文件（用锁定值继续）: {rel_file}")

    sha = pinned_sha or local_sha
    if pinned_sha and local_sha and pinned_sha != local_sha:
        rep.warn(
            f"{who}: 本地制品哈希 ≠ 锁定值（本地未发布？以锁定值为准）: "
            f"{rel_file} local={local_sha[:12]}… pinned={pinned_sha[:12]}…"
        )
    size = pinned_size if pinned_size is not None else local_size
    if (
        pinned_size is not None
        and local_size is not None
        and int(pinned_size) != int(local_size)
        and not (pinned_sha and local_sha and pinned_sha != local_sha)
    ):
        rep.warn(
            f"{who}: 本地大小 ≠ 锁定 size_bytes: {rel_file} "
            f"local={local_size} pinned={pinned_size}"
        )

    if not name:
        rep.error(f"{who}: 缺 name/file，无法生成下载名")
    if not sha:
        rep.error(f"{who}: 缺 sha256（无本地制品也无锁定值）")

    # URL 推导（允许 YAML 显式 url/urls 覆盖）
    if entry.get("urls"):
        urls = [str(u) for u in entry["urls"] if u]
    elif entry.get("url"):
        urls = [str(entry["url"])]
    elif channel == "lfs":
        urls = [cnb_lfs_url(sha)] if sha else []
    else:
        urls = (
            [f"{CNB_REPO_URL}/-/releases/download/{release_tag}/{name}"] if name else []
        )

    # 边车（.sha256）是 65 字节纯文本，本来就该留在 git 里 —— 制品搬去 Release
    # 不代表边车也搬了。所以按「仓库里有没有这个文件」来选，不按 channel 猜：
    # 猜错的代价是清单里挂着一条 404，而且没人会发现，因为边车只是二次校验。
    if entry.get("sha256_urls"):
        sha_urls = [str(u) for u in entry["sha256_urls"] if u]
    elif rel_file and (paths.cnb / (rel_file + ".sha256")).is_file():
        sha_urls = [cnb_raw_url(rel_file + ".sha256")]
    elif channel == "release" and name:
        sha_urls = [f"{CNB_REPO_URL}/-/releases/download/{release_tag}/{name}.sha256"]
    elif channel == "lfs" and rel_file:
        sha_urls = [cnb_raw_url(rel_file + ".sha256")]
    else:
        sha_urls = []

    # channel/URL 一致性（客户端 cnb_sources 会按此过滤，不一致=用户下不到）
    for u in urls:
        if channel == "lfs" and "/-/releases/download/" in u:
            rep.error(f"{who}: channel=lfs 但 URL 是 Release 形态: {u}")
        if channel == "release" and "/-/lfs/" in u:
            rep.error(f"{who}: channel=release 但 URL 是 LFS 形态: {u}")

    return {
        "name": name,
        "sha256": sha,
        "size_bytes": int(size) if size is not None else 0,
        "urls": urls,
        "sha256_urls": sha_urls,
        "file": rel_file,
    }


# ------------------------------------------------------------------ sources


def load_sources(paths: Paths, rep: Report) -> dict:
    """读取 catalog-src/ 全部 YAML → 原始源字典。"""
    src = paths.src
    if not src.is_dir():
        rep.error(f"源目录不存在: {src}（先运行 init）")
        return {}
    out: dict[str, Any] = {}
    for key, fname in (
        ("meta", "meta.yaml"),
        ("app", "app.yaml"),
        ("community", "community.yaml"),
        ("engine_core", "engine-core.yaml"),
        ("vbcable", "vbcable.yaml"),
        ("setup", "setup.yaml"),
    ):
        p = src / fname
        if not p.is_file():
            rep.error(f"缺源文件: catalog-src/{fname}")
            out[key] = {}
            continue
        try:
            out[key] = _load_yaml(p)
        except Exception as e:
            rep.error(f"catalog-src/{fname}: 解析失败: {e}")
            out[key] = {}

    # plaza.yaml 是可选源：不存在/为空 = {}，plaza.json 仍会生成（自动派生条目）
    out["plaza"] = {}
    p = src / "plaza.yaml"
    if p.is_file():
        try:
            out["plaza"] = _load_yaml(p)
        except Exception as e:
            rep.error(f"catalog-src/plaza.yaml: 解析失败: {e}")

    # changelog.yaml 可选：壳层更新日志单一源 → changelog.json + gui.notes
    out["changelog"] = {}
    p = src / "changelog.yaml"
    if p.is_file():
        try:
            out["changelog"] = _load_yaml(p)
        except Exception as e:
            rep.error(f"catalog-src/changelog.yaml: 解析失败: {e}")

    out["runtimes"] = {}
    for variant in VALID_VARIANTS:
        p = src / "runtimes" / f"{variant}.yaml"
        if not p.is_file():
            rep.error(f"缺源文件: catalog-src/runtimes/{variant}.yaml")
            continue
        try:
            out["runtimes"][variant] = _load_yaml(p)
        except Exception as e:
            rep.error(f"runtimes/{variant}.yaml: 解析失败: {e}")
    extra = (
        sorted(
            f.stem
            for f in (src / "runtimes").glob("*.yaml")
            if (src / "runtimes").is_dir() and f.stem not in VALID_VARIANTS
        )
        if (src / "runtimes").is_dir()
        else []
    )
    for stem in extra:
        rep.error(
            f"runtimes/{stem}.yaml: 非法 variant（只允许 {'/'.join(VALID_VARIANTS)}）"
        )

    out["voices"] = []
    missing_auth: list[str] = []
    vdir = src / "voices"
    if vdir.is_dir():
        for p in sorted(vdir.glob("*.yaml")):
            try:
                v = _load_yaml(p)
            except Exception as e:
                rep.error(f"voices/{p.name}: 解析失败: {e}")
                continue
            v.setdefault("id", p.stem)
            if str(v["id"]) != p.stem:
                rep.warn(f"voices/{p.name}: id={v['id']} 与文件名不一致")
            out["voices"].append(v)
            # 官方源授权记录：建议 YAML 注释或 authorization 字段（不阻断）
            try:
                raw_txt = p.read_text(encoding="utf-8")
            except OSError:
                raw_txt = ""
            if "# 授权" not in raw_txt and "authorization:" not in raw_txt:
                missing_auth.append(p.stem)
        if missing_auth:
            # 一条汇总，避免每色一条刷屏（fixture/CI 日志）
            sample = "、".join(missing_auth[:6])
            more = f" 等{len(missing_auth)}个" if len(missing_auth) > 6 else ""
            rep.warn(
                f"官方音色建议补录授权注释（# 授权: …）或 authorization 字段："
                f"{sample}{more}"
            )
    else:
        rep.error("缺源目录: catalog-src/voices/")

    # 附加资源（分离模型 / 训练底模）：目录不存在 = 空（老仓兼容）。
    # 这些不像 runtime 那样人人都要，客户端也不写死规格 —— 加一个模型只改这里。
    out["extras"] = []
    edir = src / "extras"
    if edir.is_dir():
        for p in sorted(edir.glob("*.yaml")):
            try:
                v = _load_yaml(p)
            except Exception as e:
                rep.error(f"extras/{p.name}: 解析失败: {e}")
                continue
            v.setdefault("key", p.stem)
            if str(v["key"]) != p.stem:
                rep.warn(f"extras/{p.name}: key={v['key']} 与文件名不一致")
            out["extras"].append(v)

    # 第三方源：目录不存在 = 空列表（老仓/最小 fixture 兼容）
    out["thirdparty"] = []
    tpdir = src / "thirdparty"
    if tpdir.is_dir():
        for p in sorted(tpdir.glob("*.yaml")):
            try:
                v = _load_yaml(p)
            except Exception as e:
                rep.error(f"thirdparty/{p.name}: 解析失败: {e}")
                continue
            v.setdefault("id", p.stem)
            if str(v["id"]) != p.stem:
                rep.warn(f"thirdparty/{p.name}: id={v['id']} 与文件名不一致")
            out["thirdparty"].append(v)
    return out


# ------------------------------------------------------------------ compile


def _compile_voice(v: dict, paths: Paths, rep: Report) -> Optional[dict]:
    vid = str(v.get("id") or "").strip()
    who = f"voices/{vid or '?'}"
    if not vid:
        rep.error(f"{who}: 缺 id")
        return None
    date = _yymmdd(v.get("date") or v.get("released"))
    if not date:
        rep.error(f"{who}: date 必须是 YYMMDD")
        return None

    cover = str(v.get("cover") or f"ch-banner/{vid}.jpg").replace("\\", "/")
    if not (paths.cnb / cover).is_file():
        rep.warn(f"{who}: 封面文件不存在: {cover}")

    explicit_pack = str(v.get("pack_url") or "").strip()
    explicit_pth = str(v.get("pth_url") or "").strip()
    if explicit_pth and not explicit_pack and not v.get("file"):
        art = {
            "sha256": str(v.get("sha256") or ""),
            "size_bytes": int(v.get("size_bytes") or 0),
        }
        pack_url = ""
    else:
        # channel 以前在这里写死成 lfs，条目 YAML 里写的 release 被无视，
        # pack_url 也总是照 sha256 拼 LFS 地址。制品搬走之后，官方音色的下载
        # 地址还全指着 LFS —— 眼下还能下，只是因为 git 里删掉指针并不会删掉
        # LFS 对象；等 CNB 回收无引用对象，就是一次性全挂。
        v_channel = str(v.get("channel") or "lfs").strip().lower()
        # 只把制品字段递进去。整条音色递进去的话，`name` 会被当成下载文件名
        # —— 音色条目里的 name 是显示名（kikiV1、千早爱音），拼出来就是
        # /releases/download/voices/千早爱音，404。LFS 时代 URL 只认 sha256，
        # 从来用不到 name，所以这个重名一直没暴露。
        art_src = {
            k: v[k]
            for k in ("file", "sha256", "size_bytes", "url", "urls", "sha256_urls")
            if k in v
        }
        art = _resolve_artifact(
            art_src,
            paths,
            rep,
            who=who,
            channel=v_channel,
            release_tag=_release_tag_of(v, rep, who=who, channel=v_channel),
        )
        pack_url = explicit_pack or (art["urls"][0] if art["urls"] else "")
        if not pack_url:
            rep.error(f"{who}: 无法得到 pack_url（缺 sha256）")
            return None

    known = {
        "id",
        "name",
        "tag",
        "series",
        "author",
        "author_url",
        "date",
        "released",
        "version",
        "description",
        "file",
        "cover",
        "sha256",
        "size_bytes",
        "package_type",
        "publisher",
        "fabric_official",
        "pack_url",
        "pth_url",
        "index_url",
        "urls",
        "url",
        "sha256_urls",
        "name_display",
        "name_ja",
        "name_en",
        "name_zh_Hant",
        "tag_i18n",
        "description_i18n",
        "series_ja",
        "series_en",
        "series_zh_Hant",
        "notes",
    }
    item: dict[str, Any] = {
        "id": vid,
        "name": str(v.get("name") or vid),
        "author": str(v.get("author") or "RVC Fabric"),
        "author_url": str(v.get("author_url") or "https://cnb.cool/Turing-Mirror"),
        "released": date,
        "tag": str(v.get("tag") or "音色"),
        "version": str(v.get("version") or "1"),
        "package_type": str(v.get("package_type") or "voice_pack"),
        "cover": cover,
        "cover_url": cnb_cover_url(cover),
    }
    if explicit_pth:
        item["pth_url"] = explicit_pth
        if v.get("index_url"):
            item["index_url"] = str(v["index_url"])
    else:
        item["pack_url"] = pack_url
    item["sha256"] = art["sha256"]
    item["size_bytes"] = int(art["size_bytes"] or 0)
    item["description"] = str(v.get("description") or "")
    _attach_i18n_fields(v, item, ["tag", "description", "name", "series", "author"])
    item["publisher"] = str(v.get("publisher") or "rvc_fabric")
    item["fabric_official"] = bool(v.get("fabric_official", True))
    item["date"] = date
    series = str(v.get("series") or "").strip()
    if series:
        item["series"] = series
    # 未识别字段原样透传（客户端容忍额外键）
    for k, val in v.items():
        if k not in known and k not in item:
            item[k] = val
    return item


def _compile_thirdparty_voice(
    v: dict, paths: Paths, rep: Report, *, official_ids: set[str]
) -> Optional[dict]:
    """编译第三方源音色：直链托管在社区站，不进 CNB LFS。"""
    vid = str(v.get("id") or "").strip()
    who = f"thirdparty/{vid or '?'}"
    if not vid:
        rep.error(f"{who}: 缺 id")
        return None
    if not vid.startswith("tp-"):
        rep.error(f"{who}: id 必须以 tp- 前缀（避免与官方目录冲突）")
        return None
    if vid in official_ids:
        rep.error(f"{who}: id 与官方 voices 冲突: {vid}")
        return None
    if v.get("fabric_official") is True or str(
        v.get("publisher") or ""
    ).strip().lower() in ("rvc_fabric", "rvc-fabric"):
        rep.error(
            f"{who}: 禁止写 fabric_official/publisher=rvc_fabric（第三方不得盖官方章）"
        )
        return None

    # 未验证的不发布。
    #
    # 第三方直链指向的那串字节，在 verify_voice_pack.py 跑过之前没有人打开过：
    # 可能是空壳 zip、只有训练中间产物、也可能整个是 SoVITS —— 这三种都能正常
    # 下载解压、里面也确实有 .pth，用户要等到点「开启变声」才发现不对。既然
    # 商店里第三方和官方音色长得一模一样，就不能让没验过的东西混进去。
    ver = v.get("verified") if isinstance(v.get("verified"), dict) else None
    if not ver:
        rep.error(
            f"{who}: 缺 verified —— 先跑 "
            f"python scripts/verify_voice_pack.py 验证并把结果写进 YAML"
        )
        return None
    checks = [str(c) for c in (ver.get("checks") or [])]
    if "pth_struct_ok" not in checks:
        rep.error(
            f"{who}: verified.checks 里没有 pth_struct_ok —— "
            f"只确认了文件能下载，没确认里面真是 RVC 模型。实际: {checks}"
        )
        return None

    date = _yymmdd(v.get("date") or v.get("released"))
    if not date:
        rep.error(f"{who}: date 必须是 YYMMDD")
        return None

    pth_url = str(v.get("pth_url") or "").strip()
    pack_url = str(v.get("pack_url") or "").strip()
    if not pth_url and not pack_url:
        rep.error(f"{who}: 需要 pth_url 或 pack_url（http/https）")
        return None
    for label, u in (("pth_url", pth_url), ("pack_url", pack_url)):
        if u and not u.lower().startswith(("http://", "https://")):
            rep.error(f"{who}: {label} 必须是 http(s) 直链")
            return None

    sha = str(v.get("sha256") or "").strip().lower()
    if sha and (len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha)):
        rep.error(f"{who}: sha256 须为 64 位 hex")
        return None
    if not sha:
        rep.warn(f"{who}: 无 sha256（非 LFS 文件常见；客户端将跳过校验）")

    cover = str(v.get("cover") or "").strip().replace("\\", "/")
    cover_url = ""
    if cover:
        if cover.lower().startswith(("http://", "https://")):
            cover_url = cover
            cover = ""
        else:
            if not (paths.cnb / cover).is_file():
                rep.warn(f"{who}: 封面文件不存在: {cover}")
            cover_url = cnb_cover_url(cover)

    pkg = str(v.get("package_type") or "").strip()
    if not pkg:
        pkg = "voice_pack" if pack_url and not pth_url else "voice_files"

    item: dict[str, Any] = {
        "id": vid,
        "name": str(v.get("name") or vid),
        "tag": str(v.get("tag") or "音色"),
        "origin": str(v.get("origin") or "huggingface"),
        "source_url": str(v.get("source_url") or "").strip(),
        "author": str(v.get("author") or "").strip(),
        "author_url": str(v.get("author_url") or "").strip(),
        "package_type": pkg,
        "sha256": sha,
        "size_bytes": int(v.get("size_bytes") or 0),
        "released": date,
        "date": date,
        "description": str(
            v.get("description")
            or "收录自公开社区站点；非 RVC Fabric 官方音色，风险与官方无关。"
        ),
        "official": False,
        "publisher": "community",
        "fabric_official": False,
    }
    if pth_url:
        item["pth_url"] = pth_url
    if pack_url:
        item["pack_url"] = pack_url
    if v.get("index_url"):
        item["index_url"] = str(v.get("index_url")).strip()
    if cover:
        item["cover"] = cover
    if cover_url:
        item["cover_url"] = cover_url
    series = str(v.get("series") or "").strip()
    if series:
        item["series"] = series  # 仅搜索，不进系列专区
    _attach_i18n_fields(v, item, ["tag", "description", "name", "series", "author"])
    for k in ("hf_downloads", "hf_likes", "snapshot_date", "real_person"):
        if k in v and v[k] is not None and v[k] != "":
            item[k] = v[k]
    return item


def _compile_runtime(
    variant: str, r: dict, paths: Paths, rep: Report
) -> Optional[dict]:
    who = f"runtimes/{variant}"
    channel = str(r.get("channel") or ("lfs" if variant == "amd" else "release"))
    if channel not in VALID_CHANNELS:
        rep.error(f"{who}: channel 非法: {channel}")
        return None
    release_tag = str(r.get("release_tag") or "RVC-runtime")
    parts_src = r.get("parts") or []
    if not isinstance(parts_src, list) or not parts_src:
        rep.error(f"{who}: 缺 parts")
        return None
    parts = []
    for i, p in enumerate(parts_src):
        art = _resolve_artifact(
            dict(p),
            paths,
            rep,
            who=f"{who}.parts[{i}]",
            channel=channel,
            release_tag=release_tag,
        )
        parts.append(
            {
                "name": art["name"],
                "size_bytes": art["size_bytes"],
                "sha256": art["sha256"],
                "urls": art["urls"],
                "sha256_urls": art["sha256_urls"],
            }
        )
    total = sum(p["size_bytes"] for p in parts)
    spec: dict[str, Any] = {
        "variant": variant,
        "label": str(r.get("label") or variant),
        "version": str(r.get("version") or ""),
        "format": str(r.get("format") or "tar"),
        "size_bytes": int(r.get("size_bytes") or total),
        "extract_root": str(r.get("extract_root") or "Runtime"),
        "channel": channel,
    }
    if channel == "release":
        spec["release_tag"] = release_tag
    spec["parts"] = parts
    return spec


def _compile_blob(
    entry: dict, paths: Paths, rep: Report, *, who: str, extract_root: str
) -> dict:
    """engine_core / vbcable / setup 顶层 blob（管线 B 的直接输入）。"""
    channel = str(entry.get("channel") or "lfs")
    # release_tag 必须跟着 channel 一起传下去。以前这里漏了，_resolve_artifact
    # 就退回默认的 RVC-runtime，于是 setup / engine-core / vbcable 的下载地址
    # 全被写成 /releases/download/RVC-runtime/<文件名> —— 那个 tag 下根本没有
    # 这些附件，线上 404。runtime 三条恰好 tag 就叫 RVC-runtime，所以一直没
    # 露馅，制品从 LFS 搬到 Release 之后才炸出来。
    art = _resolve_artifact(
        entry,
        paths,
        rep,
        who=who,
        channel=channel,
        release_tag=_release_tag_of(entry, rep, who=who, channel=channel),
    )
    return {
        "name": art["name"],
        "version": str(entry.get("version") or ""),
        "channel": channel,
        "size_bytes": art["size_bytes"],
        "sha256": art["sha256"],
        "urls": art["urls"],
        "sha256_urls": art["sha256_urls"],
        "extract_root": str(entry.get("extract_root") or extract_root),
        "notes": str(entry.get("notes") or ""),
    }


_HEX = set("0123456789abcdef")


def _safe_dest(dest: str) -> bool:
    """`dest` 只能是安装目录下的相对路径。

    客户端 `extra_assets.rs::safe_dest` 会再拦一次，两边规则必须一致 —— 但
    在这里拦住的意义是：错误的清单根本发不出去，而不是发出去了靠客户端救。
    """
    d = str(dest or "").strip().replace("\\", "/")
    if not d or d.startswith("/") or ":" in d:
        return False
    return all(part not in ("", ".", "..") for part in d.split("/"))


def _safe_extra_name(name: str) -> bool:
    """附加资源的文件名，与客户端 `extra_assets.rs::safe_name` 同规则。

    PyMSS 的模型要按 catalog relpath 摆在子目录里（vocal/vocal_extraction/…），
    所以放行嵌套相对路径；`.`/`..`/绝对路径/盘符照旧拒绝。
    """
    n = str(name or "").strip().replace("\\", "/")
    if not n or ":" in n or n.startswith("/"):
        return False
    return all(part not in ("", ".", "..") for part in n.split("/"))


def _compile_extras(entries: list, rep: Report) -> dict:
    """附加资源 → index.extras。

    和 runtime 不同，这里**不查本地文件**：这些权重不进发布仓的 git，只在
    Release 附件里。所以 sha256 和 size_bytes 必须在 YAML 里写死 —— 写不出来
    就说明还没传上去，那就不该出现在清单里。
    """
    out: dict[str, Any] = {}
    for e in entries:
        key = str(e.get("key") or "").strip()
        who = f"extras/{key or '?'}"
        if not key:
            rep.error(f"{who}: 缺 key")
            continue
        dest = str(e.get("dest") or "").strip()
        if not _safe_dest(dest):
            rep.error(f"{who}: dest 必须是安装目录下的相对路径，且不能含 ..（当前：{dest!r}）")
            continue

        default_tag = str(e.get("release_tag") or "").strip()
        default_channel = str(e.get("channel") or "release").strip().lower()
        files = []
        ok = True
        for f in e.get("files") or []:
            name = str(f.get("name") or "").strip().replace("\\", "/")
            if not _safe_extra_name(name):
                rep.error(f"{who}: 文件名非法（只允许嵌套相对路径，不许 .. / 绝对路径）：{name!r}")
                ok = False
                continue
            sha = str(f.get("sha256") or "").strip().lower()
            if len(sha) != 64 or not set(sha) <= _HEX:
                rep.error(f"{who}/{name}: sha256 必须是 64 位十六进制（还没传上去？）")
                ok = False
                continue
            size = int(f.get("size_bytes") or 0)
            if size <= 0:
                rep.error(f"{who}/{name}: 缺 size_bytes，客户端靠它判断有没有下全")
                ok = False
                continue
            channel = str(f.get("channel") or default_channel).strip().lower()
            if channel not in ("release", "lfs"):
                rep.error(f"{who}/{name}: channel 只能是 release 或 lfs")
                ok = False
                continue
            tag = str(f.get("release_tag") or default_tag).strip()
            if channel == "release" and not tag:
                rep.error(f"{who}/{name}: channel=release 但没写 release_tag，地址会指错")
                ok = False
                continue
            # Release 附件按平铺 base name 寻址（上传时就是按 base name 传的）；
            # 清单里的嵌套相对路径只决定客户端本地摆哪，与客户端同规则。
            base = name.rsplit("/", 1)[-1]
            urls = [cnb_lfs_url(sha)] if channel == "lfs" else [cnb_release_url(tag, base)]
            row = {
                "name": name,
                "sha256": sha,
                "size_bytes": size,
                "channel": channel,
                "urls": urls,
            }
            if channel == "release":
                row["release_tag"] = tag
            files.append(row)
        if not ok:
            continue
        if not files:
            rep.error(f"{who}: 一个文件都没有")
            continue
        # group 决定客户端下载列表怎么分组：train=训练音色 / separate=人声分离。
        # 老 YAML 没写时按 key 前缀兜底，避免清单一发布客户端就全堆成一坨。
        group = str(e.get("group") or "").strip().lower()
        if group not in ("train", "separate", "other"):
            if key.startswith("pretrained"):
                group = "train"
            elif key.startswith("pymss") or key.startswith("uvr"):
                group = "separate"
            else:
                group = "other"
        try:
            order = int(e.get("order") or 100)
        except (TypeError, ValueError):
            order = 100
        recommended = bool(e.get("recommended"))
        out[key] = {
            "key": key,
            "label": str(e.get("label") or key),
            "dest": dest.replace("\\", "/"),
            "notes": str(e.get("notes") or ""),
            "group": group,
            "recommended": recommended,
            "order": order,
            "size_bytes": sum(f["size_bytes"] for f in files),
            "files": files,
        }
        if default_tag:
            out[key]["release_tag"] = default_tag
    return out


def _package_row(entry: dict, blob: dict, *, kind: str, package_type: str = "") -> dict:
    released = _yymmdd(
        entry.get("released") or entry.get("date")
    ) or datetime.now().strftime("%y%m%d")
    row: dict[str, Any] = {
        "id": str(entry.get("id") or f"{kind.replace('_', '-')}-{released}"),
        "name": str(entry.get("display_name") or entry.get("name") or blob["name"]),
        "kind": kind,
    }
    if package_type:
        row["package_type"] = package_type
    row.update(
        {
            "released": released,
            "version": str(entry.get("version") or ""),
            "file": str(entry.get("file") or ""),
            "url": (blob["urls"][0] if blob["urls"] else ""),
            "sha256": blob["sha256"],
        }
    )
    if blob["sha256_urls"]:
        row["sha256_url"] = blob["sha256_urls"][0]
    row["size_bytes"] = blob["size_bytes"]
    row["channel"] = blob["channel"]
    if entry.get("notes"):
        row["notes"] = str(entry["notes"])
    return row


def _validate_shell_versions(app: dict, rep: Report) -> None:
    """Stable channel shell Full must be X.Y.Z or X.Y.Z-hotfixN; forbid -partN."""
    is_stable_shell_version = _is_stable_shell_version

    channel = str(app.get("channel") or "stable").strip().lower()
    if channel != "stable":
        return
    ver = str(app.get("version") or "").strip()
    gui = app.get("gui") if isinstance(app.get("gui"), dict) else {}
    gver = str(gui.get("version") or ver).strip()
    for who, v in (("app.version", ver), ("app.gui.version", gver)):
        if not v:
            rep.error(f"{who}: 稳定通道不能为空")
            continue
        low = v.lower()
        if "-part" in low:
            rep.error(
                f"{who}={v!r}: 稳定通道禁止 -partN（历史预发布）；"
                "热修用 X.Y.Z-hotfixN，或抬升正式基线 X.Y.(Z+1)"
            )
            continue
        if not is_stable_shell_version(v):
            # 版本号新规（2026-07-30）：稳定通道只有 X.Y.Z 一种形态，
            # -hotfixN / -partN 全部作废，任何修补按 +0.0.1 发小版本。
            rep.error(
                f"{who}={v!r}: 稳定通道必须是 X.Y.Z；"
                "热修请发 +0.0.1 的新小版本，不要用 -hotfixN；"
                "build 序号写 tm_package.build_id，不要写进 version 字符串"
            )
    if ver and gver and ver != gver:
        rep.warn(
            f"app.version ({ver}) 与 app.gui.version ({gver}) 不一致；"
            "OTA 以 gui.version 为准，发布时建议对齐为同一 Full"
        )


def _compile_gui(app: dict, paths: Paths, rep: Report) -> dict:
    gui_src = app.get("gui") if isinstance(app.get("gui"), dict) else {}
    gui: dict[str, Any] = {
        "package_type": str(gui_src.get("package_type") or "gui_patch"),
        "version": str(gui_src.get("version") or app.get("version") or ""),
        "kind": str(gui_src.get("kind") or "zip"),
    }
    url = str(gui_src.get("url") or "").strip()
    sha = str(gui_src.get("sha256") or "").strip().lower()
    size = int(gui_src.get("size_bytes") or 0)
    if gui_src.get("file"):
        # 同样别写死 channel：界面增量包也跟着搬到了 Release 附件。
        # 只认 gui 自己的 channel —— app 顶层那个 channel 是更新通道
        # （stable/beta），和制品通道（lfs/release）同名不同义，串了就全错。
        g_channel = str(gui_src.get("channel") or "lfs").strip().lower()
        art = _resolve_artifact(
            dict(gui_src),
            paths,
            rep,
            who="app.gui",
            channel=g_channel,
            release_tag=_release_tag_of(
                dict(gui_src), rep, who="app.gui", channel=g_channel
            ),
        )
        sha = sha or art["sha256"]
        url = url or (art["urls"][0] if art["urls"] else "")
        # _resolve_artifact 已经算好了体积，这里以前直接丢掉，下游又把
        # packages.gui_patch.size_bytes 写死成 0 —— 界面增量包在清单里一直是
        # 「0 字节」，客户端既显示不出大小，也没法用体积做完整性兜底。
        size = size or int(art.get("size_bytes") or 0)
    if not url and sha:
        url = cnb_lfs_url(sha)
    gui["url"] = url
    gui["sha256"] = sha
    gui["size_bytes"] = size
    gui["min_app_version"] = str(gui_src.get("min_app_version") or "")
    gui["notes"] = str(gui_src.get("notes") or "")
    if url and not sha:
        rep.error("app.gui: 有 url 但缺 sha256 — 客户端会拒绝一键增量更新")
    return gui


def compile_catalog(src: dict, paths: Paths, rep: Report) -> Optional[dict]:
    """源字典 → {index, snippet, bundled} 产物 dict（广场/日志走独立管线）。"""
    if rep.errors:
        return None
    meta = src.get("meta") or {}
    # Deep-copy app so changelog can override notes without mutating YAML load cache
    app_src = dict(src.get("app") or {})
    if isinstance(app_src.get("gui"), dict):
        app_src["gui"] = dict(app_src["gui"])
    changelog_payload = compile_changelog(src, rep)
    src["_changelog_compiled"] = changelog_payload
    _apply_changelog_notes(app_src, changelog_payload, rep)
    community = {
        "qq_group": str((src.get("community") or {}).get("qq_group") or ""),
        "qq_link": str((src.get("community") or {}).get("qq_link") or ""),
        "sharepoint_full": str(
            (src.get("community") or {}).get("sharepoint_full") or ""
        ),
        "note": str((src.get("community") or {}).get("note") or ""),
    }
    runtime_release_tag = str(meta.get("runtime_release_tag") or "RVC-runtime")

    gui = _compile_gui(app_src, paths, rep)
    app = {
        "version": str(app_src.get("version") or ""),
        "channel": str(app_src.get("channel") or "stable"),
        "gui": gui,
    }
    _validate_shell_versions(app, rep)

    extras = _compile_extras(src.get("extras") or [], rep)

    engine_core = _compile_blob(
        src.get("engine_core") or {}, paths, rep, who="engine-core", extract_root="."
    )
    vbcable = _compile_blob(
        src.get("vbcable") or {}, paths, rep, who="vbcable", extract_root="VBCABLE"
    )
    # 兼容线上现状：顶层 vbcable 曾带标量 url
    vbcable_top = dict(vbcable)
    if vbcable_top.get("urls"):
        vbcable_top["url"] = vbcable_top["urls"][0]
        vbcable_top = {  # 保持线上键序（url 紧跟 urls）
            k: vbcable_top[k]
            for k in (
                "name",
                "version",
                "channel",
                "size_bytes",
                "sha256",
                "urls",
                "url",
                "sha256_urls",
                "extract_root",
                "notes",
            )
            if k in vbcable_top
        }

    runtimes: dict[str, Any] = {}
    runtime_rows: list[dict] = []
    for variant in VALID_VARIANTS:
        r = (src.get("runtimes") or {}).get(variant)
        if not r:
            continue
        spec = _compile_runtime(variant, r, paths, rep)
        if not spec:
            continue
        runtimes[variant] = spec
        p0 = spec["parts"][0]
        released = _yymmdd(r.get("released") or r.get("version")) or ""
        row = {
            "id": f"runtime-{variant}-{released}",
            "variant": variant,
            "released": released,
            "version": spec["version"],
            "channel": spec["channel"],
            "name": p0["name"],
            "url": p0["urls"][0] if p0["urls"] else "",
            "sha256": p0["sha256"],
        }
        if p0["sha256_urls"]:
            row["sha256_url"] = p0["sha256_urls"][0]
        row["size_bytes"] = p0["size_bytes"]
        runtime_rows.append(row)

    voices: list[dict] = []
    seen_ids: set[str] = set()
    for v in src.get("voices") or []:
        item = _compile_voice(v, paths, rep)
        if not item:
            continue
        if item["id"] in seen_ids:
            rep.error(f"voices: id 重复: {item['id']}")
            continue
        seen_ids.add(item["id"])
        voices.append(item)
    voices.sort(key=lambda x: (x.get("date") or "", str(x.get("id") or "").lower()))

    thirdparty_voices: list[dict] = []
    tp_ids: set[str] = set()
    for v in src.get("thirdparty") or []:
        item = _compile_thirdparty_voice(v, paths, rep, official_ids=seen_ids)
        if not item:
            continue
        if item["id"] in tp_ids or item["id"] in seen_ids:
            rep.error(f"thirdparty_voices: id 重复: {item['id']}")
            continue
        tp_ids.add(item["id"])
        thirdparty_voices.append(item)
    thirdparty_voices.sort(
        key=lambda x: (x.get("date") or "", str(x.get("id") or "").lower())
    )

    setup_src = src.get("setup") or {}
    setup_blob = _compile_blob(setup_src, paths, rep, who="setup", extract_root=".")
    packages = {
        "setup": [
            _package_row(
                setup_src, setup_blob, kind="setup", package_type="full_package"
            )
        ],
        "gui_patch": [],
        "engine_core": [
            _package_row(src.get("engine_core") or {}, engine_core, kind="engine_core")
        ],
        "runtime": runtime_rows,
        "vbcable": [_package_row(src.get("vbcable") or {}, vbcable, kind="vbcable")],
    }
    # packages.gui_patch 行仅当 app.yaml 显式给出 released 时生成
    # （app.gui 本身已是管线 A 的权威入口，这行只是索引可读性补充）
    gui_released = _yymmdd(app_src.get("released"))
    if gui_released and gui.get("url") and gui.get("sha256"):
        packages["gui_patch"] = [
            {
                "id": f"gui-{gui_released}",
                "name": "RVC Fabric GUI Patch",
                "kind": "gui_patch",
                "package_type": "gui_patch",
                "released": gui_released,
                "version": gui["version"],
                "url": gui["url"],
                "sha256": gui["sha256"],
                "size_bytes": int(gui.get("size_bytes") or 0),
                "channel": "lfs",
                "notes": gui["notes"],
            }
        ]

    if rep.errors:
        return None

    note = str(meta.get("note") or "")
    index = {
        "schema": 2,
        "format": "rvc_fabric_index",
        "product": str(meta.get("product") or "RVC Fabric"),
        "updated": "",  # 幂等：仅内容变化时由 build 刷新
        "released": "",
        "cnb_repo": CNB_REPO_URL,
        "cnb_git": f"{CNB_REPO_URL}.git",
        "raw_base": RAW,
        "lfs_base": LFS,
        "ch_banner_dir": "ch-banner",
        "note": note,
        "packages": packages,
        "app": app,
        "community": community,
        "voices": voices,
        "thirdparty_voices": thirdparty_voices,
        "runtime_release_tag": runtime_release_tag,
        "runtimes": runtimes,
        "manifest_urls": list(meta.get("manifest_urls") or MANIFEST_URLS),
        "engine_core": engine_core,
        "vbcable": vbcable_top,
        "extras": extras,
    }
    snippet = {
        "schema": 1,
        "note": "兼容清单；主索引请用根目录 index.json（本文件为生成物，勿手改）",
        "cnb_repo": CNB_REPO_URL,
        "raw_base": RAW,
        "lfs_base": LFS,
        "manifest_urls": index["manifest_urls"],
        "app": app,
        "community": community,
        "voices": voices,
        "thirdparty_voices": thirdparty_voices,
        "runtime_release_tag": runtime_release_tag,
        "runtimes": runtimes,
        "engine_core": engine_core,
        "vbcable": vbcable_top,
        "extras": extras,
    }
    bundled = {
        "schema": 1,
        "app": app,
        "community": community,
        "cnb_repo": CNB_REPO_URL,
        "runtime_release_tag": runtime_release_tag,
        "engine_core": engine_core,
        "vbcable": vbcable_top,
        "manifest_urls": index["manifest_urls"],
        "runtimes": runtimes,
        "voices": voices,
        "thirdparty_voices": thirdparty_voices,
        # 附加资源（训练底模 / 分离模型）也进内置兜底：离线或 CNB 抽风时
        # extra_list 仍能列出「该下什么」，下载 URL 仍指向 CNB Release。
        "extras": extras,
    }
    return {"index": index, "snippet": snippet, "bundled": bundled}


# -------------------------------------------------------------------- plaza
#
# 广场 feed 是独立管线：plaza.yaml（可选）+ app.yaml 自动派生 → plaza.json。
# 不进 index.json；客户端契约见 launcher/online/plaza.py。

_PLAZA_KNOWN_TYPES = ("news", "notice", "banner", "ad", "sponsor")
_PLAZA_AD_TYPES = ("ad", "sponsor")
_PLAZA_BODY_CAP = 220  # 自动派生资讯正文截断长度
# 广场置顶区最多几条。必须和客户端 `plaza::MAX_PINNED` 一致 ——
# 那边是硬削，这边只警告，两个数对不上的话警告就成了假消息。
_PLAZA_MAX_PINNED = 5

_PLAZA_YAML_TEMPLATE = """\
# 广场 feed 源文件（可选）— 编译产物为 CNB 根目录 plaza.json，独立于 index.json。
# 本文件不存在或为空时，plaza.json 仍会生成（内容 = 自动派生的版本资讯）。
# 编译: python scripts/build_catalog.py build --diff

# true（默认）= 自动从 app.yaml 派生一条版本资讯：
#   id=release-<version>，title="RVC Fabric v<version> 发布"，body=notes 截断 220 字，
#   date=released，priority=50。显示顺序只由 pinned/priority/date 决定
#   （自动条目 priority=50，手写条目想压过它就写更高 priority 或 pinned）；
#   手写了同 id 条目则不再自动生成。
auto_release_news: true

# 条目字段（仅 id/title 必填）：
#   id            全局唯一；用户按 id 永久关闭，想重新曝光就换新 id
#   type          news | notice | banner | ad | sponsor（ad/sponsor 强制可关闭 + 「广告」角标）
#   title / body  标题 / 正文
#   image         CNB 仓内相对路径（本地必须存在）或 cnb.cool https 直链；外部图床禁止
#   url           点击跳转链接，仅 http(s)
#   action_label  按钮文案（如「查看详情」）
#   date          YYMMDD；start / end 为投放窗口（含当天）
#   priority      数字越大越靠前（默认 0）
#   pinned: true  同时进广场顶部「置顶」那一排（封面 + 一行标题，点了滚到本条并高亮）
#                 最多五条 —— 那一排一行放五张卡，多的客户端会削掉，编译时先警告
#   pin_title     只在 pinned 时有用：置顶卡上单独写的短标题（不写就用 title）
#                 投放标题按整行排，十几二十字塞进一张卡只能截断，所以留这个口子
#                 封面和跳转目标共用同一条内容 —— 一条内容，两处展示
#   dismissible   是否可关闭（资讯默认 false；ad/sponsor 编译时强制 true）
#   placements    [plaza] 和/或 [models_page]（模型页至多显示一条且必须可关闭）
#   min_app_version / max_app_version  版本门槛（含 -partN 语义）
#   sponsor       广告主名（非空即按广告处理）
#   utm: true     给 url 追加 utm_source/utm_medium/utm_campaign（ad/sponsor 一律自动追加）
items:
#   - id: notice-260801-maintenance
#     type: notice
#     title: 下载源维护公告
#     body: CNB 下载源 8 月 1 日 02:00-04:00 维护，期间社区下载可能失败。
#     url: https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases
#     date: 260801
#     image: ch-banner/example.jpg   # 置顶卡要有封面，没有就只剩四个字的占位
#     pinned: true
#     pin_title: 下载源维护          # 置顶卡上那一行；不写就用上面的 title
#     utm: true
"""

_CHANGELOG_YAML_TEMPLATE = """\
# 壳层更新日志（唯一维护源）— 编译产物 CNB 根目录 changelog.json
# 规则见发布仓 docs-发布规则.md，流程见 docs-发布流程.md
# 稳定通道只记 X.Y.Z；正向积累。编译: python scripts/build_catalog.py build --diff
#
# version     必填 X.Y.Z（稳定通道；历史 -hotfixN 勿新发）
# date        可选 YYMMDD
# title       可选
# highlights  可选短要点（广场主卡摘要）
# body        建议填写；gui.notes 取最新条 body（无则 highlights 拼接）
entries:
#   - version: 1.2.3
#     date: '260730'
#     title: 1.2.3
#     highlights:
#       - 修复某某
#     body: >
#       完整说明……
"""


def _plaza_types() -> tuple[tuple, tuple]:
    """KNOWN_TYPES/AD_TYPES 以客户端为准；launcher 不可导入时用本地兜底。"""
    r = _client_call(["types"])
    if r:
        return tuple(r.get("known_types") or ()), tuple(r.get("ad_types") or ())
    return _PLAZA_KNOWN_TYPES, _PLAZA_AD_TYPES


def _stamp_utm(url: str, *, medium: str, campaign: str) -> str:
    """给 url 追加 utm 参数；已含 utm_source 则原样返回。"""
    parts = urlsplit(url)
    if "utm_source" in parse_qs(parts.query):
        return url
    extra = urlencode(
        {
            "utm_source": "rvc_fabric",
            "utm_medium": medium,
            "utm_campaign": campaign,
        }
    )
    query = f"{parts.query}&{extra}" if parts.query else extra
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _compile_plaza_item(
    raw: Any, paths: Paths, rep: Report, *, who: str, known: tuple, ads: tuple
) -> Optional[dict]:
    """单条 plaza.yaml 条目 → feed 行；不可用返回 None（错误已进 rep）。"""
    if not isinstance(raw, dict):
        rep.error(f"{who}: 条目必须是映射（mapping）")
        return None
    item_id = str(raw.get("id") or "").strip()
    title = str(raw.get("title") or "").strip()
    if not item_id:
        rep.error(f"{who}: 缺 id")
    if not title:
        rep.error(f"{who}: 缺 title")
    if not item_id or not title:
        return None

    typ = str(raw.get("type") or "news").strip().lower()
    if typ not in known:
        rep.warn(f"{who}: 未知 type={typ}（前向兼容允许，但旧客户端不会显示此条）")
    sponsor = str(raw.get("sponsor") or "").strip()
    is_ad = typ in ads or bool(sponsor)

    placements = raw.get("placements") or ["plaza"]
    if isinstance(placements, str):
        placements = [placements]
    if not isinstance(placements, list):
        rep.error(f"{who}: placements 必须是列表或字符串")
        placements = ["plaza"]
    placements = [str(p).strip() for p in placements if str(p).strip()] or ["plaza"]

    image = str(raw.get("image") or "").strip().replace("\\", "/")
    if image:
        if image.lower().startswith(("http://", "https://")):
            host = (urlparse(image).hostname or "").lower()
            if not (host == "cnb.cool" or host.endswith(".cnb.cool")):
                rep.error(f"{who}: image 只允许 cnb.cool 域名（客户端会丢弃）: {image}")
        elif not (paths.cnb / image).is_file():
            rep.error(f"{who}: image 文件不存在于 CNB 仓: {image}")

    url = str(raw.get("url") or "").strip()
    if url and not url.lower().startswith(("http://", "https://")):
        rep.error(f"{who}: url 必须是 http(s): {url}")
        url = ""
    # utm 盖章：广告一律；其他条目仅当源里 utm: true。utm 字段本身不进产物。
    if url and (is_ad or bool(raw.get("utm"))):
        url = _stamp_utm(url, medium=placements[0], campaign=item_id)

    row: dict[str, Any] = {"id": item_id, "type": typ, "title": title}
    body = str(raw.get("body") or "").strip()
    if body:
        row["body"] = body
    if image:
        row["image"] = image
    if url:
        row["url"] = url
    action = str(raw.get("action_label") or "").strip()
    if action:
        row["action_label"] = action
    date = _yymmdd(raw.get("date"))
    if raw.get("date") and not date:
        rep.warn(f"{who}: date 无法解析为 YYMMDD: {raw.get('date')}")
    if date:
        row["date"] = date
    try:
        priority = int(raw.get("priority") or 0)
    except (TypeError, ValueError):
        rep.warn(f"{who}: priority 不是整数，按 0 处理: {raw.get('priority')}")
        priority = 0
    if priority:
        row["priority"] = priority
    if raw.get("pinned"):
        row["pinned"] = True
        # 置顶卡片上单独写的短标题。封面和跳转目标仍然共用同一条内容，
        # 只是卡片那一行字可以另写 —— 投放标题按整行排，塞进卡片会截断。
        pin_title = str(raw.get("pin_title") or "").strip()
        if pin_title:
            row["pin_title"] = pin_title
    elif str(raw.get("pin_title") or "").strip():
        # 写了短标题却没置顶 = 这条永远不会出现在置顶区，那行字白写了。
        rep.warn(f"{who}: 写了 pin_title 但没有 pinned: true，该标题不会被用到")
    # 广告必须可关闭——编译时强制写 true，feed 无权关掉这个开关
    if bool(raw.get("dismissible", False)) or is_ad:
        row["dismissible"] = True
    # 模型页横幅契约：客户端 pick_models_banner 只接受可关闭条目。
    # 忘写 dismissible 的 models_page 条目会在所有界面静默隐身——编译期拦下。
    if "models_page" in placements and not row.get("dismissible"):
        rep.error(
            f"{who}: placements 含 models_page 的条目必须 dismissible: true"
            "（模型页横幅强制可关闭，否则客户端不会展示该条目）"
        )
    row["placements"] = placements
    for key in ("start", "end"):
        v = _yymmdd(raw.get(key))
        if raw.get(key) and not v:
            rep.warn(f"{who}: {key} 无法解析为 YYMMDD: {raw.get(key)}")
        if v:
            row[key] = v
    for key in ("min_app_version", "max_app_version"):
        v = str(raw.get(key) or "").strip()
        if v:
            row[key] = v
    if sponsor:
        row["sponsor"] = sponsor
    _attach_i18n_fields(
        raw,
        row,
        ["title", "body", "pin_title", "action_label", "sponsor"],
    )
    return row





def compile_changelog(src: dict, rep: Report) -> dict:
    """changelog.yaml → changelog.json payload（schema 1, entries newest-first）。"""
    compare_versions = _client_compare_versions
    is_stable_shell_version = _is_stable_shell_version

    raw_src = src.get("changelog") or {}
    rows_src = raw_src.get("entries") or raw_src.get("items") or []
    if raw_src and not isinstance(rows_src, list):
        rep.error("changelog: entries 必须是列表")
        rows_src = []

    entries: list[dict] = []
    seen: set[str] = set()
    for i, raw in enumerate(rows_src):
        who = f"changelog.entries[{i}]"
        if not isinstance(raw, dict):
            rep.error(f"{who}: 必须是映射")
            continue
        version = str(raw.get("version") or raw.get("ver") or "").strip()
        if not version:
            rep.error(f"{who}: 缺 version")
            continue
        if not is_stable_shell_version(version):
            rep.error(
                f"{who}: version={version!r} 必须是 X.Y.Z 或 X.Y.Z-hotfixN"
            )
            continue
        if version in seen:
            rep.error(f"changelog: version 重复: {version}")
            continue
        seen.add(version)
        highlights: list[str] = []
        hl = raw.get("highlights") or raw.get("bullets") or []
        if isinstance(hl, str) and hl.strip():
            highlights = [hl.strip()]
        elif isinstance(hl, list):
            for x in hl:
                s = str(x or "").strip()
                if s:
                    highlights.append(s)
        body = str(raw.get("body") or raw.get("notes") or raw.get("text") or "").strip()
        if not body and not highlights:
            rep.error(f"{who} ({version}): body 与 highlights 至少填一项")
            continue
        row: dict[str, Any] = {"version": version}
        date = _yymmdd(raw.get("date") or raw.get("released"))
        if date:
            row["date"] = date
        title = str(raw.get("title") or "").strip()
        if title:
            row["title"] = title
        if highlights:
            row["highlights"] = highlights
        if body:
            row["body"] = body
        _attach_i18n_fields(raw, row, ["title", "body", "highlights", "notes"])
        entries.append(row)

    from functools import cmp_to_key

    def _cmp(a: dict, b: dict) -> int:
        c = compare_versions(str(a.get("version") or ""), str(b.get("version") or ""))
        if c != 0:
            return -c
        da, db = str(a.get("date") or ""), str(b.get("date") or "")
        if da != db:
            return (da < db) - (da > db)
        return 0

    entries.sort(key=cmp_to_key(_cmp))
    return {"schema": 1, "entries": entries}


def _notes_from_changelog_row(row: dict) -> str:
    body = str(row.get("body") or "").strip()
    if body:
        return body
    hl = row.get("highlights") or []
    if isinstance(hl, list) and hl:
        return "；".join(str(x).strip() for x in hl if str(x).strip())
    return ""


def _apply_changelog_notes(app_src: dict, changelog: dict, rep: Report) -> None:
    """Single source: latest changelog entry overwrites app.gui.notes."""
    entries = changelog.get("entries") if isinstance(changelog, dict) else None
    if not entries:
        return
    latest = entries[0]
    notes = _notes_from_changelog_row(latest)
    if not notes:
        return
    gui = app_src.get("gui") if isinstance(app_src.get("gui"), dict) else {}
    if not isinstance(gui, dict):
        gui = {}
        app_src["gui"] = gui
    old = str(gui.get("notes") or app_src.get("notes") or "").strip()
    if old and old != notes:
        rep.warn(
            "app.gui.notes 已被 changelog.yaml 最新条覆盖（请只维护 changelog.yaml）"
        )
    gui["notes"] = notes
    # Carry multi-language notes for OTA dialog (client picks by ui_locale).
    if isinstance(latest, dict):
        _attach_i18n_fields(latest, gui, ["notes", "body"])
        # body_i18n maps onto notes_i18n for the update banner.
        bi = gui.get("body_i18n")
        if isinstance(bi, dict) and bi:
            ni = gui.setdefault("notes_i18n", {})
            if isinstance(ni, dict):
                for loc, val in bi.items():
                    ni.setdefault(loc, val)
            if "body_i18n" in gui:
                # keep body_i18n too for clients that look there
                pass
    app_src["gui"] = gui
    app_src["notes"] = notes


def _auto_release_news(
    app_src: dict, changelog: Optional[dict] = None
) -> Optional[dict]:
    """从 changelog 最新条（优先）或 app.yaml 派生版本资讯 id=release-<version>。"""
    entries = (changelog or {}).get("entries") if isinstance(changelog, dict) else None
    if entries:
        latest = entries[0]
        version = str(latest.get("version") or "").strip()
        body = _notes_from_changelog_row(latest)
        date = _yymmdd(latest.get("date")) or _yymmdd(app_src.get("released"))
        # Fixed wording for old clients; changelog has its own display_title
        title = f"RVC Fabric v{version} 发布" if version else ""
    else:
        version = str(app_src.get("version") or "").strip()
        gui = app_src.get("gui") if isinstance(app_src.get("gui"), dict) else {}
        body = str(app_src.get("notes") or gui.get("notes") or "").strip()
        date = _yymmdd(app_src.get("released"))
        title = f"RVC Fabric v{version} 发布" if version else ""
    if not version:
        return None
    if len(body) > _PLAZA_BODY_CAP:
        body = body[:_PLAZA_BODY_CAP] + "……"
    row: dict[str, Any] = {
        "id": f"release-{version}",
        "type": "news",
        "title": title or f"RVC Fabric v{version} 发布",
    }
    if body:
        row["body"] = body
    if date:
        row["date"] = date
    row["priority"] = 50
    row["placements"] = ["plaza"]
    return row


def compile_plaza(src: dict, paths: Paths, rep: Report) -> dict:
    """plaza.yaml（可选）+ changelog/app 派生 → plaza.json payload（schema 1）。"""
    plaza_src = src.get("plaza") or {}
    known, ads = _plaza_types()
    changelog = src.get("_changelog_compiled") or compile_changelog(src, rep)

    rows_src = plaza_src.get("items") or []
    if not isinstance(rows_src, list):
        rep.error("plaza: items 必须是列表")
        rows_src = []

    items: list[dict] = []
    seen: set[str] = set()
    for i, raw in enumerate(rows_src):
        row = _compile_plaza_item(
            raw, paths, rep, who=f"plaza.items[{i}]", known=known, ads=ads
        )
        if row is None:
            continue
        if row["id"] in seen:
            rep.error(f"plaza: id 重复: {row['id']}")
            continue
        seen.add(row["id"])
        items.append(row)

    # 置顶最多五条 —— 广场置顶区一行五张卡，第六张会换行，那一排就从横幅变成
    # 了第二个投放列表。客户端 `plaza::MAX_PINNED` 会把多出来的削掉（内容照常
    # 留在「投放」里），所以这里只是警告：发布的人应该知道自己标多了。
    pinned_ids = [r["id"] for r in items if r.get("pinned")]
    if len(pinned_ids) > _PLAZA_MAX_PINNED:
        dropped = pinned_ids[_PLAZA_MAX_PINNED:]
        rep.warn(
            f"plaza: 标了 {len(pinned_ids)} 条 pinned，客户端只展示前 "
            f"{_PLAZA_MAX_PINNED} 条（按 priority / 日期排序）；"
            f"这几条不会出现在置顶区: {', '.join(dropped)}"
        )

    # 自动派生版本资讯（changelog 优先）。
    #
    # 默认关掉了：这条本来是给「没有更新日志区块」的老客户端用的，现在广场
    # 自己就有更新日志，再派生一条「RVC Fabric vX 发布」等于把同一件事说两遍，
    # 而且它会落进「投放」区 —— 版本发布不是投放内容。真要单独投放某次发布，
    # 在 plaza.yaml 里手写一条，别靠自动派生。
    if plaza_src.get("auto_release_news", False):
        auto = _auto_release_news(src.get("app") or {}, changelog)
        if auto and auto["id"] not in seen:
            seen.add(auto["id"])
            items.append(auto)

    return {"schema": 1, "items": items}


def _changelog_roundtrip(payload: dict, rep: Report) -> None:
    """回环：产物可被客户端 parse_changelog 解析。"""
    r = _client_call(["changelog"], json.loads(json.dumps(payload)))
    if r is None:
        rep.warn("回环[changelog]跳过（客户端解析器不可用；装 Rust 工具链后重跑）")
        return
    rows = payload.get("entries") or []
    parsed = r.get("versions") or []
    want = {str(x.get("version")) for x in rows}
    got = set(parsed)
    if want != got:
        lost = sorted(want - got)
        rep.error(
            f"回环[changelog]: 客户端解析 {len(parsed)}/{len(rows)} 条"
            f"（丢弃: {', '.join(lost) or '?'}）"
        )


def _plaza_roundtrip(payload: dict, rep: Report) -> None:
    """回环[C]: 产物喂给真实客户端 plaza 解析器 — 防 schema 手滑让内容隐身。"""
    r = _client_call(["plaza"], json.loads(json.dumps(payload)))
    if r is None:
        rep.warn("回环[C]跳过（客户端解析器不可用；装 Rust 工具链后重跑）")
        return
    rows = payload.get("items") or []
    parsed = r.get("items") or []  # dicts from the Rust parser
    want_ids = {str(x.get("id")) for x in rows}
    got_ids = {str(x.get("id")) for x in parsed}
    if len(parsed) != len(rows) or want_ids != got_ids:
        lost = sorted(want_ids - got_ids)
        rep.error(
            f"回环[C]: 客户端只解析出 {len(parsed)}/{len(rows)} 条"
            f"（被静默丢弃: {', '.join(lost) or '?'}）"
        )

    _, ad_types = _plaza_types()
    for it in parsed:
        is_adish = it.get("type") in ad_types or it.get("sponsor")
        if is_adish and not it.get("is_ad"):
            rep.error(f"回环[C]: 广告条目未标记 is_ad: {it.get('id')}")
        # 可关闭性由投放位置决定：广场位不可关闭（广场就是拿来投放的），
        # 模型页横幅必须可关闭。
        on_models = "models_page" in (it.get("placements") or [])
        if on_models and not it.get("dismissible"):
            rep.error(f"回环[C]: 模型页横幅必须可关闭: {it.get('id')}")
        if is_adish and not on_models and it.get("dismissible"):
            rep.warn(f"回环[C]: 广场位广告被标成可关闭: {it.get('id')}")


def _roundtrip_check(outputs: dict, src: dict, rep: Report) -> None:
    """把产物喂给真实客户端解析器 — schema 对但客户端读不出 = 直接报错。"""
    index = outputs["index"]
    n_src = len(src.get("voices") or [])
    n_tp = len(index.get("thirdparty_voices") or [])
    # 回环[A]：三份产物里的音色数必须一致，且每条都带客户端要用的字段。
    # 旧实现 import launcher.online.catalog；Python 壳已退役，改为结构校验。
    for name in ("index", "snippet", "bundled"):
        payload = outputs[name]
        voices = payload.get("voices") or []
        if len(voices) != n_src:
            rep.error(
                f"回环[A]: {name} 音色数 {len(voices)} != 源 {n_src}"
            )
        for v in voices:
            vid = str(v.get("id") or "")
            if not vid:
                rep.error(f"回环[A]: {name} 有音色缺 id")
                continue
            if not (v.get("pack_url") or v.get("pth_url") or v.get("url")):
                rep.error(f"回环[A]: {name} 音色 {vid} 无下载地址")
            if not v.get("sha256"):
                rep.error(f"回环[A]: {name} 音色 {vid} 无 sha256")
    gui = (outputs["index"].get("gui") or {})
    if gui.get("url") and not gui.get("sha256"):
        rep.error("回环[A]: gui.url 存在但 sha256 为空")

    # 回环[B]：运行时规格喂给真实客户端解析器
    r = _client_call(["runtimes"], json.loads(json.dumps(index)))
    if r is None:
        rep.warn("回环[B]跳过（客户端解析器不可用；装 Rust 工具链后重跑）")
    else:
        for row in r.get("runtimes") or []:
            variant = row.get("variant")
            if not row.get("urls"):
                rep.error(f"回环[B]: runtimes.{variant} 客户端解析后无可用 URL")
            if not row.get("sha256"):
                rep.error(f"回环[B]: runtimes.{variant} 客户端解析后无 sha256")
    for key in ("engine_core", "vbcable"):
        blob = index.get(key) or {}
        if blob and not blob.get("sha256"):
            rep.error(f"回环[B]: {key} 缺 sha256")

def _semantic_diff(old: Any, new: Any, path: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(old, dict) and isinstance(new, dict):
        for k in sorted(set(old) | set(new)):
            p = f"{path}.{k}" if path else str(k)
            if k not in old:
                out.append(f"+ {p}")
            elif k not in new:
                out.append(f"- {p}")
            else:
                out.extend(_semantic_diff(old[k], new[k], p))
    elif isinstance(old, list) and isinstance(new, list):

        def _key(x: Any) -> str:
            return str(x.get("id")) if isinstance(x, dict) and x.get("id") else ""

        old_by = {_key(x): x for x in old if _key(x)}
        new_by = {_key(x): x for x in new if _key(x)}
        if old_by or new_by:
            for k in sorted(set(old_by) | set(new_by)):
                p = f"{path}[{k}]"
                if k not in old_by:
                    out.append(f"+ {p}")
                elif k not in new_by:
                    out.append(f"- {p}")
                else:
                    out.extend(_semantic_diff(old_by[k], new_by[k], p))
        elif old != new:
            out.append(
                f"~ {path}: {json.dumps(old, ensure_ascii=False)[:60]} -> "
                f"{json.dumps(new, ensure_ascii=False)[:60]}"
            )
    elif old != new:
        o = json.dumps(old, ensure_ascii=False)
        n = json.dumps(new, ensure_ascii=False)
        out.append(f"~ {path}: {o[:60]} -> {n[:60]}")
    return out


def _stable_equal(a: dict, b: dict) -> bool:
    ka = {k: v for k, v in a.items() if k not in ("updated", "released")}
    kb = {k: v for k, v in b.items() if k not in ("updated", "released")}
    return ka == kb


# --------------------------------------------------------------------- init


def _voice_local_zip(paths: Paths, vid: str, pinned_sha: str) -> str:
    d = paths.cnb / "voices" / vid
    if not d.is_dir():
        return ""
    zips = sorted(d.glob("*.zip"))
    if not zips:
        return ""
    for z in zips:
        side = _sidecar_path(z)
        if side.is_file():
            head = side.read_text(encoding="utf-8", errors="replace").split()
            if head and head[0].lower() == pinned_sha:
                return f"voices/{vid}/{z.name}"
    return f"voices/{vid}/{zips[-1].name}"


def cmd_init(paths: Paths, *, force: bool = False) -> int:
    """从线上真值 index.json 反向生成 YAML 源；configs 只补它独有的字段。"""
    if paths.src.exists() and any(paths.src.iterdir()) and not force:
        print(f"ERROR: {paths.src} 已存在（--force 覆盖）", file=sys.stderr)
        return 2
    if not paths.index_out.is_file():
        print(f"ERROR: 找不到线上真值 {paths.index_out}", file=sys.stderr)
        return 2
    index = json.loads(paths.index_out.read_text(encoding="utf-8"))
    bundled = {}
    if paths.bundled_out.is_file():
        try:
            bundled = json.loads(paths.bundled_out.read_text(encoding="utf-8"))
        except Exception:
            bundled = {}

    hdr = "由 build_catalog.py init 生成；此后人工维护本文件，产物 json 勿手改。"

    _dump_yaml(
        paths.src / "meta.yaml",
        {
            "product": str(index.get("product") or "RVC Fabric"),
            "note": str(index.get("note") or ""),
            "runtime_release_tag": str(
                index.get("runtime_release_tag") or "RVC-runtime"
            ),
            "manifest_urls": list(index.get("manifest_urls") or MANIFEST_URLS),
        },
        hdr,
    )

    # app：bundled（1.1.0-hotfix1 + 真实 gui url/sha256）比 index 新，优先
    app = (bundled.get("app") if isinstance(bundled.get("app"), dict) else None) or (
        index.get("app") or {}
    )
    gui = app.get("gui") if isinstance(app.get("gui"), dict) else {}
    _dump_yaml(
        paths.src / "app.yaml",
        {
            "version": str(app.get("version") or ""),
            "channel": str(app.get("channel") or "stable"),
            "gui": {
                "package_type": str(gui.get("package_type") or "gui_patch"),
                "version": str(gui.get("version") or ""),
                "kind": str(gui.get("kind") or "zip"),
                "sha256": str(gui.get("sha256") or ""),
                "min_app_version": str(gui.get("min_app_version") or ""),
                "notes": str(gui.get("notes") or ""),
            },
        },
        hdr
        + "\ngui.url 由 sha256 推导（LFS）；发新增量包时改 version/sha256/min_app_version。",
    )

    community = index.get("community") or {}
    _dump_yaml(
        paths.src / "community.yaml",
        {
            "qq_group": str(community.get("qq_group") or ""),
            "qq_link": str(community.get("qq_link") or ""),
            "sharepoint_full": str(community.get("sharepoint_full") or ""),
            "note": str(community.get("note") or ""),
        },
        hdr,
    )

    pkgs = index.get("packages") or {}

    def _pkg0(kind: str) -> dict:
        rows = pkgs.get(kind) or []
        return rows[0] if rows and isinstance(rows[0], dict) else {}

    ec_row = _pkg0("engine_core")
    ec_top = (
        bundled.get("engine_core")
        if isinstance(bundled.get("engine_core"), dict)
        else {}
    )
    _dump_yaml(
        paths.src / "engine-core.yaml",
        {
            "file": str(ec_row.get("file") or "assets/core/engine-core-260722.zip"),
            "version": str(ec_row.get("version") or ec_top.get("version") or ""),
            "released": _yymmdd(ec_row.get("released")),
            "channel": str(ec_row.get("channel") or "lfs"),
            "extract_root": str(ec_top.get("extract_root") or "."),
            "sha256": str(ec_row.get("sha256") or ec_top.get("sha256") or ""),
            "size_bytes": int(
                ec_row.get("size_bytes") or ec_top.get("size_bytes") or 0
            ),
            "notes": str(ec_row.get("notes") or ec_top.get("notes") or ""),
        },
        hdr,
    )

    vb_row = _pkg0("vbcable")
    vb_top = index.get("vbcable") if isinstance(index.get("vbcable"), dict) else {}
    _dump_yaml(
        paths.src / "vbcable.yaml",
        {
            "display_name": str(vb_row.get("name") or "VB-Cable Setup Pack"),
            "file": str(vb_row.get("file") or "vbcable/vbcable-setup.zip"),
            "version": str(vb_row.get("version") or vb_top.get("version") or "1.0.0"),
            "released": _yymmdd(vb_row.get("released")),
            "channel": str(vb_row.get("channel") or "lfs"),
            "extract_root": str(vb_top.get("extract_root") or "VBCABLE"),
            "sha256": str(vb_row.get("sha256") or vb_top.get("sha256") or ""),
            "size_bytes": int(
                vb_row.get("size_bytes") or vb_top.get("size_bytes") or 0
            ),
            "notes": str(vb_row.get("notes") or vb_top.get("notes") or ""),
        },
        hdr,
    )

    st_row = _pkg0("setup")
    _dump_yaml(
        paths.src / "setup.yaml",
        {
            "display_name": str(st_row.get("name") or "RVC Fabric Setup"),
            "file": str(st_row.get("file") or "setup/RVC_Fabric_Setup.exe"),
            "version": str(st_row.get("version") or ""),
            "released": _yymmdd(st_row.get("released")),
            "channel": str(st_row.get("channel") or "lfs"),
            "sha256": str(st_row.get("sha256") or ""),
            "size_bytes": int(st_row.get("size_bytes") or 0),
            "notes": str(st_row.get("notes") or ""),
        },
        hdr,
    )

    rt_rows = {
        str(r.get("variant")): r
        for r in (pkgs.get("runtime") or [])
        if isinstance(r, dict)
    }
    for variant, spec in (index.get("runtimes") or {}).items():
        if variant not in VALID_VARIANTS or not isinstance(spec, dict):
            continue
        parts = []
        for p in spec.get("parts") or []:
            parts.append(
                {
                    "file": f"runtime/{variant}/{p.get('name')}",
                    "sha256": str(p.get("sha256") or ""),
                    "size_bytes": int(p.get("size_bytes") or 0),
                }
            )
        row = rt_rows.get(variant) or {}
        data = {
            "variant": variant,
            "label": str(spec.get("label") or variant),
            "version": str(spec.get("version") or ""),
            "released": _yymmdd(row.get("released") or spec.get("version")),
            "format": str(spec.get("format") or "tar"),
            "channel": str(spec.get("channel") or ""),
            "extract_root": str(spec.get("extract_root") or "Runtime"),
        }
        if spec.get("release_tag"):
            data["release_tag"] = str(spec["release_tag"])
        data["parts"] = parts
        _dump_yaml(
            paths.src / "runtimes" / f"{variant}.yaml",
            data,
            hdr
            + "\nsha256/size_bytes 为已发布锁定值；重发 Runtime 时更新为新制品的值。",
        )

    bundled_series = {
        str(v.get("id")): str(v.get("series") or "")
        for v in (bundled.get("voices") or [])
        if isinstance(v, dict)
    }
    for v in index.get("voices") or []:
        if not isinstance(v, dict) or not v.get("id"):
            continue
        vid = str(v["id"])
        series = bundled_series.get(vid, "")
        if not series and "mygo" in str(v.get("description") or "").lower():
            series = "MyGO!!!!!"
        sha = str(v.get("sha256") or "").lower()
        data = {
            "id": vid,
            "name": str(v.get("name") or vid),
            "tag": str(v.get("tag") or "音色"),
        }
        if series:
            data["series"] = series
        data.update(
            {
                "author": str(v.get("author") or "RVC Fabric"),
                "author_url": str(v.get("author_url") or ""),
                "date": _yymmdd(v.get("date") or v.get("released")),
                "version": str(v.get("version") or "1"),
                "description": str(v.get("description") or ""),
                "file": _voice_local_zip(paths, vid, sha),
                "cover": str(v.get("cover") or f"ch-banner/{vid}.jpg"),
                "sha256": sha,
                "size_bytes": int(v.get("size_bytes") or 0),
            }
        )
        _dump_yaml(paths.src / "voices" / f"{vid}.yaml", data, hdr)

    (paths.src / "plaza.yaml").write_text(_PLAZA_YAML_TEMPLATE, encoding="utf-8")
    (paths.src / "changelog.yaml").write_text(
        _CHANGELOG_YAML_TEMPLATE, encoding="utf-8"
    )

    n = len(list((paths.src / "voices").glob("*.yaml")))
    print(
        f"init 完成: {paths.src}（voices={n}，runtimes={len(index.get('runtimes') or {})}）"
    )
    print(
        "请人工核对 YAML（尤其 series 归类）后运行: python scripts/build_catalog.py build --diff"
    )
    return 0


# -------------------------------------------------------------- check/build


def _compile_all(paths: Paths) -> tuple[Optional[dict], Report]:
    rep = Report()
    src = load_sources(paths, rep)
    outputs = compile_catalog(src, paths, rep) if not rep.errors else None
    if outputs:
        _roundtrip_check(outputs, src, rep)
        n_err = len(rep.errors)
        outputs["changelog"] = src.get("_changelog_compiled") or compile_changelog(
            src, rep
        )
        outputs["plaza"] = compile_plaza(src, paths, rep)
        if len(rep.errors) == n_err:  # 编译干净才回环，避免级联报错
            _plaza_roundtrip(outputs["plaza"], rep)
            _changelog_roundtrip(outputs["changelog"], rep)
    return outputs, rep


def _collect_urls(node: Any, out: set[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("url", "pack_url", "sha256_url") and isinstance(v, str):
                if v.startswith("http"):
                    out.add(v)
            elif k in ("urls", "sha256_urls") and isinstance(v, list):
                out.update(u for u in v if isinstance(u, str) and u.startswith("http"))
            else:
                _collect_urls(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_urls(v, out)


def probe_urls(outputs: dict, rep: Report, *, include_external: bool = False) -> None:
    """把清单里每条下载地址真的拉一下头 8 字节。

    加这个是因为迁移之后出过一次：`check` 全绿，线上 engine-core / VB-Cable /
    Setup 三条全是 404 —— URL 语法完全正确，只是指向的 release tag 里没有那个
    附件。静态校验永远看不出这种错，只有真去拉一次才知道。

    HEAD 在 CNB 的 LFS 端点上不可靠（GET 能下的对象 HEAD 会回 404），所以统一
    用 Range 拉前 8 字节。CNB 的错误响应是 JSON，开头 `{"er`，据此和真制品区分。
    """
    import urllib.error
    import urllib.request

    urls: set[str] = set()
    _collect_urls(outputs, urls)
    targets = sorted(
        u for u in urls if include_external or "cnb.cool" in u
    )
    if not targets:
        return
    print(f"--- 链接探活（{len(targets)} 条）---")
    for u in targets:
        req = urllib.request.Request(
            u,
            headers={
                "Range": "bytes=0-7",
                "User-Agent": "Turing-Mirror/RVC-Fabric build_catalog",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                head = r.read(8)
                if head.startswith(b'{"er'):
                    rep.error(f"下载地址返回错误 JSON（附件不存在？）: {u}")
                    print(f"  坏  {u}")
                else:
                    print(f"  OK  {u}")
        except urllib.error.HTTPError as e:
            rep.error(f"下载地址 HTTP {e.code}: {u}")
            print(f"  坏  HTTP {e.code}  {u}")
        except Exception as e:  # 网络抖动不该把 check 判死，但要说出来
            rep.warn(f"下载地址探活失败（网络？）: {u} — {e}")
            print(f"  ？  {u}")


def cmd_check(paths: Paths, *, strict: bool = False, urls: bool = False) -> int:
    outputs, rep = _compile_all(paths)
    if urls and outputs is not None:
        probe_urls(outputs, rep)
    rep.print()
    if rep.failed(strict) or outputs is None:
        print(f"check 失败（错误 {len(rep.errors)}，警告 {len(rep.warnings)}）")
        return 1
    n_cl = len((outputs.get("changelog") or {}).get("entries") or [])
    print(
        f"check 通过（警告 {len(rep.warnings)}，音色 {len(outputs['index']['voices'])} 个，"
        f"广场 {len(outputs['plaza']['items'])} 条，更新日志 {n_cl} 条）"
    )
    return 0


def cmd_build(paths: Paths, *, strict: bool = False, show_diff: bool = False) -> int:
    outputs, rep = _compile_all(paths)
    rep.print()
    if rep.failed(strict) or outputs is None:
        print("build 中止：先修复上述问题")
        return 1

    index = outputs["index"]
    old_index: dict = {}
    if paths.index_out.is_file():
        try:
            old_index = json.loads(paths.index_out.read_text(encoding="utf-8"))
        except Exception:
            old_index = {}

    if _stable_equal(index, old_index):
        index["updated"] = str(
            old_index.get("updated") or datetime.now().strftime("%Y-%m-%d")
        )
        index["released"] = str(
            old_index.get("released") or datetime.now().strftime("%y%m%d")
        )
    else:
        index["updated"] = datetime.now().strftime("%Y-%m-%d")
        index["released"] = datetime.now().strftime("%y%m%d")

    if show_diff and old_index:
        lines = _semantic_diff(
            {k: v for k, v in old_index.items() if k not in ("updated", "released")},
            {k: v for k, v in index.items() if k not in ("updated", "released")},
        )
        print("--- index.json 语义 diff（不含时间戳）---")
        if lines:
            for ln in lines:
                print(" ", ln)
        else:
            print("  （无变化）")
        print("---")

    plaza = outputs["plaza"]
    changelog = outputs.get("changelog") or {"schema": 1, "entries": []}
    if show_diff and paths.plaza_out.is_file():
        old_plaza: dict = {}
        try:
            old_plaza = json.loads(paths.plaza_out.read_text(encoding="utf-8"))
        except Exception:
            old_plaza = {}
        lines = _semantic_diff(old_plaza, plaza)
        print("--- plaza.json 语义 diff ---")
        if lines:
            for ln in lines:
                print(" ", ln)
        else:
            print("  （无变化）")
        print("---")
    if show_diff and paths.changelog_out.is_file():
        old_cl: dict = {}
        try:
            old_cl = json.loads(paths.changelog_out.read_text(encoding="utf-8"))
        except Exception:
            old_cl = {}
        lines = _semantic_diff(old_cl, changelog)
        print("--- changelog.json 语义 diff ---")
        if lines:
            for ln in lines:
                print(" ", ln)
        else:
            print("  （无变化）")
        print("---")

    _write_json(paths.index_out, index)
    _write_json(paths.snippet_out, outputs["snippet"])
    _write_json(paths.bundled_out, outputs["bundled"])
    _write_json(paths.plaza_out, plaza)
    _write_json(paths.changelog_out, changelog)
    print(
        f"已写出:\n  {paths.index_out}\n  {paths.snippet_out}\n"
        f"  {paths.bundled_out}\n  {paths.plaza_out}\n  {paths.changelog_out}"
    )
    print(
        f"（音色 {len(index['voices'])} 个，广场 {len(plaza['items'])} 条，"
        f"更新日志 {len(changelog.get('entries') or [])} 条，警告 {len(rep.warnings)}）"
    )
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="CNB 清单编译器（YAML 源 → JSON 产物）")
    ap.add_argument(
        "--cnb", type=Path, default=None, help="CNB-GIT-RELEASE 目录（默认仓内）"
    )
    ap.add_argument(
        "--bundled",
        type=Path,
        default=None,
        help="configs/online_catalog.json 输出路径",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init", help="从线上 index.json 反向生成 YAML 源（一次性）")
    p_init.add_argument("--force", action="store_true")
    p_check = sub.add_parser("check", help="只校验，不写文件（CI 可用）")
    p_check.add_argument("--strict", action="store_true", help="警告也算失败")
    p_check.add_argument(
        "--urls", action="store_true", help="真去拉一次每条下载地址（要联网，慢）"
    )
    p_build = sub.add_parser("build", help="校验并写出四份 JSON 产物")
    p_build.add_argument("--strict", action="store_true")
    p_build.add_argument("--diff", action="store_true", help="写出前打印语义 diff")
    args = ap.parse_args(argv)

    paths = Paths(cnb=args.cnb, bundled=args.bundled)
    if args.cmd == "init":
        return cmd_init(paths, force=args.force)
    if args.cmd == "check":
        return cmd_check(paths, strict=args.strict, urls=args.urls)
    return cmd_build(paths, strict=args.strict, show_diff=args.diff)


if __name__ == "__main__":
    raise SystemExit(main())
