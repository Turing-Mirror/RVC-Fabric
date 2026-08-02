# -*- coding: utf-8 -*-
"""把一个制品传到 CNB 的 Release 附件，并回读校验。

人话：Runtime tar、音色包这些几百 MB 到几个 GB 的东西不该待在 git 里。放进
git + LFS 意味着谁想改一行 YAML 都得先把几个 GB 拉下来，而且删掉之后对象仍然
永远留在历史里。Release 附件是按文件寻址的：传一个不需要 clone 任何东西，
删一个是真删。

这个项目几乎全靠 AI 维护，所以整条链路必须能脚本化。实测可以：三条 CLI 调用
加一次 HTTP PUT，没有任何需要浏览器或人工的环节。

用法::

    export CNB_TOKEN=<PAT>        # 或 . ~/.cnb/agent-token
    python scripts/publish_asset.py --tag RVC-runtime \\
        --file /path/to/runtime-nvidia-2026.07.21.tar

    # 传完顺便把 sha256 / size_bytes 写回清单
    python scripts/publish_asset.py --tag voices --file kiki-v2.zip \\
        --write-yaml <发布仓>/catalog-src/voices/kiki.yaml

**权限**：需要 `repo-release:rw`。`cnb login` 走的 OAuth 客户端拿不到这个
范围（授权页上根本没有这一项），必须用个人访问令牌，通过 `CNB_TOKEN` 注入。

**ttl 必须是 0**。CNB 的附件接口有 `--ttl`，文档写「0 表示永久，最大不能超过
180 天」。不显式传 0 的话附件有可能过期，那就是所有用户下载 404。本脚本把
`--ttl 0` 写死，不给调。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_REPO = "Turing-Mirror/RVC-Fabric-Releases"
UA = "Turing-Mirror/RVC-Fabric (https://github.com/Turing-Mirror/RVC-Fabric)"


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def cnb(*args: str) -> str:
    """跑一条 cnb CLI，返回 stdout。失败直接抛。"""
    if not os.environ.get("CNB_TOKEN"):
        raise SystemExit(
            "缺 CNB_TOKEN。cnb login 那套 OAuth 拿不到 repo-release:rw，\n"
            "要用个人访问令牌：export CNB_TOKEN=<PAT> 或 . ~/.cnb/agent-token"
        )
    cnb_bin = "cnb.cmd" if os.name == "nt" else "cnb"
    p = subprocess.run(
        [cnb_bin, *args], capture_output=True, text=True, encoding="utf-8", timeout=300
    )
    if p.returncode != 0:
        raise RuntimeError(f"cnb {' '.join(args[:2])} 失败:\n{p.stdout}\n{p.stderr}")
    if "status: 4" in p.stdout or "status: 5" in p.stdout:
        raise RuntimeError(f"cnb {' '.join(args[:2])} 返回错误:\n{p.stdout}")
    return p.stdout


def _field(text: str, key: str) -> str:
    """从 CLI 的 YAML 式输出里抠一个字段。"""
    m = re.search(rf'^\s*{re.escape(key)}:\s*"?([^"\n]+)"?\s*$', text, re.M)
    return m.group(1).strip() if m else ""


# setup 标签是固定下载位（固定名 + OTA 包都在这里）。Release 页面的标题/正文
# 统一用静态说明，**不写版本号**：版本权威在 catalog-src/ 与附件文件名。
# 历史教训：建 release 时写了 "RVC Fabric 1.3.1"，之后发版只传附件、从不更新
# release 本体，页面永远停在 1.3.1。所以每次上传 setup 都把它归一成静态说明，
# 「页面旧一版」这种事从机制上不可能发生。其他 tag 的页面不管。
SETUP_RELEASE_TITLE = "RVC Fabric 安装包"
SETUP_RELEASE_BODY = """# RVC Fabric 安装包（固定下载位）

本页是安装包的固定下载位。**页面标题与描述不维护版本号**——版本以附件文件名与发布仓在线清单为准，避免两处漂移。

