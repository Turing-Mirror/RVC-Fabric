from __future__ import annotations

import contextlib
import os
import sys
from dotenv import load_dotenv
import shutil

load_dotenv()

os.environ["OMP_NUM_THREADS"] = "4"
if sys.platform == "darwin":
    os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

now_dir = os.getcwd()
sys.path.append(now_dir)
import multiprocessing

flag_vc = False


def printt(strr, *args):
    if len(args) == 0:
        print(strr)
    else:
        print(strr % args)


# 和 Rust engine_assets.rs 同一套五件套。缺任何一件就别去建 RVC：
# hubert/rmvpe 会炸，ffmpeg 是离线工具用的，产品层把它们绑成一份 engine-core。
_ENGINE_CORE_FILES = (
    (os.path.join("assets", "hubert", "hubert_base.pt"), 1_000_000),
    (os.path.join("assets", "rmvpe", "rmvpe.pt"), 1_000_000),
    (os.path.join("assets", "rmvpe", "rmvpe.onnx"), 100_000),
    ("ffmpeg.exe", 1_000_000),
    ("ffprobe.exe", 1_000_000),
)


def _engine_core_ready(root=None):
    base = root or now_dir
    for rel, min_sz in _ENGINE_CORE_FILES:
        p = os.path.join(base, rel)
        try:
            if not os.path.isfile(p) or os.path.getsize(p) < min_sz:
                return False
        except OSError:
            return False
    return True


# Upstream engine pieces (ffmpeg/faiss/model loaders) are unreliable on
# non-ASCII install paths — warn early so support can spot it in the log
if any(ord(_c) > 127 for _c in os.getcwd()):
    printt("WARNING: install path contains non-ASCII characters: %s", os.getcwd())
    printt("WARNING: 安装路径含中文/特殊字符，部分组件可能异常，建议移到纯英文路径")


try:
    from tools.msg_codes import (  # noqa: F401
        DEV_INVALID,
        DEV_LIST_FAILED,
        DEV_REFRESHED,
        ENGINE_LOOP_ERROR,
        ENGINE_QUIT,
        VC_BAD_SETTINGS,
        VC_LOADING_HUBERT,
        VC_LOADING_INDEX,
        VC_LOADING_MODEL,
        VC_LOADING_NET,
        VC_NEED_MODEL,
        VC_OPENING_STREAM,
        VC_PARAMS_APPLIED,
        VC_PTH_MISSING,
        VC_RUNNING,
        VC_START_FAILED,
        VC_STOP_FAILED,
        VC_SWAP_FAILED,
        VC_SWAPPING,
        VC_UNKNOWN_CMD,
        VC_WARMUP,
    )
except Exception:
    # `tools` 不在 path 上（脚本被单独跑起来）。码本身就是字符串常量，
    # 抄一份不会漂 —— 真漂了 tests/test_realtime_protocol.py 会当场报出来。
    DEV_INVALID = "dev.invalid"
    DEV_LIST_FAILED = "dev.list_failed"
    DEV_REFRESHED = "dev.refreshed"
    ENGINE_LOOP_ERROR = "engine.loop_error"
    ENGINE_QUIT = "engine.quit"
    VC_BAD_SETTINGS = "vc.bad_settings"
    VC_LOADING_HUBERT = "vc.loading_hubert"
    VC_LOADING_INDEX = "vc.loading_index"
    VC_LOADING_MODEL = "vc.loading_model"
    VC_LOADING_NET = "vc.loading_net"
    VC_NEED_MODEL = "vc.need_model"
    VC_OPENING_STREAM = "vc.opening_stream"
    VC_PARAMS_APPLIED = "vc.params_applied"
    VC_PTH_MISSING = "vc.pth_missing"
    VC_RUNNING = "vc.running"
    VC_START_FAILED = "vc.start_failed"
    VC_STOP_FAILED = "vc.stop_failed"
    VC_SWAP_FAILED = "vc.swap_failed"
    VC_SWAPPING = "vc.swapping"
    VC_UNKNOWN_CMD = "vc.unknown_cmd"
    VC_WARMUP = "vc.warmup"


def _msg(code: str, **params):
    """状态消息的一套字段：`message_code` + zh-CN 兜底 `message`（+ `message_params`）。

    状态栏那行小字以前是直接写中文的，界面切到别的语言也照样是中文 —— 壳层
    只会翻译带 `message_code` 的消息。这里统一走 msg_codes，每条消息都带上码，
    壳层按当前界面语言取译文，取不到才落回这里的中文。

    `tools` 不在 path 上时（脚本被单独跑起来）退回只有中文的那份，不让一个
    import 失败把整条状态写没了。
    """
    try:
        from tools.msg_codes import status_fields

        return status_fields(code, params or None)
    except Exception:
        out = {"message_code": code, "message": code}
        if params:
            out["message_params"] = dict(params)
        return out


def soft_clip_np(data: "np.ndarray", ceiling: float = 0.97) -> "np.ndarray":
    """Gentle peak soft-clip (cubic) then hard limit — less DAC harshness than bare clip."""
    import numpy as np

    x = np.asarray(data, dtype=np.float32)
    # slightly stronger soft knee than 0.12 — peaks a bit less brittle
    y = x - (x * x * x) * 0.15
    np.clip(y, -ceiling, ceiling, out=y)
    return y


