# -*- coding: utf-8 -*-
"""发布前验证一条音色能不能用 —— 下载、拆开、确认里面真是 RVC 模型。

人话：清单里写着某个 Hugging Face 直链，但那串字节到底是不是一个能跑的 RVC
音色，在这一步之前从来没有人确认过。zip 可能是空壳、可能只有训练中间产物
（G_/D_），也可能整个是 SoVITS —— 这三种都能正常下载、正常解压、里面也确实
有 .pth，用户要等到点「开启变声」才发现不对。

所以收编第三方音色时先跑这个脚本。它做三件事：

1. 把制品真的下载下来，算 sha256。清单里原本的哈希来自 Hugging Face 的 API
   元数据（``lfs.oid``），是「HF 说它是这个」；跑完这一步才变成「我们下过、
   打开过、确认是这个」。
2. 按**和客户端完全相同的规则**在包里挑 pth / index（见
   ``app/src-tauri/src/store.rs`` 的 ``find_first``），把挑中的文件名记下来。
   记名字是为了留证据和排障，客户端仍然用它自己那套启发式——哈希已经钉死了
   字节，让客户端去读清单里的文件名只会多一种失败模式。
3. 用 torch 打开 pth，确认它有 RVC 检查点该有的结构。这一条才是分水岭：
   前两条挡不住「能解压、有 .pth、但那是 SoVITS」。

安全上有一条硬规矩：**永远用 ``weights_only=True`` 加载**。.pth 是 pickle，
反序列化等于执行任意代码——我们正是要保护用户不吃这一口，自己就更不能为了
「验证」而去执行它。安全模式下加载不了的包，结论是「验证不通过」，不是
「换个不安全的方式再试」。

用法::

    # 单个仓库（形态自动判断）
    python scripts/verify_voice_pack.py --hf AppleAndA/ATRI_RVC_Models

    # 指定包内路径（大合集仓必须指定）
    python scripts/verify_voice_pack.py --hf ArkanDash/rvc-genshin-impact \\
        --pack "prezipped/v2/furina-jp 275 epochs 48k v2.zip"

    # 直接验一个已经写好的 YAML，并把结果写回去
    python scripts/verify_voice_pack.py --yaml <发布仓>/catalog-src/thirdparty/tp-atri.yaml --write

torch 不在时只做第 1、2 两层，结论会标成 ``pth_struct_unchecked``；这种条目
不应该发布。装法见 docs/第三方音色收编与验证.md。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENDPOINT = "https://hf-mirror.com"
CANONICAL = "https://huggingface.co"
UA = "Turing-Mirror/RVC-Fabric (https://github.com/Turing-Mirror/RVC-Fabric)"
TIMEOUT = 60

# 与客户端 store.rs 保持一致：小于这个体积的 .pth 视为损坏。
MIN_PTH_BYTES = 1_000_000
# 同上，index 小于这个体积就当没有。
MIN_INDEX_BYTES = 1000


def _cache_dir() -> Path:
    d = Path(os.environ.get("RVCF_VERIFY_CACHE") or (ROOT / ".verify-cache"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _to_endpoint(url: str, endpoint: str) -> str:
    """清单里存 huggingface.co 规范形态；下载走镜像。"""
    if endpoint and url.startswith(CANONICAL):
        return endpoint.rstrip("/") + url[len(CANONICAL) :]
    return url


def cache_path(url: str) -> Path:
    """缓存文件名带 URL 指纹。

    直接拿 URL 的 basename 当缓存名会撞车：binant 的初音和 Trump 两个仓库里
    都有一个叫 model.pth 的文件，第二个会当场复用第一个的缓存，验证结果就是
    另一条音色的。第一次批量跑就踩到了。
    """
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    name = urllib.parse.unquote(url.rsplit("/", 1)[-1]) or "artifact"
    return _cache_dir() / f"{digest}-{name}"


def download(url: str, dest: Path, *, quiet: bool = False) -> Path:
    """下载到 dest（已存在且非空则复用）。"""
    if dest.is_file() and dest.stat().st_size > 0:
        if not quiet:
            print(f"  复用缓存 {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with tmp.open("wb") as f:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if not quiet and total:
                    pct = done * 100 // total
                    print(f"\r  下载 {dest.name} {pct:3d}%", end="", flush=True)
    if not quiet:
        print()
    tmp.replace(dest)
    return dest


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 包内挑文件 —— 规则必须和 store.rs 的 find_first 一致
# ---------------------------------------------------------------------------


def _find_content_root(base: Path) -> Path:
    """跳过外面套的那一层目录（很多包解开是 <名字>/ 里面才是内容）。"""
    entries = [p for p in base.iterdir() if not p.name.startswith(".")]
    if len(entries) == 1 and entries[0].is_dir():
        return _find_content_root(entries[0])
    return base


def _find_first(root: Path, ext: str) -> Optional[Path]:
    """深度优先找第一个该扩展名的文件，取最大的那个。"""
    hits = [p for p in root.rglob(f"*.{ext}") if p.is_file()]
    if not hits:
        return None
    hits.sort(key=lambda p: p.stat().st_size, reverse=True)
    return hits[0]


def inspect_zip(zip_path: Path, work: Path) -> dict[str, Any]:
    """解压并按客户端规则挑 pth / index。"""
    out: dict[str, Any] = {"checks": [], "errors": []}
    try:
        with zipfile.ZipFile(zip_path) as zf:
            bad = [
                n
                for n in zf.namelist()
                if n.startswith("/") or ".." in Path(n).parts or ":" in n
            ]
            if bad:
                out["errors"].append(f"包内路径不安全（会写到解压目录外）: {bad[:3]}")
                return out
            out["members"] = len(zf.namelist())
            zf.extractall(work)
    except zipfile.BadZipFile as e:
        out["errors"].append(f"zip 打不开: {e}")
        return out
    out["checks"].append("zip_ok")

    content = _find_content_root(work)
    pth = _find_first(content, "pth")
    if pth is None:
        out["errors"].append("包内没有 .pth")
        return out
    out["pth"] = pth.name
    out["pth_path"] = pth
    if pth.stat().st_size < MIN_PTH_BYTES:
        out["errors"].append(
            f".pth 过小（{pth.stat().st_size} 字节），客户端会判为损坏"
        )
        return out

    idx = _find_first(content, "index")
    if idx is not None and idx.stat().st_size > MIN_INDEX_BYTES:
        out["index"] = idx.name
        out["index_path"] = idx
    return out


# ---------------------------------------------------------------------------
# 第二层：确认 pth 真是 RVC 检查点
# ---------------------------------------------------------------------------

# RVC 检查点必有的键；SoVITS / VITS / 训练中间产物都对不上这一组。
REQUIRED_KEYS = ("weight", "config")


def inspect_pth(pth: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"checks": [], "errors": []}
    try:
        import torch  # noqa: PLC0415  — 可选依赖，缺了就降级
    except ImportError:
        out["errors"].append(
            "torch 不可用，无法确认 pth 结构（这条不应该发布）"
        )
        out["unchecked"] = True
        return out

    try:
        # weights_only=True 是硬要求：pth 是 pickle，反序列化等于执行任意代码。
        # 我们正是要保护用户不吃这一口，自己更不能为了「验证」去执行它。
        cpt = torch.load(str(pth), map_location="cpu", weights_only=True)
    except Exception as e:  # noqa: BLE001 — 任何失败都是「验证不通过」
        out["errors"].append(
            f"安全模式下加载失败（不会改用不安全方式重试）: {type(e).__name__}: {e}"
        )
        return out

    if not isinstance(cpt, dict):
        out["errors"].append(f"pth 顶层不是 dict，而是 {type(cpt).__name__}")
        return out
    missing = [k for k in REQUIRED_KEYS if k not in cpt]
    if missing:
        out["errors"].append(
            f"缺少 RVC 检查点必需的键 {missing}；实际有 {sorted(cpt)[:8]}"
            "（SoVITS / VITS / 训练中间产物会长这样）"
        )
        return out
    out["checks"].append("pth_struct_ok")
    out["version"] = str(cpt.get("version") or "")
    out["sr"] = cpt.get("sr")
    out["f0"] = cpt.get("f0")
    return out


def inspect_index(idx: Path) -> dict[str, Any]:
    """index 能不能读。faiss 缺席时退化成体积 + 非空检查。"""
    out: dict[str, Any] = {"checks": [], "errors": []}
    if idx.stat().st_size <= MIN_INDEX_BYTES:
        out["errors"].append("index 过小，客户端会忽略它")
        return out
    try:
        import faiss  # noqa: PLC0415 — 可选
    except ImportError:
        out["checks"].append("index_present")
        return out
    try:
        faiss.read_index(str(idx))
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"faiss 读不了 index: {type(e).__name__}: {e}")
        return out
    out["checks"].append("index_readable")
    return out


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def verify(
    *,
    pack_url: str = "",
    pth_url: str = "",
    index_url: str = "",
    endpoint: str = DEFAULT_ENDPOINT,
    keep: bool = False,
) -> dict[str, Any]:
    _cache_dir()
    result: dict[str, Any] = {
        "ok": False,
        "at": datetime.now().strftime("%y%m%d"),
        "checks": [],
        "errors": [],
    }
    work = Path(tempfile.mkdtemp(prefix="rvcf-verify-"))
    try:
        if pack_url:
            url = _to_endpoint(pack_url, endpoint)
            zp = download(url, cache_path(pack_url))
            result["sha256"] = sha256_file(zp)
            result["size_bytes"] = zp.stat().st_size
            got = inspect_zip(zp, work)
            result["checks"] += got.get("checks", [])
            result["errors"] += got.get("errors", [])
            if got.get("errors"):
                return result
            result["pth"] = got.get("pth", "")
            if got.get("index"):
                result["index"] = got["index"]
            pth_path = got.get("pth_path")
            index_path = got.get("index_path")
        else:
            if not pth_url:
                result["errors"].append("既没有 pack_url 也没有 pth_url")
                return result
            pth_path = download(_to_endpoint(pth_url, endpoint), cache_path(pth_url))
            # 记原始文件名，不是本地缓存名（缓存名带 URL 指纹前缀）。
            result["pth"] = urllib.parse.unquote(pth_url.rsplit("/", 1)[-1])
            result["sha256"] = sha256_file(pth_path)
            size = pth_path.stat().st_size
            index_path = None
            if index_url:
                index_path = download(
                    _to_endpoint(index_url, endpoint), cache_path(index_url)
                )
                result["index"] = urllib.parse.unquote(index_url.rsplit("/", 1)[-1])
                result["index_sha256"] = sha256_file(index_path)
                # 商店显示的体积必须是用户实际要下的总量。只记 pth 的话，
                # ATRI 会显示 57 MB 而实际下 590 MB。
                size += index_path.stat().st_size
            result["size_bytes"] = size
            if pth_path.stat().st_size < MIN_PTH_BYTES:
                result["errors"].append(".pth 过小，客户端会判为损坏")
                return result
            result["checks"].append("files_ok")

        got = inspect_pth(pth_path)
        result["checks"] += got.get("checks", [])
        result["errors"] += got.get("errors", [])
        for k in ("version", "sr", "f0"):
            if got.get(k) is not None:
                result[k] = got[k]
        if got.get("unchecked"):
            result["unchecked"] = True
        if got.get("errors"):
            return result

        if index_path is not None:
            got = inspect_index(index_path)
            result["checks"] += got.get("checks", [])
            result["errors"] += got.get("errors", [])

        result["ok"] = not result["errors"]
        return result
    finally:
        if keep:
            print(f"  解压内容保留在 {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)


def _yaml_block(res: dict[str, Any]) -> str:
    lines = ["verified:", f"  at: '{res['at']}'"]
    if res.get("pth"):
        lines.append(f"  pth: {res['pth']}")
    if res.get("index"):
        lines.append(f"  index: {res['index']}")
    if res.get("version"):
        lines.append(f"  rvc_version: '{res['version']}'")
    lines.append("  checks: [" + ", ".join(res.get("checks", [])) + "]")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="下载并验证一条音色的制品，确认里面真是可用的 RVC 模型"
    )
    ap.add_argument("--hf", default="", help="org/repo（配合 --pack / --pth）")
    ap.add_argument("--pack", default="", help="仓库内 zip 相对路径")
    ap.add_argument("--pth", default="", help="仓库内 .pth 相对路径")
    ap.add_argument("--index", default="", help="仓库内 .index 相对路径")
    ap.add_argument("--pack-url", default="", help="直接给 zip 完整 URL")
    ap.add_argument("--pth-url", default="", help="直接给 pth 完整 URL")
    ap.add_argument("--index-url", default="", help="直接给 index 完整 URL")
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="下载镜像根")
    ap.add_argument("--json", action="store_true", help="只输出 JSON")
    ap.add_argument("--keep", action="store_true", help="保留解压内容供人工过目")
    args = ap.parse_args()

    def hf_url(rel: str) -> str:
        if not rel:
            return ""
        quoted = urllib.parse.quote(rel)
        return f"{CANONICAL}/{args.hf}/resolve/main/{quoted}"

    pack_url = args.pack_url or hf_url(args.pack)
    pth_url = args.pth_url or hf_url(args.pth)
    index_url = args.index_url or hf_url(args.index)

    if not (pack_url or pth_url):
        ap.error("需要 --pack / --pth（配合 --hf）或 --pack-url / --pth-url")

    if not args.json:
        print(f"验证 {args.hf or pack_url or pth_url}")
    res = verify(
        pack_url=pack_url,
        pth_url=pth_url,
        index_url=index_url,
        endpoint=args.endpoint,
        keep=args.keep,
    )
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["ok"] else 1

    print()
    for e in res["errors"]:
        print(f"  [不通过] {e}")
    if res["ok"]:
        print(f"  [通过] {' / '.join(res['checks'])}")
        print(f"  sha256      {res['sha256']}")
        print(f"  size_bytes  {res['size_bytes']}")
        if res.get("index_sha256"):
            print(f"  index_sha256 {res['index_sha256']}")
        print()
        print(_yaml_block(res))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