## 制品

- `RVC_Fabric_Setup.exe` — 手动下载安装（固定名，文件名永不改）
- `RVC Fabric_<版本>_x64-setup.exe` — 自动更新下载包（文件名带当前版本号）

## 版本与更新日志

当前版本、sha256、更新日志统一以发布仓 `catalog-src/`（setup.yaml / app.yaml / changelog.yaml）为准；客户端「检查更新」读取 updater.json。

## 校验

发布仓 `setup/` 目录有各制品的 `.sha256` 边车，下载后可自行核对。"""


def ensure_release(repo: str, tag: str, title: str) -> str:
    """返回 release id；已存在就复用。"""
    try:
        out = cnb("releases", "get-release-by-tag", "--repo", repo, "--tag", tag)
        rid = _field(out, "id")
        if rid:
            print(f"  复用已有 release {tag} (id={rid})")
            if tag == "setup":
                cnb(
                    "releases", "patch-release", "--repo", repo,
                    "--release-id", rid,
                    "--name", SETUP_RELEASE_TITLE, "--body", SETUP_RELEASE_BODY,
                )
                print("  setup 页面已归一为静态说明（不写版本号）")
            return rid
    except RuntimeError:
        pass
    out = cnb(
        "releases", "post-release", "--repo", repo,
        "--tag-name", tag, "--name", title or tag, "--target-commitish", "main",
    )
    rid = _field(out, "id")
    if not rid:
        raise RuntimeError(f"建 release 没拿到 id:\n{out}")
    print(f"  新建 release {tag} (id={rid})")
    return rid


def upload(repo: str, release_id: str, path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    local_sha = sha256_file(path)
    print(f"  本地 sha256 {local_sha}")

    out = cnb(
        "releases", "post-release-asset-upload-url", "--repo", repo,
        "--release-id", release_id, "--asset-name", path.name,
        "--size", str(size), "--overwrite", "--ttl", "0",
    )
    upload_url = _field(out, "upload_url")
    verify_url = _field(out, "verify_url")
    if not upload_url or not verify_url:
        raise RuntimeError(f"没拿到上传地址:\n{out}")

    # verify_url 形如 .../asset-upload-confirmation/<token>/<url-encoded path>?ttl=0
    m = re.search(r"/asset-upload-confirmation/([^/]+)/([^?]+)", verify_url)
    if not m:
        raise RuntimeError(f"verify_url 解析不出 token/path: {verify_url}")
    token = m.group(1)
    asset_path = urllib.parse.unquote(m.group(2))

    print(f"  PUT {size / 1e6:.1f} MB …")
    with path.open("rb") as f:
        req = urllib.request.Request(
            upload_url, data=f, method="PUT",
            headers={"User-Agent": UA, "Content-Length": str(size)},
        )
        with urllib.request.urlopen(req, timeout=3600) as resp:
            if resp.status not in (200, 201, 204):
                raise RuntimeError(f"PUT 返回 {resp.status}")

    cnb(
        "releases", "post-release-asset-upload-confirmation", "--repo", repo,
        "--release-id", release_id, "--upload-token", token,
        "--asset-path", asset_path, "--ttl", "0",
    )

    # 回读校验：CNB 服务端自己算 sha256，和本地比对上才算成功。
    out = cnb(
        "releases", "get-release-by-id", "--repo", repo, "--release-id", release_id
    )
    # 附件块的字段顺序是 path → hash_algo → hash_value → url → name，所以从
    # 「name: <本文件名>」那行往回找 hash_value。不能直接 split(文件名)：
    # path 那行里也含文件名，会切在 hash_value 之前，永远读不到。
    remote_sha = ""
    lines = out.splitlines()
    idx = next(
        (i for i, ln in enumerate(lines) if ln.strip() == f"name: {path.name}"), -1
    )
    if idx > 0:
        for ln in reversed(lines[:idx]):
            if "hash_value:" in ln:
                remote_sha = ln.split(":", 1)[1].strip().strip('"')
                break
    if not remote_sha:
        raise RuntimeError("回读不到服务端 sha256，无法确认上传完整")
    if remote_sha and remote_sha != local_sha:
        raise RuntimeError(
            f"服务端算的 sha256 和本地对不上！\n  本地 {local_sha}\n  远端 {remote_sha}"
        )
    print("  服务端 sha256 一致")

    return {
        "sha256": local_sha,
        "size_bytes": size,
        "url": f"https://cnb.cool{asset_path}",
        "name": path.name,
    }


def write_yaml(yaml_path: Path, res: dict[str, Any], tag: str) -> None:
    """把 sha256 / size_bytes / channel / release_tag 写回清单。

    故意用逐行替换而不是 YAML 库：这些文件是人工维护的，注释和顺序都有意义，
    round-trip 一遍会把它们全冲掉。
    """
    lines = yaml_path.read_text(encoding="utf-8").splitlines()
    seen = set()
    out = []
    repl = {
        "sha256": res["sha256"],
        "size_bytes": str(res["size_bytes"]),
        "channel": "release",
        "release_tag": tag,
    }
    for line in lines:
        k = line.split(":", 1)[0].strip() if ":" in line else ""
        if k in repl and not line.startswith(" "):
            out.append(f"{k}: {repl[k]}")
            seen.add(k)
        else:
            out.append(line)
    for k, v in repl.items():
        if k not in seen:
            out.append(f"{k}: {v}")
    yaml_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"  已写回 {yaml_path.name}")
    _write_sidecar(yaml_path, out, res["sha256"])


def _write_sidecar(yaml_path: Path, lines: list[str], sha: str) -> None:
    """同步清单旁边那个 <制品>.sha256 边车。

    这一步以前是漏掉的，于是每发一版边车就旧一版：build_catalog 会把它的地址
    写进 index.json 的 sha256_url，客户端照着那个地址校验 Setup，拿到的却是
    上一版的哈希 —— 制品明明是好的，校验却过不了。1.3.1、1.3.2 连着踩了两次，
    所以放在这里自动做，不靠人记。

    发布仓已经退化成纯清单仓，制品本身不在 git 里，因此边车只能按 YAML 里
    `file:` 声明的路径去写。
    """
    rel = ""
    for line in lines:
        if line.startswith("file:"):
            rel = line.split(":", 1)[1].strip().strip("'\"")
            break
    if not rel:
        return
    # catalog-src/setup.yaml -> 发布仓根 -> setup/RVC_Fabric_Setup.exe.sha256
    sidecar = yaml_path.parents[1] / (rel + ".sha256")
    if not sidecar.parent.is_dir():
        print(f"  [跳过边车] 没有目录 {sidecar.parent}")
        return
    sidecar.write_text(f"{sha}  {Path(rel).name}\n", encoding="utf-8")
    print(f"  已写回 {sidecar.relative_to(yaml_path.parents[1])}")


def main() -> int:
    ap = argparse.ArgumentParser(description="上传制品到 CNB Release 附件")
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--tag", required=True, help="release 标签，如 RVC-runtime / voices")
    ap.add_argument("--title", default="", help="release 标题（新建时用）")
    ap.add_argument("--file", required=True, action="append", help="要传的文件，可重复")
    ap.add_argument("--write-yaml", default="", help="传完把哈希/体积写回这个 YAML")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    files = [Path(f).expanduser() for f in args.file]
    missing = [f for f in files if not f.is_file()]
    if missing:
        raise SystemExit(f"文件不存在: {missing}")

    rid = ensure_release(args.repo, args.tag, args.title)
    results = []
    for f in files:
        print(f"== {f.name}")
        results.append(upload(args.repo, rid, f))

    if args.write_yaml and len(results) == 1:
        write_yaml(Path(args.write_yaml), results[0], args.tag)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print()
        for r in results:
            print(f"  {r['name']}")
            print(f"    sha256      {r['sha256']}")
            print(f"    size_bytes  {r['size_bytes']}")
            print(f"    url         {r['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
