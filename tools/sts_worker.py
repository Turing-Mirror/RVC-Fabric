# -*- coding: utf-8 -*-
"""离线语音转换 worker（Speech-to-Speech / 音频 → 目标音色）。

对应官方 RVC WebUI「推理 / 批量推理」：用当前选中的 .pth 把人声音频换成
目标音色。不是 TTS——输入必须是声音文件。

用法::

    Runtime\\python.exe tools/sts_worker.py <请求.json>

请求::

    {
      "input": "文件或文件夹",
      "output": "输出目录",
      "model": "绝对路径.pth",
      "index": "可选.index",
      "pitch": 0,
      "f0method": "rmvpe",
      "index_rate": 0.75,
      "filter_radius": 3,
      "resample_sr": 0,
      "rms_mix_rate": 1.0,
      "protect": 0.33
    }

stdout 每行一条 JSON（与 separate_worker 同形）::

    {"phase":"start","total":N}
    {"phase":"run","done":i,"total":N,"message":"..."}
    {"phase":"done","files":[...]}
    {"phase":"error","message":"..."}
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"}

# 与仓库根 .env / 官方 RVC 一致。安装包历史上未带 .env，worker 必须自带默认值。
_RVC_ENV_DEFAULTS = {
    "weight_root": "assets/weights",
    "weight_uvr5_root": "assets/uvr5_weights",
    "index_root": "logs",
    "outside_index_root": "assets/indices",
    "rmvpe_root": "assets/rmvpe",
    "OPENBLAS_NUM_THREADS": "1",
}


def _ensure_stdio_utf8() -> None:
    """Windows 管道下 stdout 常是系统代码页，中文 JSON 会 OSError 22。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _ensure_rvc_env() -> None:
    """加载产品根 .env（若有），并补齐缺失的 RVC 路径变量。"""
    try:
        from dotenv import load_dotenv

        # 先 cwd（Rust 会 current_dir=产品根），再脚本所在产品根，双保险。
        load_dotenv()
        load_dotenv(ROOT / ".env")
    except Exception:
        pass
    for key, val in _RVC_ENV_DEFAULTS.items():
        os.environ.setdefault(key, val)


def emit(**kw) -> None:
    line = json.dumps(kw, ensure_ascii=False) + "\n"
    try:
        sys.stdout.write(line)
        sys.stdout.flush()
    except (OSError, UnicodeEncodeError):
        # 管道/控制台编码异常时退到 binary UTF-8，避免二次崩溃吞掉真实错误。
        try:
            sys.stdout.buffer.write(line.encode("utf-8", errors="replace"))
            sys.stdout.buffer.flush()
        except Exception:
            pass


def collect_inputs(path: str) -> list[Path]:
    p = Path(path)
    if p.is_file():
        return [p]
    if not p.is_dir():
        return []
    files: list[Path] = []
    for f in sorted(p.rglob("*")):
        if f.is_file() and f.suffix.lower() in AUDIO_EXT:
            files.append(f)
    return files


def main(argv: list[str]) -> int:
    _ensure_stdio_utf8()
    if len(argv) < 2:
        emit(phase="error", message="缺请求文件参数")
        return 2
    try:
        req = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    except Exception as e:
        emit(phase="error", message=f"请求文件读不了：{e}")
        return 2

    inp = str(req.get("input") or "").strip()
    out_dir = str(req.get("output") or "").strip()
    model = str(req.get("model") or "").strip()
    index = str(req.get("index") or "").strip()
    pitch = int(req.get("pitch") or 0)
    f0method = str(req.get("f0method") or "rmvpe").strip() or "rmvpe"
    index_rate = float(req.get("index_rate") if req.get("index_rate") is not None else 0.75)
    filter_radius = int(req.get("filter_radius") if req.get("filter_radius") is not None else 3)
    resample_sr = int(req.get("resample_sr") or 0)
    rms_mix_rate = float(req.get("rms_mix_rate") if req.get("rms_mix_rate") is not None else 1.0)
    protect = float(req.get("protect") if req.get("protect") is not None else 0.33)

    if not inp or not out_dir or not model:
        emit(phase="error", message="输入 / 输出 / 音色模型 都不能为空")
        return 2
    if not Path(model).is_file():
        emit(phase="error", message=f"找不到音色模型：{model}")
        return 2

    files = collect_inputs(inp)
    if not files:
        emit(phase="error", message="没有找到可转换的音频（支持 wav/mp3/flac/ogg/m4a 等）")
        return 2

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    total = len(files)
    emit(phase="start", total=total, message=f"共 {total} 个文件")

    try:
        from scipy.io import wavfile

        from configs.config import Config
        from infer.modules.vc.modules import VC

        _ensure_rvc_env()
        # Config 也会读 sys.argv；清掉以免和本脚本参数打架。
        sys.argv = [sys.argv[0]]
        config = Config()
        vc = VC(config)
        # get_vc 认绝对路径（User_Data/models/...）
        vc.get_vc(model)
    except Exception as e:
        traceback.print_exc()
        emit(phase="error", message=f"加载模型失败：{e}")
        return 1

    out_files: list[str] = []
    for i, src in enumerate(files, start=1):
        emit(
            phase="run",
            done=i - 1,
            total=total,
            message=f"正在转换 {src.name}（{i}/{total}）",
        )
        try:
            # 单文件输入：输出到目录下同名 wav；文件夹输入：保持相对路径扁平到文件名
            stem = src.stem
            dest = Path(out_dir) / f"{stem}_rvc.wav"
            # 重名则加序号
            n = 1
            while dest.exists():
                dest = Path(out_dir) / f"{stem}_rvc_{n}.wav"
                n += 1

            info, wav_opt = vc.vc_single(
                0,
                str(src),
                pitch,
                None,
                f0method,
                index if index and Path(index).is_file() else None,
                None,
                index_rate,
                filter_radius,
                resample_sr,
                rms_mix_rate,
                protect,
            )
            if wav_opt is None or wav_opt[0] is None:
                emit(
                    phase="error",
                    message=f"{src.name} 转换失败：{info or '未知错误'}",
                )
                return 1
            wavfile.write(str(dest), wav_opt[0], wav_opt[1])
            out_files.append(str(dest))
            emit(
                phase="run",
                done=i,
                total=total,
                message=f"完成 {src.name}",
            )
        except Exception as e:
            traceback.print_exc()
            emit(phase="error", message=f"{src.name} 失败：{e}")
            return 1

    emit(phase="done", files=out_files, total=total, message=f"全部完成，共 {len(out_files)} 个")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except SystemExit:
        raise
    except Exception as e:
        traceback.print_exc()
        emit(phase="error", message=str(e))
        raise SystemExit(1)
