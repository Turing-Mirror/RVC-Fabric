"""训练流水线驱动。

原版把训练做在 infer-web.py 里，和 gradio 缠在一起：每一步都是 generator，
进度靠 `yield 整个日志文件` 刷到网页上。我们要在 Tauri 壳里用，就不能把 gradio
拖进来 —— 那是几十兆的依赖和一个必须开着的 web 服务。

所以这里把「驱动」和「界面」拆开：本文件只负责按顺序把原版那几个训练脚本
起成子进程，把进度折算成 JSON 行打到 stdout；壳读这些行画进度条。预处理和
`extract_f0_print` 的 argv 从模块顶层挪进了 `__main__`（Windows spawn 否则
会把子进程砸死），其余尽量不动，跟进上游时对一下这两处即可。

协议（每行一个 JSON 对象，stdout）::

    {"phase": "stage", "stage": "preprocess", "index": 1, "total_stages": 5,
     "done": 12, "total": 40, "message": "切片中…"}
    {"phase": "done", "weights": "assets/weights/xx.pth", "index": "logs/xx/added_...index"}
    {"phase": "error", "message": "..."}

请求走文件不走命令行：数据集路径里有中文和空格是常态，拼进命令行就是一串
转义地雷。用法::

    python tools/train_worker.py <request.json>
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

# 产品根：Rust 会把 cwd 设成这里，但脚本自己也认，免得有人从别处起。
ROOT = Path(__file__).resolve().parent.parent
NOW_DIR = str(ROOT)
if os.getcwd() != NOW_DIR:
    os.chdir(NOW_DIR)
if NOW_DIR not in sys.path:
    sys.path.insert(0, NOW_DIR)

# 必须在 sys.path 补好之后：Runtime 的 python39._pth 不认脚本目录。
from tools import msg_codes as mc  # noqa: E402

# 采样率字符串 → 整数。原版 infer-web.py 的 sr_dict。
SR_MAP = {"32k": 32000, "40k": 40000, "48k": 48000}
SR_FROM_HZ = {32000: "32k", 40000: "40k", 48000: "48k"}

# train.py 正常结束走 os._exit(2333333)，不是失败。
TRAIN_PY_DONE = 2333333

# 跟 infer/modules/train/preprocess.py 的 _AUDIO_EXT 一致。
AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"}

STAGE_DIRS = (
    "0_gt_wavs",
    "1_16k_wavs",
    "2a_f0",
    "2b-f0nsf",
    "3_feature256",
    "3_feature768",
)

# v2 只有 32k/48k 两份 config；40k 走 v1 的那份（原版 click_train 的判断）。
VERSION = "v2"
FEATURE_DIM = 768

STAGES = ("preprocess", "f0", "feature", "train", "index")

_emit_lock = threading.Lock()


def emit(**kw):
    """一行一个 JSON。带锁是因为 tail 线程和主线程都会往 stdout 写。"""
    with _emit_lock:
        sys.stdout.write(json.dumps(kw, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def fail(message):
    """没有码的报错：上游 RVC 返回的原文，我们编不了码。"""
    emit(phase="error", message=str(message))
    sys.exit(1)


def fail_code(code, params=None):
    """我们自己写的报错。带码，壳按界面语言取译文。"""
    emit(phase="error", **mc.msg_fields(code, params))
    sys.exit(1)


# ---------------------------------------------------------------------------
# 进度
# ---------------------------------------------------------------------------


def count_files(d, suffix=None):
    p = Path(d)
    if not p.is_dir():
        return 0
    if suffix is None:
        return sum(1 for x in p.iterdir() if x.is_file())
    return sum(1 for x in p.iterdir() if x.is_file() and x.name.endswith(suffix))


def count_audio(d):
    p = Path(d)
    if not p.is_dir():
        return 0
    return sum(
        1
        for x in p.rglob("*")
        if x.is_file() and x.suffix.lower() in AUDIO_EXT
    )


def file_bytes(p):
    try:
        return p.stat().st_size if p.is_file() else 0
    except OSError:
        return 0


def latest_epoch_in_log(log_path):
    """train.log 里最后一次 ``====> Epoch: N``。文件不在或读失败就当没训过。"""
    p = Path(log_path)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    epoch = None
    marker = "====> Epoch: "
    for line in text.splitlines():
        at = line.find(marker)
        if at < 0:
            continue
        tail = line[at + len(marker):].strip().split()
        if not tail:
            continue
        try:
            epoch = int(tail[0])
        except ValueError:
            continue
    return epoch


def list_pths(d):
    p = Path(d)
    if not p.is_dir():
        return []
    out = []
    try:
        names = sorted(p.iterdir(), key=lambda x: x.name)
    except OSError:
        return []
    for x in names:
        if x.is_file() and x.suffix.lower() == ".pth":
            out.append({"name": x.name, "bytes": file_bytes(x)})
    return out


def artifact_snapshot(exp_dir, root, req):
    """一次训练结束时盘上到底有什么。

    取消、崩、成功都要能从这份快照判断：有没有可用音色、卡在哪一步。
    26.8.16 两份用户日志只有一句「已取消」或预处理 traceback，看不出
    切片有没有切完、权重写没写出来。
    """
    exp = str(req.get("exp") or Path(exp_dir).name)
    exp_dir = Path(exp_dir)
    root = Path(root)
    counts = {
        "0_gt_wavs": count_files(exp_dir / "0_gt_wavs"),
        "1_16k_wavs": count_files(exp_dir / "1_16k_wavs"),
        "2a_f0": count_files(exp_dir / "2a_f0"),
        "2b-f0nsf": count_files(exp_dir / "2b-f0nsf"),
        "3_feature768": count_files(exp_dir / "3_feature768"),
    }
    filelist_lines = 0
    fl = exp_dir / "filelist.txt"
    if fl.is_file():
        try:
            filelist_lines = sum(
                1 for line in fl.read_text(encoding="utf-8", errors="replace").splitlines()
                if line.strip()
            )
        except OSError:
            filelist_lines = 0
    weights = root / "assets" / "weights" / ("%s.pth" % exp)
    # 发布位置要跟 publish_voice 一致：用户设了输出目录时音色不在 User_Data 下，
    # 写死这一条会让诊断包里永远显示「published 0 字节」，看的人以为发布失败。
    out_dir = str(req.get("output_dir") or "").strip()
    published_base = Path(out_dir) if out_dir else root / "User_Data" / "models"
    published = published_base / exp / ("%s.pth" % exp)
    weight_pths = [
        x for x in list_pths(root / "assets" / "weights")
        if x["name"] == ("%s.pth" % exp) or x["name"].startswith("%s_e" % exp)
    ]
    exp_pths = list_pths(exp_dir)
    if file_bytes(weights) > 0 or file_bytes(published) > 0:
        usable = "final"
    elif weight_pths or exp_pths:
        usable = "intermediate"
    elif counts["1_16k_wavs"] > 0:
        usable = "slices_only"
    else:
        usable = "none"
    return {
        "exp": exp,
        "counts": counts,
        "filelist_lines": filelist_lines,
        "latest_epoch": latest_epoch_in_log(exp_dir / "train.log"),
        "final_weights_bytes": file_bytes(weights),
        "published_bytes": file_bytes(published),
        "weight_pths": weight_pths,
        "exp_pths": exp_pths,
        "usable": usable,
    }


def emit_checkpoint(stage, exp_dir, root, req):
    snap = artifact_snapshot(exp_dir, root, req)
    emit(phase="checkpoint", stage=stage, **snap)
    # stderr 也会进壳的训练日志（stdout 只走进度管道）。进程被 taskkill
    # 时这条可能写不完，所以壳侧结束时还会自己再扫一遍盘。
    sys.stderr.write(
        "checkpoint stage=%s usable=%s epoch=%s slices=%s f0=%s feat=%s "
        "filelist=%s weights=%s published=%s exp_pths=%s\n"
        % (
            stage,
            snap["usable"],
            snap["latest_epoch"],
            snap["counts"]["1_16k_wavs"],
            snap["counts"]["2a_f0"],
            snap["counts"]["3_feature768"],
            snap["filelist_lines"],
            snap["final_weights_bytes"],
            snap["published_bytes"],
            ",".join(x["name"] for x in snap["exp_pths"]) or "-",
        )
    )
    sys.stderr.flush()
    return snap


def dump_log_tail(path, n=50, max_bytes=65536):
    """失败时把阶段日志尾巴打到 stderr，诊断包里就能看见真正的报错。"""
    p = Path(path)
    try:
        size = p.stat().st_size
    except OSError:
        sys.stderr.write("=== tail %s (missing) ===\n" % p)
        sys.stderr.flush()
        return
    try:
        with open(p, "rb") as f:
            if size > max_bytes:
                f.seek(-max_bytes, os.SEEK_END)
            data = f.read()
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        shown = lines[-n:]
        sys.stderr.write(
            "=== tail %s (%d bytes, last %d lines) ===\n"
            % (p, size, len(shown))
        )
        sys.stderr.write("\n".join(shown) + "\n")
        sys.stderr.flush()
    except OSError as e:
        sys.stderr.write("=== tail %s (unreadable: %s) ===\n" % (p, e))
        sys.stderr.flush()


def write_meta(exp_dir, req):
    (exp_dir / "tm_meta.json").write_text(
        json.dumps({"sample_rate": req["sample_rate"], "exp": req["exp"]}, ensure_ascii=False),
        encoding="utf-8",
    )


def infer_sr(exp_dir):
    """续跑时用已有切片的采样率，不能信界面当下选的那档。"""
    meta = exp_dir / "tm_meta.json"
    if meta.is_file():
        try:
            sr = json.loads(meta.read_text(encoding="utf-8")).get("sample_rate")
            if sr in SR_MAP:
                return sr
        except (OSError, ValueError):
            pass
    cfg = exp_dir / "config.json"
    if cfg.is_file():
        try:
            n = json.loads(cfg.read_text(encoding="utf-8")).get("data", {}).get(
                "sampling_rate"
            )
            if n in SR_FROM_HZ:
                return SR_FROM_HZ[n]
        except (OSError, ValueError):
            pass
    gt = exp_dir / "0_gt_wavs"
    if gt.is_dir():
        for p in gt.iterdir():
            if p.suffix.lower() != ".wav":
                continue
            try:
                with wave.open(str(p), "rb") as w:
                    n = w.getframerate()
                if n in SR_FROM_HZ:
                    return SR_FROM_HZ[n]
            except Exception:
                continue
    return None


def publish_voice(root, req, weights, index_path):
    """把训好的 pth/index 装进音色库，模型页能直接「使用」。

    savee 只写 assets/weights。那边会被当成旧版单文件音色，没有检索库。
    复制一份进用户音色库，并写 sidecar。

    `output_dir` 非空时改放到用户指定的目录 —— 一个音色连模型带索引三四百 MB，
    训十个就是几个 G，不该全部压在系统盘上。壳那边会把这个目录一并加进音色库
    的扫描范围，所以放到别处也照样在模型页里看得见、用得上。
    """
    base = Path(req["output_dir"]) if req.get("output_dir") else root / "User_Data" / "models"
    dest = base / req["exp"]
    dest.mkdir(parents=True, exist_ok=True)
    pth_dest = dest / ("%s.pth" % req["exp"])
    try:
        shutil.copy2(weights, pth_dest)
        if index_path:
            ip = Path(index_path)
            if ip.is_file():
                shutil.copy2(ip, dest / ip.name)
        sidecar = dest / "config.json"
        data = {}
        if sidecar.is_file():
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
        if not isinstance(data, dict):
            data = {}
        data["name"] = req["exp"]
        data["tag"] = data.get("tag") or "自制"
        data["source"] = "trained"
        data["sample_rate"] = req["sample_rate"]
        sidecar.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return pth_dest
    except OSError:
        return None


def wipe_stage_dirs(exp_dir):
    for name in STAGE_DIRS:
        d = exp_dir / name
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
    for name in ("filelist.txt", "config.json", "tm_meta.json", "total_fea.npy"):
        p = exp_dir / name
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass


class StageProgress(threading.Thread):
    """轮询产物目录来估进度。

    原版是把整个日志文件 yield 到网页上，我们要的是一个百分比。数产物文件比
    解析日志稳：日志格式跟着上游变，产物目录的名字十年没动过。
    """

    daemon = True

    def __init__(self, stage, index, total_stages, target_dir, total,
                 message_code, suffix=None, message_params=None):
        super().__init__()
        self.stage = stage
        self.index = index
        self.total_stages = total_stages
        self.target_dir = target_dir
        self.total = max(int(total), 1)
        # 收的是消息码不是成品中文：这行每 1.5 秒往界面刷一次，
        # 写死中文的话非中文用户整个训练过程都在看中文。
        self.message_code = message_code
        self.message_params = message_params
        self.suffix = suffix
        # 不能叫 _stop：Thread.join 收尾会调 self._stop()，盖成 Event
        # 就是 26.8.15/2 那条 TypeError: 'Event' object is not callable。
        self._halt = threading.Event()
        self._last = -1

    def stop(self):
        self._halt.set()

    def run(self):
        while not self._halt.wait(1.5):
            done = count_files(self.target_dir, self.suffix)
            if done == self._last:
                continue
            self._last = done
            emit(
                phase="stage",
                stage=self.stage,
                index=self.index,
                total_stages=self.total_stages,
                done=min(done, self.total),
                total=self.total,
                **mc.msg_fields(self.message_code, self.message_params),
            )


class TrainLogTail(threading.Thread):
    """训练进度只能从 train.log 里读。

    train.py 的 logger 只挂了 FileHandler，没有 StreamHandler —— 也就是说
    `====> Epoch: 12` 这行**不会**出现在 stdout 上，管道里读不到。所以只能
    盯着文件。
    """

    daemon = True

    def __init__(self, log_path, total_epoch, index, total_stages):
        super().__init__()
        self.log_path = Path(log_path)
        self.total_epoch = max(int(total_epoch), 1)
        self.index = index
        self.total_stages = total_stages
        # 同 StageProgress：不能叫 _stop，见那边的注释。
        self._halt = threading.Event()
        # 从现成日志的末尾开始追。续跑时 train.log 里还躺着上一轮的 epoch 行，
        # 从头扫会把它们全部当成本轮进度重播 —— 界面瞬间冲到 200/200，真实
        # 跑着的第一轮反而看不见，用户看到的就是「进度条卡住」（diag 26.8.20/4
        # 第二、三次训练：205 行进度 3 秒内打完，之后 13 分钟一动不动）。
        self._pos = self.log_path.stat().st_size if self.log_path.is_file() else 0
        self._epoch = 0

    def stop(self):
        self._halt.set()

    def _scan(self):
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._pos)
                chunk = f.read()
                self._pos = f.tell()
        except OSError:
            return
        for line in chunk.splitlines():
            marker = "====> Epoch: "
            at = line.find(marker)
            if at < 0:
                continue
            tail = line[at + len(marker):].strip().split()
            if not tail:
                continue
            try:
                ep = int(tail[0])
            except ValueError:
                continue
            if ep <= self._epoch:
                continue
            self._epoch = ep
            emit(
                phase="stage",
                stage="train",
                index=self.index,
                total_stages=self.total_stages,
                done=min(ep, self.total_epoch),
                total=self.total_epoch,
                **mc.msg_fields(
                    mc.TRAIN_EPOCH, {"epoch": ep, "total": self.total_epoch}
                ),
            )

    def run(self):
        while not self._halt.wait(2.0):
            self._scan()
        self._scan()


# ---------------------------------------------------------------------------
# 子进程
# ---------------------------------------------------------------------------


def spawn(args, log_file, env=None):
    """起一个训练子进程。

    stdout/stderr 全部倒进日志文件而不是管道：这几个脚本会打大量 tqdm 进度，
    走管道既没人读又会在缓冲区满的时候把子进程卡死。
    """
    creation = 0
    if os.name == "nt":
        creation = 0x08000000  # CREATE_NO_WINDOW
    with open(log_file, "a+", encoding="utf-8", errors="replace") as f:
        f.write(
            "\n===== %s %s =====\nargv: %s\n"
            % (
                Path(args[1]).name if len(args) > 1 else "stage",
                time.strftime("%Y-%m-%d %H:%M:%S"),
                " ".join(str(a) for a in args),
            )
        )
        f.flush()
        return subprocess.Popen(
            args,
            cwd=NOW_DIR,
            stdin=subprocess.DEVNULL,
            stdout=f,
            stderr=subprocess.STDOUT,
            creationflags=creation,
            env=env or os.environ.copy(),
        )


def run_stage(args, log_file, watcher=None, env=None,
              stage_code=mc.TRAIN_STEP_FAILED, ok_codes=(0,)):
    p = spawn(args, log_file, env=env)
    try:
        code = p.wait()
    except KeyboardInterrupt:
        p.kill()
        raise
    finally:
        if watcher is not None:
            watcher.stop()
            watcher.join(timeout=3)
    if code not in ok_codes:
        dump_log_tail(log_file)
        fail_code(stage_code, {"code": code, "log": log_file})
    return code


# ---------------------------------------------------------------------------
# 各阶段
# ---------------------------------------------------------------------------


def stage_preprocess(req, exp_dir, py, n_stages):
    dataset = req["dataset"]
    n_files = count_audio(dataset)
    log = exp_dir / "preprocess.log"
    log.write_text("", encoding="utf-8")
    emit(
        phase="stage", stage="preprocess", index=1, total_stages=n_stages,
        done=0, total=max(n_files, 1), **mc.msg_fields(mc.TRAIN_PREPROCESS),
    )
    # 切片会把一条长音频切成多段，产出数量必然多于输入数量。用输入数量当分母
    # 只是个下界，所以上面 emit 的 done 一律 min() 住，不会出现 120%。
    w = StageProgress("preprocess", 1, n_stages, exp_dir / "0_gt_wavs",
                      max(n_files, 1), mc.TRAIN_PREPROCESS)
    w.start()
    run_stage(
        [py, "infer/modules/train/preprocess.py", dataset, str(SR_MAP[req["sample_rate"]]),
         str(req["n_cpu"]), str(exp_dir), "False", "3.7"],
        log, watcher=w, stage_code=mc.TRAIN_PREPROCESS_FAILED,
    )
    emit_checkpoint("preprocess", exp_dir, ROOT, req)
    if count_files(exp_dir / "1_16k_wavs") == 0:
        dump_log_tail(log)
        fail_code(mc.TRAIN_NO_SLICES)
    # 读不了的文件 preprocess 只写进它自己的日志，界面上一个字都看不到。用户
    # 因此可能拿着 2038 个音频、实际只切出 3 条就开训（26.8.20 诊断包），训完
    # 才发现音色不像。数目对不上就明说。
    ok_files = count_preprocess_ok(log)
    if 0 < ok_files < n_files:
        emit(
            phase="skip", stage="preprocess",
            **mc.msg_fields(
                mc.TRAIN_PREPROCESS_PARTIAL,
                {"failed": n_files - ok_files, "total": n_files, "ok": ok_files,
                 "log": log},
            ),
        )


def stage_complete(done, total) -> bool:
    """这一步的产物数目对得上切片数才算做完，半份不算。"""
    return int(total) > 0 and int(done) >= int(total)


def count_preprocess_ok(log):
    """preprocess.log 里成功了几个文件。

    preprocess.py 每处理完一个文件写一行 ``<路径>\t-> Success``，失败的写
    ``<路径>\t-> Traceback...``。数成功的那种最省事，也不用改上游脚本。
    """
    try:
        text = Path(log).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    return sum(1 for line in text.splitlines() if line.rstrip().endswith("-> Success"))


_OOM_MARKERS = ("outofmemoryerror", "out of memory", "显存")


def log_has_oom(log):
    """训练日志尾部是不是显存不足。只看最后 8000 字，前面的属于上一轮。"""
    try:
        text = Path(log).read_text(encoding="utf-8", errors="replace")[-8000:]
    except OSError:
        return False
    low = text.lower()
    return any(m in low for m in _OOM_MARKERS)


def rmvpe_ok(root):
    p = Path(root) / "assets" / "rmvpe" / "rmvpe.pt"
    try:
        return p.is_file() and p.stat().st_size > 1_000_000
    except OSError:
        return False


def stage_f0(req, exp_dir, py, n_stages):
    total = count_files(exp_dir / "1_16k_wavs")
    log = exp_dir / "extract_f0_feature.log"
    method = req["f0_method"]
    if method == "rmvpe" and not rmvpe_ok(NOW_DIR):
        fail_code(mc.TRAIN_RMVPE_MISSING)
    emit(phase="stage", stage="f0", index=2, total_stages=n_stages,
         done=0, total=max(total, 1), **mc.msg_fields(mc.TRAIN_EXTRACT_F0))
    w = StageProgress("f0", 2, n_stages, exp_dir / "2a_f0", max(total, 1),
                      mc.TRAIN_EXTRACT_F0)
    w.start()
    if method == "rmvpe" and req["device"] == "cuda":
        args = [py, "infer/modules/train/extract/extract_f0_rmvpe.py",
                "1", "0", "0", str(exp_dir), str(req["is_half"])]
    elif method == "rmvpe":
        # DirectML / CPU 走单独那份：rmvpe.py 里是写死 cuda 的。
        args = [py, "infer/modules/train/extract/extract_f0_rmvpe_dml.py", str(exp_dir)]
    else:
        args = [py, "infer/modules/train/extract/extract_f0_print.py",
                str(exp_dir), str(req["n_cpu"]), method]
    run_stage(args, log, watcher=w, stage_code=mc.TRAIN_F0_FAILED)
    emit_checkpoint("f0", exp_dir, ROOT, req)
    if count_files(exp_dir / "2a_f0") == 0 or count_files(exp_dir / "2b-f0nsf") == 0:
        dump_log_tail(log)
        fail_code(mc.TRAIN_NO_F0)


def stage_feature(req, exp_dir, py, n_stages):
    total = count_files(exp_dir / "1_16k_wavs")
    log = exp_dir / "extract_f0_feature.log"
    emit(phase="stage", stage="feature", index=3, total_stages=n_stages,
         done=0, total=max(total, 1), **mc.msg_fields(mc.TRAIN_EXTRACT_FEATURE))
    w = StageProgress("feature", 3, n_stages, exp_dir / ("3_feature%d" % FEATURE_DIM),
                      max(total, 1), mc.TRAIN_EXTRACT_FEATURE)
    w.start()
    # 单卡单进程：n_part=1, i_part=0, i_gpu=0。多卡拆分是原版为训练农场做的，
    # 我们的用户是一台家用机，多开只会互相抢显存。
    run_stage(
        [py, "infer/modules/train/extract_feature_print.py", req["device"],
         "1", "0", "0", str(exp_dir), VERSION, str(req["is_half"])],
        log, watcher=w, stage_code=mc.TRAIN_FEATURE_FAILED,
    )
    emit_checkpoint("feature", exp_dir, ROOT, req)
    if count_files(exp_dir / ("3_feature%d" % FEATURE_DIM)) == 0:
        dump_log_tail(log)
        fail_code(mc.TRAIN_NO_FEATURE)


def write_filelist(req, exp_dir, root):
    """拼 filelist.txt。原版 click_train 的前半段。

    末尾要补两条 mute：数据集小的时候 batch 里可能全是有声帧，模型学不到
    「静音该输出什么」，推理时静音段会出噪声。这两条是原版的固定做法。
    """
    gt = exp_dir / "0_gt_wavs"
    feat = exp_dir / ("3_feature%d" % FEATURE_DIM)
    f0d = exp_dir / "2a_f0"
    f0nsf = exp_dir / "2b-f0nsf"
    names = (
        {x.name.split(".")[0] for x in gt.iterdir() if x.is_file()}
        & {x.name.split(".")[0] for x in feat.iterdir() if x.is_file()}
        & {x.name.split(".")[0] for x in f0d.iterdir() if x.is_file()}
        & {x.name.split(".")[0] for x in f0nsf.iterdir() if x.is_file()}
    )
    if not names:
        fail_code(mc.TRAIN_NO_SAMPLES)

    def esc(p):
        return str(p).replace("\\", "\\\\")

    spk = 0
    opt = [
        "%s/%s.wav|%s/%s.npy|%s/%s.wav.npy|%s/%s.wav.npy|%s"
        % (esc(gt), n, esc(feat), n, esc(f0d), n, esc(f0nsf), n, spk)
        for n in sorted(names)
    ]
    mute = root / "logs" / "mute"
    if not (mute / "0_gt_wavs" / ("mute%s.wav" % req["sample_rate"])).is_file():
        fail_code(mc.TRAIN_MUTE_MISSING)
    for _ in range(2):
        opt.append(
            "%s/0_gt_wavs/mute%s.wav|%s/3_feature%d/mute.npy|"
            "%s/2a_f0/mute.wav.npy|%s/2b-f0nsf/mute.wav.npy|%s"
            % (esc(mute), req["sample_rate"], esc(mute), FEATURE_DIM,
               esc(mute), esc(mute), spk)
        )
    import random

    random.shuffle(opt)
    (exp_dir / "filelist.txt").write_text("\n".join(opt), encoding="utf-8")
    return len(opt)


def write_config(req, exp_dir, root):
    sr = req["sample_rate"]
    # v2 没有 40k 的 config，原版在这里回落到 v1 那份。
    rel = "v1/40k.json" if sr == "40k" else "v2/%s.json" % sr
    src = root / "configs" / rel
    if not src.is_file():
        fail_code(mc.TRAIN_CONFIG_MISSING, {"name": rel})
    dst = exp_dir / "config.json"
    if not dst.exists():
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def stage_train(req, exp_dir, py, root, n_stages):
    write_config(req, exp_dir, root)
    n = write_filelist(req, exp_dir, root)
    emit(phase="stage", stage="train", index=4, total_stages=n_stages,
         done=0, total=req["total_epoch"],
         **mc.msg_fields(mc.TRAIN_PREPARING, {"count": n}))

    sr = req["sample_rate"]
    pg = root / "assets" / "pretrained_v2" / ("f0G%s.pth" % sr)
    pd = root / "assets" / "pretrained_v2" / ("f0D%s.pth" % sr)
    if not pg.is_file() or not pd.is_file():
        fail_code(mc.TRAIN_PRETRAINED_MISSING, {"sample_rate": sr})

    log = exp_dir / "train.log"
    tail = TrainLogTail(log, req["total_epoch"], 4, n_stages)
    tail.start()
    args = [
        py, "infer/modules/train/train.py",
        "-e", req["exp"],
        "-sr", sr,
        "-f0", "1",
        "-bs", str(req["batch_size"]),
        "-te", str(req["total_epoch"]),
        "-se", str(req["save_every"]),
        "-pg", str(pg),
        "-pd", str(pd),
        "-l", "1",   # 只留最新的 G/D，不然 200 轮能吃掉几十 GB
        "-c", "0",   # 不缓存数据集进显存：家用卡缓存进去就没地方训练了
        "-sw", "1" if req.get("save_every_weights") else "0",
        "-v", VERSION,
    ]
    # train.py 的 n_gpus 是 torch.cuda.device_count() 数出来的，不看 -g；-g 只
    # 用来设 CUDA_VISIBLE_DEVICES。所以非 N 卡传空串，让它数到 0 卡、走 CPU 分支。
    args += ["-g", "0" if req["device"] == "cuda" else ""]
    (root / "assets" / "weights").mkdir(parents=True, exist_ok=True)
    run_stage(args, log, watcher=tail, stage_code=mc.TRAIN_TRAIN_FAILED,
              ok_codes=(0, TRAIN_PY_DONE))
    emit_checkpoint("train", exp_dir, root, req)


def stage_index(req, exp_dir, py, n_stages):
    """建检索索引。

    这段原版写在 infer-web.py 里且是 gradio generator，没法当脚本调用，所以在
    这里重写一遍 —— 逻辑就是 faiss IVF，几十行，比把 gradio 拖进来划算。

    索引失败不能把已经训好的权重打成失败：没有 index 仍能变声。
    """
    try:
        import numpy as np

        emit(phase="stage", stage="index", index=5, total_stages=n_stages,
             done=0, total=3, **mc.msg_fields(mc.TRAIN_COLLECT_FEATURE))
        feat_dir = exp_dir / ("3_feature%d" % FEATURE_DIM)
        if not feat_dir.is_dir():
            emit(phase="stage", stage="index", index=5, total_stages=n_stages,
                 done=3, total=3, **mc.msg_fields(mc.TRAIN_NO_FEATURE_DIR))
            return None
        names = sorted(x for x in feat_dir.iterdir() if x.is_file() and x.suffix == ".npy")
        if not names:
            emit(phase="stage", stage="index", index=5, total_stages=n_stages,
                 done=3, total=3, **mc.msg_fields(mc.TRAIN_NO_FEATURE_FILE))
            return None
        big = np.concatenate([np.load(str(x)) for x in names], 0)
        idx = np.arange(big.shape[0])
        np.random.shuffle(idx)
        big = big[idx]

        if big.shape[0] > 2e5:
            emit(phase="stage", stage="index", index=5, total_stages=n_stages,
                 done=1, total=3, **mc.msg_fields(mc.TRAIN_KMEANS))
            try:
                from sklearn.cluster import MiniBatchKMeans

                big = (
                    MiniBatchKMeans(
                        n_clusters=10000,
                        verbose=False,
                        batch_size=256 * max(req["n_cpu"], 1),
                        compute_labels=False,
                        init="random",
                    )
                    .fit(big)
                    .cluster_centers_
                )
            except Exception as e:  # 聚类失败不该让整次训练白跑
                emit(phase="stage", stage="index", index=5, total_stages=n_stages,
                     done=1, total=3,
                     **mc.msg_fields(mc.TRAIN_KMEANS_FAILED, {"error": e}))

        import faiss

        np.save(str(exp_dir / "total_fea.npy"), big)
        n_ivf = min(int(16 * np.sqrt(big.shape[0])), big.shape[0] // 39)
        n_ivf = max(n_ivf, 1)
        emit(phase="stage", stage="index", index=5, total_stages=n_stages,
             done=2, total=3,
             **mc.msg_fields(mc.TRAIN_BUILD_INDEX, {"count": big.shape[0]}))
        index = faiss.index_factory(FEATURE_DIM, "IVF%s,Flat" % n_ivf)
        ivf = faiss.extract_index_ivf(index)
        ivf.nprobe = 1
        index.train(big)
        for i in range(0, big.shape[0], 8192):
            index.add(big[i: i + 8192])
        out = exp_dir / ("added_IVF%s_Flat_nprobe_%s_%s_%s.index"
                         % (n_ivf, ivf.nprobe, req["exp"], VERSION))
        faiss.write_index(index, str(out))
        emit(phase="stage", stage="index", index=5, total_stages=n_stages,
             done=3, total=3, **mc.msg_fields(mc.TRAIN_INDEX_DONE))
        return out
    except Exception as e:
        emit(phase="stage", stage="index", index=5, total_stages=n_stages,
             done=3, total=3,
             **mc.msg_fields(mc.TRAIN_INDEX_FAILED, {"error": e}))
        return None


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def normalize(raw):
    exp = str(raw.get("exp") or "").strip()
    if not exp or any(c in exp for c in '\\/:*?"<>|'):
        fail_code(mc.TRAIN_NAME_INVALID)
    sr = str(raw.get("sample_rate") or "48k")
    if sr not in SR_MAP:
        fail_code(mc.TRAIN_BAD_SAMPLE_RATE, {"sample_rate": sr})
    device = str(raw.get("device") or "cuda")
    method = str(raw.get("f0_method") or "rmvpe")
    if method not in ("rmvpe", "harvest", "pm", "dio"):
        fail_code(mc.TRAIN_BAD_F0_METHOD, {"method": method})
    def num(key, default):
        """缺省用 default，写了但不合理就夹到 1。

        不能写成 `int(raw.get(k) or default)` —— 0 是假值，会被悄悄换成默认值。
        用户填了 0 轮，我们给他跑 200 轮，那是两回事。
        """
        v = raw.get(key)
        if v is None or v == "":
            return default
        try:
            return max(int(v), 1)
        except (TypeError, ValueError):
            return default

    return {
        "exp": exp,
        "dataset": str(raw.get("dataset") or ""),
        "sample_rate": sr,
        "total_epoch": num("total_epoch", 200),
        "save_every": num("save_every", 25),
        "batch_size": num("batch_size", 8),
        "n_cpu": num("n_cpu", os.cpu_count() or 4),
        "f0_method": method,
        "device": device,
        "is_half": bool(raw.get("is_half", device == "cuda")),
        "resume": bool(raw.get("resume", False)),
        "save_every_weights": bool(raw.get("save_every_weights", False)),
        # 空 = 老行为（放 User_Data/models）。合法性由壳那边判过了，这里不再
        # 二次校验：worker 是被壳启动的，不是用户直接调的。
        "output_dir": str(raw.get("output_dir") or "").strip(),
    }


def main():
    if len(sys.argv) < 2:
        fail_code(mc.TRAIN_USAGE)
    try:
        raw = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except Exception as e:
        fail_code(mc.TRAIN_BAD_REQUEST, {"error": e})
    req = normalize(raw)

    root = Path(NOW_DIR)
    exp_dir = root / "logs" / req["exp"]
    exp_dir.mkdir(parents=True, exist_ok=True)
    (root / "assets" / "weights").mkdir(parents=True, exist_ok=True)
    py = sys.executable

    n_stages = len(STAGES)
    emit(phase="start", exp=req["exp"], total_stages=n_stages,
         **mc.msg_fields(mc.TRAIN_STARTED, {"exp": req["exp"]}))
    emit(
        phase="env",
        python=sys.version.split()[0],
        executable=sys.executable,
        cwd=os.getcwd(),
        device=req["device"],
        is_half=req["is_half"],
        n_cpu=req["n_cpu"],
        dataset_audio=count_audio(req["dataset"]) if req["dataset"] else 0,
    )

    # 续跑：已经有产物的前几步直接跳过。判据是产物**数目对得上切片数** —— 比记
    # 状态文件可靠（用户手动删过目录也能自愈），也比「目录非空」老实。
    #
    # 只看非空会漏掉半份产物：上一次在音高或特征中途被取消，目录里留着一部分，
    # 续跑就整步跳过。filelist 取的是四类产物的交集，于是训练悄悄只用了那一部分
    # 数据，界面上没有任何提示。26.8.20 的诊断包里就是这样：3884 条切片只有 616
    # 条音高，最后按 618 条样本训完，用户以为整份数据集都在训。
    #
    # 补齐很便宜：两个提取脚本都会跳过已经存在的输出文件，重跑只做缺的那些。
    n_slices = count_files(exp_dir / "1_16k_wavs")
    n_f0 = count_files(exp_dir / "2a_f0")
    n_feat = count_files(exp_dir / ("3_feature%d" % FEATURE_DIM))
    have_slices = n_slices > 0
    have_f0 = stage_complete(n_f0, n_slices)
    have_feat = stage_complete(n_feat, n_slices)
    resume = bool(req["resume"] and have_slices)
    emit_checkpoint("start", exp_dir, root, req)

    if resume:
        stored = infer_sr(exp_dir)
        if stored and stored != req["sample_rate"]:
            emit(
                phase="skip",
                stage="preprocess",
                **mc.msg_fields(
                    mc.TRAIN_REUSE_SR,
                    {"actual": stored, "picked": req["sample_rate"]},
                ),
            )
        if stored:
            req["sample_rate"] = stored
    else:
        if have_slices:
            wipe_stage_dirs(exp_dir)
            have_f0 = False
            have_feat = False
        write_meta(exp_dir, req)

    try:
        if resume and have_slices:
            emit(phase="skip", stage="preprocess",
                 **mc.msg_fields(mc.TRAIN_SKIP_PREPROCESS))
            emit_checkpoint("preprocess", exp_dir, root, req)
        else:
            if not Path(req["dataset"]).is_dir():
                fail_code(mc.TRAIN_DATASET_MISSING, {"path": req["dataset"]})
            stage_preprocess(req, exp_dir, py, n_stages)

        if resume and have_f0:
            emit(phase="skip", stage="f0", **mc.msg_fields(mc.TRAIN_SKIP_F0))
            emit_checkpoint("f0", exp_dir, root, req)
        else:
            if resume and 0 < n_f0 < n_slices:
                emit(
                    phase="skip", stage="f0",
                    **mc.msg_fields(
                        mc.TRAIN_RESUME_F0_PARTIAL, {"done": n_f0, "total": n_slices}
                    ),
                )
            stage_f0(req, exp_dir, py, n_stages)

        if resume and have_feat:
            emit(phase="skip", stage="feature", **mc.msg_fields(mc.TRAIN_SKIP_FEATURE))
            emit_checkpoint("feature", exp_dir, root, req)
        else:
            if resume and 0 < n_feat < n_slices:
                emit(
                    phase="skip", stage="feature",
                    **mc.msg_fields(
                        mc.TRAIN_RESUME_FEATURE_PARTIAL,
                        {"done": n_feat, "total": n_slices},
                    ),
                )
            stage_feature(req, exp_dir, py, n_stages)

        stage_train(req, exp_dir, py, root, n_stages)
        index_path = stage_index(req, exp_dir, py, n_stages)
        emit_checkpoint("index", exp_dir, root, req)
    except KeyboardInterrupt:
        emit_checkpoint("interrupted", exp_dir, root, req)
        emit(phase="error", **mc.msg_fields(mc.TRAIN_CANCELLED))
        sys.exit(2)

    weights = root / "assets" / "weights" / ("%s.pth" % req["exp"])
    if not weights.is_file():
        emit_checkpoint("missing_weights", exp_dir, root, req)
        train_log = exp_dir / "train.log"
        dump_log_tail(train_log)
        # 「训练结束但没找到 xxx.pth」对用户没有任何指向。显存不够是这里最常见
        # 的死法（26.8.20 诊断包连着三次），日志里认得出来就直说。
        if log_has_oom(train_log):
            fail_code(
                mc.TRAIN_OOM,
                {"batch": req.get("batch_size"), "log": train_log},
            )
        fail_code(mc.TRAIN_NO_WEIGHT, {"name": weights, "exp": req["exp"]})
    published = publish_voice(root, req, weights, index_path)
    snap = emit_checkpoint("done", exp_dir, root, req)
    msg = "训练完成" if index_path else "训练完成（索引没建成，音色仍可用）"
    emit(phase="done", weights=str(published or weights),
         index=str(index_path) if index_path else "",
         usable=snap["usable"],
         message=msg)


if __name__ == "__main__":
    main()
