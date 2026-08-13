# -*- coding: utf-8 -*-
"""收编公开社区音色（Hugging Face 等）→ catalog-src/thirdparty/<id>.yaml。

人话：在「模型托管站」上看中某个公开 RVC 模型后，用本脚本生成清单条目；
人工过目名字/封面后，再 build_catalog 发布。客户端不爬网，只下载清单里的直链。

用法::

    python scripts/add_thirdparty_voice.py --hf binant/Hatsune_Miku__RVC_v2_ ^
        --name 初音未来 --tag 二次元 --series VOCALOID --yes

    python scripts/add_thirdparty_voice.py --hf user/repo --real-person --no-cover --yes
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]


def _default_cnb() -> Path:
    """发布仓工作区。见 build_catalog.default_cnb_dir —— 两处必须一致。

    环境变量 RVCF_CNB_DIR → 同级的 RVC-Fabric-Release → 仓内旧位置。
    """
    env = os.environ.get("RVCF_CNB_DIR")
    if env:
        return Path(env).expanduser()
    sibling = ROOT.parent / "RVC-Fabric-Release"
    if (sibling / ".git").exists():
        return sibling
    return ROOT / "CNB-GIT-RELEASE"


DEFAULT_CNB = _default_cnb()
DEFAULT_ENDPOINT = "https://hf-mirror.com"
UA = "Turing-Mirror/RVC-Fabric (https://github.com/Turing-Mirror/RVC-Fabric)"
TIMEOUT = 15


def _http_json(url: str) -> Any:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _http_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def _today_yymmdd() -> str:
    return datetime.now().strftime("%y%m%d")


def _slug_id(repo: str, explicit: str) -> str:
    if explicit:
        s = explicit.strip()
        if not s.startswith("tp-"):
            s = "tp-" + s
        return re.sub(r"[^a-zA-Z0-9_\-]", "-", s).lower()
    name = repo.split("/")[-1] if "/" in repo else repo
    name = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    if not name:
        name = "voice"
    return f"tp-{name[:40]}"


def _guess_name(filename: str, repo: str) -> str:
    base = Path(filename or repo.split("/")[-1]).stem
    s = re.sub(r"[_\-.]+", " ", base)
    drop = re.compile(
        r"\b(rvc|v1|v2|v3|model|voice|ai|tts|harvest|crepe|rmvpe|fcpe|"
        r"e\d+\s*epochs?|s\d+\s*steps?|\d+k|\d+\s*epoch)\b",
        re.I,
    )
    s = drop.sub(" ", s)
    s = re.sub(r"[\(\[\{].*?[\)\]\}]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or base or repo


def _pick_artifacts(tree: list) -> dict[str, Any]:
    """优先最大 .pth（>50KB）+ 同干 .index；否则唯一 zip。"""
    files = [x for x in tree if isinstance(x, dict) and x.get("type") == "file"]
    pths = []
    for f in files:
        path = str(f.get("path") or "")
        if not path.lower().endswith(".pth"):
            continue
        size = int((f.get("lfs") or {}).get("size") or f.get("size") or 0)
        if size < 50_000 and size != 0:
            continue
        if size == 0:
            size = int(f.get("size") or 0)
        if size < 50_000:
            continue
        oid = str((f.get("lfs") or {}).get("oid") or "").lower()
        pths.append((size, path, oid))
    pths.sort(reverse=True)
    if pths:
        size, path, oid = pths[0]
        stem = Path(path).stem
        index_path = ""
        for f in files:
            p = str(f.get("path") or "")
            if p.lower().endswith(".index") and Path(p).stem == stem:
                index_path = p
                break
        if not index_path:
            # 常见 model.pth + model.index 或 任意 .index
            for f in files:
                p = str(f.get("path") or "")
                if p.lower().endswith(".index"):
                    index_path = p
                    break
        return {
            "kind": "voice_files",
            "pth": path,
            "index": index_path,
            "sha256": oid,
            "size_bytes": size,
            "candidates": [p for _, p, _ in pths[:8]],
        }
    zips = []
    for f in files:
        path = str(f.get("path") or "")
        if not path.lower().endswith(".zip"):
            continue
        size = int((f.get("lfs") or {}).get("size") or f.get("size") or 0)
        oid = str((f.get("lfs") or {}).get("oid") or "").lower()
        zips.append((size, path, oid))
    zips.sort(reverse=True)
    if zips:
        size, path, oid = zips[0]
        return {
            "kind": "voice_pack",
            "pack": path,
            "sha256": oid,
            "size_bytes": size,
            "candidates": [p for _, p, _ in zips[:8]],
        }
    raise SystemExit("仓库里找不到可用的 .pth（>50KB）或 .zip")


def _resolve_url(endpoint: str, repo: str, path: str) -> str:
    # 清单统一存 huggingface.co 规范形态；客户端再按镜像重写。
    # 路径里的空格/中文必须 percent-encode，否则 urllib / 部分下载器直接拒。
    import urllib.parse

    segs = [urllib.parse.quote(s, safe="") for s in path.replace("\\", "/").split("/")]
    quoted = "/".join(segs)
    return f"https://huggingface.co/{repo}/resolve/main/{quoted}"


def _bangumi_search(keyword: str) -> list[dict]:
    """Bangumi 角色搜索；失败返回空列表。"""
    body = json.dumps({"keyword": keyword}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "https://api.bgm.tv/v0/search/characters",
        data=body,
        headers={
            "User-Agent": UA,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        print(f"[warn] Bangumi 搜索失败: {e}", file=sys.stderr)
        return []
    items = (
        data if isinstance(data, list) else data.get("data") or data.get("list") or []
    )
    out = []
    for it in items[:5]:
        if not isinstance(it, dict):
            continue
        images = it.get("images") or {}
        img = (
            images.get("large")
            or images.get("medium")
            or images.get("common")
            or images.get("grid")
            or ""
        )
        out.append(
            {
                "id": it.get("id"),
                "name": it.get("name") or it.get("name_cn") or "",
                "name_cn": it.get("name_cn") or "",
                "image": img,
            }
        )
    return out


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml  # type: ignore

        text = yaml.safe_dump(
            data, allow_unicode=True, sort_keys=False, default_flow_style=False
        )
    except ImportError:
        # 无 PyYAML 时手写最小子集
        lines = []
        for k, v in data.items():
            if isinstance(v, bool):
                lines.append(f"{k}: {'true' if v else 'false'}")
            elif isinstance(v, (int, float)):
                lines.append(f"{k}: {v}")
            elif v is None:
                continue
            else:
                s = str(v).replace('"', '\\"')
                # 空格也必须引号：否则 YAML 可能把 `...ayaka-jp 101 epochs` 折成多行
                if any(c in s for c in ":#\n ") or s == "":
                    lines.append(f'{k}: "{s}"')
                else:
                    lines.append(f"{k}: {s}")
        text = "\n".join(lines) + "\n"
    header = (
        "# 第三方音色（人工维护）— 收录自公开社区站点，非 RVC Fabric 官方。\n"
        f"# 源: {data.get('source_url', '')}\n"
    )
    path.write_text(header + text, encoding="utf-8")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="收编 Hugging Face 公开 RVC 音色到 thirdparty/"
    )
    ap.add_argument(
        "--hf", required=True, help="仓库 org/name，如 binant/Hatsune_Miku__RVC_v2_"
    )
    ap.add_argument(
        "--id", default="", help="音色 id（默认 tp- + 仓库名；强制 tp- 前缀）"
    )
    ap.add_argument("--name", default="", help="展示名")
    ap.add_argument("--tag", default="二次元", help="标签，如 二次元 / 真人")
    ap.add_argument("--series", default="", help="系列名（仅搜索，不进系列专区）")
    ap.add_argument("--group", default="", help="系列内社团/部门，如 研讨会")
    ap.add_argument("--real-person", action="store_true", help="真人条目，跳过 Bangumi")
    ap.add_argument("--no-cover", action="store_true", help="不下载封面")
    ap.add_argument("--bangumi-id", type=int, default=0, help="指定 Bangumi 角色 id")
    ap.add_argument("--pth-path", default="", help="多候选时指定仓库内 .pth 相对路径")
    ap.add_argument(
        "--pack-path",
        default="",
        help="大合集仓内指定 zip 相对路径（与 --pth-path 二选一）",
    )
    ap.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help="查询 API 用的镜像根（默认 hf-mirror.com）",
    )
    ap.add_argument(
        "--cnb",
        default=str(DEFAULT_CNB),
        help="CNB-GIT-RELEASE 路径",
    )
    ap.add_argument(
        "--yes",
        action="store_true",
        help="非交互：直接接受启发式名字，不询问",
    )
    args = ap.parse_args(argv)

    repo = args.hf.strip().strip("/")
    if repo.count("/") != 1:
        print("错误: --hf 须为 org/name", file=sys.stderr)
        return 2
    endpoint = (args.endpoint or DEFAULT_ENDPOINT).rstrip("/")
    cnb = Path(args.cnb)

    print(f"查询 {endpoint}/api/models/{repo} …")
    try:
        info = _http_json(f"{endpoint}/api/models/{repo}")
    except urllib.error.HTTPError as e:
        print(f"错误: 模型 API HTTP {e.code}: {e.reason}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"错误: 无法访问模型 API: {e}", file=sys.stderr)
        return 1
    if isinstance(info, dict) and info.get("error"):
        print(f"错误: {info.get('error')}", file=sys.stderr)
        return 1

    downloads = int(info.get("downloads") or 0)
    likes = int(info.get("likes") or 0)
    author = str(info.get("author") or repo.split("/")[0])

    print(f"拉取文件树 …")
    try:
        tree = _http_json(f"{endpoint}/api/models/{repo}/tree/main?recursive=true")
    except Exception as e:
        print(f"错误: 文件树失败: {e}", file=sys.stderr)
        return 1
    if not isinstance(tree, list):
        print(f"错误: 文件树格式异常: {tree}", file=sys.stderr)
        return 1

    if args.pth_path and args.pack_path:
        print("错误: --pth-path 与 --pack-path 只能选一个", file=sys.stderr)
        return 2

    if args.pack_path:
        hit = next(
            (
                x
                for x in tree
                if isinstance(x, dict) and str(x.get("path")) == args.pack_path
            ),
            None,
        )
        if not hit:
            print(f"错误: 找不到 --pack-path {args.pack_path}", file=sys.stderr)
            return 1
        art = {
            "kind": "voice_pack",
            "pack": args.pack_path,
            "sha256": str((hit.get("lfs") or {}).get("oid") or "").lower(),
            "size_bytes": int(
                (hit.get("lfs") or {}).get("size") or hit.get("size") or 0
            ),
            "candidates": [],
        }
    elif args.pth_path:
        # 人工指定路径
        hit = next(
            (
                x
                for x in tree
                if isinstance(x, dict) and str(x.get("path")) == args.pth_path
            ),
            None,
        )
        if not hit:
            print(f"错误: 找不到 --pth-path {args.pth_path}", file=sys.stderr)
            return 1
        art = {
            "kind": "voice_files",
            "pth": args.pth_path,
            "index": "",
            "sha256": str((hit.get("lfs") or {}).get("oid") or "").lower(),
            "size_bytes": int(
                (hit.get("lfs") or {}).get("size") or hit.get("size") or 0
            ),
            "candidates": [],
        }
        stem = Path(args.pth_path).stem
        pth_dir = str(Path(args.pth_path).parent).replace("\\", "/")
        if pth_dir == ".":
            pth_dir = ""
        # 优先：同目录 + 同 stem；其次同目录任意 index；再退回全仓
        same_dir: list[str] = []
        for x in tree:
            if not isinstance(x, dict):
                continue
            p = str(x.get("path") or "").replace("\\", "/")
            if not p.lower().endswith(".index"):
                continue
            parent = str(Path(p).parent).replace("\\", "/")
            if parent == ".":
                parent = ""
            if pth_dir and parent != pth_dir:
                continue
            same_dir.append(p)
        if same_dir:
            exact = [p for p in same_dir if Path(p).stem == stem]
            art["index"] = exact[0] if exact else same_dir[0]
        else:
            for x in tree:
                if not isinstance(x, dict):
                    continue
                p = str(x.get("path") or "")
                if p.lower().endswith(".index") and Path(p).stem == stem:
                    art["index"] = p
                    break
    else:
        art = _pick_artifacts(tree)
        if len(art.get("candidates") or []) > 1:
            print("候选文件:")
            for c in art["candidates"]:
                mark = " *" if c == art.get("pth") or c == art.get("pack") else ""
                print(f"  {c}{mark}")
            print("（可用 --pth-path / --pack-path 指定）")

    vid = _slug_id(repo, args.id)
    guess = _guess_name(
        art.get("pth") or art.get("pack") or "",
        repo,
    )
    name = args.name.strip() or guess
    if not args.yes and not args.name:
        try:
            ans = input(f"展示名 [{name}]: ").strip()
        except EOFError:
            ans = ""
        if ans:
            name = ans

    data: dict[str, Any] = {
        "id": vid,
        "name": name,
        "tag": "真人" if args.real_person else (args.tag or "二次元"),
        "origin": "huggingface",
        "source_url": f"https://huggingface.co/{repo}",
        "author": author,
        "author_url": f"https://huggingface.co/{author}",
        "package_type": art["kind"],
        "sha256": art.get("sha256") or "",
        "size_bytes": int(art.get("size_bytes") or 0),
        "real_person": bool(args.real_person),
        "date": _today_yymmdd(),
        "description": (
            "收录自 Hugging Face 公开仓库；非 RVC Fabric 官方音色，"
            "授权/音质/版权由来源站点与上传者负责，与官方无关。"
        ),
        "hf_downloads": downloads,
        "hf_likes": likes,
        "snapshot_date": _today_yymmdd(),
    }
    if args.series:
        data["series"] = args.series
    if args.group:
        data["group"] = args.group.strip()
    if art["kind"] == "voice_files":
        data["pth_url"] = _resolve_url(endpoint, repo, art["pth"])
        if art.get("index"):
            data["index_url"] = _resolve_url(endpoint, repo, art["index"])
    else:
        data["pack_url"] = _resolve_url(endpoint, repo, art["pack"])

    # 封面
    if not args.real_person and not args.no_cover:
        cands = _bangumi_search(name)
        chosen = None
        if args.bangumi_id:
            for c in cands:
                if int(c.get("id") or 0) == args.bangumi_id:
                    chosen = c
                    break
            if chosen is None:
                # 仍尝试直接拉角色详情
                try:
                    detail = _http_json(
                        f"https://api.bgm.tv/v0/characters/{args.bangumi_id}"
                    )
                    images = (detail or {}).get("images") or {}
                    chosen = {
                        "id": args.bangumi_id,
                        "name": detail.get("name"),
                        "image": images.get("large") or images.get("medium") or "",
                    }
                except Exception as e:
                    print(f"[warn] Bangumi 角色 {args.bangumi_id} 失败: {e}")
        elif cands:
            print("Bangumi 候选:")
            for i, c in enumerate(cands, 1):
                print(f"  {i}. id={c.get('id')} {c.get('name_cn') or c.get('name')}")
            if args.yes:
                chosen = cands[0]
            else:
                try:
                    ans = input("选序号 [1] 或 0 跳过: ").strip() or "1"
                except EOFError:
                    ans = "1"
                if ans != "0":
                    try:
                        chosen = cands[int(ans) - 1]
                    except (ValueError, IndexError):
                        chosen = cands[0]
        if chosen and chosen.get("image"):
            cover_rel = f"ch-banner/{vid}.jpg"
            dest = cnb / cover_rel
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(_http_bytes(str(chosen["image"])))
                data["cover"] = cover_rel
                print(f"封面已写入 {dest}（请人工看图确认）")
            except Exception as e:
                print(f"[warn] 封面下载失败: {e}", file=sys.stderr)
        else:
            print("未写入封面（可稍后手动放 ch-banner/<id>.jpg 并在 YAML 写 cover）")

    out = cnb / "catalog-src" / "thirdparty" / f"{vid}.yaml"
    _write_yaml(out, data)
    print(f"已写入 {out}")
    print("下一步:")
    print("  python scripts/build_catalog.py build --diff")
    print("  核对后提交 CNB 仓并推送 index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
