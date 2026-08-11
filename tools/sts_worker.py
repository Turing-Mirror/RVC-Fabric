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
        "weight_uvr5_root",
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


def _friendly_error(exc: BaseException | str) -> str:
    """把 torch / CUDA 的长 traceback 收成用户能照着做的中文提示。

    vc_single 失败时会把整段 traceback 塞进 info 字符串，所以参数既可能是
    Exception 也可能是那串文本。
    """
    text = str(exc) if not isinstance(exc, BaseException) else (str(exc) or type(exc).__name__)
    low = text.lower()
    if "out of memory" in low or "cuda out of memory" in low:
        return (
            "显存不够（CUDA OOM）。常见原因：实时变声还在跑、音频太长、或显卡显存较小（如 3GB）。\n"
            "请先在主界面停止变声，关闭其他占 GPU 的程序后重试；"
            "仍失败可把音高算法改成 harvest 或 pm（更省显存），或把长音频切短再转。"
        )
    if "显存不够" in text or "缺少 hubert" in text:
        return text
    return text


def _cuda_empty_cache() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def collect_inputs(path: str) -> list[tuple[Path, Path]]:
    """返回 (源文件, 相对路径)。

    相对路径决定输出落在哪：文件夹输入时按原目录层级还原到输出目录，
    不然 `A/vocal.wav` 和 `B/vocal.wav` 会被铺平成 `vocal_rvc.wav` 和
    `vocal_rvc_1.wav`，谁是谁分不出来。
    """
    p = Path(path)
    if p.is_file():
        return [(p, Path(p.name))]
    if not p.is_dir():
        return []
    files: list[tuple[Path, Path]] = []
    for f in sorted(p.rglob("*")):
        if f.is_file() and f.suffix.lower() in AUDIO_EXT:
            try:
                rel = f.relative_to(p)
            except ValueError:
                rel = Path(f.name)
            files.append((f, rel))
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

    _ensure_rvc_env()
    miss = _preflight_engine(f0method)
    if miss:
        emit(phase="error", message=miss)
        return 1

    emit(phase="start", total=total, message=f"共 {total} 个文件")
    _cuda_empty_cache()

    try:
        from scipy.io import wavfile

        from configs.config import Config
        from infer.modules.vc.modules import VC

        # Config 也会读 sys.argv；清掉以免和本脚本参数打架。
        sys.argv = [sys.argv[0]]
        config = Config()
        vc = VC(config)
        # get_vc 认绝对路径（User_Data/models/...）
        vc.get_vc(model)
        _cuda_empty_cache()
    except Exception as e:
        traceback.print_exc()
        emit(phase="error", message=f"加载模型失败：{_friendly_error(e)}")
        return 1

    out_files: list[str] = []
    skipped: list[dict] = []
    for i, (src, rel) in enumerate(files, start=1):
        emit(
            phase="run",
            done=i - 1,
            total=total,
            message=f"正在转换 {src.name}（{i}/{total}）",
        )
        try:
            # 输出保持输入的目录层级：单文件时 rel 就是文件名，落在输出目录根下。
            sub = Path(out_dir) / rel.parent
            sub.mkdir(parents=True, exist_ok=True)
            stem = src.stem
            dest = sub / f"{stem}_rvc.wav"
            # 重名则加序号
            n = 1
            while dest.exists():
                dest = sub / f"{stem}_rvc_{n}.wav"
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
                # vc_single 吞掉异常后把 traceback 塞进 info；OOM 也走这条。
                raise RuntimeError(_friendly_error(info or "未知错误"))
            wavfile.write(str(dest), wav_opt[0], wav_opt[1])
            out_files.append(str(dest))
            emit(
                phase="run",
                done=i,
                total=total,
                message=f"完成 {src.name}",
            )
        except Exception as e:
            # 单个文件坏掉不该毁掉整批：记下来接着跑，最后一起报。
            # 批量转 50 个，第 3 个是段损坏的 mp3，剩下 47 个照样得转出来。
            traceback.print_exc()
            reason = _friendly_error(e)
            skipped.append({"file": str(src), "name": src.name, "reason": reason})
            emit(
                phase="skip",
                done=i,
                total=total,
                message=f"跳过 {src.name}：{reason}",
            )
        finally:
            _cuda_empty_cache()

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
        message=f"完成 {len(out_files)} 个，跳过 {len(skipped)} 个",
    )
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