def phase_vocoder(a, b, fade_out, fade_in):
    window = torch.sqrt(fade_out * fade_in)
    fa = torch.fft.rfft(a * window)
    fb = torch.fft.rfft(b * window)
    absab = torch.abs(fa) + torch.abs(fb)
    n = a.shape[0]
    if n % 2 == 0:
        absab[1:-1] *= 2
    else:
        absab[1:] *= 2
    phia = torch.angle(fa)
    phib = torch.angle(fb)
    deltaphase = phib - phia
    deltaphase = deltaphase - 2 * np.pi * torch.floor(deltaphase / 2 / np.pi + 0.5)
    w = 2 * np.pi * torch.arange(n // 2 + 1).to(a) + deltaphase
    t = torch.arange(n).unsqueeze(-1).to(a) / n
    result = (
        a * (fade_out**2)
        + b * (fade_in**2)
        + torch.sum(absab * torch.cos(w * t + phia), -1) * window / n
    )
    return result


class Harvest(multiprocessing.Process):
    def __init__(self, inp_q, opt_q):
        multiprocessing.Process.__init__(self)
        self.inp_q = inp_q
        self.opt_q = opt_q

    def run(self):
        import numpy as np
        import pyworld

        while 1:
            idx, x, res_f0, n_cpu, ts = self.inp_q.get()
            f0, t = pyworld.harvest(
                x.astype(np.double),
                fs=16000,
                f0_ceil=1100,
                f0_floor=50,
                frame_period=10,
            )
            res_f0[idx] = f0
            if len(res_f0.keys()) >= n_cpu:
                self.opt_q.put(ts)


if __name__ == "__main__":
    import json
    import multiprocessing
    import re
    import threading
    import time
    import traceback
    from multiprocessing import Queue, cpu_count
    from tools.audio_io_process import AudioIoProcess
    from multiprocessing.shared_memory import SharedMemory
    from queue import Empty

    # Multiprocessing children must use pythonw (no Runtime\\python.exe flash)
    try:
        from tools.worker_protocol import force_windowed_multiprocessing

        force_windowed_multiprocessing()
    except Exception:
        try:
            from pathlib import Path as _Path

            _pyw = _Path(sys.executable).with_name("pythonw.exe")
            if _pyw.is_file():
                multiprocessing.set_executable(str(_pyw))
        except Exception:
            pass

    import librosa
    from tools.torchgate import TorchGate
    import numpy as np
    import FreeSimpleGUI as sg
    import sounddevice as sd
    if os.environ.get("TM_REALTIME_WORKER", "").strip() in ("1", "true", "yes"):
        try:
            from tools.worker_protocol import write_status as _boot_status
            from tools.msg_codes import ENGINE_IMPORTING, status_fields as _boot_sf

            _boot_status(
                state="starting",
                progress=16,
                **_boot_sf(ENGINE_IMPORTING),
            )
        except Exception:
            pass
    import torch
    import torch.nn.functional as F
    import torchaudio.transforms as tat

    if os.environ.get("TM_REALTIME_WORKER", "").strip() in ("1", "true", "yes"):
        try:
            from tools.worker_protocol import write_status as _boot_status2
            from tools.msg_codes import ENGINE_IMPORTING, status_fields as _boot_sf2

            _boot_status2(
                state="starting",
                progress=22,
                **_boot_sf2(ENGINE_IMPORTING),
            )
        except Exception:
            pass

    # realtime process is inference-only: skip autograd bookkeeping everywhere
    # (SOLA / noise gate / resample run outside the engine's no_grad blocks)
    torch.set_grad_enabled(False)

    from infer.lib import rtrvc as rvc_for_realtime
    from i18n.i18n import I18nAuto
    from configs.config import Config

    i18n = I18nAuto()

    # device = rvc_for_realtime.config.device
    # device = torch.device(
    #     "cuda"
    #     if torch.cuda.is_available()
    #     else ("mps" if torch.backends.mps.is_available() else "cpu")
    # )
    current_dir = os.getcwd()
    inp_q = Queue()
    opt_q = Queue()
    n_cpu = min(cpu_count(), 8)
    # Harvest only if user config uses harvest (see ensure_harvest_workers)
    _harvest_workers: list = []

    def ensure_harvest_workers(n: int | None = None) -> None:
        """Start harvest pool once; default f0 fcpe/rmvpe never needs this."""
        global _harvest_workers
        if _harvest_workers:
            return
        try:
            from tools.worker_protocol import force_windowed_multiprocessing

            force_windowed_multiprocessing()
        except Exception:
            pass
        count = max(1, int(n or n_cpu))
        for _ in range(count):
            p = Harvest(inp_q, opt_q)
            p.daemon = True
            p.start()
            _harvest_workers.append(p)

    @contextlib.contextmanager
    def _sts_stage(timer, name: str):
        """timer 可能是 None（sts_perf 导入失败），两种情况都要能用。"""
        if timer is None:
            yield
            return
        with timer.stage(name):
            yield


    class GUIConfig:
        def __init__(self) -> None:
            self.pth_path: str = ""
            self.index_path: str = ""
            self.pitch: int = 0
            self.formant=0.0
            self.sr_type: str = "sr_model"
            # Defaults tuned for realtime product feel (shell may override)
            self.block_time: float = 0.22  # s — slightly snappier than 0.25
            self.threhold: int = -48  # >-60 enables gate; cuts room noise when quiet
            self.in_gain_db: float = 0.0  # mic pre-gain before gate/meter, hot
            self.crossfade_time: float = 0.05
            self.extra_time: float = 2.5
            self.I_noise_reduce: bool = False
            self.O_noise_reduce: bool = False
            self.use_pv: bool = False
            self.rms_mix_rate: float = 0.25  # follow speech loudness a bit
            self.index_rate: float = 0.0
            self.n_cpu: int = min(n_cpu, 4)
            self.f0method: str = "fcpe"
            self.sg_hostapi: str = ""
            self.wasapi_exclusive: bool = False
            self.sg_input_device: str = ""
            self.sg_output_device: str = ""
            self.monitor_device: str = ""
            self.monitor_enabled: bool = False
            # Post-RVC DSP (tools.dsp_fx) — flat keys mirrored from app_config
            self.fx_enabled: bool = False
            self.fx_gate_enabled: bool = True
            self.fx_gate_threshold_db: float = -50.0
            self.fx_gate_release_ms: float = 50.0
            self.fx_gate_hold_ms: float = 20.0
            self.fx_gate_range_db: float = 20.0
            self.fx_comp_enabled: bool = True
            self.fx_comp_threshold_db: float = -20.0
            self.fx_comp_ratio: float = 4.0
            self.fx_comp_attack_ms: float = 5.0
            self.fx_comp_release_ms: float = 100.0
            self.fx_comp_makeup_db: float = 0.0
            self.fx_eq_enabled: bool = True
            self.fx_eq_gains: list = [0.0, 0.0, 0.0, 0.0, 0.0]
            self.fx_eq_preset: str = "flat"
            self.fx_out_gain_db: float = 0.0
            # 无模型 DSP 变声（tools.dsp_voice）。dsp_enabled 打开时可以完全
            # 不选音色就开声，function 走 "fx" 分支；跟 RVC 同时开就是叠加。
            self.dsp_enabled: bool = False
            self.dsp_preset: str = ""
            self.dsp_params: dict = {}

    class GUI:
        def __init__(self) -> None:
            self.gui_config = GUIConfig()
            self.config = Config()
            self.function = "vc"
            self._fx_chain = None
            self._voice_chain = None
            # 正在跑的离线转换是哪条命令发的。转换途中靠它认出后来的 sts_cancel。
            self._sts_seq = 0
            self.delay_time = 0
            self.last_infer_ms = 0
            self.last_input_db = -90.0  # mic level for the launcher meter
            # 变声中换模型：命令线程把新模型放这儿，音频线程在两块之间取走并装上。
            # 用「排队 + 由音频线程自己动手」而不是加锁，是因为 audio_infer 从头到
            # 尾都在读 self.rvc / self.resampler2；只要换的动作发生在它自己手里，
            # 就不存在「一块音频用了新模型的采样率、旧模型的重采样器」这种半截状态。
            self._pending_model = None
            self._pending_model_lock = threading.Lock()
            # 后台线程建好的新 RVC；音频线程只做指针替换。
            self._swap_ready = None
            self._swap_busy = False
            self._swap_progress = 0
            self._swap_loader = None
            # 换模型失败时留一句话给状态栏，成功就清空。
            self._model_swap_error = ""
            self.worker_mode = os.environ.get("TM_REALTIME_WORKER", "").strip().lower() in (
                "1",
                "true",
                "yes",
            )
            self.hostapis = None
            self.input_devices = None
            self.output_devices = None
            self.input_devices_indices = None
            self.output_devices_indices = None
            self.audio_proc = None
            self.in_mem = None
            self.out_mem = None
            self.in_buf = None
            self.out_buf = None
            self.in_ptr = None
            self.out_ptr = None
            self.play_ptr = None
            self.in_evt = None
            self.stop_evt = None
            self.window = None
            self.monitor_stream = None
            self.monitor_channels = 2
            self.monitor_sr = 0
            self._monitor_q = None  # collections.deque of float32 frames
            self._monitor_err_count = 0
            self._monitor_status = ""  # last open/write message for UI
            self.update_devices()
            if self.worker_mode:
                self.worker_main()
            else:
                self.launcher()

        def _pick_default_devices(self, data):
            """Fill only missing sides. Never treat NVIDIA Broadcast as a real mic."""
            from tools.device_pick import fill_missing_devices

            inn, out, notes = fill_missing_devices(
                str(data.get("sg_input_device") or ""),
                str(data.get("sg_output_device") or ""),
                self.input_devices or [],
                self.output_devices or [],
            )
            if inn:
                data["sg_input_device"] = inn
            if out:
                data["sg_output_device"] = out
            for n in notes:
                printt("device pick: %s", n)
            return data

        def load(self):
            try:
                if not os.path.exists("configs/inuse/config.json"):
                    # 不复制模板：configs/config.json 是开发机示例配置
                    # （pitch=12、设备名全是别的机器上的），拿它当用户配置会把
                    # 音高/共鸣/设备全部顶成模板值。inuse 缺失时由 Tauri 壳每次
                    # 启动从 User_Data/app_config.json 重建，这里返回默认即可。
                    data = {}
                else:
                    with open("configs/inuse/config.json", "r", encoding="utf-8") as j:
                        data = json.load(j)
                    data["sr_model"] = data.get("sr_type", "sr_model") == "sr_model"
                    data["sr_device"] = data.get("sr_type", "sr_model") == "sr_device"
                    data["pm"] = data.get("f0method", "") == "pm"
                    data["harvest"] = data.get("f0method", "") == "harvest"
                    data["crepe"] = data.get("f0method", "") == "crepe"
                    data["rmvpe"] = data.get("f0method", "") == "rmvpe"
                    data["fcpe"] = data.get("f0method", "") == "fcpe"
                    # Drop broken index (stale logs/*.index) so start won't crash
                    ip = str(data.get("index_path") or "").strip()
                    if ip and not os.path.isfile(ip):
                        data["index_path"] = ""
                        data["index_rate"] = 0
                    elif not ip:
                        data["index_rate"] = 0
                    # 设备枚举失败不能毁配置：以前这一段一抛异常，外面的 except
                    # 就用 "w" 打开 inuse/config.json —— 文件被截断成 0 字节，
                    # 用户保存的音高/共鸣等参数全部蒸发，下次开变声还会回退到
                    # 示例模板。设备问题只影响本次启动的设备选择，配置必须保留。
                    try:
                        if data.get("sg_hostapi") in self.hostapis:
                            self.update_devices(hostapi_name=data["sg_hostapi"])
                        else:
                            # Prefer MME for Cable compatibility when present
                            if "MME" in self.hostapis:
                                data["sg_hostapi"] = "MME"
                                self.update_devices(hostapi_name="MME")
                            else:
                                data["sg_hostapi"] = self.hostapis[0]
                                self.update_devices(hostapi_name=self.hostapis[0])
                        # Resolve truncated names; only fill a side that is gone.
                        # Used to re-pick BOTH when only the output name missed,
                        # which swapped a saved Realtek mic for NVIDIA Broadcast.
                        data = self._pick_default_devices(data)
                    except Exception:
                        printt("load: 设备刷新失败，保留已保存的配置")
                        traceback.print_exc()
            except Exception:
                # 读配置失败只影响本次启动：返回默认值，但绝不写文件。
                # 以前这里 open(..., "w") 会截断 inuse，用户参数全丢。
                printt("load failed, using defaults (%s)", traceback.format_exc())
                from tools.device_pick import pick_default_input, pick_default_output

                data = {
                    "pth_path": "",
                    "index_path": "",
                    "sg_hostapi": self.hostapis[0] if self.hostapis else "",
                    "sg_wasapi_exclusive": False,
                    "sg_input_device": pick_default_input(self.input_devices or []),
                    "sg_output_device": pick_default_output(self.output_devices or []),
                    "sr_type": "sr_model",
                    "threhold": -48,
                    "pitch": 0,
                    "formant": 0.0,
                    "index_rate": 0,
                    "rms_mix_rate": 0.25,
                    "block_time": 0.22,
                    "crossfade_length": 0.05,
                    "extra_time": 2.5,
                    "n_cpu": 4,
                    "f0method": "fcpe",
                    "use_jit": False,
                    "use_pv": False,
                }
                data["sr_model"] = data["sr_type"] == "sr_model"
                data["sr_device"] = data["sr_type"] == "sr_device"
                data["pm"] = data["f0method"] == "pm"
                data["harvest"] = data["f0method"] == "harvest"
                data["crepe"] = data["f0method"] == "crepe"
                data["rmvpe"] = data["f0method"] == "rmvpe"
                data["fcpe"] = data["f0method"] == "fcpe"
            return data

        def launcher(self):
            data = self.load()
            self.config.use_jit = False  # data.get("use_jit", self.config.use_jit)
            sg.theme("LightBlue3")
            layout = [
                [
                    sg.Frame(
                        title=i18n("加载模型"),
                        layout=[
                            [
                                sg.Input(
                                    default_text=data.get("pth_path", ""),
                                    key="pth_path",
                                ),
                                sg.FileBrowse(
                                    i18n("选择.pth文件"),
                                    initial_folder=os.path.join(
                                        os.getcwd(), "assets/weights"
                                    ),
                                    file_types=((". pth"),),
                                ),
                            ],
                            [
                                sg.Input(
                                    default_text=data.get("index_path", ""),
                                    key="index_path",
                                ),
                                sg.FileBrowse(
                                    i18n("选择.index文件"),
                                    initial_folder=os.path.join(os.getcwd(), "logs"),
                                    file_types=((". index"),),
                                ),
                            ],
                        ],
                    )
                ],
                [
                    sg.Frame(
                        layout=[
                            [
                                sg.Text(i18n("设备类型")),
                                sg.Combo(
                                    self.hostapis,
                                    key="sg_hostapi",
                                    default_value=data.get("sg_hostapi", ""),
                                    enable_events=True,
                                    size=(20, 1),
                                ),
                                sg.Checkbox(
                                    i18n("独占 WASAPI 设备"),
                                    key="sg_wasapi_exclusive",
                                    default=data.get("sg_wasapi_exclusive", False),
                                    enable_events=True,
                                ),
                            ],
                            [
                                sg.Text(i18n("输入设备")),
                                sg.Combo(
                                    self.input_devices,
                                    key="sg_input_device",
                                    default_value=data.get("sg_input_device", ""),
                                    enable_events=True,
                                    size=(45, 1),
                                ),
                            ],
                            [
                                sg.Text(i18n("输出设备")),
                                sg.Combo(
                                    self.output_devices,
                                    key="sg_output_device",
                                    default_value=data.get("sg_output_device", ""),
                                    enable_events=True,
                                    size=(45, 1),
                                ),
                            ],
                            [
                                sg.Button(i18n("重载设备列表"), key="reload_devices"),
                                sg.Radio(
                                    i18n("使用模型采样率"),
                                    "sr_type",
                                    key="sr_model",
                                    default=data.get("sr_model", True),
                                    enable_events=True,
                                ),
                                sg.Radio(
                                    i18n("使用设备采样率"),
                                    "sr_type",
                                    key="sr_device",
                                    default=data.get("sr_device", False),
                                    enable_events=True,
                                ),
                                sg.Text(i18n("采样率:")),
                                sg.Text("", key="sr_stream"),
                            ],
                        ],
                        title=i18n("音频设备"),
                    )
                ],
                [
                    sg.Frame(
                        layout=[
                            [
                                sg.Text(i18n("响应阈值")),
                                sg.Slider(
                                    range=(-60, 0),
                                    key="threhold",
                                    resolution=1,
                                    orientation="h",
                                    default_value=data.get("threhold", -60),
                                    enable_events=True,
                                ),
                            ],
                            [
                                sg.Text(i18n("音调设置")),
                                sg.Slider(
                                    range=(-16, 16),
                                    key="pitch",
                                    resolution=1,
                                    orientation="h",
                                    default_value=data.get("pitch", 0),
                                    enable_events=True,
                                ),
                            ],
                            [
                                sg.Text(i18n("性别因子/声线粗细")),
                                sg.Slider(
                                    range=(-2, 2),
                                    key="formant",
                                    resolution=0.05,
                                    orientation="h",
                                    default_value=data.get("formant", 0.0),
                                    enable_events=True,
                                ),
                            ],
                            [
                                sg.Text(i18n("Index Rate")),
                                sg.Slider(
                                    range=(0.0, 1.0),
                                    key="index_rate",
                                    resolution=0.01,
                                    orientation="h",
                                    default_value=data.get("index_rate", 0),
                                    enable_events=True,
                                ),
                            ],
                            [
                                sg.Text(i18n("响度因子")),
                                sg.Slider(
                                    range=(0.0, 1.0),
                                    key="rms_mix_rate",
                                    resolution=0.01,
                                    orientation="h",
                                    default_value=data.get("rms_mix_rate", 0),
                                    enable_events=True,
                                ),
                            ],
                            [
                                sg.Text(i18n("音高算法")),
                                sg.Radio(
                                    "pm",
                                    "f0method",
                                    key="pm",
                                    default=data.get("pm", False),
                                    enable_events=True,
                                ),
                                sg.Radio(
                                    "harvest",
                                    "f0method",
                                    key="harvest",
                                    default=data.get("harvest", False),
                                    enable_events=True,
                                ),
                                sg.Radio(
                                    "crepe",
                                    "f0method",
                                    key="crepe",
                                    default=data.get("crepe", False),
                                    enable_events=True,
                                ),
                                sg.Radio(
                                    "rmvpe",
                                    "f0method",
                                    key="rmvpe",
                                    default=data.get("rmvpe", False),
                                    enable_events=True,
                                ),
                                sg.Radio(
                                    "fcpe",
                                    "f0method",
                                    key="fcpe",
                                    default=data.get("fcpe", True),
                                    enable_events=True,
                                ),
                            ],
                        ],
                        title=i18n("常规设置"),
                    ),
                    sg.Frame(
                        layout=[
                            [
                                sg.Text(i18n("采样长度")),
                                sg.Slider(
                                    range=(0.02, 1.5),
                                    key="block_time",
                                    resolution=0.01,
                                    orientation="h",
                                    default_value=data.get("block_time", 0.25),
                                    enable_events=True,
                                ),
                            ],
                            # [
                            #     sg.Text("设备延迟"),
                            #     sg.Slider(
                            #         range=(0, 1),
                            #         key="device_latency",
                            #         resolution=0.001,
                            #         orientation="h",
                            #         default_value=data.get("device_latency", 0.1),
                            #         enable_events=True,
                            #     ),
                            # ],
                            [
                                sg.Text(i18n("harvest进程数")),
                                sg.Slider(
                                    range=(1, n_cpu),
                                    key="n_cpu",
                                    resolution=1,
                                    orientation="h",
                                    default_value=data.get(
                                        "n_cpu", min(self.gui_config.n_cpu, n_cpu)
                                    ),
                                    enable_events=True,
                                ),
                            ],
                            [
                                sg.Text(i18n("淡入淡出长度")),
                                sg.Slider(
                                    range=(0.01, 0.15),
                                    key="crossfade_length",
                                    resolution=0.01,
                                    orientation="h",
                                    default_value=data.get("crossfade_length", 0.05),
                                    enable_events=True,
                                ),
                            ],
                            [
                                sg.Text(i18n("额外推理时长")),
                                sg.Slider(
                                    range=(0.05, 5.00),
                                    key="extra_time",
                                    resolution=0.01,
                                    orientation="h",
                                    default_value=data.get("extra_time", 2.5),
                                    enable_events=True,
                                ),
                            ],
                            [
                                sg.Checkbox(
                                    i18n("输入降噪"),
                                    key="I_noise_reduce",
                                    enable_events=True,
                                ),
                                sg.Checkbox(
                                    i18n("输出降噪"),
                                    key="O_noise_reduce",
                                    enable_events=True,
                                ),
                                sg.Checkbox(
                                    i18n("启用相位声码器"),
                                    key="use_pv",
                                    default=data.get("use_pv", False),
                                    enable_events=True,
                                ),
                                # sg.Checkbox(
                                #     "JIT加速",
                                #     default=self.config.use_jit,
                                #     key="use_jit",
                                #     enable_events=False,
                                # ),
                            ],
                            # [sg.Text("注：首次使用JIT加速时，会出现卡顿，\n      并伴随一些噪音，但这是正常现象！")],
                        ],
                        title=i18n("性能设置"),
                    ),
                ],
                [
                    sg.Button(i18n("开始音频转换"), key="start_vc"),
                    sg.Button(i18n("停止音频转换"), key="stop_vc"),
                    sg.Radio(
                        i18n("输入监听"),
                        "function",
                        key="im",
                        default=False,
                        enable_events=True,
                    ),
                    sg.Radio(
                        i18n("输出变声"),
                        "function",
                        key="vc",
                        default=True,
                        enable_events=True,
                    ),
                    sg.Text(i18n("算法延迟(ms):")),
                    sg.Text("0", key="delay_time"),
                    sg.Text(i18n("推理时间(ms):")),
                    sg.Text("0", key="infer_time"),
                ],
            ]
            self.window = sg.Window("RVC - GUI", layout=layout, finalize=True)
            self._try_auto_start_vc()
            self.event_handler()

        def _try_auto_start_vc(self):
            """Main app sets TM_AUTO_START_VC=1 when user clicks 开启变声."""
            flag = os.environ.get("TM_AUTO_START_VC", "").strip().lower()
            if flag not in ("1", "true", "yes"):
                return
            try:
                # One short read to materialize widget values
                _ev, values = self.window.read(timeout=150)
                if not values:
                    return
                if self.set_values(values) is not True:
                    return
                printt("auto-start VC (TM_AUTO_START_VC)")
                printt("cuda_is_available: %s", torch.cuda.is_available())
                self.start_vc()
                if self.audio_proc is not None:
                    self.delay_time = (
                        self.audio_proc.get_latency()
                        + float(values.get("block_time") or 0.25)
                        + float(values.get("crossfade_length") or 0.05)
                        + 0.01
                    )
                    self.window["sr_stream"].update(self.gui_config.samplerate)
                    self.window["delay_time"].update(
                        int(np.round(self.delay_time * 1000))
                    )
            except Exception as e:
                traceback.print_exc()
                try:
                    sg.popup_error(
                        i18n("自动开始音频转换失败")
                        + f"\n\n{type(e).__name__}: {e}\n\n"
                        + i18n("请检查输入/输出设备，或手动点「开始音频转换」。")
                    )
                except Exception:
                    pass

        def event_handler(self):
            global flag_vc
            while True:
                event, values = self.window.read()
                if event == sg.WINDOW_CLOSED:
                    self.stop_stream()
                    exit()
                if event == "reload_devices" or event == "sg_hostapi":
                    self.gui_config.sg_hostapi = values["sg_hostapi"]
                    self.update_devices(hostapi_name=values["sg_hostapi"])
                    if self.gui_config.sg_hostapi not in self.hostapis:
                        self.gui_config.sg_hostapi = self.hostapis[0]
                    self.window["sg_hostapi"].Update(values=self.hostapis)
                    self.window["sg_hostapi"].Update(value=self.gui_config.sg_hostapi)
                    if (
                        self.gui_config.sg_input_device not in self.input_devices
                        and len(self.input_devices) > 0
                    ):
                        self.gui_config.sg_input_device = self.input_devices[0]
                    self.window["sg_input_device"].Update(values=self.input_devices)
                    self.window["sg_input_device"].Update(
                        value=self.gui_config.sg_input_device
                    )
                    if self.gui_config.sg_output_device not in self.output_devices:
                        self.gui_config.sg_output_device = self.output_devices[0]
                    self.window["sg_output_device"].Update(values=self.output_devices)
                    self.window["sg_output_device"].Update(
                        value=self.gui_config.sg_output_device
                    )
                if event == "start_vc" and not flag_vc:
                    if self.set_values(values) == True:
                        printt("cuda_is_available: %s", torch.cuda.is_available())
                        try:
                            self.start_vc()
                        except Exception as e:
                            traceback.print_exc()
                            flag_vc = False
                            try:
                                self.stop_stream()
                            except Exception:
                                pass
                            sg.popup_error(
                                i18n("启动音频转换失败")
                                + f"\n\n{type(e).__name__}: {e}\n\n"
                                + i18n(
                                    "常见原因：模型路径无效、显存不足、声卡占用、index 损坏。"
                                    "无 index 文件时可把 Index Rate 设为 0。"
                                )
                            )
                            continue
                        settings = {
                            "pth_path": values["pth_path"],
                            "index_path": values["index_path"],
                            "sg_hostapi": values["sg_hostapi"],
                            "sg_wasapi_exclusive": values["sg_wasapi_exclusive"],
                            "sg_input_device": values["sg_input_device"],
                            "sg_output_device": values["sg_output_device"],
                            "sr_type": ["sr_model", "sr_device"][
                                [
                                    values["sr_model"],
                                    values["sr_device"],
                                ].index(True)
                            ],
                            "threhold": values["threhold"],
                            "pitch": values["pitch"],
                            "rms_mix_rate": values["rms_mix_rate"],
                            "index_rate": values["index_rate"],
                            # "device_latency": values["device_latency"],
                            "block_time": values["block_time"],
                            "crossfade_length": values["crossfade_length"],
                            "extra_time": values["extra_time"],
                            "n_cpu": values["n_cpu"],
                            # "use_jit": values["use_jit"],
                            "use_jit": False,
                            "use_pv": values["use_pv"],
                            "f0method": ["pm", "harvest", "crepe", "rmvpe", "fcpe"][
                                [
                                    values["pm"],
                                    values["harvest"],
                                    values["crepe"],
                                    values["rmvpe"],
                                    values["fcpe"],
                                ].index(True)
                            ],
                        }
                        # Keep formant if present in values
                        if "formant" in values:
                            settings["formant"] = values["formant"]
                        _cfg = "configs/inuse/config.json"
                        _tmp = _cfg + ".tmp"
                        with open(_tmp, "w", encoding="utf-8") as j:
                            json.dump(settings, j, ensure_ascii=False, indent=2)
                        os.replace(_tmp, _cfg)
                        if self.audio_proc is not None:
                            self.delay_time = (
                                self.audio_proc.get_latency()
                                + values["block_time"]
                                + values["crossfade_length"]
                                + 0.01
                            )
                        if values["I_noise_reduce"]:
                            self.delay_time += min(values["crossfade_length"], 0.04)
                        self.window["sr_stream"].update(self.gui_config.samplerate)
                        self.window["delay_time"].update(
                            int(np.round(self.delay_time * 1000))
                        )
                # Parameter hot update
                if event == "threhold":
                    self.gui_config.threhold = values["threhold"]
                elif event == "pitch":
                    self.gui_config.pitch = values["pitch"]
                    if hasattr(self, "rvc"):
                        self.rvc.change_key(values["pitch"])
                elif event == "formant":
                    self.gui_config.formant = values["formant"]
                    if hasattr(self, "rvc"):
                        self.rvc.change_formant(values["formant"])
                elif event == "index_rate":
                    self.gui_config.index_rate = values["index_rate"]
                    if hasattr(self, "rvc"):
                        self.rvc.change_index_rate(values["index_rate"])
                elif event == "rms_mix_rate":
                    self.gui_config.rms_mix_rate = values["rms_mix_rate"]
                elif event in ["pm", "harvest", "crepe", "rmvpe", "fcpe"]:
                    self.gui_config.f0method = event
                elif event == "I_noise_reduce":
                    self.gui_config.I_noise_reduce = values["I_noise_reduce"]
                    if self.audio_proc is not None:
                        self.delay_time += (
                            1 if values["I_noise_reduce"] else -1
                        ) * min(values["crossfade_length"], 0.04)
                        self.window["delay_time"].update(
                            int(np.round(self.delay_time * 1000))
                        )
                elif event == "O_noise_reduce":
                    self.gui_config.O_noise_reduce = values["O_noise_reduce"]
                elif event == "use_pv":
                    self.gui_config.use_pv = values["use_pv"]
                elif event in ["vc", "im"]:
                    self.function = event
                elif event == "stop_vc" or event != "start_vc":
                    # Other parameters do not support hot update
                    self.stop_stream()

        def _notify(self, msg: str, code: str = "", **params) -> None:
            """把一条「检查没过」的原因同时送去日志和状态栏。

            `code` 是给状态栏用的：壳层按当前界面语言翻译它。日志和 `error`
            字段仍旧写 `msg` 那份原文（带路径、带异常文本），排障要看的是它。
            """
            printt("%s", msg)
            # Remembered so _worker_start can report the actual reason. It used
            # to write the specific message here and overwrite it one line
            # later with a generic「模型路径 / 设备」, which told the user
            # nothing about which of the four checks had failed.
            self._last_invalid_reason = str(msg)
            if self.worker_mode:
                try:
                    if code:
                        self._worker_write_status(
                            error=str(msg), **_msg(code, **params)
                        )
                    else:
                        self._worker_write_status(error=str(msg), message=str(msg))
                except Exception:
                    pass
                return
            try:
                sg.popup(msg)
            except Exception:
                pass

        def set_values(self, values):
            # 没引擎资源 → 只要开了 DSP 就走纯 fx，音色路径留着，下完资源再叠。
            # 有资源 + 选了音色 + 开了 DSP → RVC 和 DSP 同时走。
            pth = values["pth_path"].strip()
            dsp_on = bool(values.get("dsp_enabled"))
            core_ok = _engine_core_ready()
            dsp_only = dsp_on and (not pth or not core_ok)
            if not pth and not dsp_on:
                self._notify(i18n("请选择pth文件"), VC_NEED_MODEL)
                return False
            if pth and not core_ok and not dsp_on:
                self._notify(
                    i18n(
                        "实时变声需要引擎资源。请到广场下载模型，或先选用一个 DSP 预设。"
                    ),
                    VC_NEED_MODEL,
                )
                return False
            index_path = (values.get("index_path") or "").strip()
            # Index is optional. Missing file used to hard-crash faiss on start.
            if index_path and not os.path.isfile(index_path):
                printt("index missing, disable index: %s", index_path)
                index_path = ""
                values["index_path"] = ""
                if self.window is not None:
                    try:
                        self.window["index_path"].update("")
                    except Exception:
                        pass
            if not index_path:
                # Force rate 0 so rtrvc never calls faiss.read_index
                values["index_rate"] = 0
            # Non-ASCII paths.
            #
            # The model checkpoint is fine: get_synthesizer goes through
            # torch.load, which opens the file with Python and handles a
            # Unicode path on Windows without trouble. This check only ever
            # existed because faiss does not — and rejecting the whole start
            # meant every voice whose folder carries a Chinese name (which is
            # most of the store catalog, and most of what people import) came
            # back as「设置无效」 and could not be used at all.
            #
            # So: keep the check for the index only, and treat a non-ASCII
            # index the same way a missing one is already treated — drop it and
            # carry on, rather than blocking the voice.
            pattern = re.compile("[^\x00-\x7F]+")
            if index_path and pattern.findall(index_path):
                printt("index path is not ASCII, disable index: %s", index_path)
                index_path = ""
                values["index_path"] = ""
                values["index_rate"] = 0
                if self.window is not None:
                    try:
                        self.window["index_path"].update("")
                    except Exception:
                        pass
            if pth and not os.path.isfile(pth) and not dsp_only:
                self._notify(i18n("pth文件不存在") + f"\n{pth}", VC_PTH_MISSING, path=pth)
                return False
            # Devices must exist for current hostapi list
            try:
                self.set_devices(values["sg_input_device"], values["sg_output_device"])
            except Exception as e:
                self._notify(f"设备无效: {e}", DEV_INVALID, detail=str(e))
                return False
            self.config.use_jit = False  # values["use_jit"]
            # self.device_latency = values["device_latency"]
            self.gui_config.sg_hostapi = values["sg_hostapi"]
            self.gui_config.sg_wasapi_exclusive = values["sg_wasapi_exclusive"]
            self.gui_config.sg_input_device = values["sg_input_device"]
            self.gui_config.sg_output_device = values["sg_output_device"]
            self.gui_config.monitor_device = str(
                values.get("monitor_device") or values.get("sg_monitor_device") or ""
            )
            self.gui_config.monitor_enabled = bool(values.get("monitor_enabled", False))
            self.gui_config.pth_path = pth
            self.gui_config.index_path = index_path
            self.gui_config.sr_type = ["sr_model", "sr_device"][
                [
                    values["sr_model"],
                    values["sr_device"],
                ].index(True)
            ]
            self.gui_config.threhold = values["threhold"]
            self.gui_config.in_gain_db = float(values.get("in_gain_db") or 0.0)
            self.gui_config.pitch = values["pitch"]
            self.gui_config.formant = values["formant"]
            self.gui_config.block_time = values["block_time"]
            self.gui_config.crossfade_time = values["crossfade_length"]
            self.gui_config.extra_time = values["extra_time"]
            self.gui_config.I_noise_reduce = values["I_noise_reduce"]
            self.gui_config.O_noise_reduce = values["O_noise_reduce"]
            self.gui_config.use_pv = values["use_pv"]
            self.gui_config.rms_mix_rate = values["rms_mix_rate"]
            self.gui_config.index_rate = (
                0 if not index_path else values["index_rate"]
            )
            self.gui_config.n_cpu = values["n_cpu"]
            self.gui_config.f0method = ["pm", "harvest", "crepe", "rmvpe", "fcpe"][
                [
                    values["pm"],
                    values["harvest"],
                    values["crepe"],
                    values["rmvpe"],
                    values["fcpe"],
                ].index(True)
            ]
            self._load_fx_from_values(values)
            return True

        def _load_fx_from_values(self, values: dict) -> None:
            """Copy fx_* keys from values/config into gui_config + rebuild chain."""
            gc = self.gui_config
            gc.fx_enabled = bool(values.get("fx_enabled", False))
            gc.fx_gate_enabled = bool(values.get("fx_gate_enabled", True))
            gc.fx_gate_threshold_db = float(values.get("fx_gate_threshold_db", -50))
            gc.fx_gate_release_ms = float(values.get("fx_gate_release_ms", 50))
            gc.fx_gate_hold_ms = float(values.get("fx_gate_hold_ms", 20))
            gc.fx_gate_range_db = float(values.get("fx_gate_range_db", 20))
            gc.fx_comp_enabled = bool(values.get("fx_comp_enabled", True))
            gc.fx_comp_threshold_db = float(values.get("fx_comp_threshold_db", -20))
            gc.fx_comp_ratio = float(values.get("fx_comp_ratio", 4))
            gc.fx_comp_attack_ms = float(values.get("fx_comp_attack_ms", 5))
            gc.fx_comp_release_ms = float(values.get("fx_comp_release_ms", 100))
            gc.fx_comp_makeup_db = float(values.get("fx_comp_makeup_db", 0))
            gc.fx_eq_enabled = bool(values.get("fx_eq_enabled", True))
            gains = values.get("fx_eq_gains") or [0, 0, 0, 0, 0]
            if isinstance(gains, (list, tuple)):
                gc.fx_eq_gains = [float(x) for x in list(gains)[:5]]
            while len(gc.fx_eq_gains) < 5:
                gc.fx_eq_gains.append(0.0)
            gc.fx_eq_preset = str(values.get("fx_eq_preset") or "flat")
            gc.fx_out_gain_db = float(values.get("fx_out_gain_db") or 0)
            gc.dsp_enabled = bool(values.get("dsp_enabled", False))
            gc.dsp_preset = str(values.get("dsp_preset") or "")
            params = values.get("dsp_params")
            gc.dsp_params = params if isinstance(params, dict) else {}
            self._rebuild_fx_chain()
            self._rebuild_voice_chain()

        def _rebuild_voice_chain(self) -> None:
            """建 / 更新 DSP 变声链。参数热改，不重建实例——重建会清掉延迟线。"""
            gc = self.gui_config
            if not bool(getattr(gc, "dsp_enabled", False)):
                self._voice_chain = None
                return
            try:
                from tools.dsp_voice import VoiceChain

                params = gc.dsp_params if isinstance(gc.dsp_params, dict) else {}
                if self._voice_chain is None:
                    self._voice_chain = VoiceChain(params)
                else:
                    self._voice_chain.apply(params)
            except Exception:
                traceback.print_exc()
                self._voice_chain = None

        def _apply_voice_chain(self, wav: torch.Tensor) -> torch.Tensor:
            """DSP 变声跑在最后一块上（前面是 SOLA 要的重叠历史）。"""
            if self._voice_chain is None:
                self._rebuild_voice_chain()
            if self._voice_chain is None:
                return wav
            sr = int(getattr(self.gui_config, "samplerate", 48000) or 48000)
            n = int(getattr(self, "block_frame", 0) or 0)
            if n <= 0 or wav.numel() < n:
                x = wav.cpu().numpy()
                y = self._voice_chain.process(x, sr)
                return torch.from_numpy(np.asarray(y, dtype=np.float32)).to(
                    wav.device
                ).type_as(wav)
            head = wav[:-n]
            tail = wav[-n:].cpu().numpy()
            y = self._voice_chain.process(tail, sr)
            tail_t = torch.from_numpy(np.asarray(y, dtype=np.float32)).to(
                wav.device
            ).type_as(wav)
            return torch.cat([head, tail_t], dim=0)

        def _fx_config_dict(self) -> dict:
            gc = self.gui_config
            return {
                "fx_enabled": bool(gc.fx_enabled),
                "fx_gate_enabled": bool(gc.fx_gate_enabled),
                "fx_gate_threshold_db": float(gc.fx_gate_threshold_db),
                "fx_gate_release_ms": float(gc.fx_gate_release_ms),
                "fx_gate_hold_ms": float(gc.fx_gate_hold_ms),
                "fx_gate_range_db": float(gc.fx_gate_range_db),
                "fx_comp_enabled": bool(gc.fx_comp_enabled),
                "fx_comp_threshold_db": float(gc.fx_comp_threshold_db),
                "fx_comp_ratio": float(gc.fx_comp_ratio),
                "fx_comp_attack_ms": float(gc.fx_comp_attack_ms),
                "fx_comp_release_ms": float(gc.fx_comp_release_ms),
                "fx_comp_makeup_db": float(gc.fx_comp_makeup_db),
                "fx_eq_enabled": bool(gc.fx_eq_enabled),
                "fx_eq_gains": list(gc.fx_eq_gains),
                "fx_eq_preset": str(gc.fx_eq_preset or "flat"),
                "fx_out_gain_db": float(gc.fx_out_gain_db or 0),
            }

        def _rebuild_fx_chain(self) -> None:
            try:
                from tools.dsp_fx import RealtimeFxChain

                if self._fx_chain is None:
                    self._fx_chain = RealtimeFxChain(self._fx_config_dict())
                else:
                    self._fx_chain.apply_config(self._fx_config_dict())
            except Exception:
                traceback.print_exc()
                self._fx_chain = None

        def _apply_fx_chain(self, infer_wav: torch.Tensor) -> torch.Tensor:
            """Run numpy DSP on last block_frame samples of infer_wav (device tensor)."""
            if self._fx_chain is None:
                self._rebuild_fx_chain()
            if self._fx_chain is None or not self._fx_chain.enabled:
                return infer_wav
            sr = int(getattr(self.gui_config, "samplerate", 40000) or 40000)
            n = int(getattr(self, "block_frame", 0) or 0)
            if n <= 0 or infer_wav.numel() < n:
                # process whole tensor — .cpu() already detaches + copies
                x = infer_wav.cpu().numpy()
                y = self._fx_chain.process(x, sr)
                return torch.from_numpy(np.asarray(y, dtype=np.float32)).to(
                    infer_wav.device
                ).type_as(infer_wav)
            # only shape the newest block (rest is overlap history for SOLA)
            head = infer_wav[:-n]
            tail = infer_wav[-n:]
            x = tail.cpu().numpy()
            y = self._fx_chain.process(x, sr)
            tail_t = torch.from_numpy(np.asarray(y, dtype=np.float32)).to(
                infer_wav.device
            ).type_as(infer_wav)
            return torch.cat([head, tail_t], dim=0)

        def start_vc(self):
            # DML: ensure previous heavy objects are gone before allocating new ones
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                else:
                    import gc

                    gc.collect()
            except Exception:
                pass
            self._report_load(VC_LOADING_MODEL, 18)
            # 纯 DSP：没选音色，或开了 DSP 但 engine-core 还没齐。
            # 后一种不把音色忘掉，只是这次不加载 RVC。
            pth = str(self.gui_config.pth_path or "").strip()
            dsp_on = bool(getattr(self.gui_config, "dsp_enabled", False))
            self.dsp_only = (not pth) or (dsp_on and not _engine_core_ready())
            if self.dsp_only:
                self.rvc = None
                self.function = "fx"
                self.gui_config.samplerate = self.get_device_samplerate()
            else:
                if str(getattr(self.gui_config, "f0method", "") or "") == "harvest":
                    try:
                        ensure_harvest_workers(self.gui_config.n_cpu)
                    except Exception:
                        pass
                self.rvc = rvc_for_realtime.RVC(
                    self.gui_config.pitch,
                    self.gui_config.formant,
                    self.gui_config.pth_path,
                    self.gui_config.index_path,
                    self.gui_config.index_rate,
                    self.gui_config.n_cpu,
                    inp_q,
                    opt_q,
                    self.config,
                    self.rvc if getattr(self, "rvc", None) is not None else None,
                    on_progress=self._on_rvc_progress,
                )
                if self.function == "fx":
                    self.function = "vc"
                self.gui_config.samplerate = (
                    self.rvc.tgt_sr
                    if self.gui_config.sr_type == "sr_model"
                    else self.get_device_samplerate()
                )
            self.gui_config.channels = self.get_device_channels()
            try:
                self._rebuild_fx_chain()
                if self._fx_chain is not None:
                    self._fx_chain.reset()
                self._rebuild_voice_chain()
                if self._voice_chain is not None:
                    self._voice_chain.reset()
            except Exception:
                traceback.print_exc()
            self.zc = self.gui_config.samplerate // 100
            self.block_frame = (
                int(
                    np.round(
                        self.gui_config.block_time
                        * self.gui_config.samplerate
                        / self.zc
                    )
                )
                * self.zc
            )
            self.block_frame_16k = 160 * self.block_frame // self.zc
            self.crossfade_frame = (
                int(
                    np.round(
                        self.gui_config.crossfade_time
                        * self.gui_config.samplerate
                        / self.zc
                    )
                )
                * self.zc
            )
            self.sola_buffer_frame = min(self.crossfade_frame, 4 * self.zc)
            self.sola_search_frame = self.zc
            self.extra_frame = (
                int(
                    np.round(
                        self.gui_config.extra_time
                        * self.gui_config.samplerate
                        / self.zc
                    )
                )
                * self.zc
            )
            self.input_wav: torch.Tensor = torch.zeros(
                self.extra_frame
                + self.crossfade_frame
                + self.sola_search_frame
                + self.block_frame,
                device=self.config.device,
                dtype=torch.float32,
            )
            self.input_wav_denoise: torch.Tensor = self.input_wav.clone()
            self.input_wav_res: torch.Tensor = torch.zeros(
                160 * self.input_wav.shape[0] // self.zc,
                device=self.config.device,
                dtype=torch.float32,
            )
            self.rms_buffer: np.ndarray = np.zeros(4 * self.zc, dtype="float32")
            self.sola_buffer: torch.Tensor = torch.zeros(
                self.sola_buffer_frame, device=self.config.device, dtype=torch.float32
            )
            self.nr_buffer: torch.Tensor = self.sola_buffer.clone()
            self.output_buffer: torch.Tensor = self.input_wav.clone()
            self.skip_head = self.extra_frame // self.zc
            self.return_length = (
                self.block_frame + self.sola_buffer_frame + self.sola_search_frame
            ) // self.zc
            self.fade_in_window: torch.Tensor = (
                torch.sin(
                    0.5
                    * np.pi
                    * torch.linspace(
                        0.0,
                        1.0,
                        steps=self.sola_buffer_frame,
                        device=self.config.device,
                        dtype=torch.float32,
                    )
                )
                ** 2
            )
            self.fade_out_window: torch.Tensor = 1 - self.fade_in_window
            self.resampler = tat.Resample(
                orig_freq=self.gui_config.samplerate,
                new_freq=16000,
                dtype=torch.float32,
            ).to(self.config.device)
            # DSP 模式没有模型，也就没有 tgt_sr，输入输出同一个采样率。
            if self.rvc is not None and self.rvc.tgt_sr != self.gui_config.samplerate:
                self.resampler2 = tat.Resample(
                    orig_freq=self.rvc.tgt_sr,
                    new_freq=self.gui_config.samplerate,
                    dtype=torch.float32,
                ).to(self.config.device)
            else:
                self.resampler2 = None
            self.tg = TorchGate(
                sr=self.gui_config.samplerate, n_fft=4 * self.zc, prop_decrease=0.9
            ).to(self.config.device)
            # Bill one-time costs (lazy f0 model load, cudnn autotune, CUDA context)
            # here instead of inside the first audible blocks
            self._report_load(VC_WARMUP, 78)
            try:
                self._warmup_engine()
            except Exception:
                traceback.print_exc()
            self._report_load(VC_OPENING_STREAM, 92)
            self.start_stream()

        def _on_rvc_progress(self, code, pct):
            self._report_load(code, pct)

        def _report_load(self, code, progress, **params):
            """启动/预热分阶段写状态。progress 0–100，界面底栏画进度条。"""
            try:
                self._worker_write_status(
                    state="starting",
                    error="",
                    pid=os.getpid(),
                    progress=int(progress),
                    **self._worker_device_payload(),
                    **_msg(code, **params),
                )
            except Exception:
                pass

        def _swap_in_flight(self) -> bool:
            if getattr(self, "_swap_ready", None) is not None:
                return True
            if getattr(self, "_pending_model", None) is not None:
                return True
            return bool(getattr(self, "_swap_busy", False))

        def _warmup_engine(self):
            # DSP 模式没有模型可预热，直接跳过——这也正是它启动即时的原因。
            if self.rvc is None:
                return
            dummy = torch.zeros_like(self.input_wav_res)
            # a short voiced tail so the f0 extractor runs its full path
            n = min(int(dummy.shape[0]), 4000)
            t = torch.arange(n, device=dummy.device, dtype=torch.float32)
            dummy[-n:] = 0.1 * torch.sin(2 * np.pi * 150.0 * t / 16000.0)
            for _ in range(2):
                infer_wav = self.rvc.infer(
                    dummy,
                    self.block_frame_16k,
                    self.skip_head,
                    self.return_length,
                    self.gui_config.f0method,
                )
                if self.resampler2 is not None:
                    infer_wav = self.resampler2(infer_wav)
            # drop warmup pitch history so the real stream starts clean
            self.rvc.cache_pitch.zero_()
            self.rvc.cache_pitchf.zero_()

        def _perf_meta(self) -> dict:
            meta = {"created": time.strftime("%Y-%m-%d %H:%M:%S")}
            try:
                meta["mode"] = (
                    "worker" if os.environ.get("TM_REALTIME_WORKER") == "1" else "gui"
                )
                meta["torch"] = str(getattr(torch, "__version__", ""))
                meta["device"] = str(self.config.device)
                meta["half"] = bool(self.config.is_half)
                if torch.cuda.is_available():
                    meta["gpu"] = torch.cuda.get_device_name(0)
                meta["samplerate"] = int(self.gui_config.samplerate)
                meta["block_time"] = float(self.gui_config.block_time)
                meta["f0method"] = str(self.gui_config.f0method)
                meta["index_on"] = bool(getattr(self.gui_config, "index_rate", 0))
                meta["model"] = os.path.basename(
                    str(getattr(self.gui_config, "pth_path", ""))
                )
            except Exception:
                pass
            return meta

        def _save_perf_report(self):
            perf = getattr(self, "_perf", None)
            self._perf = None
            if perf is None:
                return
            from tools.perf_report import MIN_SESSION_SAMPLES, should_save

            out_dir = os.path.join("User_Data", "perf_reports")
            if os.environ.get("TM_PERF_REPORT") != "1":
                # occasional sampling: skip trivial sessions and rate-limit
                if perf.summary().get("n", 0) < MIN_SESSION_SAMPLES:
                    return
                if not should_save(out_dir):
                    return
            path = perf.save(out_dir)
            if path:
                printt("perf report saved: %s", path)

        def start_stream(self):
            global flag_vc
            if not flag_vc:
                flag_vc = True
                # Occasional local perf sampling (User_Data/perf_reports): saved
                # at most once per interval, never uploaded — users share the
                # file themselves. TM_PERF_REPORT=0 disables, =1 forces saving.
                try:
                    if os.environ.get("TM_PERF_REPORT") != "0":
                        from tools.perf_report import PerfCollector

                        self._perf = PerfCollector(self._perf_meta())
                    else:
                        self._perf = None
                except Exception:
                    self._perf = None
                if (
                    "WASAPI" in self.gui_config.sg_hostapi
                    and self.gui_config.sg_wasapi_exclusive
                ):
                    wasapi_exclusive = True
                else:
                    wasapi_exclusive = False
                try:
                    self.audio_proc = AudioIoProcess(
                        input_device=sd.default.device[0],
                        output_device=sd.default.device[1],
                        input_audio_block_size=self.block_frame,
                        sample_rate=self.gui_config.samplerate,
                        channel_num=self.gui_config.channels,
                        is_input_wasapi_exclusive=wasapi_exclusive,
                        is_output_wasapi_exclusive=wasapi_exclusive,
                        is_device_combined=True
                        # TODO: Add control UI to allow devices with different type API & different WASAPI settings
                    )
                    self.in_mem = SharedMemory(name=self.audio_proc.get_in_mem_name())
                    self.out_mem = SharedMemory(name=self.audio_proc.get_out_mem_name())
                    self.in_buf = np.ndarray(
                        self.audio_proc.get_np_shape(),
                        dtype=self.audio_proc.get_np_dtype(),
                        buffer=self.in_mem.buf,
                        order="C",
                    )
                    self.out_buf = np.ndarray(
                        self.audio_proc.get_np_shape(),
                        dtype=self.audio_proc.get_np_dtype(),
                        buffer=self.out_mem.buf,
                        order="C",
                    )
                    (
                        self.in_ptr,
                        self.out_ptr,
                        self.play_ptr,
                        self.in_evt,
                        self.stop_evt,
                    ) = self.audio_proc.get_ptrs_and_events()

                    self.audio_proc.start()
                    # Optional self-monitor (headphones) while main out stays on CABLE
                    try:
                        self._open_monitor_stream()
                    except Exception:
                        traceback.print_exc()

                    def audio_loop():
                        while flag_vc:
                            try:
                                self.audio_infer(self.block_frame << 1)
                            except Exception:
                                traceback.print_exc()
                                break

                    threading.Thread(target=audio_loop, daemon=True).start()
                except Exception:
                    flag_vc = False
                    self.audio_proc = None
                    try:
                        self._close_monitor_stream()
                    except Exception:
                        pass
                    raise

        @staticmethod
        def _is_virtual_playback_name(name: str) -> bool:
            """Virtual / non-listening endpoints — not real headphones/speakers."""
            low = (name or "").lower()
            if not low:
                return True
            keys = (
                "cable",
                "voicemeeter",
                "mapper",
                "steam streaming",
                "steam streaming speakers",
                "virtual cable",
                "vb-audio",
                "vb audio",
                "nvidia high definition",
                "nvidia broadcast",
                "网易虚拟",
                "网易云",
                "fxsound",
                "discord",
                "obs virtual",
                "stereo mix",
                "what u hear",
                "wave speaker",  # SteelSeries Sonar virtual ends
                "sonar_vad",
                "steelseries_sonar",
                "vac ",
                "line 1",
                "primary sound driver",
                "主声音驱动",
            )
            return any(k in low for k in keys)

        def _close_monitor_stream(self) -> None:
            stream = getattr(self, "monitor_stream", None)
            self.monitor_stream = None
            self._monitor_q = None
            if stream is None:
                return
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
            printt("monitor stream closed")

        def _resolve_output_device_index(self, name: str):
            """Find output device index; prefer current hostapi list."""
            if not name:
                return None
            # Prefer same host API as main VC (stable names + indices)
            try:
                if self.output_devices and self.output_devices_indices:
                    resolved = self._resolve_device_name(
                        name, list(self.output_devices)
                    )
                    if resolved is not None:
                        return self.output_devices_indices[
                            self.output_devices.index(resolved)
                        ]
            except Exception:
                pass
            try:
                devices = sd.query_devices()
            except Exception:
                return None
            # exact
            for i, d in enumerate(devices):
                if d.get("max_output_channels", 0) <= 0:
                    continue
                dn = d.get("name") or ""
                if dn == name:
                    return d.get("index", i)
            # prefix / truncated
            for i, d in enumerate(devices):
                if d.get("max_output_channels", 0) <= 0:
                    continue
                dn = d.get("name") or ""
                if dn.startswith(name) or name.startswith(dn[: max(8, len(name) - 2)]):
                    return d.get("index", i)
            return None

        def _pick_better_monitor_device(self, preferred: str = "") -> str:
            """Choose a real headphone/speaker from current hostapi output list."""
            outs = list(self.output_devices or [])
            if not outs:
                return preferred or ""
            main_out = str(getattr(self.gui_config, "sg_output_device", "") or "")

            def _usable(n: str) -> bool:
                if not n or n == main_out:
                    return False
                if self._is_virtual_playback_name(n):
                    return False
                # Same as main CABLE with truncated names
                if main_out and (
                    n.startswith(main_out[:20]) or main_out.startswith(n[:20])
                ):
                    # Allow if one is clearly headphones and other is cable
                    if "cable" in main_out.lower() and "cable" not in n.lower():
                        return True
                    if "cable" in n.lower():
                        return False
                return True

            # 1) keep preferred if it's a real device
            if preferred and preferred in outs and _usable(preferred):
                return preferred
            if preferred:
                resolved = self._resolve_device_name(preferred, outs)
                if resolved and _usable(resolved):
                    return resolved

            # 2) system default output (if listed under this hostapi)
            try:
                def_idx = sd.default.device[1]
                if def_idx is not None and int(def_idx) >= 0:
                    def_name = sd.query_devices(int(def_idx)).get("name") or ""
                    hit = self._resolve_device_name(def_name, outs)
                    if hit and _usable(hit):
                        return hit
            except Exception:
                pass

            # 3) prefer headphones / 耳机
            for n in outs:
                low = n.lower()
                if _usable(n) and (
                    "耳机" in n
                    or "headphone" in low
                    or "headset" in low
                    or "earphone" in low
                ):
                    return n

            # 4) first non-virtual
            for n in outs:
                if _usable(n):
                    return n
            return preferred if preferred in outs else (outs[0] if outs else "")

        def _open_monitor_stream(self) -> None:
            """Play converted audio to a second device (headphones) for self-listen.

            Uses callback + queue so the infer thread never blocks on stream.write,
            and opens at the *device* default sample rate (resample if needed).
            """
            self._close_monitor_stream()
            self._monitor_status = ""
            self._monitor_err_count = 0
            if not bool(getattr(self.gui_config, "monitor_enabled", False)):
                return
            name = str(getattr(self.gui_config, "monitor_device", "") or "").strip()
            # Auto-fix virtual / empty monitor targets (common bug: Steam Speakers)
            if (not name) or self._is_virtual_playback_name(name):
                better = self._pick_better_monitor_device("")
                if better and better != name:
                    printt(
                        "monitor device auto-fixed: %r -> %r",
                        name or "(empty)",
                        better,
                    )
                    name = better
                    self.gui_config.monitor_device = better
            if not name:
                msg = "monitor enabled but no usable device"
                printt(msg)
                self._monitor_status = msg
                return
            main_out = str(getattr(self.gui_config, "sg_output_device", "") or "")
            # Exact same endpoint only (avoid false skip on both starting with 扬声器)
            if name == main_out:
                msg = "monitor same as main output, skip: %s" % name
                printt(msg)
                self._monitor_status = msg
                return
            if main_out and "cable" in main_out.lower() and "cable" in name.lower():
                msg = "monitor is also CABLE, skip: %s" % name
                printt(msg)
                self._monitor_status = msg
                return

            idx = self._resolve_output_device_index(name)
            if idx is None:
                msg = "monitor device not found: %s" % name
                printt(msg)
                self._monitor_status = msg
                return
            try:
                from collections import deque

                info = sd.query_devices(idx)
                ch = min(
                    int(getattr(self.gui_config, "channels", 2) or 2),
                    int(info.get("max_output_channels") or 2),
                    2,
                )
                ch = max(1, ch)
                # Prefer device native rate (stable). Fall back to VC rate.
                dev_sr = int(float(info.get("default_samplerate") or 0) or 0)
                vc_sr = int(getattr(self.gui_config, "samplerate", 0) or 0) or 48000
                sr = dev_sr if dev_sr > 0 else vc_sr
                # ~0.5s ring so short stalls don't underrun
                block = max(256, int(sr * 0.02))
                q = deque(maxlen=64)
                self._monitor_q = q
                self.monitor_channels = ch
                self.monitor_sr = sr
                self._monitor_src_sr = vc_sr

                def _cb(outdata, frames, time_info, status):
                    if status:
                        pass
                    need = frames
                    pos = 0
                    outdata.fill(0)
                    while need > 0 and q:
                        chunk = q[0]
                        take = min(need, chunk.shape[0])
                        outdata[pos : pos + take] = chunk[:take]
                        if take < chunk.shape[0]:
                            q[0] = chunk[take:]
                        else:
                            q.popleft()
                        pos += take
                        need -= take

                stream = sd.OutputStream(
                    device=idx,
                    samplerate=sr,
                    channels=ch,
                    dtype=np.float32,
                    latency="high",
                    blocksize=block,
                    callback=_cb,
                )
                stream.start()
                self.monitor_stream = stream
                self._monitor_status = "ok:%s" % name
                printt(
                    "monitor stream open: %s idx=%s ch=%s sr=%s (vc_sr=%s)",
                    name,
                    idx,
                    ch,
                    sr,
                    vc_sr,
                )
            except Exception as e:
                msg = "monitor open failed: %s" % e
                printt(msg)
                self._monitor_status = msg
                self.monitor_stream = None
                self._monitor_q = None

        def _write_monitor(self, outdata: np.ndarray) -> None:
            q = getattr(self, "_monitor_q", None)
            if q is None or outdata is None:
                return
            if getattr(self, "monitor_stream", None) is None:
                return
            try:
                data = np.ascontiguousarray(outdata, dtype=np.float32)
                if data.ndim == 1:
                    data = data.reshape(-1, 1)
                want = int(
                    getattr(self, "monitor_channels", data.shape[1]) or data.shape[1]
                )
                if data.shape[1] != want:
                    if want == 1:
                        data = data.mean(axis=1, keepdims=True).astype(np.float32)
                    elif data.shape[1] == 1:
                        data = np.repeat(data, want, axis=1)
                    else:
                        data = data[:, :want].copy()
                # Resample VC rate → monitor device rate when they differ
                src_sr = int(getattr(self, "_monitor_src_sr", 0) or 0)
                dst_sr = int(getattr(self, "monitor_sr", 0) or 0)
                if src_sr > 0 and dst_sr > 0 and src_sr != dst_sr and data.shape[0] > 1:
                    n_out = max(1, int(round(data.shape[0] * float(dst_sr) / src_sr)))
                    x_old = np.linspace(0.0, 1.0, data.shape[0], endpoint=False)
                    x_new = np.linspace(0.0, 1.0, n_out, endpoint=False)
                    cols = [
                        np.interp(x_new, x_old, data[:, c]).astype(np.float32)
                        for c in range(data.shape[1])
                    ]
                    data = np.stack(cols, axis=1)
                # Soft clip to avoid DAC harshness (cubic + ceiling)
                data = soft_clip_np(data)
                q.append(data)
            except Exception as e:
                self._monitor_err_count = int(
                    getattr(self, "_monitor_err_count", 0) or 0
                ) + 1
                if self._monitor_err_count <= 3 or self._monitor_err_count % 50 == 0:
                    printt("monitor write err (%s): %s", self._monitor_err_count, e)

        def stop_stream(self):
            """Always tear down audio I/O — even if flag_vc was cleared elsewhere.

            Previous bug: update_devices/list_devices set flag_vc=False first, then
            stop_stream became a no-op and AudioIoProcess kept capturing/playing
            (looping audio / stuck mic). Multiple workers made it worse.
            """
            global flag_vc
            flag_vc = False
            try:
                self._save_perf_report()
            except Exception:
                traceback.print_exc()
            try:
                self._close_monitor_stream()
            except Exception:
                pass
            proc = getattr(self, "audio_proc", None)
            if proc is not None:
                printt("stop_stream: shutting down AudioIoProcess")
                try:
                    if getattr(self, "stop_evt", None) is not None:
                        try:
                            self.stop_evt.set()
                        except Exception:
                            pass
                    try:
                        if getattr(self, "in_evt", None) is not None:
                            self.in_evt.set()
                    except Exception:
                        pass
                    try:
                        if getattr(self, "in_mem", None) is not None:
                            self.in_mem.close()
                    except Exception:
                        pass
                    try:
                        if getattr(self, "out_mem", None) is not None:
                            self.out_mem.close()
                    except Exception:
                        pass
                    try:
                        if proc.is_alive():
                            proc.join(timeout=3.0)
                    except Exception:
                        pass
                    try:
                        if proc.is_alive():
                            proc.terminate()
                            proc.join(timeout=2.0)
                    except Exception:
                        pass
                    try:
                        if proc.is_alive():
                            proc.kill()
                    except Exception:
                        pass
                finally:
                    self.audio_proc = None
                    self.in_mem = None
                    self.out_mem = None
                    self.in_buf = None
                    self.out_buf = None
                    self.stop_evt = None
                    self.in_evt = None
            # Free VRAM so second start after denoise/settings is less likely to OOM
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            # DML path has no empty_cache; rely on del + gc
            # (ref: infer/modules/vc/pipeline.py DML memory release pattern)
            try:
                if not torch.cuda.is_available():
                    import gc

                    # Drop heavy model refs so DML allocator can reclaim memory
                    for attr in (
                        "rvc",
                        "resampler",
                        "resampler2",
                        "tg",
                        "_fx_chain",
                    ):
                        if hasattr(self, attr):
                            setattr(self, attr, None)
                    gc.collect()
            except Exception:
                pass

        def audio_infer(
            self, buf_size:int # 2 * self.block_frame
        ):
            """
            音频处理
            """
            global flag_vc

            # Timeout so stop_stream can unblock this thread
            got = self.in_evt.wait(timeout=0.5)
            if not flag_vc:
                return
            if not got:
                return
            rptr = self.in_ptr.value
            self.in_evt.clear()

            # 换音色：后台线程把权重读好，这里只换指针。DML 仍在本线程现读。
            if getattr(self, "_swap_ready", None) is not None:
                self._install_ready_model()
            elif self._pending_model is not None and not getattr(self, "_swap_busy", False):
                self._apply_pending_model()

            start_time = time.perf_counter()

            rend = rptr + self.block_frame
            indata = np.copy(self.in_buf[rptr:rend])

            indata = librosa.to_mono(indata.T)
            # Mic pre-gain (dB) before meter/gate so both see the boosted signal
            in_gain_db = float(getattr(self.gui_config, "in_gain_db", 0.0) or 0.0)
            if abs(in_gain_db) >= 0.05:
                indata = indata * np.float32(10.0 ** (in_gain_db / 20.0))
                np.clip(indata, -1.0, 1.0, out=indata)
            # Block input level in dB for the launcher's mic meter (cheap)
            try:
                _rms = float(np.sqrt(np.mean(np.square(indata))) + 1e-9)
                self.last_input_db = float(max(-90.0, 20.0 * np.log10(_rms)))
            except Exception:
                pass
            if self.gui_config.threhold > -60:
                indata = np.append(self.rms_buffer, indata)
                rms = librosa.feature.rms(
                    y=indata, frame_length=4 * self.zc, hop_length=self.zc
                )[:, 2:]
                self.rms_buffer[:] = indata[-4 * self.zc :]
                indata = indata[2 * self.zc - self.zc // 2 :]
                db_threhold = (
                    librosa.amplitude_to_db(rms, ref=1.0)[0] < self.gui_config.threhold
                )
                for i in range(db_threhold.shape[0]):
                    if db_threhold[i]:
                        indata[i * self.zc : (i + 1) * self.zc] = 0
                indata = indata[self.zc // 2 :]
            self.input_wav[: -self.block_frame] = self.input_wav[
                self.block_frame :
            ].clone()
            self.input_wav[-indata.shape[0] :] = torch.from_numpy(indata).to(
                self.config.device
            )
            self.input_wav_res[: -self.block_frame_16k] = self.input_wav_res[
                self.block_frame_16k :
            ].clone()
            # input noise reduction and resampling
            if self.gui_config.I_noise_reduce:
                self.input_wav_denoise[: -self.block_frame] = self.input_wav_denoise[
                    self.block_frame :
                ].clone()
                input_wav = self.input_wav[-self.sola_buffer_frame - self.block_frame :]
                input_wav = self.tg(
                    input_wav.unsqueeze(0), self.input_wav.unsqueeze(0)
                ).squeeze(0)
                input_wav[: self.sola_buffer_frame] *= self.fade_in_window
                input_wav[: self.sola_buffer_frame] += (
                    self.nr_buffer * self.fade_out_window
                )
                self.input_wav_denoise[-self.block_frame :] = input_wav[
                    : self.block_frame
                ]
                self.nr_buffer[:] = input_wav[self.block_frame :]
                self.input_wav_res[-self.block_frame_16k - 160 :] = self.resampler(
                    self.input_wav_denoise[-self.block_frame - 2 * self.zc :]
                )[160:]
            else:
                self.input_wav_res[-160 * (indata.shape[0] // self.zc + 1) :] = (
                    self.resampler(self.input_wav[-indata.shape[0] - 2 * self.zc :])[
                        160:
                    ]
                )
            # infer
            if self.function == "vc":
                # Skip full RVC when this block is gated silent — less GPU load / no "ghost" noise
                peak = float(np.max(np.abs(indata))) if indata.size else 0.0
                if peak < 2e-5:
                    need = (
                        int(self.block_frame)
                        + int(self.sola_buffer_frame)
                        + int(self.sola_search_frame)
                        + 32
                    )
                    infer_wav = torch.zeros(
                        need, device=self.config.device, dtype=torch.float32
                    )
                    # Decay SOLA tail so stop-speaking does not leave a short "aftertaste"
                    try:
                        self.sola_buffer.mul_(0.88)
                    except Exception:
                        pass
                else:
                    infer_wav = self.rvc.infer(
                        self.input_wav_res,
                        self.block_frame_16k,
                        self.skip_head,
                        self.return_length,
                        self.gui_config.f0method,
                    )
                    if self.resampler2 is not None:
                        infer_wav = self.resampler2(infer_wav)
            elif self.gui_config.I_noise_reduce:
                infer_wav = self.input_wav_denoise[self.extra_frame :].clone()
            else:
                infer_wav = self.input_wav[self.extra_frame :].clone()
            # output noise reduction
            if self.gui_config.O_noise_reduce and self.function == "vc":
                self.output_buffer[: -self.block_frame] = self.output_buffer[
                    self.block_frame :
                ].clone()
                self.output_buffer[-self.block_frame :] = infer_wav[-self.block_frame :]
                infer_wav = self.tg(
                    infer_wav.unsqueeze(0), self.output_buffer.unsqueeze(0)
                ).squeeze(0)
            # DSP 变声（tools.dsp_voice）。跟 RVC 是叠加关系，不是二选一：
            # 有音色时它接在 RVC 之后（音色给音色、DSP 给性格），没音色时
            # function 是 "fx"，上面直接走的干声，这里就是唯一的处理。
            if self.function in ("vc", "fx") and bool(
                getattr(self.gui_config, "dsp_enabled", False)
            ):
                try:
                    infer_wav = self._apply_voice_chain(infer_wav)
                except Exception:
                    traceback.print_exc()
            # DSP 修音链（gate / 压缩 / EQ）—— numpy on CPU
            if (
                self.function in ("vc", "fx")
                and bool(getattr(self.gui_config, "fx_enabled", False))
            ):
                try:
                    infer_wav = self._apply_fx_chain(infer_wav)
                except Exception:
                    traceback.print_exc()
            # volume envelop mixing
            if self.gui_config.rms_mix_rate < 1 and self.function == "vc":
                if self.gui_config.I_noise_reduce:
                    input_wav = self.input_wav_denoise[self.extra_frame :]
                else:
                    input_wav = self.input_wav[self.extra_frame :]
                rms1 = librosa.feature.rms(
                    y=input_wav[: infer_wav.shape[0]].cpu().numpy(),
                    frame_length=4 * self.zc,
                    hop_length=self.zc,
                )
                rms1 = torch.from_numpy(rms1).to(self.config.device)
                rms1 = F.interpolate(
                    rms1.unsqueeze(0),
                    size=infer_wav.shape[0] + 1,
                    mode="linear",
                    align_corners=True,
                )[0, 0, :-1]
                rms2 = librosa.feature.rms(
                    y=infer_wav[:].cpu().numpy(),
                    frame_length=4 * self.zc,
                    hop_length=self.zc,
                )
                rms2 = torch.from_numpy(rms2).to(self.config.device)
                rms2 = F.interpolate(
                    rms2.unsqueeze(0),
                    size=infer_wav.shape[0] + 1,
                    mode="linear",
                    align_corners=True,
                )[0, 0, :-1]
                rms2 = torch.max(rms2, torch.zeros_like(rms2) + 2e-3)
                # Clamp envelope gain — avoids rare sudden loud pops when rms2 dips
                exp = float(1.0 - self.gui_config.rms_mix_rate)
                gain = torch.pow(rms1 / rms2, exp)
                gain = torch.clamp(gain, 0.15, 3.5)
                infer_wav *= gain
            # SOLA algorithm from https://github.com/yxlllc/DDSP-SVC
            conv_input = infer_wav[
                None, None, : self.sola_buffer_frame + self.sola_search_frame
            ]
            cor_nom = F.conv1d(conv_input, self.sola_buffer[None, None, :])
            cor_den = torch.sqrt(
                F.conv1d(
                    conv_input**2,
                    torch.ones(1, 1, self.sola_buffer_frame, device=self.config.device),
                )
                + 1e-8
            )
            if sys.platform == "darwin":
                _, sola_offset = torch.max(cor_nom[0, 0] / cor_den[0, 0])
                sola_offset = sola_offset.item()
            else:
                sola_offset = torch.argmax(cor_nom[0, 0] / cor_den[0, 0])
            # Hot-path: no per-block log (was printt every chunk → latency)
            infer_wav = infer_wav[sola_offset:]
            if "privateuseone" in str(self.config.device) or not self.gui_config.use_pv:
                infer_wav[: self.sola_buffer_frame] *= self.fade_in_window
                infer_wav[: self.sola_buffer_frame] += (
                    self.sola_buffer * self.fade_out_window
                )
            else:
                infer_wav[: self.sola_buffer_frame] = phase_vocoder(
                    self.sola_buffer,
                    infer_wav[: self.sola_buffer_frame],
                    self.fade_out_window,
                    self.fade_in_window,
                )
            self.sola_buffer[:] = infer_wav[
                self.block_frame : self.block_frame + self.sola_buffer_frame
            ]
            outdata = (
                infer_wav[: self.block_frame]
                .repeat(self.gui_config.channels, 1)
                .t()
                .cpu()
                .numpy()
            )
            outdata = soft_clip_np(outdata)

            # Self-monitor: same converted audio to headphones (main out stays CABLE)
            self._write_monitor(outdata)

            # 装填输出缓冲
            start = self.out_ptr.value
            play_pos = self.play_ptr.value

            # 计算播放进度差（写指针距离播放指针的帧数）
            delta = (start - play_pos + buf_size) % buf_size

            if delta < self.block_frame:
                # 装填赶不上播放，导致播放进度追上来了，
                # 此时已产生无法挽回的破音，
                # 只好直接卡着播放指针写入，保证接下来的尽快放出来
                n_u = int(getattr(self, "_underrun_n", 0) or 0) + 1
                self._underrun_n = n_u
                if n_u <= 2 or n_u % 40 == 0:
                    print("[W] Output underrun")
                write_pos = play_pos
            else:
                # 否则按块对齐
                write_pos = (start + self.block_frame) % buf_size

            # 写入共享缓冲区
            end = (write_pos + self.block_frame) % buf_size
            if end > write_pos:
                self.out_buf[write_pos:end] = outdata
            else:
                first = buf_size - write_pos
                self.out_buf[write_pos:] = outdata[:first]
                self.out_buf[:end] = outdata[first:]

            # 更新写指针
            self.out_ptr.value = write_pos

            if self.in_evt.is_set():
                n_o = int(getattr(self, "_overrun_n", 0) or 0) + 1
                self._overrun_n = n_o
                if n_o <= 2 or n_o % 40 == 0:
                    print("[W] Input overrun")
                self.in_evt.clear()

            total_time = time.perf_counter() - start_time
            self.last_infer_ms = int(total_time * 1000)
            perf = getattr(self, "_perf", None)
            if perf is not None:
                perf.add(total_time)
            if flag_vc and self.window is not None:
                try:
                    self.window["infer_time"].update(self.last_infer_ms)
                except Exception:
                    pass
            # Soft-clip main output buffer write (below) via outdata path
            # Rate-limit timing log
            _lt = getattr(self, "_last_infer_log_t", 0.0)
            if total_time > 0.05 or (time.perf_counter() - _lt) > 2.0:
                self._last_infer_log_t = time.perf_counter()
                if total_time > 0.05:
                    printt("Infer time: %.2f", total_time)

        def update_devices(self, hostapi_name=None):
            """获取设备列表 — must fully stop stream before re-init sounddevice."""
            # Properly release AudioIoProcess (do NOT only clear flag_vc)
            try:
                self.stop_stream()
            except Exception:
                traceback.print_exc()
            sd._terminate()
            sd._initialize()
            devices = sd.query_devices()
            hostapis = sd.query_hostapis()
            for hostapi in hostapis:
                for device_idx in hostapi["devices"]:
                    devices[device_idx]["hostapi_name"] = hostapi["name"]
            self.hostapis = [hostapi["name"] for hostapi in hostapis]
            if hostapi_name not in self.hostapis:
                hostapi_name = self.hostapis[0]
            self.input_devices = [
                d["name"]
                for d in devices
                if d["max_input_channels"] > 0 and d["hostapi_name"] == hostapi_name
            ]
            self.output_devices = [
                d["name"]
                for d in devices
                if d["max_output_channels"] > 0 and d["hostapi_name"] == hostapi_name
            ]
            self.input_devices_indices = [
                d["index"] if "index" in d else d["name"]
                for d in devices
                if d["max_input_channels"] > 0 and d["hostapi_name"] == hostapi_name
            ]
            self.output_devices_indices = [
                d["index"] if "index" in d else d["name"]
                for d in devices
                if d["max_output_channels"] > 0 and d["hostapi_name"] == hostapi_name
            ]

        def _resolve_device_name(self, name, names):
            """Exact or truncated-MME prefix. See tools.device_pick.resolve_device_name."""
            from tools.device_pick import resolve_device_name

            return resolve_device_name(name or "", names or [])

        def set_devices(self, input_device, output_device):
            """设置输入输出设备（允许截断的设备名）。"""
            in_name = self._resolve_device_name(input_device, self.input_devices or [])
            out_name = self._resolve_device_name(output_device, self.output_devices or [])
            if in_name is None:
                raise ValueError(f"输入设备不在列表中: {input_device!r}")
            if out_name is None:
                raise ValueError(f"输出设备不在列表中: {output_device!r}")
            sd.default.device[0] = self.input_devices_indices[
                self.input_devices.index(in_name)
            ]
            sd.default.device[1] = self.output_devices_indices[
                self.output_devices.index(out_name)
            ]
            self.gui_config.sg_input_device = in_name
            self.gui_config.sg_output_device = out_name
            printt(
                "Input device: %s:%s (requested=%r)",
                str(sd.default.device[0]),
                in_name,
                input_device,
            )
            printt(
                "Output device: %s:%s (requested=%r)",
                str(sd.default.device[1]),
                out_name,
                output_device,
            )

        def get_device_samplerate(self):
            return int(
                sd.query_devices(device=sd.default.device[0])["default_samplerate"]
            )

        def get_device_channels(self):
            max_input_channels = sd.query_devices(device=sd.default.device[0])[
                "max_input_channels"
            ]
            max_output_channels = sd.query_devices(device=sd.default.device[1])[
                "max_output_channels"
            ]
            return min(max_input_channels, max_output_channels, 2)

        # ----- Headless worker mode (driven by main_app via JSON files) -----

        def _worker_write_status(self, **fields):
            try:
                from tools.worker_protocol import write_status

                write_status(**fields)
            except Exception:
                traceback.print_exc()

        def _device_latency_sec(self) -> float:
            """Sounddevice stream latency in seconds; 0 if not ready / absurd."""
            if self.audio_proc is None:
                return 0.0
            try:
                lat = float(self.audio_proc.get_latency())
            except Exception:
                return 0.0
            # Reject unready (-1) and legacy meme sentinel (~114514)
            if lat < 0 or lat > 5.0:
                return 0.0
            return lat

        def _refresh_delay_time(self) -> float:
            """Algorithm delay estimate: device + block + crossfade (+ denoise)."""
            self.delay_time = (
                self._device_latency_sec()
                + float(getattr(self.gui_config, "block_time", 0.25) or 0.25)
                + float(getattr(self.gui_config, "crossfade_time", 0.05) or 0.05)
                + 0.01
            )
            if getattr(self.gui_config, "I_noise_reduce", False):
                self.delay_time += min(
                    float(getattr(self.gui_config, "crossfade_time", 0.05) or 0.05),
                    0.04,
                )
            return self.delay_time

        def _worker_device_payload(self):
            return {
                "hostapis": list(self.hostapis or []),
                "input_devices": list(self.input_devices or []),
                "output_devices": list(self.output_devices or []),
                "sg_hostapi": self.gui_config.sg_hostapi,
                "sg_input_device": self.gui_config.sg_input_device,
                "sg_output_device": self.gui_config.sg_output_device,
            }

        def _cuda_graph_payload(self):
            """录了几张图、重放了多少次、退回 eager 多少次。

            没有这个就没法判断加速到底有没有生效：CUDA Graph 抓不住的时候是
            静默退回普通调用的，延迟数字看起来只是「没变快」，和没开一模一样。
            """
            try:
                from tools.cuda_graph import cuda_graph_enabled, get_cuda_graph_stats

                if not cuda_graph_enabled(self.config.device):
                    return {"cuda_graph": "off"}
                rvc = getattr(self, "rvc", None)
                if rvc is None:
                    return {"cuda_graph": "on"}
                a = get_cuda_graph_stats(getattr(rvc, "net_g", None))
                b = get_cuda_graph_stats(getattr(rvc, "model", None))
                return {
                    "cuda_graph": "on",
                    "cuda_graph_captures": a["captures"] + b["captures"],
                    "cuda_graph_replays": a["replays"] + b["replays"],
                    "cuda_graph_fallbacks": a["fallbacks"] + b["fallbacks"],
                }
            except Exception:
                return {"cuda_graph": "?"}

        def _values_from_config_file(self):
            """Build set_values-compatible dict from configs/inuse/config.json."""
            path = "configs/inuse/config.json"
            data = {}
            try:
                # 空/缺失时**不**复制 configs/config.json：那是开发机示例配置
                # （pitch=12、别的机器上的设备名），拿来当用户配置等于把用户
                # 参数全顶成模板值。inuse 由 Tauri 壳从 User_Data/app_config.json
                # 重建，缺失时先用空字典（下面的 data.get 全部有默认值）。
                if os.path.isfile(path) and os.path.getsize(path) > 0:
                    with open(path, "r", encoding="utf-8") as j:
                        raw = j.read().strip()
                    if raw:
                        data = json.loads(raw)
                        if not isinstance(data, dict):
                            data = {}
            except Exception as e:
                printt("config read failed (%s), using defaults", e)
                data = {}
            f0 = data.get("f0method") or "fcpe"
            sr = data.get("sr_type") or "sr_model"
            # Ensure devices are refreshed for hostapi
            hostapi = data.get("sg_hostapi") or (
                self.hostapis[0] if self.hostapis else ""
            )
            if hostapi:
                try:
                    self.update_devices(hostapi_name=hostapi)
                except Exception:
                    traceback.print_exc()
            # Drop missing / foreign-machine absolute model paths (common Setup pollution)
            pth = str(data.get("pth_path") or "")
            idx = str(data.get("index_path") or "")
            if pth and not os.path.isfile(pth):
                printt("config pth_path missing on this machine, cleared: %s", pth)
                pth = ""
            if idx and not os.path.isfile(idx):
                printt("config index_path missing on this machine, cleared: %s", idx)
                idx = ""
            values = {
                "pth_path": pth,
                "index_path": idx,
                "sg_hostapi": hostapi,
                "sg_wasapi_exclusive": bool(data.get("sg_wasapi_exclusive")),
                "sg_input_device": str(data.get("sg_input_device") or ""),
                "sg_output_device": str(data.get("sg_output_device") or ""),
                "monitor_device": str(data.get("monitor_device") or ""),
                "monitor_enabled": bool(data.get("monitor_enabled")),
                "sr_model": sr == "sr_model",
                "sr_device": sr == "sr_device",
                "threhold": data.get("threhold", -60),
                "in_gain_db": float(data.get("in_gain_db") or 0.0),
                "pitch": data.get("pitch", 0),
                "formant": data.get("formant", 0.0),
                "index_rate": data.get("index_rate", 0),
                "rms_mix_rate": data.get("rms_mix_rate", 0),
                "block_time": data.get("block_time", 0.25),
                "crossfade_length": data.get("crossfade_length", 0.05),
                "extra_time": data.get("extra_time", 2.5),
                "n_cpu": data.get("n_cpu", 4),
                "I_noise_reduce": bool(data.get("I_noise_reduce")),
                "O_noise_reduce": bool(data.get("O_noise_reduce")),
                "use_pv": bool(data.get("use_pv")),
                "pm": f0 == "pm",
                "harvest": f0 == "harvest",
                "crepe": f0 == "crepe",
                "rmvpe": f0 == "rmvpe",
                "fcpe": f0 == "fcpe",
                # Post-RVC DSP
                "fx_enabled": bool(data.get("fx_enabled")),
                "fx_gate_enabled": bool(data.get("fx_gate_enabled", True)),
                "fx_gate_threshold_db": float(data.get("fx_gate_threshold_db", -50)),
                "fx_gate_release_ms": float(data.get("fx_gate_release_ms", 50)),
                "fx_gate_hold_ms": float(data.get("fx_gate_hold_ms", 20)),
                "fx_gate_range_db": float(data.get("fx_gate_range_db", 20)),
                "fx_comp_enabled": bool(data.get("fx_comp_enabled", True)),
                "fx_comp_threshold_db": float(data.get("fx_comp_threshold_db", -20)),
                "fx_comp_ratio": float(data.get("fx_comp_ratio", 4)),
                "fx_comp_attack_ms": float(data.get("fx_comp_attack_ms", 5)),
                "fx_comp_release_ms": float(data.get("fx_comp_release_ms", 100)),
                "fx_comp_makeup_db": float(data.get("fx_comp_makeup_db", 0)),
                "fx_eq_enabled": bool(data.get("fx_eq_enabled", True)),
                "fx_eq_gains": data.get("fx_eq_gains") or [0.0, 0.0, 0.0, 0.0, 0.0],
                "fx_eq_preset": str(data.get("fx_eq_preset") or "flat"),
                "fx_out_gain_db": float(data.get("fx_out_gain_db") or 0),
                # 无模型 DSP 变声
                "dsp_enabled": bool(data.get("dsp_enabled")),
                "dsp_preset": str(data.get("dsp_preset") or ""),
                "dsp_params": data.get("dsp_params") or {},
            }
            # CUDA Graph 加速。设 0/1 到环境变量里，rtrvc 起模型时读它决定探不
            # 探测；只有 N 卡吃得到，A/I 卡和 CPU 那边探测函数自己会返回 False。
            # 默认关：这是改推理核心的东西，先让用户自己开，量过再谈默认值。
            os.environ["RVC_CUDA_GRAPH"] = (
                "1" if bool(data.get("cuda_graph", False)) else "0"
            )
            # Resolve truncated names; only fill a side that is actually gone.
            values = self._pick_default_devices(values)
            # Fix virtual monitor targets (Steam Speakers / CABLE / empty)
            if values.get("monitor_enabled"):
                mon = str(values.get("monitor_device") or "")
                try:
                    self.gui_config.sg_output_device = str(
                        values.get("sg_output_device") or ""
                    )
                except Exception:
                    pass
                if (not mon) or self._is_virtual_playback_name(mon):
                    better = self._pick_better_monitor_device(mon)
                    if better:
                        printt("config monitor device fixed: %r -> %r", mon, better)
                        values["monitor_device"] = better
            return values

        def _worker_list_devices(self, hostapi=None):
            try:
                name = hostapi or self.gui_config.sg_hostapi or None
                self.update_devices(hostapi_name=name)
                if name and name in (self.hostapis or []):
                    self.gui_config.sg_hostapi = name
                elif self.hostapis:
                    self.gui_config.sg_hostapi = self.hostapis[0]
                payload = self._worker_device_payload()
                self._worker_write_status(
                    state="idle" if not flag_vc else "running",
                    error="",
                    **_msg(DEV_REFRESHED),
                    **payload,
                )
            except Exception as e:
                traceback.print_exc()
                self._worker_write_status(
                    state="error",
                    error=f"list_devices: {type(e).__name__}: {e}",
                    **_msg(DEV_LIST_FAILED),
                )

        def _worker_apply_hot(self, payload: dict):
            """Apply hot-updatable parameters while stream may be running."""
            if "pitch" in payload and payload["pitch"] is not None:
                self.gui_config.pitch = payload["pitch"]
                if getattr(self, "rvc", None) is not None:
                    self.rvc.change_key(payload["pitch"])
            if "formant" in payload and payload["formant"] is not None:
                self.gui_config.formant = payload["formant"]
                if getattr(self, "rvc", None) is not None:
                    self.rvc.change_formant(payload["formant"])
            if "index_rate" in payload and payload["index_rate"] is not None:
                rate = float(payload["index_rate"])
                if not self.gui_config.index_path:
                    rate = 0.0
                self.gui_config.index_rate = rate
                if getattr(self, "rvc", None) is not None:
                    try:
                        self.rvc.change_index_rate(rate)
                    except Exception:
                        traceback.print_exc()
            if "rms_mix_rate" in payload and payload["rms_mix_rate"] is not None:
                self.gui_config.rms_mix_rate = float(payload["rms_mix_rate"])
            if "threhold" in payload and payload["threhold"] is not None:
                self.gui_config.threhold = payload["threhold"]
            if "in_gain_db" in payload and payload["in_gain_db"] is not None:
                self.gui_config.in_gain_db = float(payload["in_gain_db"])
            if "f0method" in payload and payload["f0method"]:
                method = str(payload["f0method"] or "fcpe")
                self.gui_config.f0method = method
                if method == "harvest":
                    try:
                        ensure_harvest_workers(self.gui_config.n_cpu)
                    except Exception:
                        pass
            if "I_noise_reduce" in payload:
                self.gui_config.I_noise_reduce = bool(payload["I_noise_reduce"])
            if "O_noise_reduce" in payload:
                self.gui_config.O_noise_reduce = bool(payload["O_noise_reduce"])
            if "use_pv" in payload:
                self.gui_config.use_pv = bool(payload["use_pv"])
            if "function" in payload and payload["function"] in ("vc", "im", "fx"):
                nxt = str(payload["function"])
                rvc = getattr(self, "rvc", None)
                dsp_on = bool(getattr(self.gui_config, "dsp_enabled", False))
                # 底栏只有 vc/bypass。纯 DSP 时壳可能推来 vc，rvc 是 None 不能跟。
                if nxt == "vc" and rvc is None and dsp_on:
                    nxt = "fx"
                # 音色已经在跑：配置里残留的 fx 不能把 RVC 关掉，两层要叠着。
                if nxt == "fx" and rvc is not None:
                    nxt = "vc"
                self.function = nxt
            # Self-monitor can toggle while running
            mon_changed = False
            if "monitor_enabled" in payload:
                new_en = bool(payload["monitor_enabled"])
                if new_en != bool(getattr(self.gui_config, "monitor_enabled", False)):
                    mon_changed = True
                self.gui_config.monitor_enabled = new_en
            if "monitor_device" in payload and payload["monitor_device"] is not None:
                new_dev = str(payload["monitor_device"] or "")
                if new_dev != str(getattr(self.gui_config, "monitor_device", "") or ""):
                    mon_changed = True
                self.gui_config.monitor_device = new_dev
            if mon_changed and flag_vc:
                try:
                    if self.gui_config.monitor_enabled:
                        self._open_monitor_stream()
                    else:
                        self._close_monitor_stream()
                except Exception:
                    traceback.print_exc()
            # DSP chain hot params
            fx_keys = (
                "fx_enabled",
                "fx_gate_enabled",
                "fx_gate_threshold_db",
                "fx_gate_release_ms",
                "fx_gate_hold_ms",
                "fx_gate_range_db",
                "fx_comp_enabled",
                "fx_comp_threshold_db",
                "fx_comp_ratio",
                "fx_comp_attack_ms",
                "fx_comp_release_ms",
                "fx_comp_makeup_db",
                "fx_eq_enabled",
                "fx_eq_gains",
                "fx_eq_preset",
                "fx_out_gain_db",
            )
            if any(k in payload for k in fx_keys):
                merged = self._fx_config_dict()
                for k in fx_keys:
                    if k in payload and payload[k] is not None:
                        merged[k] = payload[k]
                self._load_fx_from_values(merged)
            # DSP 变声热参数。只更新参数、不重建 VoiceChain —— 重建会清掉延迟线
            # 和重叠缓冲，拖滑条就会一路咔哒。
            if any(k in payload for k in ("dsp_enabled", "dsp_preset", "dsp_params")):
                gc = self.gui_config
                if payload.get("dsp_enabled") is not None:
                    gc.dsp_enabled = bool(payload["dsp_enabled"])
                if payload.get("dsp_preset") is not None:
                    gc.dsp_preset = str(payload["dsp_preset"] or "")
                if isinstance(payload.get("dsp_params"), dict):
                    gc.dsp_params = payload["dsp_params"]
                self._rebuild_voice_chain()
            # 换音色放在最后：上面那些（音高、共鸣、检索强度）已经落到
            # gui_config 上了，新的 RVC 实例正好用这些值建起来，不会先用旧参数
            # 建好再补一遍。
            if "pth_path" in payload and str(payload["pth_path"] or "").strip():
                self._worker_swap_model(
                    payload["pth_path"],
                    payload.get("index_path"),
                    payload.get("index_rate"),
                )
            # 「丢掉当前音色」的反向操作，和 pth_path 热推对称。
            #
            # 光把配置里的路径清空是不够的：正在跑的这个 worker 手里还攥着
            # RVC 实例，function 还是 vc，用户在界面上看到音色没了、耳朵里
            # 听到的还是那个音色。
            if payload.get("drop_model"):
                self._worker_drop_model()

        def _worker_drop_model(self):
            """变声中丢掉音色，退回纯 DSP（或直通），不重开流。

            和 `_worker_swap_model` 对称：只换该换的那一件东西。缓冲区、设备、
            SOLA 窗口全都不动 —— 它们只跟采样率有关，跟有没有音色无关。

            排队中的换模型也要一起取消，否则刚清掉音色，后台那个正在读的权重
            读完了又自己接回来。
            """
            with self._pending_model_lock:
                self._pending_model = None
                self._swap_ready = None
            self._swap_busy = False
            self.rvc = None
            self.resampler2 = None
            self.gui_config.pth_path = ""
            self.gui_config.index_path = ""
            self.dsp_only = True
            # 没音色了，vc 无从谈起：开着 DSP 就走 fx，否则只剩直通。
            if self.function == "vc":
                self.function = (
                    "fx" if bool(getattr(self.gui_config, "dsp_enabled", False)) else "im"
                )
            try:
                self.sola_buffer.zero_()
            except Exception:
                pass
            printt("已丢掉音色，function=%s", self.function)

        def _ckpt_tgt_sr(self, pth: str):
            """只读出这个权重的目标采样率，不建模型。

            换模型要不要重开流，只取决于采样率会不会变。为这一个数把整套
            RVC 建起来太贵，而 torch.load 出来的 cpt["config"][-1] 就是它。

            weights_only=True 是硬性的：.pth 是 pickle，允许它执行代码等于
            让任何一个从广场下下来的音色包在用户机器上跑任意程序。
            """
            try:
                cpt = torch.load(pth, map_location="cpu", weights_only=True)
                return int(cpt["config"][-1])
            except Exception:
                printt("读不出 %s 的采样率：%s", pth, traceback.format_exc())
                return None

        def _worker_swap_model(self, pth: str, index_path=None, index_rate=None):
            """变声中换音色。

            引擎原来根本不认 pth_path 这个热更新键：换模型只写了配置文件，正在跑
            的这个 worker 手里还攥着上一个模型，于是界面上名字变了、声音没变。
            上一版的做法是「停流再开流」—— 能换过去，但要几秒，设备重开，
            延迟设置重算，用户听到的是一段静音加一次咔哒。

            现在只换该换的那一件东西：RVC 实例。缓冲区的尺寸、音频进程、设备、
            SOLA 的窗口全都不动，因为它们只跟采样率有关，跟哪个音色无关。

            唯一换不了的情况是采样率真的会变 —— 只有「跟随模型」那档才可能，
            这时候整条流水线的几何尺寸都变了，老老实实重开。
            """
            global flag_vc
            pth = str(pth or "").strip()
            if not pth or not os.path.isfile(pth):
                self._model_swap_error = "音色文件不在了，仍在用上一个音色"
                printt("换模型：文件不存在 %s", pth)
                return
            idx = (
                str(index_path or "").strip()
                if index_path is not None
                else str(getattr(self.gui_config, "index_path", "") or "")
            )
            if idx and not os.path.isfile(idx):
                idx = ""
            rate = (
                float(index_rate)
                if index_rate is not None
                else float(getattr(self.gui_config, "index_rate", 0.0) or 0.0)
            )
            if not idx:
                rate = 0.0

            # 没在跑：配置文件里已经是新模型了，下次开启自然就对，这里只把
            # 内存里的那份对齐，免得随后的热更新拿旧路径去比。
            if not flag_vc:
                self.gui_config.pth_path = pth
                self.gui_config.index_path = idx
                self.gui_config.index_rate = rate
                return

            if pth == str(getattr(self.gui_config, "pth_path", "") or ""):
                return  # 同一个模型，没什么可换的

            if str(getattr(self.gui_config, "sr_type", "") or "") == "sr_model":
                sr = self._ckpt_tgt_sr(pth)
                if sr is None or sr != int(getattr(self.gui_config, "samplerate", 0) or 0):
                    printt("换模型：采样率要从 %s 变，重开流", self.gui_config.samplerate)
                    self.gui_config.pth_path = pth
                    self.gui_config.index_path = idx
                    self.gui_config.index_rate = rate
                    self._worker_start()
                    return

            job = (pth, idx, rate)
            with self._pending_model_lock:
                self._pending_model = job
                self._swap_ready = None
            self._swap_busy = True
            self._swap_progress = 20
            self._model_swap_error = ""
            self._worker_write_status(
                state="running",
                error="",
                progress=20,
                pid=os.getpid(),
                **_msg(VC_SWAPPING),
            )
            printt("换模型：已排队 %s", pth)
            # DirectML 跟音频线程抢设备容易炸；CUDA/CPU 后台读权重，旧音色继续出声。
            if bool(getattr(self.config, "dml", False)):
                self._swap_busy = False
                return
            t = threading.Thread(
                target=self._preload_pending_model,
                args=(job,),
                name="swap-model",
                daemon=True,
            )
            self._swap_loader = t
            t.start()

        def _preload_pending_model(self, job):
            """在命令线程之外读新权重，音频线程只做指针替换。"""
            pth, idx, rate = job
            try:
                self._swap_progress = 45
                self._worker_write_status(
                    state="running",
                    error="",
                    progress=45,
                    pid=os.getpid(),
                    **_msg(VC_LOADING_NET),
                )
                old = getattr(self, "rvc", None)
                new = rvc_for_realtime.RVC(
                    self.gui_config.pitch,
                    self.gui_config.formant,
                    pth,
                    idx,
                    rate,
                    self.gui_config.n_cpu,
                    inp_q,
                    opt_q,
                    self.config,
                    old,
                    on_progress=self._on_swap_progress,
                )
                if getattr(new, "net_g", None) is None or not getattr(new, "tgt_sr", 0):
                    raise RuntimeError("incomplete rvc")
                with self._pending_model_lock:
                    if self._pending_model != job:
                        return
                    self._swap_ready = (new, pth, idx, rate)
                self._swap_progress = 88
                self._worker_write_status(
                    state="running",
                    error="",
                    progress=88,
                    pid=os.getpid(),
                    **_msg(VC_SWAPPING),
                )
            except Exception:
                printt("换模型失败：%s", traceback.format_exc())
                with self._pending_model_lock:
                    if self._pending_model == job:
                        self._pending_model = None
                        self._swap_ready = None
                self._swap_busy = False
                self._swap_progress = 100
                self._model_swap_error = "换模型失败，仍在用上一个音色"
                self._worker_write_status(
                    state="running",
                    error="",
                    progress=100,
                    pid=os.getpid(),
                    **_msg(VC_SWAP_FAILED),
                )

        def _on_swap_progress(self, code, pct):
            # 换模型期间不要把 state 写成 starting，否则底栏会变成「启动中」。
            lo = max(25, min(85, int(pct)))
            self._swap_progress = lo
            try:
                self._worker_write_status(
                    state="running",
                    error="",
                    progress=lo,
                    pid=os.getpid(),
                    **_msg(code if str(code or "").startswith("vc.") else VC_SWAPPING),
                )
            except Exception:
                pass

        def _install_ready_model(self):
            """把预加载好的模型接到流上。**只在音频线程里调用。**"""
            with self._pending_model_lock:
                pack = self._swap_ready
                self._swap_ready = None
                self._pending_model = None
            if not pack:
                return
            new, pth, idx, rate = pack
            self._attach_rvc(new, pth, idx, rate)
            self._swap_busy = False
            self._swap_progress = 100
            self._model_swap_error = ""
            self._worker_write_status(
                state="running",
                error="",
                progress=100,
                pid=os.getpid(),
                **_msg(VC_RUNNING),
            )

        def _attach_rvc(self, new, pth, idx, rate):
            self.rvc = new
            # 纯 DSP 跑着的时候选了个音色：RVC 装上了，但 function 还是 fx，
            # 音频线程只在 function == "vc" 时才走 self.rvc.infer —— 不翻回来
            # 的话，用户选了音色却一点变化都听不到，而界面上音色名已经换了。
            self.dsp_only = False
            if self.function == "fx":
                self.function = "vc"
            self.gui_config.pth_path = pth
            self.gui_config.index_path = idx
            self.gui_config.index_rate = rate
            if new.tgt_sr != self.gui_config.samplerate:
                self.resampler2 = tat.Resample(
                    orig_freq=new.tgt_sr,
                    new_freq=self.gui_config.samplerate,
                    dtype=torch.float32,
                ).to(self.config.device)
            else:
                self.resampler2 = None
            try:
                self.sola_buffer.zero_()
            except Exception:
                pass
            printt("换模型完成：%s（tgt_sr=%s）", pth, new.tgt_sr)

        def _apply_pending_model(self):
            """装上排队中的新模型。**只在音频线程里调用。**（DML 走这条）"""
            with self._pending_model_lock:
                job = self._pending_model
                self._pending_model = None
            if not job:
                return
            pth, idx, rate = job
            old = getattr(self, "rvc", None)
            self._swap_progress = 40
            self._worker_write_status(
                state="running",
                error="",
                progress=40,
                pid=os.getpid(),
                **_msg(VC_SWAPPING),
            )
            try:
                # 把当前这个当 last_rvc 传进去：hubert、rmvpe、fcpe 都是跟音色无关
                # 的公共模型，RVC 的构造函数会直接沿用，只重新读合成器权重。
                new = rvc_for_realtime.RVC(
                    self.gui_config.pitch,
                    self.gui_config.formant,
                    pth,
                    idx,
                    rate,
                    self.gui_config.n_cpu,
                    inp_q,
                    opt_q,
                    self.config,
                    old,
                    on_progress=self._on_swap_progress,
                )
            except Exception:
                printt("换模型失败：%s", traceback.format_exc())
                self._swap_busy = False
                self._swap_progress = 100
                self._model_swap_error = "换模型失败，仍在用上一个音色"
                self._worker_write_status(
                    state="running",
                    error="",
                    progress=100,
                    pid=os.getpid(),
                    **_msg(VC_SWAP_FAILED),
                )
                return
            # RVC 的构造函数把异常全吞了（只打日志），失败时返回的是个半成品。
            # 不验一下就换上去，下一块推理会拿 None 去做卷积，整条流当场炸掉。
            if getattr(new, "net_g", None) is None or not getattr(new, "tgt_sr", 0):
                printt("换模型失败：新模型没建起来，保持原样")
                self._swap_busy = False
                self._swap_progress = 100
                self._model_swap_error = "换模型失败，仍在用上一个音色"
                self._worker_write_status(
                    state="running",
                    error="",
                    progress=100,
                    pid=os.getpid(),
                    **_msg(VC_SWAP_FAILED),
                )
                return

            self._attach_rvc(new, pth, idx, rate)
            self._swap_busy = False
            self._swap_progress = 100
            self._model_swap_error = ""
            self._worker_write_status(
                state="running",
                error="",
                progress=100,
                pid=os.getpid(),
                **_msg(VC_RUNNING),
            )

        def _worker_start(self):
            global flag_vc
            # 排在半路的换模型请求作废：重开流会照配置文件重新建 RVC，那份配置
            # 里已经是新模型了。留着它只会在新流刚起来时再白换一次。
            with self._pending_model_lock:
                self._pending_model = None
                self._swap_ready = None
            self._swap_busy = False
            self._swap_progress = 0
            self._model_swap_error = ""
            # Always stop previous stream before start (device change / restart)
            try:
                self.stop_stream()
            except Exception:
                traceback.print_exc()
            try:
                from tools.msg_codes import VC_LOADING_MODEL, status_fields as _sf_start

                _load_fields = _sf_start(VC_LOADING_MODEL)
            except Exception:
                _load_fields = {
                    "message_code": "vc.loading_model",
                    "message": "正在加载音色模型…",
                }

            self._worker_write_status(
                state="starting",
                error="",
                pid=os.getpid(),
                progress=12,
                **self._worker_device_payload(),
                # Distinct from process boot (engine.starting) so a sticky code
                # cannot freeze the dock on “引擎进程已启动，正在加载…”.
                **_load_fields,
            )
            try:
                values = self._values_from_config_file()
                self._last_invalid_reason = ""
                ok = self.set_values(values)
                if ok is not True:
                    self._worker_write_status(
                        state="error",
                        error=(
                            getattr(self, "_last_invalid_reason", "")
                            or "设置无效（模型路径 / 设备）"
                        ),
                        **_msg(VC_BAD_SETTINGS),
                    )
                    return
                try:
                    with open("configs/inuse/config.json", "r", encoding="utf-8") as jf:
                        raw = json.load(jf)
                    fn = str(raw.get("function") or "vc")
                    if fn in ("vc", "im", "fx"):
                        self.function = fn
                except Exception:
                    self.function = "vc"
                printt("worker start_vc")
                printt("cuda_is_available: %s", torch.cuda.is_available())
                printt(
                    "I_nr=%s O_nr=%s sr_type=%s block=%s",
                    self.gui_config.I_noise_reduce,
                    self.gui_config.O_noise_reduce,
                    self.gui_config.sr_type,
                    self.gui_config.block_time,
                )
                sys.stdout.flush()
                self.start_vc()
                # Wait briefly for AudioIoProcess to publish real device latency
                # (child sets latency after sd.Stream opens; old code read 114514 sentinel)
                if self.audio_proc is not None:
                    for _ in range(30):
                        lat = float(self.audio_proc.get_latency())
                        if 0 <= lat < 5.0:
                            break
                        time.sleep(0.05)
                    self._refresh_delay_time()
                printt(
                    "delay_ms=%s infer_ms=%s device_lat=%.3f block=%.3f xf=%.3f extra=%.3f hostapi=%s",
                    int(round(float(getattr(self, "delay_time", 0.0) or 0.0) * 1000)),
                    int(getattr(self, "last_infer_ms", 0) or 0),
                    self._device_latency_sec(),
                    float(getattr(self.gui_config, "block_time", 0.25) or 0.25),
                    float(getattr(self.gui_config, "crossfade_time", 0.05) or 0.05),
                    float(getattr(self.gui_config, "extra_time", 2.5) or 2.5),
                    getattr(self.gui_config, "sg_hostapi", ""),
                )
                # persist
                try:
                    settings = {
                        "pth_path": self.gui_config.pth_path,
                        "index_path": self.gui_config.index_path,
                        "sg_hostapi": self.gui_config.sg_hostapi,
                        "sg_wasapi_exclusive": self.gui_config.sg_wasapi_exclusive,
                        "sg_input_device": self.gui_config.sg_input_device,
                        "sg_output_device": self.gui_config.sg_output_device,
                        "sr_type": self.gui_config.sr_type,
                        "threhold": self.gui_config.threhold,
                        "in_gain_db": float(
                            getattr(self.gui_config, "in_gain_db", 0.0) or 0.0
                        ),
                        "pitch": self.gui_config.pitch,
                        "formant": self.gui_config.formant,
                        "rms_mix_rate": self.gui_config.rms_mix_rate,
                        "index_rate": self.gui_config.index_rate,
                        "block_time": self.gui_config.block_time,
                        "crossfade_length": self.gui_config.crossfade_time,
                        "extra_time": self.gui_config.extra_time,
                        "n_cpu": self.gui_config.n_cpu,
                        "use_jit": False,
                        "use_pv": self.gui_config.use_pv,
                        "f0method": self.gui_config.f0method,
                        "I_noise_reduce": self.gui_config.I_noise_reduce,
                        "O_noise_reduce": self.gui_config.O_noise_reduce,
                        "monitor_enabled": bool(
                            getattr(self.gui_config, "monitor_enabled", False)
                        ),
                        "monitor_device": str(
                            getattr(self.gui_config, "monitor_device", "") or ""
                        ),
                        "dsp_enabled": bool(
                            getattr(self.gui_config, "dsp_enabled", False)
                        ),
                        "dsp_preset": str(
                            getattr(self.gui_config, "dsp_preset", "") or ""
                        ),
                        "dsp_params": getattr(self.gui_config, "dsp_params", {}) or {},
                        "function": str(getattr(self, "function", "vc") or "vc"),
                    }
                    # Atomic write — plain "w" left 0-byte file when process killed mid-write
                    cfg_path = "configs/inuse/config.json"
                    tmp_path = cfg_path + ".tmp"
                    with open(tmp_path, "w", encoding="utf-8") as j:
                        json.dump(settings, j, ensure_ascii=False, indent=2)
                    os.replace(tmp_path, cfg_path)
                except Exception:
                    traceback.print_exc()
                self._worker_write_status(
                    state="running",
                    error="",
                    **_msg(VC_RUNNING),
                    progress=100,
                    delay_ms=int(np.round(self.delay_time * 1000)),
                    infer_ms=0,
                    samplerate=int(getattr(self.gui_config, "samplerate", 0) or 0),
                    **self._worker_device_payload(),
                    **self._cuda_graph_payload(),
                )
            except Exception as e:
                traceback.print_exc()
                flag_vc = False
                try:
                    self.stop_stream()
                except Exception:
                    pass
                self._worker_write_status(
                    state="error",
                    error=f"{type(e).__name__}: {e}",
                    **_msg(VC_START_FAILED),
                )

        def _worker_stop(self):
            try:
                self.stop_stream()
            except Exception as e:
                traceback.print_exc()
                self._worker_write_status(
                    state="error",
                    error=f"stop: {type(e).__name__}: {e}",
                    **_msg(VC_STOP_FAILED),
                    pid=os.getpid(),
                )
                return
            try:
                from tools.msg_codes import ENGINE_STOPPED, status_fields as _sf_idle

                _idle_fields = _sf_idle(ENGINE_STOPPED)
            except Exception:
                _idle_fields = {
                    "message_code": "engine.idle",
                    "message": "已停止",
                }

            self._worker_write_status(
                state="idle",
                error="",
                delay_ms=0,
                infer_ms=0,
                progress=100,
                pid=os.getpid(),
                **self._worker_device_payload(),
                **_idle_fields,
            )

        # ------------------------------------------------------------------
        # 离线语音转换（热路径）
        # ------------------------------------------------------------------

        def _sts_timer(self):
            """计时器拿不到就返回 None —— 计时永远不该让转换失败。"""
            try:
                from tools.sts_perf import StsTimer

                return StsTimer(hot=True)
            except Exception:
                return None

        def _sts_emit(self, **fields):
            try:
                from tools.worker_protocol import write_sts

                write_sts(**fields)
            except Exception:
                traceback.print_exc()

        def _sts_cancelled(self) -> bool:
            """转换途中壳有没有发过 sts_cancel。

            读的是命令文件本身而不是等主循环派发——主循环这会儿正卡在
            `_worker_convert` 里面，谁也不会来通知我们。
            """
            try:
                from tools.worker_protocol import read_command

                cmd = read_command()
                if str(cmd.get("cmd") or "").strip().lower() != "sts_cancel":
                    return False
                return int(cmd.get("seq") or 0) > int(self._sts_seq or 0)
            except Exception:
                return False

        def _sts_resident_vc(self, config, model_path: str = ""):
            """把常驻的实时模型包成离线 `VC` 的样子。

            `rtrvc.RVC` 手里的 hubert / net_g / rmvpe / faiss 索引，正好就是离线
            `Pipeline` 需要的全部。`VC.__init__` 只是把这几个字段置空，所以直接
            塞进去就行——不新建 shim 类，`vc_single` 的行为跟冷路径一字不差。

            这就是热路径省掉几十秒的地方：一个字节都不读盘。

            `model_path` 指向别的音色时（工具窗可以选跟首页不一样的目标音色），
            只把那 55MB 的 pth 读进来，hubert(189MB) 和 rmvpe(181MB) 照样复用。
            省不掉全部，但省掉大头——不然「换个音色转」就又要等一分钟。
            """
            from infer.modules.vc.modules import VC
            from infer.modules.vc.pipeline import Pipeline

            rvc = getattr(self, "rvc", None)
            if rvc is None or getattr(rvc, "net_g", None) is None:
                return None, "实时引擎里还没有加载好的音色模型"

            want = (model_path or "").strip()
            cur = str(getattr(rvc, "pth_path", "") or "").strip()
            same = not want or (
                os.path.normcase(os.path.abspath(want))
                == os.path.normcase(os.path.abspath(cur))
            )

            device = getattr(rvc, "device", config.device)
            is_half = bool(getattr(rvc, "is_half", config.is_half))
            hubert = getattr(rvc, "model", None)
            rmvpe = getattr(rvc, "model_rmvpe", None)

            if same:
                vc = VC(config)
                vc.net_g = rvc.net_g
                vc.tgt_sr = rvc.tgt_sr
                vc.if_f0 = rvc.if_f0
                vc.version = rvc.version
                vc.pipeline = Pipeline(rvc.tgt_sr, config)
            else:
                if not os.path.isfile(want):
                    return None, f"找不到音色模型：{want}"
                # get_vc 自己会建 net_g 和 Pipeline，且跟冷路径完全同一段代码。
                vc = VC(config)
                vc.get_vc(want)

            # 以常驻张量的实际精度/设备为准。config 是转换开始时才读的，可能跟
            # 当初建 net_g 时的那份不一致；对不上就是 half/float 混算直接炸。
            vc.pipeline.is_half = is_half
            vc.pipeline.device = device
            vc.hubert_model = hubert
            # DirectML 下 Pipeline.get_f0 会 del 掉 model_rmvpe 来收显存，那是
            # 实时那份，删了实时就没法用了。这条路上宁可让它自己再加载一份。
            if rmvpe is not None and "privateuseone" not in str(device):
                vc.pipeline.model_rmvpe = rmvpe
            return vc, ""

        def _worker_convert(self, payload):
            """壳发来的 `convert`：用常驻模型跑离线转换，跳过全部冷启动。"""
            from tools import sts_core

            self._sts_seq = int(payload.get("seq") or 0)
            inp = str(payload.get("input") or "").strip()
            out_dir = str(payload.get("output") or "").strip()
            f0method, f0_note = sts_core.normalize_f0method(
                str(payload.get("f0method") or "rmvpe")
            )

            def fail(msg):
                self._sts_emit(phase="error", message=msg, pct=0)

            if not inp or not out_dir:
                fail("输入 / 输出目录不能为空")
                return
            files = sts_core.collect_inputs(inp)
            if not files:
                fail("没有找到可转换的音频（支持 wav/mp3/flac/ogg/m4a 等）")
                return

            # 离线转换要独占显存，实时流先停。停完不自动重开——用户自己点，
            # 跟「关闭变声」的心智保持一致。
            was_running = bool(flag_vc)
            if was_running:
                try:
                    self.stop_stream()
                except Exception:
                    traceback.print_exc()

            total = len(files)
            srcs = [p for p, _ in files]
            # 热路径没有加载阶段，进度从 0 就是第一个文件。
            prog = sts_core.StsProgress(
                total,
                f0method,
                weights=sts_core.file_weights(srcs),
                emit=self._sts_emit,
                load_end=0.0,
            )
            head = "共 1 个文件，准备开始" if total == 1 else f"共 {total} 个文件（按体积加权进度），准备开始"
            if f0_note:
                head = f"{head}（{f0_note}）"
            self._sts_emit(
                phase="start", total=total, done=0, pct=0, current=0, ok=0, skip=0,
                message=head,
            )

            try:
                os.makedirs(out_dir, exist_ok=True)
            except OSError as e:
                fail(f"输出目录建不了：{e}")
                return

            # 热路径也计时。跟冷路径同一份格式，两条路的数字才好对着看 ——
            # 「省掉了多少」这句话得有具体的秒数撑着。
            timer = self._sts_timer()

            try:
                with _sts_stage(timer, "model"):
                    vc, why = self._sts_resident_vc(
                        self.config, str(payload.get("model") or "")
                    )
            except Exception as e:
                traceback.print_exc()
                fail(f"复用实时模型失败：{sts_core.friendly_error(e)}")
                return
            if vc is None:
                fail(why or "实时引擎里没有可用的模型")
                return

            index_path = str(payload.get("index") or "").strip()
            if not index_path or not os.path.isfile(index_path):
                index_path = str(getattr(self.gui_config, "index_path", "") or "").strip()
            if index_path and not os.path.isfile(index_path):
                index_path = ""

            out_files: list = []
            skipped: list = []
            try:
                with _sts_stage(timer, "convert"):
                    out_files, skipped, cancelled = sts_core.run_batch(
                        vc,
                        files,
                        out_dir,
                        {
                            "pitch": int(payload.get("pitch") or 0),
                            "f0method": f0method,
                            "index_path": index_path or None,
                            "index_rate": float(
                                payload.get("index_rate")
                                if payload.get("index_rate") is not None
                                else 0.75
                            ),
                            "filter_radius": int(
                                payload.get("filter_radius")
                                if payload.get("filter_radius") is not None
                                else 3
                            ),
                            "resample_sr": int(payload.get("resample_sr") or 0),
                            "rms_mix_rate": float(
                                payload.get("rms_mix_rate")
                                if payload.get("rms_mix_rate") is not None
                                else 0.25
                            ),
                            "protect": float(
                                payload.get("protect")
                                if payload.get("protect") is not None
                                else 0.33
                            ),
                            "format": sts_core.normalize_format(
                                str(payload.get("format") or "wav")
                            ),
                        },
                        prog,
                        self._sts_emit,
                        should_cancel=self._sts_cancelled,
                    )
            except Exception as e:
                traceback.print_exc()
                fail(sts_core.friendly_error(e))
                return
            finally:
                if timer is not None:
                    timer.save(
                        os.path.join("User_Data", "perf_reports"),
                        extra={"total": total, "ok": len(out_files)},
                    )
                # 常驻模型不能动，只把这一轮的中间张量还给分配器。
                sts_core.cuda_empty_cache()

            if cancelled:
                self._sts_emit(
                    phase="cancelled",
                    total=total,
                    done=len(out_files),
                    pct=prog.last_pct,
                    files=out_files,
                    skipped=skipped,
                    ok=len(out_files),
                    skip=len(skipped),
                    message="已取消",
                )
                return
            if not out_files:
                first = skipped[0]["reason"] if skipped else "未知错误"
                fail(f"{total} 个文件全部转换失败。第一个原因：{first}")
                return
            self._sts_emit(
                phase="done",
                files=out_files,
                skipped=skipped,
                total=total,
                done=total,
                pct=100,
                current=total,
                ok=len(out_files),
                skip=len(skipped),
                message=f"完成 {len(out_files)} 个，跳过 {len(skipped)} 个",
            )

        def worker_main(self):
            """No FreeSimpleGUI window — poll User_Data/runtime_control/command.json."""
            from tools.worker_protocol import (
                default_status,
                read_command,
                write_status,
                write_worker_pid_file,
                clear_worker_pid_file,
            )

            printt("realtime worker mode (no GUI window) pid=%s", os.getpid())
            write_worker_pid_file(os.getpid())
            # Initial status + devices (load may call update_devices → stop is fine)
            try:
                data = self.load()
                # Prewarm Harvest only when user config actually uses harvest
                try:
                    f0m = str(data.get("f0method") or "fcpe")
                    self.gui_config.f0method = f0m
                    if f0m == "harvest":
                        ensure_harvest_workers(
                            int(data.get("n_cpu") or self.gui_config.n_cpu or 4)
                        )
                        printt("harvest workers prewarmed (f0method=harvest)")
                except Exception:
                    traceback.print_exc()
                self.gui_config.sg_hostapi = data.get("sg_hostapi") or (
                    self.hostapis[0] if self.hostapis else ""
                )
                self.gui_config.sg_input_device = data.get("sg_input_device") or ""
                self.gui_config.sg_output_device = data.get("sg_output_device") or ""
                self.function = data.get("function") or "vc"
            except Exception:
                traceback.print_exc()
            base = default_status()
            base.update(self._worker_device_payload())
            base["state"] = "idle"
            base["pid"] = os.getpid()
            base["progress"] = 100
            try:
                from tools.msg_codes import ENGINE_READY, status_fields as _sf_ready

                base.update(_sf_ready(ENGINE_READY))
            except Exception:
                base["message"] = "引擎就绪"
                base["message_code"] = "engine.ready"
            write_status(**base)

            # Ignore stale commands left from previous sessions
            try:
                prev = read_command()
                last_seq = int(prev.get("seq") or 0)
            except Exception:
                last_seq = 0
            running = True
            try:
                while running:
                    try:
                        cmd = read_command()
                        seq = int(cmd.get("seq") or 0)
                        if seq > last_seq and cmd.get("cmd"):
                            last_seq = seq
                            action = str(cmd.get("cmd") or "").strip().lower()
                            printt("worker cmd seq=%s action=%s", seq, action)
                            write_status(last_cmd_seq=seq, pid=os.getpid())
                            if action == "quit":
                                self._worker_stop()
                                write_status(
                                    state="idle",
                                    **_msg(ENGINE_QUIT),
                                    pid=0,
                                    last_cmd_seq=seq,
                                )
                                running = False
                                break
                            elif action == "list_devices":
                                # Reloading hostapi stops stream — report idle after
                                host = cmd.get("sg_hostapi") or cmd.get("hostapi")
                                self._worker_list_devices(host)
                            elif action == "start":
                                self._worker_start()
                            elif action == "stop":
                                self._worker_stop()
                            elif action == "convert":
                                # 离线语音转换热路径：模型已经在手里，不重新加载。
                                # 这一句会阻塞到整批转完，期间命令循环不派发新
                                # 命令——取消靠 _sts_cancelled 自己去读命令文件。
                                params = (
                                    cmd.get("params")
                                    if isinstance(cmd.get("params"), dict)
                                    else cmd
                                )
                                self._worker_convert({**params, "seq": seq})
                            elif action == "sts_cancel":
                                # 转换途中由 _sts_cancelled 直接读命令文件认领；
                                # 走到这儿说明转换早结束了，什么都不用做。
                                pass
                            elif action == "set":
                                params = (
                                    cmd.get("params")
                                    if isinstance(cmd.get("params"), dict)
                                    else cmd
                                )
                                self._worker_apply_hot(params)
                                if flag_vc and self._swap_in_flight():
                                    self._worker_write_status(
                                        state="running",
                                        **_msg(VC_SWAPPING),
                                        progress=int(
                                            getattr(self, "_swap_progress", 20) or 20
                                        ),
                                        delay_ms=int(np.round(self.delay_time * 1000)),
                                        infer_ms=self.last_infer_ms,
                                        pid=os.getpid(),
                                        **self._worker_device_payload(),
                                    )
                                else:
                                    self._worker_write_status(
                                        state="running" if flag_vc else "idle",
                                        **_msg(VC_PARAMS_APPLIED),
                                        progress=100,
                                        delay_ms=int(np.round(self.delay_time * 1000)),
                                        infer_ms=self.last_infer_ms,
                                        pid=os.getpid(),
                                        **self._worker_device_payload(),
                                    )
                            else:
                                self._worker_write_status(
                                    **_msg(VC_UNKNOWN_CMD, action=action),
                                    last_cmd_seq=seq,
                                    pid=os.getpid(),
                                )
                        # heartbeat metrics — refresh delay (device latency may arrive late)
                        if flag_vc:
                            self._refresh_delay_time()
                            hb = {
                                "state": "running",
                                "delay_ms": int(np.round(self.delay_time * 1000)),
                                "infer_ms": self.last_infer_ms,
                                "input_db": round(
                                    float(getattr(self, "last_input_db", -90.0)), 1
                                ),
                                "samplerate": int(
                                    getattr(self.gui_config, "samplerate", 0) or 0
                                ),
                                "pid": os.getpid(),
                            }
                            if self._swap_in_flight():
                                hb["progress"] = int(
                                    getattr(self, "_swap_progress", 20) or 20
                                )
                                hb.update(_msg(VC_SWAPPING))
                            elif self._model_swap_error:
                                hb["progress"] = 100
                                hb.update(_msg(VC_SWAP_FAILED))
                            else:
                                hb["progress"] = 100
                            self._worker_write_status(**hb)
                    except Exception as e:
                        traceback.print_exc()
                        self._worker_write_status(
                            state="error",
                            error=f"loop: {type(e).__name__}: {e}",
                            **_msg(ENGINE_LOOP_ERROR),
                            pid=os.getpid(),
                        )
                    time.sleep(0.08)
            finally:
                try:
                    self.stop_stream()
                except Exception:
                    pass
                clear_worker_pid_file()
                printt("worker exit pid=%s", os.getpid())

    gui = GUI()
