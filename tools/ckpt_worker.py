# -*- coding: utf-8 -*-
"""原版 ckpt 处理 / ONNX 导出。训练窗进阶设置调用。

请求走文件::

    {"action": "merge"|"change"|"show"|"extract"|"onnx", ...}

stdout 每行一个 JSON，和 train_worker 同形。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if os.getcwd() != str(ROOT):
    os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def emit(**kw):
    sys.stdout.write(json.dumps(kw, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def fail(message):
    emit(phase="error", message=str(message))
    sys.exit(1)


def _name_ok(name: str) -> str:
    n = (name or "").strip()
    if not n:
        fail("保存名不能为空")
    if any(c in n for c in '\\/:*?"<>|'):
        fail("保存名不能含 \\ / : * ? \" < > |")
    if n in (".", "..") or n.startswith("."):
        fail("保存名不合法")
    return n


def _must_file(path: str, what: str) -> Path:
    p = Path(path)
    if not p.is_file():
        fail("%s不存在：%s" % (what, path))
    return p


def publish(root: Path, pth: Path, name: str):
    dest = root / "User_Data" / "models" / name
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / ("%s.pth" % name)
    try:
        shutil.copy2(pth, out)
        side = dest / "config.json"
        data = {}
        if side.is_file():
            try:
                data = json.loads(side.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
        if not isinstance(data, dict):
            data = {}
        data["name"] = name
        data["source"] = data.get("source") or "ckpt"
        side.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        return None
    return out


def do_show(req):
    from infer.lib.train.process_ckpt import show_info

    p = _must_file(str(req.get("path") or ""), "模型")
    text = show_info(str(p))
    emit(phase="done", message=str(text), info=str(text))


def do_change(req):
    from infer.lib.train.process_ckpt import change_info

    p = _must_file(str(req.get("path") or ""), "模型")
    info = str(req.get("info") or "")
    raw = str(req.get("name") or "").strip()
    name = raw if raw else p.name
    if raw:
        name = _name_ok(raw)
        if not name.lower().endswith(".pth"):
            name = name + ".pth"
    msg = change_info(str(p), info, name)
    if not str(msg).lower().startswith("success"):
        fail(msg)
    out = ROOT / "assets" / "weights" / name
    published = publish(ROOT, out, Path(name).stem) if out.is_file() else None
    emit(phase="done", message="已改模型信息", weights=str(published or out))


def do_merge(req):
    from i18n.i18n import I18nAuto
    from infer.lib.train.process_ckpt import merge

    a = _must_file(str(req.get("path_a") or ""), "A 模型")
    b = _must_file(str(req.get("path_b") or ""), "B 模型")
    name = _name_ok(str(req.get("name") or ""))
    try:
        alpha = float(req.get("alpha") if req.get("alpha") is not None else 0.5)
    except (TypeError, ValueError):
        alpha = 0.5
    alpha = min(max(alpha, 0.0), 1.0)
    sr = str(req.get("sample_rate") or "48k")
    if sr not in ("32k", "40k", "48k"):
        fail("不支持的采样率：%s" % sr)
    version = str(req.get("version") or "v2")
    if version not in ("v1", "v2"):
        version = "v2"
    i18n = I18nAuto()
    f0_flag = i18n("是") if req.get("if_f0", True) else "0"
    info = str(req.get("info") or "")
    msg = merge(str(a), str(b), alpha, sr, f0_flag, info, name, version)
    if not str(msg).lower().startswith("success"):
        fail(msg)
    out = ROOT / "assets" / "weights" / ("%s.pth" % name)
    published = publish(ROOT, out, name) if out.is_file() else None
    emit(phase="done", message="融合完成", weights=str(published or out))


def do_extract(req):
    from infer.lib.train.process_ckpt import extract_small_model

    p = _must_file(str(req.get("path") or ""), "大模型")
    name = _name_ok(str(req.get("name") or ""))
    sr = str(req.get("sample_rate") or "48k")
    if sr not in ("32k", "40k", "48k"):
        fail("不支持的采样率：%s" % sr)
    version = str(req.get("version") or "v2")
    if version not in ("v1", "v2"):
        version = "v2"
    if_f0 = "1" if req.get("if_f0", True) else "0"
    info = str(req.get("info") or "")
    msg = extract_small_model(str(p), name, sr, if_f0, info, version)
    if not str(msg).lower().startswith("success"):
        fail(msg)
    out = ROOT / "assets" / "weights" / ("%s.pth" % name)
    published = publish(ROOT, out, name) if out.is_file() else None
    emit(phase="done", message="已提取小模型", weights=str(published or out))


def do_onnx(req):
    src = _must_file(str(req.get("path") or ""), "模型")
    dest = str(req.get("dest") or "").strip()
    if not dest:
        dest = str(src.with_suffix(".onnx"))
    if not dest.lower().endswith(".onnx"):
        dest = dest + ".onnx"
    out = Path(dest)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        fail("建不了输出目录：%s" % e)
    try:
        from infer.modules.onnx.export import export_onnx
    except Exception as e:
        fail("当前 Runtime 没有 ONNX 导出依赖（onnx / onnxsim）：%s" % e)
    try:
        msg = export_onnx(str(src), str(out))
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        fail("ONNX 导出失败：%s" % e)
    emit(phase="done", message=str(msg or "Finished"), onnx=str(out))


def main():
    if len(sys.argv) < 2:
        fail("用法：ckpt_worker.py <request.json>")
    try:
        req = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except Exception as e:
        fail("读不了请求文件：%s" % e)
    action = str(req.get("action") or "").strip()
    emit(phase="start", action=action, message="开始…")
    if action == "show":
        do_show(req)
    elif action == "change":
        do_change(req)
    elif action == "merge":
        do_merge(req)
    elif action == "extract":
        do_extract(req)
    elif action == "onnx":
        do_onnx(req)
    else:
        fail("未知操作：%s" % action)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
