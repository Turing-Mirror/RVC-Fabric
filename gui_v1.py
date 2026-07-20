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

    import librosa
    from tools.torchgate import TorchGate
    import numpy as np
    import FreeSimpleGUI as sg
    import sounddevice as sd
    import torch
    import torch.nn.functional as F
    import torchaudio.transforms as tat

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
    for _ in range(n_cpu):
        p = Harvest(inp_q, opt_q)
        p.daemon = True
        p.start()

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

    class GUI:
        def __init__(self) -> None:
            self.gui_config = GUIConfig()
            self.config = Config()
            self.function = "vc"
            self._fx_chain = None
            self.delay_time = 0
            self.last_infer_ms = 0
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
            """Prefer real mic in + CABLE Input out (VB-Cable / VoiceMeeter path)."""
            def _match(names, keywords, exclude=()):
                for n in names:
                    low = n.lower()
                    if any(x in low for x in exclude):
                        continue
                    if any(k in low for k in keywords):
                        return n
                return None

            ins = list(self.input_devices or [])
            outs = list(self.output_devices or [])
            # Input: real mic — avoid cable/voicemeeter virtual outputs as mic
            mic = _match(
                ins,
                ("microphone", "mic", "麦克风", "array"),
                exclude=("cable", "voicemeeter", "vb-audio", "virtual"),
            )
            if mic is None and ins:
                mic = next(
                    (
                        n
                        for n in ins
                        if "cable" not in n.lower() and "voicemeeter" not in n.lower()
                    ),
                    ins[0],
                )
            # Output: CABLE Input / VoiceMeeter Input (game apps listen on CABLE Output)
            cable_out = _match(
                outs,
                ("cable input", "voicemeeter input", "vb-audio"),
                exclude=("output",),
            )
            if cable_out is None:
                cable_out = _match(outs, ("cable input", "cable"))
            if cable_out is None and outs:
                cable_out = outs[0]
            if mic:
                data["sg_input_device"] = mic
            if cable_out:
                data["sg_output_device"] = cable_out
            return data

        def load(self):
            try:
                if not os.path.exists("configs/inuse/config.json"):
                    shutil.copy("configs/config.json", "configs/inuse/config.json")
                with open("configs/inuse/config.json", "r") as j:
                    data = json.load(j)
                    data["sr_model"] = data["sr_type"] == "sr_model"
                    data["sr_device"] = data["sr_type"] == "sr_device"
                    data["pm"] = data["f0method"] == "pm"
                    data["harvest"] = data["f0method"] == "harvest"
                    data["crepe"] = data["f0method"] == "crepe"
                    data["rmvpe"] = data["f0method"] == "rmvpe"
                    data["fcpe"] = data["f0method"] == "fcpe"
                    # Drop broken index (stale logs/*.index) so start won't crash
                    ip = str(data.get("index_path") or "").strip()
                    if ip and not os.path.isfile(ip):
                        data["index_path"] = ""
                        data["index_rate"] = 0
                    elif not ip:
                        data["index_rate"] = 0
                    if data.get("sg_hostapi") in self.hostapis:
                        self.update_devices(hostapi_name=data["sg_hostapi"])
                        if (
                            data.get("sg_input_device") not in self.input_devices
                            or data.get("sg_output_device") not in self.output_devices
                        ):
                            self.update_devices(hostapi_name=data["sg_hostapi"])
                            data = self._pick_default_devices(data)
                    else:
                        # Prefer MME for Cable compatibility when present
                        if "MME" in self.hostapis:
                            data["sg_hostapi"] = "MME"
                            self.update_devices(hostapi_name="MME")
                        else:
                            data["sg_hostapi"] = self.hostapis[0]
                            self.update_devices(hostapi_name=self.hostapis[0])
                        data = self._pick_default_devices(data)
            except:
                with open("configs/inuse/config.json", "w") as j:
                    data = {
                        "pth_path": "",
                        "index_path": "",
                        "sg_hostapi": self.hostapis[0],
                        "sg_wasapi_exclusive": False,
                        "sg_input_device": self.input_devices[
                            self.input_devices_indices.index(sd.default.device[0])
                        ],
                        "sg_output_device": self.output_devices[
                            self.output_devices_indices.index(sd.default.device[1])
                        ],
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

        def _notify(self, msg: str) -> None:
            printt("%s", msg)
            if self.worker_mode:
                try:
                    self._worker_write_status(error=str(msg), message=str(msg))
                except Exception:
                    pass
                return
            try:
                sg.popup(msg)
            except Exception:
                pass

        def set_values(self, values):
            if len(values["pth_path"].strip()) == 0:
                self._notify(i18n("请选择pth文件"))
                return False
            pth = values["pth_path"].strip()
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
            pattern = re.compile("[^\x00-\x7F]+")
            if pattern.findall(pth):
                self._notify(i18n("pth文件路径不可包含中文"))
                return False
            if index_path and pattern.findall(index_path):
                self._notify(i18n("index文件路径不可包含中文"))
                return False
            if not os.path.isfile(pth):
                self._notify(i18n("pth文件不存在") + f"\n{pth}")
                return False
            # Devices must exist for current hostapi list
            try:
                self.set_devices(values["sg_input_device"], values["sg_output_device"])
            except Exception as e:
                self._notify(f"设备无效: {e}")
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
            self._rebuild_fx_chain()

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
                # process whole tensor
                x = infer_wav.detach().float().cpu().numpy()
                y = self._fx_chain.process(x, sr)
                return torch.from_numpy(y).to(infer_wav.device).type_as(infer_wav)
            # only shape the newest block (rest is overlap history for SOLA)
            head = infer_wav[:-n]
            tail = infer_wav[-n:]
            x = tail.detach().float().cpu().numpy()
            y = self._fx_chain.process(x, sr)
            tail_t = torch.from_numpy(np.asarray(y, dtype=np.float32)).to(
                infer_wav.device
            ).type_as(infer_wav)
            return torch.cat([head, tail_t], dim=0)

        def start_vc(self):
            torch.cuda.empty_cache()
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
                self.rvc if hasattr(self, "rvc") else None,
            )
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
            if self.rvc.tgt_sr != self.gui_config.samplerate:
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
            try:
                self._warmup_engine()
            except Exception:
                traceback.print_exc()
            self.start_stream()

        def _warmup_engine(self):
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
            path = perf.save(os.path.join("User_Data", "perf_reports"))
            if path:
                printt("perf report saved: %s", path)

        def start_stream(self):
            global flag_vc
            if not flag_vc:
                flag_vc = True
                # Local perf report (User_Data/perf_reports) — how we get timing
                # data from user GPUs we don't own; nothing is uploaded
                try:
                    from tools.perf_report import PerfCollector

                    self._perf = PerfCollector(self._perf_meta())
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
            
            start_time = time.perf_counter()

            rend = rptr + self.block_frame
            indata = np.copy(self.in_buf[rptr:rend])

            indata = librosa.to_mono(indata.T)
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
            # Post-RVC DSP chain (gate / compressor / EQ) — numpy on CPU
            if (
                self.function == "vc"
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
            """Exact or prefix match (saved names are often truncated by UI/JSON)."""
            if not name or not names:
                return None
            if name in names:
                return name
            # Prefix / contains match for truncated MME names
            for n in names:
                if n.startswith(name) or name.startswith(n[: max(8, len(name) - 2)]):
                    return n
            # Fuzzy: strip spaces compare head
            head = name[:24].lower()
            for n in names:
                if n[:24].lower() == head or head in n.lower():
                    return n
            return None

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
            printt("Input device: %s:%s", str(sd.default.device[0]), in_name)
            printt("Output device: %s:%s", str(sd.default.device[1]), out_name)

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
                from launcher.realtime_protocol import write_status

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

        def _values_from_config_file(self):
            """Build set_values-compatible dict from configs/inuse/config.json."""
            path = "configs/inuse/config.json"
            data = {}
            try:
                if (not os.path.isfile(path)) or os.path.getsize(path) == 0:
                    if os.path.isfile("configs/config.json"):
                        shutil.copy("configs/config.json", path)
                with open(path, "r", encoding="utf-8") as j:
                    raw = j.read().strip()
                if not raw:
                    raise ValueError("empty inuse config")
                data = json.loads(raw)
                if not isinstance(data, dict):
                    data = {}
            except Exception as e:
                printt("config read failed (%s), using defaults", e)
                # Repair empty/corrupt file so next start works
                try:
                    if os.path.isfile("configs/config.json"):
                        shutil.copy("configs/config.json", path)
                        with open(path, "r", encoding="utf-8") as j:
                            data = json.load(j)
                    else:
                        data = {}
                        with open(path, "w", encoding="utf-8") as j:
                            json.dump(data, j)
                except Exception:
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
            values = {
                "pth_path": str(data.get("pth_path") or ""),
                "index_path": str(data.get("index_path") or ""),
                "sg_hostapi": hostapi,
                "sg_wasapi_exclusive": bool(data.get("sg_wasapi_exclusive")),
                "sg_input_device": str(data.get("sg_input_device") or ""),
                "sg_output_device": str(data.get("sg_output_device") or ""),
                "monitor_device": str(data.get("monitor_device") or ""),
                "monitor_enabled": bool(data.get("monitor_enabled")),
                "sr_model": sr == "sr_model",
                "sr_device": sr == "sr_device",
                "threhold": data.get("threhold", -60),
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
            }
            # Fill missing devices with defaults
            if (
                values["sg_input_device"] not in (self.input_devices or [])
                and self.input_devices
            ):
                values = self._pick_default_devices(values)
                if "sg_input_device" not in values or not values["sg_input_device"]:
                    values["sg_input_device"] = self.input_devices[0]
            if (
                values["sg_output_device"] not in (self.output_devices or [])
                and self.output_devices
            ):
                if not values.get("sg_output_device"):
                    values = self._pick_default_devices(values)
                if values["sg_output_device"] not in self.output_devices:
                    values["sg_output_device"] = self.output_devices[0]
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
                    message="devices refreshed",
                    **payload,
                )
            except Exception as e:
                traceback.print_exc()
                self._worker_write_status(
                    state="error",
                    error=f"list_devices: {type(e).__name__}: {e}",
                )

        def _worker_apply_hot(self, payload: dict):
            """Apply hot-updatable parameters while stream may be running."""
            if "pitch" in payload and payload["pitch"] is not None:
                self.gui_config.pitch = payload["pitch"]
                if hasattr(self, "rvc") and self.rvc is not None:
                    self.rvc.change_key(payload["pitch"])
            if "formant" in payload and payload["formant"] is not None:
                self.gui_config.formant = payload["formant"]
                if hasattr(self, "rvc") and self.rvc is not None:
                    self.rvc.change_formant(payload["formant"])
            if "index_rate" in payload and payload["index_rate"] is not None:
                rate = float(payload["index_rate"])
                if not self.gui_config.index_path:
                    rate = 0.0
                self.gui_config.index_rate = rate
                if hasattr(self, "rvc") and self.rvc is not None:
                    try:
                        self.rvc.change_index_rate(rate)
                    except Exception:
                        traceback.print_exc()
            if "rms_mix_rate" in payload and payload["rms_mix_rate"] is not None:
                self.gui_config.rms_mix_rate = float(payload["rms_mix_rate"])
            if "threhold" in payload and payload["threhold"] is not None:
                self.gui_config.threhold = payload["threhold"]
            if "f0method" in payload and payload["f0method"]:
                self.gui_config.f0method = str(payload["f0method"])
            if "I_noise_reduce" in payload:
                self.gui_config.I_noise_reduce = bool(payload["I_noise_reduce"])
            if "O_noise_reduce" in payload:
                self.gui_config.O_noise_reduce = bool(payload["O_noise_reduce"])
            if "use_pv" in payload:
                self.gui_config.use_pv = bool(payload["use_pv"])
            if "function" in payload and payload["function"] in ("vc", "im"):
                self.function = payload["function"]
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

        def _worker_start(self):
            global flag_vc
            # Always stop previous stream before start (device change / restart)
            try:
                self.stop_stream()
            except Exception:
                traceback.print_exc()
            self._worker_write_status(
                state="starting",
                error="",
                message="loading model…",
                pid=os.getpid(),
                **self._worker_device_payload(),
            )
            try:
                values = self._values_from_config_file()
                ok = self.set_values(values)
                if ok is not True:
                    self._worker_write_status(
                        state="error",
                        error="invalid settings (model path / devices)",
                        message="set_values failed",
                    )
                    return
                try:
                    with open("configs/inuse/config.json", "r", encoding="utf-8") as jf:
                        raw = json.load(jf)
                    fn = str(raw.get("function") or "vc")
                    if fn in ("vc", "im"):
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
                    message="vc running",
                    delay_ms=int(np.round(self.delay_time * 1000)),
                    infer_ms=0,
                    samplerate=int(getattr(self.gui_config, "samplerate", 0) or 0),
                    **self._worker_device_payload(),
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
                    message="start failed",
                )

        def _worker_stop(self):
            try:
                self.stop_stream()
            except Exception as e:
                traceback.print_exc()
                self._worker_write_status(
                    state="error",
                    error=f"stop: {type(e).__name__}: {e}",
                    pid=os.getpid(),
                )
                return
            self._worker_write_status(
                state="idle",
                error="",
                message="stopped",
                delay_ms=0,
                infer_ms=0,
                pid=os.getpid(),
                **self._worker_device_payload(),
            )

        def worker_main(self):
            """No FreeSimpleGUI window — poll User_Data/runtime_control/command.json."""
            from launcher.realtime_protocol import (
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
            base["message"] = "worker ready"
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
                                    message="quit",
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
                            elif action == "set":
                                params = (
                                    cmd.get("params")
                                    if isinstance(cmd.get("params"), dict)
                                    else cmd
                                )
                                self._worker_apply_hot(params)
                                self._worker_write_status(
                                    state="running" if flag_vc else "idle",
                                    message="params applied",
                                    delay_ms=int(np.round(self.delay_time * 1000)),
                                    infer_ms=self.last_infer_ms,
                                    pid=os.getpid(),
                                    **self._worker_device_payload(),
                                )
                            else:
                                self._worker_write_status(
                                    message=f"unknown cmd: {action}",
                                    last_cmd_seq=seq,
                                    pid=os.getpid(),
                                )
                        # heartbeat metrics — refresh delay (device latency may arrive late)
                        if flag_vc:
                            self._refresh_delay_time()
                            self._worker_write_status(
                                state="running",
                                delay_ms=int(np.round(self.delay_time * 1000)),
                                infer_ms=self.last_infer_ms,
                                samplerate=int(
                                    getattr(self.gui_config, "samplerate", 0) or 0
                                ),
                                pid=os.getpid(),
                            )
                    except Exception as e:
                        traceback.print_exc()
                        self._worker_write_status(
                            state="error",
                            error=f"loop: {type(e).__name__}: {e}",
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
