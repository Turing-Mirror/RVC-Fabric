# -*- coding: utf-8 -*-
"""人声分离 worker：跑一次 PyMSS，把进度按行吐给 Rust 侧。

为什么不直接调 `python -m tools.pymss.cli infer`：它的进度是 tqdm 画在
stderr 上的进度条，要靠正则去刮，格式一变就瞎。PyMSS 的 separator 本来就收
`progress_callback(done, total, message)`，接上它按行输出 JSON 干净得多。

用法（Rust 侧这么调）::

    pythonw tools/separate_worker.py <请求文件.json>

请求文件::

    {"model": "...", "model_dir": "...", "input": "...", "output": "...",
     "device": "auto", "format": "wav"}

stdout 每行一条 JSON：
    {"phase":"start"}                          开始
    {"phase":"run","done":3,"total":10,"message":"..."}
    {"phase":"done","files":["..."]}           成功
    {"phase":"error","message":"..."}          失败

只走 stdout，不掺日志：PyMSS 自己的 logger 走 stderr，Rust 那边单独收到日志
文件里，两边不会互相踩。
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

def setup_sys_path() -> None:
    """Make top-level ``pymss`` and ``pymss_core`` importable.

    Runtime python ships a ``python39._pth``, which ignores the script
    directory. We used to import ``tools.pymss`` from the product root.
    That loads the same files under a different package name, and then
    ``uvr_lib_v5`` calls ``alias_submodules(__name__, …)`` which only
    accepts names starting with ``pymss.modules.`` — VR models (HP3/HP4)
    die after the catalog loads. Import as ``pymss`` so the name matches
    what the vendored package expects.
    """
    tools = Path(__file__).resolve().parent
    root = tools.parent
    # tools first so `import pymss` / `import pymss_core` win.
    # root second for anything that still does `import tools.xxx`.
    for p in (root, tools):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)


setup_sys_path()

# 必须在 setup_sys_path 之后：Runtime 的 python39._pth 不认脚本目录。
from tools import msg_codes as mc  # noqa: E402


def emit(**kw) -> None:
    sys.stdout.write(json.dumps(kw, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main(argv: list[str]) -> int:
    try:
        from tools.worker_protocol import prepare_headless_windows

        prepare_headless_windows()
    except Exception:
        pass
    if len(argv) < 2:
        emit(phase="error", **mc.msg_fields(mc.SEP_NO_REQUEST))
        return 2
    try:
        req = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    except Exception as e:
        emit(phase="error", **mc.msg_fields(mc.SEP_BAD_REQUEST, {"error": e}))
        return 2

    model = str(req.get("model") or "").strip()
    model_dir = str(req.get("model_dir") or "").strip()
    inp = str(req.get("input") or "").strip()
    out = str(req.get("output") or "").strip()
    device = str(req.get("device") or "auto").strip()
    fmt = str(req.get("format") or "wav").strip().lower()
    if fmt not in ("wav", "flac", "mp3", "m4a"):
        fmt = "wav"
    try:
        agg = int(req.get("aggression") if req.get("aggression") is not None else 10)
    except (TypeError, ValueError):
        agg = 10
    agg = max(0, min(agg, 20))
    if not (model and inp and out):
        emit(phase="error", **mc.msg_fields(mc.SEP_EMPTY_FIELDS))
        return 2

    # PyMSS 默认把权重放 ~/.cache/pymss；我们要它只认安装目录里的那份，
    # 免得用户 C 盘被悄悄塞几百 MB，也免得离线时它去联网拉。
    if model_dir:
        os.environ["PYMSS_MODEL_DIR"] = model_dir

    emit(phase="start")
    try:
        from pymss.model_registry import create_separator

        last = [-1]

        def on_progress(done, total, message=""):
            # 回调频率很高，同一个百分比不重复发 —— 每行都要过一次 IPC。
            pct = int(done * 100 / total) if total else 0
            if pct == last[0]:
                return
            last[0] = pct
            emit(
                phase="run",
                done=int(done),
                total=int(total or 1),
                message=str(message or ""),
            )

        with create_separator(
            model,
            model_dir=model_dir or None,
            device=device,
            device_ids=[0],
            output_format=fmt,
            store_dirs=out,
            progress_callback=on_progress,
            inference_params={"aggression": agg},
        ) as sep:
            files = sep.process_folder(inp)
        emit(phase="done", files=[str(f) for f in (files or [])])
        return 0
    except Exception as e:
        # 原始异常进 stderr（壳会收进日志），界面上只给中文。
        traceback.print_exc(file=sys.stderr)
        emit(
            phase="error",
            detail=f"{type(e).__name__}: {e}",
            **mc.msg_fields(mc.SEP_FAILED),
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
