import argparse
import os
import sys

now_dir = os.getcwd()
sys.path.append(now_dir)
from dotenv import load_dotenv
from scipy.io import wavfile

from configs.config import Config
from infer.modules.vc.modules import VC

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
    load_dotenv()
    args = arg_parse()
    config = Config()
    if args.device:
        config.device = args.device
    if args.is_half is not None:
        config.is_half = args.is_half
    vc = VC(config)
    vc.get_vc(args.model_name)
    info, wav_opt = vc.vc_single(
        0,
        args.input_path,
        args.f0up_key,
        None,
        args.f0method,
        args.index_path,
        None,
        args.index_rate,
        args.filter_radius,
        args.resample_sr,
        args.rms_mix_rate,
        args.protect,
    )
    if wav_opt is None or wav_opt[0] is None:
        raise SystemExit(f"inference failed:\n{info}")
    wavfile.write(args.opt_path, wav_opt[0], wav_opt[1])
    print(info)


if __name__ == "__main__":
    main()