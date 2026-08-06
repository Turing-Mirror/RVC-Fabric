#!/usr/bin/env python3
"""为 Tauri 安装包准备干净的引擎负载。

## 为什么需要这一步

Tauri 的 `bundle.resources` 是「把这个路径拷进安装包」，它不做任何筛选。
直接写 `"../../assets": "assets"` 看着能用，实际上是个雷：

* 干净 clone 出来 `assets/` 只有 712 KB，但**只要这台机器跑过一次程序**，
  `assets/hubert/hubert_base.pt`、`assets/rmvpe/rmvpe.pt` 就下下来了，
  加起来三四百 MB，会原封不动进安装包。发版机器基本都跑过程序。
* `configs/inuse/config.json` 跑过之后会写进这台机器的绝对路径，
  等于把开发者的目录结构印进公开发布的安装包。
* `docs/` 里有内部开发文档，不该给用户。

Inno 那套打包脚本一直在做这些筛选（`build_setup.assemble_payload`）。
统一到 NSIS 之后这些筛选不能丢，所以先在这里把干净的负载摆好，
再让 Tauri 去拷这个负载目录，而不是去拷仓库。

## 防漂移

负载里多出一个顶层条目、而 `tauri.conf.json` 的 resources 没列上，
那个文件就会静默地不进安装包 —— 用户装完少个文件，谁也不知道为什么。
所以脚本最后会拿负载的顶层条目和配置对一遍，对不上直接失败。

## 用法

    python scripts/prepare_engine_payload.py

`npm run build` 之后自动跑（app/package.json 的 postbuild），
所以正常执行 `npm run tauri:build` 不需要单独调用。
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAYLOAD = REPO / "app" / "src-tauri" / "engine-payload"
TAURI_CONF = REPO / "app" / "src-tauri" / "tauri.conf.json"

sys.path.insert(0, str(REPO / "scripts"))
from build_setup import assemble_payload  # noqa: E402
from build_release import log  # noqa: E402

# 负载里不算「要进安装包的东西」的条目。
# User_Data/models 是空目录，Tauri 只拷文件，空目录本来也留不下；
# 程序首次启动会自己建。
SKIP_TOP_LEVEL = {"User_Data"}

# 绝对不允许出现在负载里的东西。出现了说明筛选逻辑坏了，宁可炸也不要发出去。
FORBIDDEN = (
    "assets/hubert/hubert_base.pt",
    "assets/rmvpe/rmvpe.pt",
    "assets/rmvpe/rmvpe.onnx",
    "assets/pretrained",
    "assets/pretrained_v2",
    "assets/uvr5_weights",
    "docs",
    "Runtime",
    "runtime",
    "ffmpeg.exe",
    "ffprobe.exe",
)


def build() -> None:
    if PAYLOAD.exists():
        shutil.rmtree(PAYLOAD)
    PAYLOAD.mkdir(parents=True)
    # skip_exe=True：壳和 frontend 由 Tauri 自己产出，负载只管引擎侧。
    assemble_payload(PAYLOAD, skip_exe=True)


def mark_installer_kind() -> None:
    """负载元数据里记的是 inno_setup，统一到 NSIS 之后要改过来。"""
    meta_path = PAYLOAD / "setup_package.json"
    if not meta_path.is_file():
        return
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["installer"] = "tauri_nsis"
    meta.pop("iss", None)
    meta["note"] = (
        "薄包：壳+源码。Runtime（分版）+ engine-core（共用）+ VB-Cable 均从 CNB 补全"
    )
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    log("[payload] setup_package.json → installer=tauri_nsis")


def check_forbidden() -> list[str]:
    return [rel for rel in FORBIDDEN if (PAYLOAD / rel).exists()]


def check_absolute_paths() -> list[str]:
    """跑过程序的机器会把绝对路径写进 configs/inuse/config.json。"""
    bad = []
    cfg = PAYLOAD / "configs" / "inuse" / "config.json"
    if cfg.is_file():
        text = cfg.read_text(encoding="utf-8", errors="replace")
        for marker in ("C:\\", "C:/", "/Users/", "/home/"):
            if marker in text:
                bad.append(f"configs/inuse/config.json 含绝对路径 {marker!r}")
    return bad


def check_conf_coverage() -> list[str]:
    conf = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    resources = conf["bundle"]["resources"]
    listed = set()
    for src in resources:
        if src.startswith("engine-payload/"):
            listed.add(src[len("engine-payload/") :])

    present = {
        p.name for p in PAYLOAD.iterdir() if p.name not in SKIP_TOP_LEVEL
    }
    missing = sorted(present - listed)
    stale = sorted(listed - present)

    problems = []
    for name in missing:
        problems.append(
            f"负载里有 {name}，但 tauri.conf.json 的 resources 没列 —— 它不会进安装包"
        )
    for name in stale:
        problems.append(
            f"tauri.conf.json 列了 engine-payload/{name}，但负载里没有 —— 构建会失败"
        )
    return problems


def write_env_file() -> None:
    """官方 RVC 靠产品根 `.env` 找权重目录，负载必须带一份。

    这个文件不在仓库里（`.gitignore` 把 `.env` 整个挡掉了，那条规则是拦密钥
    的，拦对了），而 `tauri.conf.json` 的 resources 又列着它 —— 于是干净 clone
    出来的仓库根本 build 不了，报「resource path engine-payload/.env doesn't
    exist」。这里按固定内容生成：里面全是相对路径，没有任何机密。

    值要和 `app/src-tauri/src/worker.rs` 的 `env_for_runtime` 那五条兜底一致，
    改一边就得改另一边。
    """
    lines = [
        "# 由 scripts/prepare_engine_payload.py 生成，不要手改。",
        "# 路径相对产品根（worker 的 cwd）。",
        "weight_root=assets/weights",
        "weight_uvr5_root=assets/uvr5_weights",
        "index_root=logs",
        "outside_index_root=assets/indices",
        "rmvpe_root=assets/rmvpe",
    ]
    (PAYLOAD / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    build()
    mark_installer_kind()
    write_env_file()

    problems = check_forbidden()
    problems = [f"负载里混进了不该有的 {x}" for x in problems]
    problems += check_absolute_paths()
    problems += check_conf_coverage()

    size = sum(f.stat().st_size for f in PAYLOAD.rglob("*") if f.is_file())
    log(f"[payload] {PAYLOAD.relative_to(REPO)} 就绪，{size / 1024 / 1024:.1f} MB")

    if problems:
        log("[payload] 检查不通过：")
        for x in problems:
            log(f"  - {x}")
        return 1

    log("[payload] 检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
