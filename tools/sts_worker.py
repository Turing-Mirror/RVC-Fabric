# -*- coding: utf-8 -*-
"""离线语音转换 worker（Speech-to-Speech / 音频 → 目标音色）——冷路径。

对应官方 RVC WebUI「推理 / 批量推理」：用当前选中的 .pth 把人声音频换成
目标音色。不是 TTS——输入必须是声音文件。

这是**冷路径**：独立进程，从盘上把 hubert / net_g / rmvpe 全读一遍，代价是
几十秒的冷启动。实时 worker 活着的时候，壳会走热路径（`gui_v1` 的 `convert`
命令，直接用常驻模型），根本不起这个进程。两条路的转换循环都在
`tools/sts_core.py`，这里只负责「把模型从盘上装起来」和「把进度写 stdout」。

加了 `--resident` 就**不在跑完一批之后退出**：模型留在显存里，从 stdin 一行
一行接下一个请求文件的路径。冷启动的几十秒从此只在开软件后的第一次转换付一
次——只用离线转换、从来不开实时变声的用户，以前是每转一次付一次。协议：

* 壳 → worker：一行一个请求 json 的路径；空行忽略；`exit` 或 stdin 关闭即退出。
* worker → 壳：原有的 start / run / skip / done / error 进度行，外加每批收尾
  后的一行 ``{"phase": "idle"}``——壳看见它才知道「这批完了、进程还活着、可以
  再派活」。不带 `--resident` 时没有这一行，行为与从前完全一致。

用法::

    Runtime\\python.exe tools/sts_worker.py <请求.json> [--resident]

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

import contextlib
import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import sts_core  # noqa: E402 — 上面要先把产品根塞进 sys.path
from tools import msg_codes as mc  # noqa: E402
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
    # 常驻模式下请求路径是从 stdin 读的，用户名是中文时管道上就是 UTF-8 字节；
    # 这里不 replace —— 路径错一个字符就是找不到文件，宁可当场炸也别静默转换。
    try:
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8")
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


def _new_timer(hot: bool):
    """计时器拿不到就返回 None —— 计时永远不该让转换失败。"""
    try:
        from tools.sts_perf import StsTimer

        return StsTimer(hot=hot)
    except Exception:
        return None


@contextlib.contextmanager
def _stage(timer, name: str):
    if timer is None:
        yield
        return
    with timer.stage(name):
        yield


def _save_timing(timer, **extra) -> None:
    if timer is None:
        return
    try:
        path = timer.save(str(ROOT / "User_Data" / "perf_reports"), extra=extra)
        if path:
            s = timer.summary(extra)
            print(
                f"[sts_perf] total={s['total_s']}s load={s['load_share'] * 100:.0f}% "
                f"stages={s['stages_s']}",
                file=sys.stderr,
            )
    except Exception:
        pass


class _Engine:
    """常驻进程里活着的那份引擎。

    冷启动那几十秒的构成是固定的：import torch / fairseq、`Config()` 探设备、
    读 net_g、读 hubert、读 rmvpe。这五样里只有 net_g 跟着音色走，其余四样换谁
    来转都一样 —— 所以它们该活到进程结束，而不是活到这一批结束。
    """

    def __init__(self) -> None:
        self.config = None
        self.vc = None
        # 已经装进显存的那个 pth 的路径。空字符串 = 还没装或上次装失败。
        self.model = ""

    def reset(self) -> None:
        """装模型这一步炸了就整个丢掉重来，别留半个 vc 给下一条请求。"""
        self.config = None
        self.vc = None
        self.model = ""
        cuda_empty_cache()


def _prepare(engine: "_Engine", model: str, f0method: str, prog, timer,
             est_seconds: float, total: int) -> None:
    """把这条请求需要的模型准备好。已经在显存里的一概不重读。"""
    if engine.vc is None:
        with _stage(timer, "import"):
            from configs.config import Config
            from infer.modules.vc.modules import VC

        # Config 也会读 sys.argv；清掉以免和本脚本参数打架。
        sys.argv = [sys.argv[0]]
        prog.load("config", 0.0)
        with _stage(timer, "config"):
            config = Config()
            # DirectML 上 hubert 的 GradMultiply 会抛 PrivateUse1。load_hubert
            # 里也会打这份补丁，这里提前打：冷路径入口必须自己接 dml_compat，
            # 不能只靠下游某层「顺手打一下」。26.8.22/4（Intel Iris Xe，1.5.4）
            # 四次语音转换全挂在同一句 x.new(x)，热路径当时根本没接上。
            from infer.lib.dml_compat import apply_for

            apply_for(config)
        prog.load("config", 1.0)
        # Config 可能刚跑过探测；再调一次 cudnn.benchmark 等。
        _tune_torch(total_seconds=est_seconds, total_files=total)
        engine.config = config
        engine.vc = VC(config)
    else:
        # 复用：import、设备探测这两段一分钱都不用再付。进度条别卡在 0。
        prog.load("config", 1.0)
        _tune_torch(total_seconds=est_seconds, total_files=total)

    if engine.model != model:
        prog.load("model", 0.0)
        with _stage(timer, "model"):
            # get_vc 会重建 pipeline，180MB 的 rmvpe 跟着 pipeline 一起没了。
            # 换音色只该付 net_g 的钱，rmvpe 原样接回去 —— 但只在半精度与设备
            # 都没变时接，两者任一不同就让 preload_side_models 重新装。
            pipe = getattr(engine.vc, "pipeline", None)
            old_rmvpe = getattr(pipe, "model_rmvpe", None)
            old_half = getattr(pipe, "is_half", None)
            old_dev = str(getattr(pipe, "device", ""))
            # get_vc 中途炸掉时 vc 里留着半个模型，下一条请求不能当它装好了。
            engine.model = ""
            engine.vc.get_vc(model)
            engine.model = model
            pipe = getattr(engine.vc, "pipeline", None)
            if (
                old_rmvpe is not None
                and pipe is not None
                and not hasattr(pipe, "model_rmvpe")
                and getattr(pipe, "is_half", None) == old_half
                and str(getattr(pipe, "device", "")) == old_dev
            ):
                pipe.model_rmvpe = old_rmvpe
        prog.load("model", 1.0)
    else:
        prog.load("model", 1.0)

    # 批量：hubert / rmvpe 先拉起来，后面每个文件只付推理成本。
    # 已经装好的话这里只是把进度打满，不重读。
    with _stage(timer, "hubert"):
        preload_side_models(engine.vc, engine.config, f0method, prog)
    # 只在显存紧时清；加载后强清一次把碎片归还给池，后面尽量不碰。
    cuda_empty_cache()


def run_request(engine: "_Engine", req: dict) -> int:
    """跑一条转换请求。返回值即进程退出码的语义（0 成功）。"""
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
    rms_mix_rate = float(req.get("rms_mix_rate") if req.get("rms_mix_rate") is not None else 0.25)
    protect = float(req.get("protect") if req.get("protect") is not None else 0.33)
    fmt = sts_core.normalize_format(str(req.get("format") or "wav"))
    try:
        sid = max(int(req.get("sid") or 0), 0)
    except (TypeError, ValueError):
        sid = 0
    f0_path = str(req.get("f0_file") or "").strip()
    f0_file = None
    if f0_path:
        if not Path(f0_path).is_file():
            emit(phase="error", **mc.msg_fields(mc.STS_F0_CURVE_MISSING, {"path": f0_path}))
            return 2
        f0_file = type("F0File", (), {"name": f0_path})()

    if not inp or not out_dir or not model:
        emit(phase="error", **mc.msg_fields(mc.STS_EMPTY_FIELDS))
        return 2
    if not Path(model).is_file():
        emit(phase="error", **mc.msg_fields(mc.STS_MODEL_MISSING, {"model": model}))
        return 2

    files = collect_inputs(inp)
    if not files:
        emit(phase="error", **mc.msg_fields(mc.STS_NO_AUDIO))
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

    # 分段计时。「一条 5 秒语音要一两分钟」之前只能靠读代码估，估错了力气就
    # 花在错的地方。落一份本地 JSON，用户发过来我们才有别人机器上的真数字。
    # reused 记的是「这次省掉了几段加载」，复用到底值多少钱要拿它对。
    reused = engine.vc is not None
    timer = _new_timer(hot=False)

    try:
        _prepare(engine, model, f0method, prog, timer, est_seconds, total)
    except Exception as e:
        traceback.print_exc()
        engine.reset()
        # 训练存档单独立码：壳侧给这个码配了「打开训练窗」按钮，用户手里的
        # G_/D_ 存档要先在模型提取里转成音色才有得转。
        if "训练过程中的存档" in str(e):
            emit(phase="error", **mc.msg_fields(mc.STS_MODEL_IS_ARCHIVE))
        else:
            emit(phase="error", **mc.msg_fields(mc.STS_LOAD_FAILED, {"error": friendly_error(e)}))
        return 1

    with _stage(timer, "convert"):
        out_files, skipped, _cancelled = run_batch(
            engine.vc,
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
                "format": fmt,
                "sid": sid,
                "f0_file": f0_file,
            },
            prog,
            emit,
            # 冷路径的取消是壳直接杀进程，不需要软取消。
            should_cancel=None,
        )
    _save_timing(timer, total=total, ok=len(out_files), seconds=est_seconds, reused=reused)

    if not out_files:
        # 一个都没成，这就是失败，不能报「全部完成 0 个」。
        first = skipped[0]["reason"] if skipped else "未知错误"
        emit(
            phase="error",
            **mc.msg_fields(mc.STS_ALL_FAILED, {"total": total, "first": first}),
        )
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
        **mc.msg_fields(
            mc.STS_DONE, {"done": len(out_files), "skipped": len(skipped)}
        ),
    )
    return 0


def _run_request_file(engine: "_Engine", path: str) -> int:
    try:
        req = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        emit(phase="error", **mc.msg_fields(mc.STS_BAD_REQUEST, {"error": e}))
        return 2
    return run_request(engine, req)


def main(argv: list[str]) -> int:
    _ensure_stdio_utf8()
    rest = list(argv[1:])
    resident = "--resident" in rest
    reqs = [a for a in rest if not a.startswith("--")]
    if not reqs:
        emit(phase="error", **mc.msg_fields(mc.STS_NO_REQUEST))
        return 2

    engine = _Engine()
    rc = _run_request_file(engine, reqs[0])
    if not resident:
        return rc

    # 壳靠这一行判断「这批收尾了、进程还活着」。不带 --resident 时没有这一行，
    # 壳那边照旧用 stdout 关闭当收尾信号，老行为一个字都没变。
    emit(phase="idle")
    while True:
        try:
            line = sys.stdin.readline()
        except Exception:
            break
        # 空串 = 壳把 stdin 关了 = 让我退出（空闲超时、开实时变声要腾显存…）。
        if not line:
            break
        path = line.strip()
        if not path:
            continue
        if path == "exit":
            break
        _run_request_file(engine, path)
        emit(phase="idle")
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
