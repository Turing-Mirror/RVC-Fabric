# -*- coding: utf-8 -*-
"""离线语音转换 worker（Speech-to-Speech / 音频 → 目标音色）——冷路径。

对应官方 RVC WebUI「推理 / 批量推理」：用当前选中的 .pth 把人声音频换成
目标音色。不是 TTS——输入必须是声音文件。

这是**冷路径**：独立进程，从盘上把 hubert / net_g / rmvpe 全读一遍，代价是
几十秒的冷启动。实时 worker 活着的时候，壳会走热路径（`gui_v1` 的 `convert`
命令，直接用常驻模型），根本不起这个进程。两条路的转换循环都在
`tools/sts_core.py`，这里只负责「把模型从盘上装起来」和「把进度写 stdout」。

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

    {"phase":"start","total":N,"message":"..."}
    {"phase":"run","done":i,"total":N,"pct":0-100,"step":"...","current":k,
     "ok":a,"skip":b,"file":"name.wav","message":"..."}
    {"phase":"skip","done":i,"total":N,"pct":..,"current":k,"ok":a,"skip":b,"message":"..."}
    {"phase":"done","files":[...],"skipped":[...]}
    {"phase":"error","message":"..."}

``pct`` 是整次任务 0–100 的细粒度进度（含模型加载与单文件内分步），
多文件时按文件体积加权，避免 10 秒小文件和 5 分钟长歌各占 1/N。
``done/total`` 仍是文件级计数；``current/ok/skip`` 供批量界面实时看板。
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import sts_core  # noqa: E402 — 上面要先把产品根塞进 sys.path
from tools.sts_core import (  # noqa: E402
    AUDIO_EXT,
    StsProgress,
    collect_inputs,
    cuda_empty_cache,
    file_weights,
    friendly_error,
    normalize_f0method,
    preload_side_models,
    run_batch,
)

# 与仓库根 .env / 官方 RVC 一致。安装包历史上未带 .env，worker 必须自带默认值。
_RVC_ENV_DEFAULTS = {
    "weight_root": "assets/weights",
    "index_root": "logs",
    "outside_index_root": "assets/indices",
    "rmvpe_root": "assets/rmvpe",
    "OPENBLAS_NUM_THREADS": "1",
}

_ = AUDIO_EXT  # 兼容旧的 `from tools.sts_worker import AUDIO_EXT`


def _ensure_stdio_utf8() -> None:
    """Windows 管道下 stdout 常是系统代码页，中文 JSON 会 OSError 22。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _ensure_rvc_env() -> None:
    """cwd 切到产品根、加载 .env、补齐 RVC 路径（相对路径改成绝对路径）。"""
    try:
        os.chdir(ROOT)
    except OSError:
        pass
    os.environ["TM_VOICE_ROOT"] = str(ROOT)
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        load_dotenv()
    except Exception:
        pass
    for key, val in _RVC_ENV_DEFAULTS.items():
        os.environ.setdefault(key, val)
    # 相对路径一律钉死在产品根，避免 fairseq / rmvpe 找不到文件。
    for key in (
        "weight_root",
        "index_root",
        "outside_index_root",
        "rmvpe_root",
    ):
        cur = (os.environ.get(key) or "").strip()
        if not cur:
            continue
        p = Path(cur)
        if not p.is_absolute():
            os.environ[key] = str((ROOT / p).resolve())


def _preflight_engine(f0method: str) -> str | None:
    """引擎资源缺了就直接说清楚，别进 torch 后再炸一长串 traceback。"""
    hubert = ROOT / "assets" / "hubert" / "hubert_base.pt"
    if not hubert.is_file() or hubert.stat().st_size < 1_000_000:
        return (
            f"缺少 hubert_base.pt（引擎资源未补全）。期望路径：{hubert}\n"
            "请回到主界面完成「引擎资源」下载后再试。"
        )
    if f0method.lower() == "rmvpe":
        rmvpe = ROOT / "assets" / "rmvpe" / "rmvpe.pt"
        if not rmvpe.is_file() or rmvpe.stat().st_size < 1_000_000:
            return (
                f"缺少 rmvpe.pt（引擎资源未补全）。期望路径：{rmvpe}\n"
                "请回到主界面完成「引擎资源」下载后再试。"
            )
    return None


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


