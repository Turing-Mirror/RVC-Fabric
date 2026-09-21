import argparse
import os
import sys
import json
import shutil
from functools import wraps
from multiprocessing import cpu_count

from configs.accel import first_real_adapter
from configs.infer_windows import infer_window_profile

import torch

try:
    import intel_extension_for_pytorch as ipex  # pylint: disable=import-error, unused-import

    if torch.xpu.is_available():
        from infer.modules.ipex import ipex_init

        ipex_init()
except Exception:  # pylint: disable=broad-exception-caught
    pass
import logging

logger = logging.getLogger(__name__)


version_config_list = [
    "v1/32k.json",
    "v1/40k.json",
    "v1/48k.json",
    "v2/48k.json",
    "v2/32k.json",
]


def singleton_variable(func):
    @wraps(func, updated=())
    def wrapper(*args, **kwargs):
        if not wrapper.instance:
            wrapper.instance = func(*args, **kwargs)
        return wrapper.instance

    wrapper.instance = None
    return wrapper


@singleton_variable
class Config:
    def __init__(self):
        self.device = "cuda:0"
        self.is_half = True
        self.use_jit = False
        self.n_cpu = 0
        self.gpu_name = None
        self.json_config = self.load_config_json()
        self.gpu_mem = None
        (
            self.python_cmd,
            self.listen_port,
            self.iscolab,
            self.noparallel,
            self.noautoopen,
            self.dml,
        ) = self.arg_parse()
        # 唯一后端选择结果（E-03）：用户显式选择 > TM_ACCEL > TM_USE_DML/--dml > 自动。
        # accel 是策略（auto|cuda|dml|cpu），device_config 全程只看它和硬件事实，
        # 不允许「界面选了 cpu，CUDA 可用就还是走 cuda」。
        self.accel = self._resolve_accel(self.dml)
        self.dml = self.accel == "dml" or (
            self.accel == "auto" and self._resolve_dml_flag(self.dml)
        )
        from configs.accel import nvidia_names_from_env, nvidia_present_without_cuda

        self.nvidia_cuda_missing = nvidia_present_without_cuda(
            torch.cuda.is_available(), nvidia_names_from_env()
        )
        self.instead = ""
        self.preprocess_per = 3.7
        self.x_pad, self.x_query, self.x_center, self.x_max = self.device_config()

    @staticmethod
    def _resolve_accel(cli_dml: bool) -> str:
        """归一化后端策略：auto|cuda|dml|cpu。

        优先级：TM_ACCEL 显式值 > TM_USE_DML / --dml（旧兼容口）> auto。
        TM_ACCEL 是壳层把用户选择传进来的通道；用户在系统环境变量里手设
        TM_ACCEL 时同样生效——两边语义一致，都是「指定了这个后端」。
        """
        accel = os.environ.get("TM_ACCEL", "").strip().lower()
        if accel in ("directml", "amd", "intel"):
            accel = "dml"
        if accel == "nvidia":
            accel = "cuda"
        if accel in ("cuda", "dml", "cpu"):
            return accel
        force = os.environ.get("TM_USE_DML", "").strip().lower()
        if force in ("1", "true", "yes") or cli_dml:
            return "dml"
        return "auto"

    @staticmethod
    def _resolve_dml_flag(cli_dml: bool) -> bool:
        """Match official RVC: CLI --dml, plus env auto for single dual-backend pack.

        TM_USE_DML=1/0 forces; TM_ACCEL=auto|cuda|dml|cpu selects policy.
        Auto: CUDA if available, else DirectML if torch_directml works, else CPU.
        """
        force = os.environ.get("TM_USE_DML", "").strip().lower()
        if force in ("1", "true", "yes"):
            return True
        if force in ("0", "false", "no"):
            return False
        accel = os.environ.get("TM_ACCEL", "").strip().lower()
        if accel in ("directml", "amd", "intel"):
            accel = "dml"
        if accel == "dml":
            return True
        if accel in ("cuda", "cpu", "nvidia"):
            return False
        if cli_dml:
            return True
        # auto
        from configs.accel import auto_use_dml, nvidia_names_from_env

        cuda_on = bool(torch.cuda.is_available())
        nv = nvidia_names_from_env()
        dml_n = 0
        try:
            import torch_directml  # type: ignore

            dml_n = int(torch_directml.device_count())
        except Exception:
            dml_n = 0
        if nv and not cuda_on:
            logger.warning(
                "NVIDIA GPU listed (%s) but CUDA unavailable; not auto-selecting DirectML",
                ", ".join(nv),
            )
        if auto_use_dml(cuda_on, dml_n, nv):
            logger.info("Auto backend: DirectML (no CUDA; torch_directml available)")
            return True
        return False

    @staticmethod
    def load_config_json() -> dict:
        d = {}
        for config_file in version_config_list:
            src = f"configs/{config_file}"
            p = f"configs/inuse/{config_file}"
            os.makedirs(os.path.dirname(p), exist_ok=True)
            if not os.path.exists(p):
                shutil.copy(src, p)
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d[config_file] = json.load(f)
            except (ValueError, OSError):
                # inuse 那份坏了（空文件 / 写了一半）就回源头重拷一份再读。
                # 以前这里直接把异常抛出去，Config() 当场崩 —— 性能测试、实时
                # worker、离线转换全都起不来，而修复只要重拷一个 2 KB 的文件
                # （diag 26.8.19/1：清缓存之后 bench 报 JSONDecodeError）。
                logger.warning(
                    "config %s unreadable; restoring from %s", p, src
                )
                try:
                    shutil.copy(src, p)
                    with open(p, "r", encoding="utf-8") as f:
                        d[config_file] = json.load(f)
                except (ValueError, OSError):
                    logger.warning("config %s still unreadable; skipping", src)
        return d

    @staticmethod
    def arg_parse() -> tuple:
        exe = sys.executable or "python"
        parser = argparse.ArgumentParser()
        parser.add_argument("--port", type=int, default=7865, help="Listen port")
        parser.add_argument("--pycmd", type=str, default=exe, help="Python command")
        parser.add_argument("--colab", action="store_true", help="Launch in colab")
        parser.add_argument(
            "--noparallel", action="store_true", help="Disable parallel processing"
        )
        parser.add_argument(
            "--noautoopen",
            action="store_true",
            help="Do not open in browser automatically",
        )
        parser.add_argument(
            "--dml",
            action="store_true",
            help="torch_dml",
        )
        # parse_known_args: gui_v1 / worker may pass extra argv
        cmd_opts, _unknown = parser.parse_known_args()

        cmd_opts.port = cmd_opts.port if 0 <= cmd_opts.port <= 65535 else 7865

        return (
            cmd_opts.pycmd,
            cmd_opts.port,
            cmd_opts.colab,
            cmd_opts.noparallel,
            cmd_opts.noautoopen,
            cmd_opts.dml,
        )

    # has_mps is only available in nightly pytorch (for now) and MasOS 12.3+.
    # check `getattr` and try it for compatibility
    @staticmethod
    def has_mps() -> bool:
        if not torch.backends.mps.is_available():
            return False
        try:
            torch.zeros(1).to(torch.device("mps"))
            return True
        except Exception:
            return False

    @staticmethod
    def has_xpu() -> bool:
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            return True
        else:
            return False

    @staticmethod
    def cuda_capability_supported() -> tuple[bool, str]:
        """Check if the current CUDA device's compute capability is supported by torch.

        torch.cuda.is_available() only checks driver + device presence, NOT whether
        the installed torch has kernels for the device's compute capability.
        RTX 50-series (Blackwell, sm_120) + torch cu118 (max sm_90) reports
        is_available()=True but crashes natively on kernel execution (no kernel image).

        Compatibility rule: a cubin compiled for sm_{A}{B} runs on a device of
        capability (X, Y) when A == X and B <= Y (forward-compat within the same
        major version). Cross-major (e.g. sm_90 cubin on sm_120 device) does NOT
        work, and PTX JIT is unreliable across generations — so we require a
        same-major cubin. This avoids false-positiving RTX 40-series (sm_89),
        which runs fine on cu118 via the sm_86 cubin.
        Returns (supported, reason).
        """
        try:
            if not torch.cuda.is_available():
                return (True, "")
            cap = torch.cuda.get_device_capability(0)
            dev_major, dev_minor = int(cap[0]), int(cap[1])
            arch_list = list(torch.cuda.get_arch_list())

            def _parse_sm(s: str):
                if not s.startswith("sm_"):
                    return None
                digits = s[3:]
                if not digits.isdigit() or len(digits) < 2:
                    return None
                return (int(digits[:-1]), int(digits[-1]))  # (major, minor)

            for s in arch_list:
                parsed = _parse_sm(s)
                if parsed is None:
                    continue
                a_major, a_minor = parsed
                if a_major == dev_major and a_minor <= dev_minor:
                    return (True, "")

            name = torch.cuda.get_device_name(0)
            reason = (
                f"{name} (CUDA capability sm_{dev_major}{dev_minor}) is not compatible "
                f"with the installed PyTorch (supports {', '.join(arch_list)}). "
                f"50-series GPU needs the nvidia50 variant (CUDA 12.8 Runtime). "
                f"Falling back to CPU."
            )
            return (False, reason)
        except Exception:
            return (True, "")

    @classmethod
    def pick_directml_device(cls) -> int:
        """挑一块真显卡，别用 DirectML 的默认设备。

        `torch_directml.default_device()` 永远返回 0。装了串流或 VR 软件的机器上
        0 号往往是一块虚拟显示适配器 —— 它没有独立显存，模型一压上去就是显存不足，
        或者干脆访问违例把进程带走（Windows 退出码 -1073741819 / 0xC0000005）。
        用户那边看到的只有「显存不足，没法打开变声器」，跟显卡设置看不出关系。

        按名字把虚拟适配器排掉，取第一块剩下的。全都像虚拟的就退回 0：至少和以前
        一样，不会因为筛得太狠反而没得选。
        """
        try:
            import torch_directml  # type: ignore

            n = int(torch_directml.device_count())
        except Exception:
            return 0
        if n <= 1:
            return 0
        names = []
        for i in range(n):
            try:
                names.append(str(torch_directml.device_name(i)))
            except Exception:
                names.append("")
        i = first_real_adapter(names)
        if i is None:
            logger.warning(
                "DirectML: every adapter looks virtual (%s), falling back to 0", names
            )
            return 0
        if i != 0:
            logger.info(
                "DirectML: skipping virtual adapter(s) %s, using %d:%s",
                names[:i],
                i,
                names[i],
            )
        return i

    def use_fp32_config(self):
        for config_file in version_config_list:
            self.json_config[config_file]["train"]["fp16_run"] = False
            with open(f"configs/inuse/{config_file}", "r") as f:
                strr = f.read().replace("true", "false")
            with open(f"configs/inuse/{config_file}", "w") as f:
                f.write(strr)
            logger.info("overwrite " + config_file)
        self.preprocess_per = 3.0
        logger.info("overwrite preprocess_per to %d" % (self.preprocess_per))

    def device_config(self) -> tuple:
        if self.accel == "cpu":
            # 显式 CPU：RVC / HuBERT / 音高提取 / 检索 / ONNX 全部走 CPU，
            # 不再探测 CUDA / MPS / DirectML，也不让「有可用核显」把它顶回去。
            logger.info("Compute backend forced to CPU by user selection")
            self.device = self.instead = "cpu"
            self.is_half = False
            self.use_fp32_config()
        elif torch.cuda.is_available():
            # Check compute capability compatibility BEFORE using CUDA.
            # RTX 50-series (sm_120) + torch cu118 (max sm_90) reports
            # is_available()=True but crashes natively on kernel execution.
            cap_ok, cap_reason = self.cuda_capability_supported()
            if not cap_ok:
                logger.warning("CUDA device incompatible, falling back to CPU: %s", cap_reason)
                print(f"[Config] {cap_reason}", flush=True)
                self.device = self.instead = "cpu"
                self.is_half = False
                self.use_fp32_config()
            else:
                if self.has_xpu():
                    self.device = self.instead = "xpu:0"
                    self.is_half = True
                i_device = int(self.device.split(":")[-1])
                self.gpu_name = torch.cuda.get_device_name(i_device)
                if (
                    ("16" in self.gpu_name and "V100" not in self.gpu_name.upper())
                    or "P40" in self.gpu_name.upper()
                    or "P10" in self.gpu_name.upper()
                    or "1060" in self.gpu_name
                    or "1070" in self.gpu_name
                    or "1080" in self.gpu_name
                ):
                    logger.info("Found GPU %s, force to fp32", self.gpu_name)
                    self.is_half = False
                    self.use_fp32_config()
                else:
                    logger.info("Found GPU %s", self.gpu_name)
                self.gpu_mem = int(
                    torch.cuda.get_device_properties(i_device).total_memory
                    / 1024
                    / 1024
                    / 1024
                    + 0.4
                )
                if self.gpu_mem <= 4:
                    self.preprocess_per = 3.0
        elif self.accel != "cuda" and self.has_mps():
            logger.info("No supported Nvidia GPU found")
            self.device = self.instead = "mps"
            self.is_half = False
            self.use_fp32_config()
        else:
            # 显式 cuda 但没有可用 CUDA：如实退回 CPU 并留警告，不偷换 DirectML。
            if self.accel == "cuda":
                logger.warning(
                    "CUDA was explicitly selected but is unavailable; using CPU"
                )
            logger.info("No supported Nvidia GPU found")
            self.device = self.instead = "cpu"
            self.is_half = False
            self.use_fp32_config()

        if self.n_cpu == 0:
            self.n_cpu = cpu_count()

        x_pad, x_query, x_center, x_max = infer_window_profile(
            self.gpu_mem, self.is_half
        )
        if self.gpu_mem is not None and self.gpu_mem <= 3:
            logger.info(
                "offline infer windows tightened for %sGB (fp32=%s): center=%ss max=%ss",
                self.gpu_mem,
                not self.is_half,
                x_center,
                x_max,
            )
        if self.dml:
            logger.info("Use DirectML instead (AMD/Intel path, official RVC --dml)")
            self._swap_onnxruntime_provider(want_dml=True)
            try:
                import torch_directml  # type: ignore

                idx = self.pick_directml_device()
                self.device = torch_directml.device(idx)
                try:
                    self.gpu_name = str(torch_directml.device_name(idx))
                except Exception:
                    self.gpu_name = "DirectML"
                self.is_half = False
                self.use_fp32_config()
            except Exception as e:
                logger.warning("DirectML unavailable (%s), fallback CPU", e)
                self.device = self.instead = "cpu"
                self.is_half = False
                self.use_fp32_config()
        else:
            if self.instead:
                logger.info(f"Use {self.instead} instead")
            self._swap_onnxruntime_provider(want_dml=False)
        # 实际生效后端（与界面选择核对用）：从最终 device 推，不重复探测。
        low = str(self.device).lower()
        if low.startswith("privateuseone") or "dml" in low:
            self.accel_resolved = "dml"
        elif low.startswith("cuda"):
            self.accel_resolved = "cuda"
        elif low.startswith("mps"):
            self.accel_resolved = "mps"
        elif low.startswith("xpu"):
            self.accel_resolved = "xpu"
        else:
            self.accel_resolved = "cpu"
        if self.accel not in ("auto", self.accel_resolved):
            # 指定后端没生效（设备不在/初始化失败）——日志里写明，界面靠
            # compute_backend 字段也能看出不一致。
            logger.warning(
                "Selected backend %s resolved to %s", self.accel, self.accel_resolved
            )
        logger.info(
            "Half-precision floating-point: %s, device: %s"
            % (self.is_half, self.device)
        )
        return x_pad, x_query, x_center, x_max

    @staticmethod
    def _swap_onnxruntime_provider(*, want_dml: bool) -> None:
        """Official RVC renames onnxruntime <-> onnxruntime-dml/cuda under Runtime.

        Paths are case-insensitive on Windows; try both runtime/ and Runtime/.
        """
        roots = []
        for name in ("Runtime", "runtime"):
            p = os.path.join(name, "Lib", "site-packages")
            if os.path.isdir(p):
                roots.append(p)
        if not roots:
            return
        for sp in roots:
            ort = os.path.join(sp, "onnxruntime")
            ort_dml = os.path.join(sp, "onnxruntime-dml")
            ort_cuda = os.path.join(sp, "onnxruntime-cuda")
            dml_dll = os.path.join(ort, "capi", "DirectML.dll")
            cuda_dll = os.path.join(ort, "capi", "onnxruntime_providers_cuda.dll")
            try:
                if want_dml:
                    if not os.path.isfile(dml_dll):
                        if os.path.isdir(ort) and not os.path.isdir(ort_cuda):
                            os.rename(ort, ort_cuda)
                        if os.path.isdir(ort_dml) and not os.path.isdir(ort):
                            os.rename(ort_dml, ort)
                else:
                    if not os.path.isfile(cuda_dll):
                        if os.path.isdir(ort) and not os.path.isdir(ort_dml):
                            # only rename away if it looks like dml package
                            if os.path.isfile(os.path.join(ort, "capi", "DirectML.dll")):
                                os.rename(ort, ort_dml)
                        if os.path.isdir(ort_cuda) and not os.path.isdir(ort):
                            os.rename(ort_cuda, ort)
            except Exception as e:
                # 改名中途失败会留下残缺的 onnxruntime 安装 —— 必须留痕，
                # 不然事后排查「ORT 突然 import 不了」没有任何线索。
                logger.warning(
                    "onnxruntime provider swap failed under %s: %s", sp, e
                )
            want_dll = dml_dll if want_dml else cuda_dll
            if os.path.isdir(ort) and not os.path.isfile(want_dll):
                logger.warning(
                    "onnxruntime provider swap incomplete under %s: %s missing",
                    sp,
                    want_dll,
                )
