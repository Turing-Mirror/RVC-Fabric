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

# 让 `tools.pymss` 能被 import：这个脚本是被绝对路径拉起来的，cwd 是产品根，
# 但 sys.path[0] 会是 tools/ 自己。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def emit(**kw) -> None:
    sys.stdout.write(json.dumps(kw, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        emit(phase="error", message="缺请求文件参数")
        return 2
    try:
        req = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    except Exception as e:
        emit(phase="error", message=f"请求文件读不了：{e}")
        return 2

    model = str(req.get("model") or "").strip()
    model_dir = str(req.get("model_dir") or "").strip()
    inp = str(req.get("input") or "").strip()
    out = str(req.get("output") or "").strip()
    device = str(req.get("device") or "auto").strip()
    fmt = str(req.get("format") or "wav").strip()
    if not (model and inp and out):
        emit(phase="error", message="模型 / 输入 / 输出 都不能为空")
        return 2

    # PyMSS 默认把权重放 ~/.cache/pymss；我们要它只认安装目录里的那份，
    # 免得用户 C 盘被悄悄塞几百 MB，也免得离线时它去联网拉。
    if model_dir:
        os.environ["PYMSS_MODEL_DIR"] = model_dir

    emit(phase="start")
    try:
        from tools.pymss.model_registry import create_separator

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
        ) as sep:
            files = sep.process_folder(inp)
        emit(phase="done", files=[str(f) for f in (files or [])])
        return 0
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        emit(phase="error", message=f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
