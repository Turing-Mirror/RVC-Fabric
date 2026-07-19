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
            self.block_time: float = 0.25  # s
            self.threhold: int = -60
            self.crossfade_time: float = 0.05
            self.extra_time: float = 2.5
            self.I_noise_reduce: bool = False
            self.O_noise_reduce: bool = False
            self.use_pv: bool = False
            self.rms_mix_rate: float = 0.0
            self.index_rate: float = 0.0
            self.n_cpu: int = min(n_cpu, 4)
            self.f0method: str = "fcpe"
            self.sg_hostapi: str = ""
            self.wasapi_exclusive: bool = False
            self.sg_input_device: str = ""
            self.sg_output_device: str = ""

    class GUI:
        def __init__(self) -> None:
            self.gui_config = GUIConfig()
            self.config = Config()
            self.function = "vc"
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
                        "threhold": -60,
                        "pitch": 0,
                        "formant": 0.0,
                        "index_rate": 0,
                        "rms_mix_rate": 0,
                        "block_time": 0.25,
                        "crossfade_length": 0.05,
                        "extra_time": 2.5,
                        "n_cpu": 4,
                        "f0method": "rmvpe",
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
                        with open("configs/inuse/config.json", "w") as j:
                            json.dump(settings, j)
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
            return True

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
            self.start_stream()

        def start_stream(self):
            global flag_vc
            if not flag_vc:
                flag_vc = True
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
                    raise

        def stop_stream(self):
            global flag_vc
            if flag_vc:
                flag_vc = False
                if self.audio_proc is not None:
                    print("Exiting")
                    self.stop_evt.set()
                    self.in_mem.close()
                    self.out_mem.close()
                    self.audio_proc.join()
                    self.audio_proc = None

        def audio_infer(
            self, buf_size:int # 2 * self.block_frame
        ):
            """
            音频处理
            """
            global flag_vc

            self.in_evt.wait()
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
                rms2 = torch.max(rms2, torch.zeros_like(rms2) + 1e-3)
                infer_wav *= torch.pow(
                    rms1 / rms2, torch.tensor(1 - self.gui_config.rms_mix_rate)
                )
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
            printt("sola_offset = %d", int(sola_offset))
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

            # 装填输出缓冲
            start = self.out_ptr.value
            play_pos = self.play_ptr.value

            # 计算播放进度差（写指针距离播放指针的帧数）
            delta = (start - play_pos + buf_size) % buf_size

            if delta < self.block_frame:
                # 装填赶不上播放，导致播放进度追上来了，
                # 此时已产生无法挽回的破音，
                # 只好直接卡着播放指针写入，保证接下来的尽快放出来
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
                print("[W] Input overrun")
                self.in_evt.clear()

            total_time = time.perf_counter() - start_time
            self.last_infer_ms = int(total_time * 1000)
            if flag_vc and self.window is not None:
                try:
                    self.window["infer_time"].update(self.last_infer_ms)
                except Exception:
                    pass
            printt("Infer time: %.2f", total_time)

        def update_devices(self, hostapi_name=None):
            """获取设备列表"""
            global flag_vc
            flag_vc = False
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

        def set_devices(self, input_device, output_device):
            """设置输出设备"""
            sd.default.device[0] = self.input_devices_indices[
                self.input_devices.index(input_device)
            ]
            sd.default.device[1] = self.output_devices_indices[
                self.output_devices.index(output_device)
            ]
            printt("Input device: %s:%s", str(sd.default.device[0]), input_device)
            printt("Output device: %s:%s", str(sd.default.device[1]), output_device)

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
            if not os.path.isfile(path):
                if os.path.isfile("configs/config.json"):
                    shutil.copy("configs/config.json", path)
            with open(path, "r", encoding="utf-8") as j:
                data = json.load(j)
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
            }
            # Fill missing devices with defaults
            if (
                values["sg_input_device"] not in (self.input_devices or [])
                and self.input_devices
            ):
                values = self._pick_default_devices(values)
                # _pick_default_devices mutates data-like dict
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

        def _worker_start(self):
            global flag_vc
            if flag_vc:
                self._worker_write_status(
                    state="running",
                    message="already running",
                    delay_ms=int(np.round(self.delay_time * 1000)),
                    infer_ms=self.last_infer_ms,
                    **self._worker_device_payload(),
                )
                return
            self._worker_write_status(
                state="starting",
                error="",
                message="loading model…",
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
                self.start_vc()
                if self.audio_proc is not None:
                    self.delay_time = (
                        self.audio_proc.get_latency()
                        + float(self.gui_config.block_time)
                        + float(self.gui_config.crossfade_time)
                        + 0.01
                    )
                    if self.gui_config.I_noise_reduce:
                        self.delay_time += min(float(self.gui_config.crossfade_time), 0.04)
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
                    }
                    with open("configs/inuse/config.json", "w", encoding="utf-8") as j:
                        json.dump(settings, j, ensure_ascii=False, indent=2)
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
                )
                return
            self._worker_write_status(
                state="idle",
                error="",
                message="stopped",
                delay_ms=0,
                infer_ms=0,
                **self._worker_device_payload(),
            )

        def worker_main(self):
            """No FreeSimpleGUI window — poll User_Data/runtime_control/command.json."""
            from launcher.realtime_protocol import (
                default_status,
                read_command,
                write_status,
            )

            printt("realtime worker mode (no GUI window)")
            # Initial status + devices
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

            last_seq = 0
            running = True
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
                                pid=os.getpid(),
                                last_cmd_seq=seq,
                            )
                            running = False
                            break
                        elif action == "list_devices":
                            host = cmd.get("sg_hostapi") or cmd.get("hostapi")
                            self._worker_list_devices(host)
                        elif action == "start":
                            self._worker_start()
                        elif action == "stop":
                            self._worker_stop()
                        elif action == "set":
                            # payload may be nested under "params" or flat
                            params = cmd.get("params") if isinstance(cmd.get("params"), dict) else cmd
                            self._worker_apply_hot(params)
                            self._worker_write_status(
                                state="running" if flag_vc else "idle",
                                message="params applied",
                                delay_ms=int(np.round(self.delay_time * 1000)),
                                infer_ms=self.last_infer_ms,
                                **self._worker_device_payload(),
                            )
                        else:
                            self._worker_write_status(
                                message=f"unknown cmd: {action}",
                                last_cmd_seq=seq,
                            )
                    # heartbeat metrics
                    if flag_vc:
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
                    )
                time.sleep(0.08)
            printt("worker exit")

    gui = GUI()
