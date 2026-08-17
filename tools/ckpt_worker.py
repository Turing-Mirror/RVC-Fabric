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

# 必须在 sys.path 补好之后：Runtime 的 python39._pth 不认脚本目录。
from tools import msg_codes as mc  # noqa: E402


def emit(**kw):
    sys.stdout.write(json.dumps(kw, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def fail(message):
    """上游 RVC 函数返回的原文（英文/中文都有），我们没法给它编码。"""
    emit(phase="error", message=str(message))
    sys.exit(1)


def fail_code(code, params=None):
    """我们自己写的报错。带码，壳按界面语言取译文。"""
    emit(phase="error", **mc.msg_fields(code, params))
    sys.exit(1)


def _name_ok(name: str) -> str:
    n = (name or "").strip()
    if not n:
        fail_code(mc.CKPT_NAME_EMPTY)
    if any(c in n for c in '\\/:*?"<>|'):
        fail_code(mc.CKPT_NAME_BAD_CHARS)
    if n in (".", "..") or n.startswith("."):
        fail_code(mc.CKPT_NAME_INVALID)
    return n


def _must_file(path: str, code: str) -> Path:
    """`code` 说的是「哪一个模型」。以前这里收的是中文名词再拼进句子，
    那样译文中间会夹一个中文词，所以按角色拆成了四个码。"""
    p = Path(path)
    if not p.is_file():
        fail_code(code, {"path": path})
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

    p = _must_file(str(req.get("path") or ""), mc.CKPT_MISSING_MODEL)
    text = show_info(str(p))
    emit(phase="done", message=str(text), info=str(text))


def do_change(req):
    from infer.lib.train.process_ckpt import change_info

    p = _must_file(str(req.get("path") or ""), mc.CKPT_MISSING_MODEL)
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
    emit(phase="done", weights=str(published or out), **mc.msg_fields(mc.CKPT_INFO_SAVED))


def do_merge(req):
    from i18n.i18n import I18nAuto
    from infer.lib.train.process_ckpt import merge

    a = _must_file(str(req.get("path_a") or ""), mc.CKPT_MISSING_MODEL_A)
    b = _must_file(str(req.get("path_b") or ""), mc.CKPT_MISSING_MODEL_B)
    name = _name_ok(str(req.get("name") or ""))
    try:
        alpha = float(req.get("alpha") if req.get("alpha") is not None else 0.5)
    except (TypeError, ValueError):
        alpha = 0.5
    alpha = min(max(alpha, 0.0), 1.0)
    sr = str(req.get("sample_rate") or "48k")
    if sr not in ("32k", "40k", "48k"):
        fail_code(mc.CKPT_BAD_SAMPLE_RATE, {"sample_rate": sr})
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
    emit(phase="done", weights=str(published or out), **mc.msg_fields(mc.CKPT_MERGED))


def do_extract(req):
    from infer.lib.train.process_ckpt import extract_small_model

    p = _must_file(str(req.get("path") or ""), mc.CKPT_MISSING_BIG_MODEL)
    name = _name_ok(str(req.get("name") or ""))
    sr = str(req.get("sample_rate") or "48k")
    if sr not in ("32k", "40k", "48k"):
        fail_code(mc.CKPT_BAD_SAMPLE_RATE, {"sample_rate": sr})
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
    emit(phase="done", weights=str(published or out), **mc.msg_fields(mc.CKPT_EXTRACTED))


def do_onnx(req):
    src = _must_file(str(req.get("path") or ""), mc.CKPT_MISSING_MODEL)
    dest = str(req.get("dest") or "").strip()
    if not dest:
        dest = str(src.with_suffix(".onnx"))
    if not dest.lower().endswith(".onnx"):
        dest = dest + ".onnx"
    out = Path(dest)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        fail_code(mc.CKPT_MKDIR_FAILED, {"error": e})
    try:
        from infer.modules.onnx.export import export_onnx
    except Exception as e:
        fail_code(mc.CKPT_ONNX_MISSING_DEPS, {"error": e})
    try:
        msg = export_onnx(str(src), str(out))
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        fail_code(mc.CKPT_ONNX_FAILED, {"error": e})
    emit(phase="done", message=str(msg or "Finished"), onnx=str(out))


def main():
    if len(sys.argv) < 2:
        fail_code(mc.CKPT_USAGE)
    try:
        req = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except Exception as e:
        fail_code(mc.CKPT_BAD_REQUEST, {"error": e})
    action = str(req.get("action") or "").strip()
    emit(phase="start", action=action, **mc.msg_fields(mc.CKPT_STARTING))
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
        fail_code(mc.CKPT_UNKNOWN_ACTION, {"action": action})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