def _tune_torch(total_seconds: float = 0.0, total_files: int = 1) -> None:
    """Offline conversion knobs — see infer.lib.torch_runtime.tune_for_inference."""
    try:
        from infer.lib.torch_runtime import tune_for_inference

        tune_for_inference(total_seconds=total_seconds, total_files=total_files)
    except TypeError:
        # 旧签名（没有规模参数）也要能跑。
        try:
            from infer.lib.torch_runtime import tune_for_inference

            tune_for_inference()
        except Exception:
            pass
    except Exception:
        pass


def _estimate_seconds(paths: list[Path]) -> float:
    """按体积粗估总时长，只用来决定要不要开 cudnn.benchmark。

    解码一遍拿准确时长对批量目录太贵。压缩音频按 16 KB/s（128kbps）估，wav
    按 44.1kHz/16bit 单声道 88 KB/s 估。估错一倍也不影响这个二值决策。
    """
    total = 0.0
    for p in paths:
        try:
            size = p.stat().st_size
        except OSError:
            continue
        per_sec = 88_200.0 if p.suffix.lower() == ".wav" else 16_000.0
        total += size / per_sec
    return total


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
    f0method_raw = str(req.get("f0method") or "rmvpe").strip() or "rmvpe"
    f0method, f0_note = normalize_f0method(f0method_raw)
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
    srcs = [p for p, _ in files]
    weights = file_weights(srcs)
    prog = StsProgress(total, f0method, weights=weights, emit=emit)

    _ensure_rvc_env()
    miss = _preflight_engine(f0method)
    if miss:
        emit(phase="error", message=miss)
        return 1

    if total == 1:
        start_msg = "共 1 个文件，准备开始"
    else:
        start_msg = f"共 {total} 个文件（按体积加权进度），准备开始"
    if f0_note:
        start_msg = f"{start_msg}（{f0_note}）"
    emit(phase="start", total=total, pct=0, current=0, ok=0, skip=0, message=start_msg)

    est_seconds = _estimate_seconds(srcs)
    _tune_torch(total_seconds=est_seconds, total_files=total)
    cuda_empty_cache()

    try:
        from configs.config import Config
        from infer.modules.vc.modules import VC

        # Config 也会读 sys.argv；清掉以免和本脚本参数打架。
        sys.argv = [sys.argv[0]]
        prog.load("config", 0.0)
        config = Config()
        prog.load("config", 1.0)
        # Config 可能刚跑过探测；再调一次 cudnn.benchmark 等。
        _tune_torch(total_seconds=est_seconds, total_files=total)
        vc = VC(config)
        # get_vc 认绝对路径（User_Data/models/...）
        prog.load("model", 0.0)
        vc.get_vc(model)
        prog.load("model", 1.0)
        # 批量：hubert / rmvpe 先拉起来，后面每个文件只付推理成本。
        preload_side_models(vc, config, f0method, prog)
        # 只在显存紧时清；加载后强清一次把碎片归还给池，后面尽量不碰。
        cuda_empty_cache()
    except Exception as e:
        traceback.print_exc()
        emit(phase="error", message=f"加载模型失败：{friendly_error(e)}")
        return 1

    out_files, skipped, _cancelled = run_batch(
        vc,
        files,
        out_dir,
        {
            "pitch": pitch,
            "f0method": f0method,
            "index_path": index if index and Path(index).is_file() else None,
            "index_rate": index_rate,
            "filter_radius": filter_radius,
            "resample_sr": resample_sr,
            "rms_mix_rate": rms_mix_rate,
            "protect": protect,
        },
        prog,
        emit,
        # 冷路径的取消是壳直接杀进程，不需要软取消。
        should_cancel=None,
    )

    if not out_files:
        # 一个都没成，这就是失败，不能报「全部完成 0 个」。
        first = skipped[0]["reason"] if skipped else "未知错误"
        emit(phase="error", message=f"{total} 个文件全部转换失败。第一个原因：{first}")
        return 1

    emit(
        phase="done",
        files=out_files,
        skipped=skipped,
        total=total,
        pct=100,
        current=total,
        ok=len(out_files),
        skip=len(skipped),
        message=f"完成 {len(out_files)} 个，跳过 {len(skipped)} 个",
    )
    return 0


# 旧名字仍被 tests/test_sts_worker.py 和外部脚本引用，保留为别名。
_friendly_error = friendly_error
_normalize_f0method = normalize_f0method
_is_oom = sts_core.is_oom
_cuda_empty_cache = cuda_empty_cache


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except SystemExit:
        raise
    except Exception as e:
        traceback.print_exc()
        emit(phase="error", message=str(e))
        raise SystemExit(1)
