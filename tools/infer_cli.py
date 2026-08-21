import argparse
import os
import sys

now_dir = os.getcwd()
sys.path.append(now_dir)
from dotenv import load_dotenv
from scipy.io import wavfile

from configs.config import Config
from infer.modules.vc.modules import VC

# 产品里这条 CLI 只给文字合成第二步用（SAPI wav → 当前音色）。DirectML 上
# hubert 会炸 PrivateUse1，必须走 dml_compat + CPU 兜底，不能再直接 vc_single。

####
# USAGE
#
# In your Terminal or CMD or whatever


def str2bool(value):
    """Parse common truthy/falsey CLI strings. argparse type=bool is broken."""
    if isinstance(value, bool):
        return value
    v = str(value).strip().lower()
    if v in ("1", "true", "t", "yes", "y", "on"):
        return True
    if v in ("0", "false", "f", "no", "n", "off"):
        return False
    raise argparse.ArgumentTypeError(f"expected a boolean, got {value!r}")


def arg_parse():
    parser = argparse.ArgumentParser(description="RVC offline inference CLI")
    parser.add_argument("--f0up_key", type=int, default=0)
    parser.add_argument("--input_path", type=str, required=True, help="input path")
    parser.add_argument("--index_path", type=str, default="", help="index path")
    parser.add_argument(
        "--f0method",
        type=str,
        default="rmvpe",
        help="pm | harvest | crepe | rmvpe | fcpe",
    )
    parser.add_argument("--opt_path", type=str, required=True, help="opt path")
    parser.add_argument(
        "--model_name",
        type=str,
        required=True,
        help="weight file name under assets/weights (weight_root)",
    )
    parser.add_argument("--index_rate", type=float, default=0.66, help="index rate")
    parser.add_argument("--device", type=str, default=None, help="device, e.g. cuda:0")
    parser.add_argument(
        "--is_half",
        type=str2bool,
        default=None,
        help="use fp16 (true/false). default: follow auto config",
    )
    parser.add_argument("--filter_radius", type=int, default=3, help="filter radius")
    parser.add_argument("--resample_sr", type=int, default=0, help="resample sr")
    parser.add_argument("--rms_mix_rate", type=float, default=1, help="rms mix rate")
    parser.add_argument("--protect", type=float, default=0.33, help="protect")

    args = parser.parse_args()
    # Config.arg_parse() also reads sys.argv; keep only the program name.
    sys.argv = sys.argv[:1]

    return args


def main():
    from pathlib import Path

    from infer.lib.dml_compat import apply_for
    from tools.sts_core import convert_one_with_cpu_fallback, friendly_error

    load_dotenv()
    args = arg_parse()
    config = Config()
    if args.device:
        config.device = args.device
    if args.is_half is not None:
        config.is_half = args.is_half
    # DirectML 上 hubert 的 GradMultiply 会抛 PrivateUse1。load_hubert 里也会
    # 打这份补丁，这里提前打：TTS 走的是这条 CLI，不是 sts_worker，26.8.21
    # 的用户日志就是 SAPI 念完之后整次换音色挂在 PrivateUse1 上。
    apply_for(config)
    vc = VC(config)
    vc.get_vc(args.model_name)

    src = Path(args.input_path)
    dest = Path(args.opt_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    def on_stage(*_a, **_k):
        return None

    def on_fallback(_err):
        print(
            "DirectML: operator missing, retrying on CPU",
            file=sys.stderr,
        )

    try:
        convert_one_with_cpu_fallback(
            vc,
            src,
            dest,
            pitch=args.f0up_key,
            f0method=args.f0method,
            index_path=args.index_path or None,
            index_rate=args.index_rate,
            filter_radius=args.filter_radius,
            resample_sr=args.resample_sr,
            rms_mix_rate=args.rms_mix_rate,
            protect=args.protect,
            on_stage=on_stage,
            wavfile=wavfile,
            fmt="wav",
            on_fallback=on_fallback,
        )
    except Exception as e:
        raise SystemExit(friendly_error(e)) from e
    print("ok")


if __name__ == "__main__":
    main()