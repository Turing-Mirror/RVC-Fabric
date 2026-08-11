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

    {"phase":"start","total":N,"message":"..."}
    {"phase":"run","done":i,"total":N,"pct":0-100,"step":"...","message":"..."}
    {"phase":"done","files":[...]}
    {"phase":"error","message":"..."}

``pct`` 是整次任务 0–100 的细粒度进度（含模型加载与单文件内分步），
界面优先用它画条；``done/total`` 仍是文件级计数，批量时对照用。
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


class StsProgress:
    """把「加载模型 + 每个文件的子步骤」映射成 0–100 的整体进度。

    单文件时 done/total 只有 0→1，转换可能跑几分钟界面却一直 0%——所以必须
    再发 ``pct`` 和分步 ``message``，用户才能知道卡在读音频 / 音高 / 推理哪一步。
    """

    # 加载模型占前 10%，其余 90% 均分给每个文件。
    LOAD_END = 10.0
    # 单文件内各阶段在文件份额中的起止（0..1）。
    STAGE_SPAN = {
        "read": (0.00, 0.08),
        "hubert": (0.08, 0.16),
        "f0": (0.16, 0.48),
        "infer": (0.48, 0.92),
        "write": (0.92, 1.00),
    }

    def __init__(self, total_files: int, f0method: str = "rmvpe"):
        self.total = max(1, int(total_files))
        self.f0method = (f0method or "rmvpe").strip() or "rmvpe"
        self._last_pct = -1
        self._last_msg = ""
        self._file_i = 0  # 0-based，当前正在处理的文件
        self._file_name = ""

    def _push(self, done_files: int, pct: float, message: str, step: str = "") -> None:
        pct_i = int(max(0, min(100, round(pct))))
        # 同百分比但文案变了（子步骤切换）必须推；文案和百分比都没变则节流。
        # 推理/音高分块可能每块只动 1%，允许同 step 下 pct 连涨。
        if pct_i == self._last_pct and message == self._last_msg:
            return
        self._last_pct = pct_i
        self._last_msg = message
        emit(
            phase="run",
            done=max(0, int(done_files)),
            total=self.total,
            pct=pct_i,
            step=step,
            message=message,
        )

    def load(self, phase: str, frac: float = 0.0) -> None:
        """phase: config | model；frac 0..1。"""
        frac = max(0.0, min(1.0, float(frac)))
        if phase == "config":
            pct = self.LOAD_END * 0.35 * frac
            msg = "正在初始化引擎…"
        else:
            pct = self.LOAD_END * (0.35 + 0.65 * frac)
            msg = "正在加载音色模型…"
        self._push(0, pct, msg, step=f"load_{phase}")

    def begin_file(self, index: int, name: str) -> None:
        """index 为 1-based 序号。"""
        self._file_i = max(0, int(index) - 1)
        self._file_name = name
        start, _ = self._file_bounds(self._file_i)
        if self.total == 1:
            msg = f"开始转换 {name}"
        else:
            msg = f"开始转换 {name}（{index}/{self.total}）"
        self._push(self._file_i, start, msg, step="file_start")

    def _file_bounds(self, file_i: int) -> tuple[float, float]:
        span = 100.0 - self.LOAD_END
        start = self.LOAD_END + span * file_i / self.total
        end = self.LOAD_END + span * (file_i + 1) / self.total
        return start, end

    def stage(self, stage: str, frac: float = 0.0) -> None:
        """文件内子步骤。stage: read/hubert/f0/infer/write；frac 0..1。"""
        frac = max(0.0, min(1.0, float(frac)))
        a, b = self.STAGE_SPAN.get(stage, (0.0, 1.0))
        start, end = self._file_bounds(self._file_i)
        pct = start + (end - start) * (a + (b - a) * frac)
        name = self._file_name or "音频"
        prefix = f"{name} · " if self.total > 1 else ""
        if stage == "read":
            msg = f"{prefix}读取音频…"
        elif stage == "hubert":
            msg = f"{prefix}加载特征模型（hubert）…"
        elif stage == "f0":
            # rmvpe 会按 mel 分块回调 frac，这里把百分比写进文案。
            if frac <= 0.02:
                msg = f"{prefix}提取音高（{self.f0method}）…"
            else:
                msg = f"{prefix}提取音高（{self.f0method}）… {int(frac * 100)}%"
        elif stage == "infer":
            if frac <= 0.0:
                msg = f"{prefix}音色转换中…"
            else:
                msg = f"{prefix}音色转换中… {int(frac * 100)}%"
        elif stage == "write":
            msg = f"{prefix}写入输出文件…"
        else:
            msg = f"{prefix}处理中…"
        self._push(self._file_i, pct, msg, step=stage)

    def file_done(self, index: int, name: str, ok: bool = True) -> None:
        _, end = self._file_bounds(max(0, int(index) - 1))
        if ok:
            msg = (
                f"完成 {name}"
                if self.total == 1
                else f"完成 {name}（{index}/{self.total}）"
            )
        else:
            msg = (
                f"跳过 {name}"
                if self.total == 1
                else f"跳过 {name}（{index}/{self.total}）"
            )
        self._push(index, end, msg, step="file_done" if ok else "file_skip")

    @property
    def last_pct(self) -> int:
        return self._last_pct if self._last_pct >= 0 else 0


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
    prog = StsProgress(total, f0method)

    _ensure_rvc_env()
    miss = _preflight_engine(f0method)
    if miss:
        emit(phase="error", message=miss)
        return 1

    emit(phase="start", total=total, pct=0, message=f"共 {total} 个文件，准备开始")
    _cuda_empty_cache()

    try:
        from scipy.io import wavfile

        from configs.config import Config
        from infer.modules.vc.modules import VC

        # Config 也会读 sys.argv；清掉以免和本脚本参数打架。
        sys.argv = [sys.argv[0]]
        prog.load("config", 0.0)
        config = Config()
        prog.load("config", 1.0)
        vc = VC(config)
        # get_vc 认绝对路径（User_Data/models/...）
        prog.load("model", 0.0)
        vc.get_vc(model)
        prog.load("model", 1.0)
        _cuda_empty_cache()
    except Exception as e:
        traceback.print_exc()
        emit(phase="error", message=f"加载模型失败：{_friendly_error(e)}")
        return 1

    out_files: list[str] = []
    skipped: list[dict] = []
    for i, (src, rel) in enumerate(files, start=1):
        prog.begin_file(i, src.name)

        def on_stage(stage: str, frac: float = 0.0, _i=i, _name=src.name) -> None:
            # 闭包默认参数钉死当前文件，避免循环变量晚绑定。
            prog._file_i = _i - 1
            prog._file_name = _name
            prog.stage(stage, frac)

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
                progress_cb=on_stage,
            )
            if wav_opt is None or wav_opt[0] is None:
                # vc_single 吞掉异常后把 traceback 塞进 info；OOM 也走这条。
                raise RuntimeError(_friendly_error(info or "未知错误"))
            prog.stage("write", 0.0)
            wavfile.write(str(dest), wav_opt[0], wav_opt[1])
            prog.stage("write", 1.0)
            out_files.append(str(dest))
            prog.file_done(i, src.name, ok=True)
        except Exception as e:
            # 单个文件坏掉不该毁掉整批：记下来接着跑，最后一起报。
            # 批量转 50 个，第 3 个是段损坏的 mp3，剩下 47 个照样得转出来。
            traceback.print_exc()
            reason = _friendly_error(e)
            skipped.append({"file": str(src), "name": src.name, "reason": reason})
            prog.file_done(i, src.name, ok=False)
            emit(
                phase="skip",
                done=i,
                total=total,
                pct=prog.last_pct,
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
        pct=100,
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
