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
import wave
from pathlib import Path

# 产品根：Rust 会把 cwd 设成这里，但脚本自己也认，免得有人从别处起。
ROOT = Path(__file__).resolve().parent.parent
NOW_DIR = str(ROOT)
if os.getcwd() != NOW_DIR:
    os.chdir(NOW_DIR)
if NOW_DIR not in sys.path:
    sys.path.insert(0, NOW_DIR)

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
    emit(phase="error", message=str(message))
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
    """把训好的 pth/index 装进 User_Data/models，模型页能直接「使用」。

    savee 只写 assets/weights。那边会被当成旧版单文件音色，没有检索库。
    复制一份进用户音色库，并写 sidecar。
    """
    dest = root / "User_Data" / "models" / req["exp"]
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

    def __init__(self, stage, index, total_stages, target_dir, total, message, suffix=None):
        super().__init__()
        self.stage = stage
        self.index = index
        self.total_stages = total_stages
        self.target_dir = target_dir
        self.total = max(int(total), 1)
        self.message = message
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
                message=self.message,
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
        self._pos = 0
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
                message="第 %d / %d 轮" % (ep, self.total_epoch),
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
        return subprocess.Popen(
            args,
            cwd=NOW_DIR,
            stdin=subprocess.DEVNULL,
            stdout=f,
            stderr=subprocess.STDOUT,
            creationflags=creation,
            env=env or os.environ.copy(),
        )


def run_stage(args, log_file, watcher=None, env=None, what="", ok_codes=(0,)):
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
        fail("%s失败（退出码 %s），详情见 %s" % (what or "该步骤", code, log_file))
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
        done=0, total=max(n_files, 1), message="切片与重采样…",
    )
    # 切片会把一条长音频切成多段，产出数量必然多于输入数量。用输入数量当分母
    # 只是个下界，所以上面 emit 的 done 一律 min() 住，不会出现 120%。
    w = StageProgress("preprocess", 1, n_stages, exp_dir / "0_gt_wavs",
                      max(n_files, 1), "切片与重采样…")
    w.start()
    run_stage(
        [py, "infer/modules/train/preprocess.py", dataset, str(SR_MAP[req["sample_rate"]]),
         str(req["n_cpu"]), str(exp_dir), "False", "3.7"],
        log, watcher=w, what="数据预处理",
    )
    if count_files(exp_dir / "1_16k_wavs") == 0:
        fail("预处理没有产出任何切片。检查数据集里是不是没有可读的音频文件。")


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
        fail("缺少 assets/rmvpe/rmvpe.pt，请先补全引擎资源。")
    emit(phase="stage", stage="f0", index=2, total_stages=n_stages,
         done=0, total=max(total, 1), message="提取音高…")
    w = StageProgress("f0", 2, n_stages, exp_dir / "2a_f0", max(total, 1), "提取音高…")
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
    run_stage(args, log, watcher=w, what="音高提取")
    if count_files(exp_dir / "2a_f0") == 0 or count_files(exp_dir / "2b-f0nsf") == 0:
        fail("音高提取没有产出。换一种音高算法再试。")


def stage_feature(req, exp_dir, py, n_stages):
    total = count_files(exp_dir / "1_16k_wavs")
    log = exp_dir / "extract_f0_feature.log"
    emit(phase="stage", stage="feature", index=3, total_stages=n_stages,
         done=0, total=max(total, 1), message="提取音色特征…")
    w = StageProgress("feature", 3, n_stages, exp_dir / ("3_feature%d" % FEATURE_DIM),
                      max(total, 1), "提取音色特征…")
    w.start()
    # 单卡单进程：n_part=1, i_part=0, i_gpu=0。多卡拆分是原版为训练农场做的，
    # 我们的用户是一台家用机，多开只会互相抢显存。
    run_stage(
        [py, "infer/modules/train/extract_feature_print.py", req["device"],
         "1", "0", "0", str(exp_dir), VERSION, str(req["is_half"])],
        log, watcher=w, what="特征提取",
    )
    if count_files(exp_dir / ("3_feature%d" % FEATURE_DIM)) == 0:
        fail("特征提取没有产出。多半是 assets/hubert/hubert_base.pt 缺失或损坏。")


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
        fail("四类产物对不上号，没有一条可用的训练样本。建议清掉实验重来。")

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
        fail("缺少 logs/mute 静音样本，安装不完整。")
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
        fail("缺少 configs/%s" % rel)
    dst = exp_dir / "config.json"
    if not dst.exists():
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def stage_train(req, exp_dir, py, root, n_stages):
    write_config(req, exp_dir, root)
    n = write_filelist(req, exp_dir, root)
    emit(phase="stage", stage="train", index=4, total_stages=n_stages,
         done=0, total=req["total_epoch"],
         message="准备训练（%d 条样本）…" % n)

    sr = req["sample_rate"]
    pg = root / "assets" / "pretrained_v2" / ("f0G%s.pth" % sr)
    pd = root / "assets" / "pretrained_v2" / ("f0D%s.pth" % sr)
    if not pg.is_file() or not pd.is_file():
        fail("缺少 %s 的底模（assets/pretrained_v2/f0G%s.pth）。不用底模从零训练"
             "需要几十小时和上百小时素材，不是这个界面的用法。" % (sr, sr))

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
    run_stage(args, log, watcher=tail, what="训练", ok_codes=(0, TRAIN_PY_DONE))


def stage_index(req, exp_dir, py, n_stages):
    """建检索索引。

    这段原版写在 infer-web.py 里且是 gradio generator，没法当脚本调用，所以在
    这里重写一遍 —— 逻辑就是 faiss IVF，几十行，比把 gradio 拖进来划算。

    索引失败不能把已经训好的权重打成失败：没有 index 仍能变声。
    """
    try:
        import numpy as np

        emit(phase="stage", stage="index", index=5, total_stages=n_stages,
             done=0, total=3, message="收集特征…")
        feat_dir = exp_dir / ("3_feature%d" % FEATURE_DIM)
        if not feat_dir.is_dir():
            emit(phase="stage", stage="index", index=5, total_stages=n_stages,
                 done=3, total=3, message="没有特征目录，跳过索引")
            return None
        names = sorted(x for x in feat_dir.iterdir() if x.is_file() and x.suffix == ".npy")
        if not names:
            emit(phase="stage", stage="index", index=5, total_stages=n_stages,
                 done=3, total=3, message="没有特征文件，跳过索引")
            return None
        big = np.concatenate([np.load(str(x)) for x in names], 0)
        idx = np.arange(big.shape[0])
        np.random.shuffle(idx)
        big = big[idx]

        if big.shape[0] > 2e5:
            emit(phase="stage", stage="index", index=5, total_stages=n_stages,
                 done=1, total=3, message="特征过多，先聚类到 1 万个中心…")
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
                     done=1, total=3, message="聚类失败，改用全量特征：%s" % e)

        import faiss

        np.save(str(exp_dir / "total_fea.npy"), big)
        n_ivf = min(int(16 * np.sqrt(big.shape[0])), big.shape[0] // 39)
        n_ivf = max(n_ivf, 1)
        emit(phase="stage", stage="index", index=5, total_stages=n_stages,
             done=2, total=3, message="训练索引（%d 条特征）…" % big.shape[0])
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
             done=3, total=3, message="索引完成")
        return out
    except Exception as e:
        emit(phase="stage", stage="index", index=5, total_stages=n_stages,
             done=3, total=3,
             message="索引没建成（%s）。音色已经训好，仍可使用。" % e)
        return None


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def normalize(raw):
    exp = str(raw.get("exp") or "").strip()
    if not exp or any(c in exp for c in '\\/:*?"<>|'):
        fail("音色名不能为空，也不能含 \\ / : * ? \" < > | 这些字符")
    sr = str(raw.get("sample_rate") or "48k")
    if sr not in SR_MAP:
        fail("不支持的采样率：%s" % sr)
    device = str(raw.get("device") or "cuda")
    method = str(raw.get("f0_method") or "rmvpe")
    if method not in ("rmvpe", "harvest", "pm", "dio"):
        fail("不支持的音高算法：%s" % method)
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
    }


def main():
    if len(sys.argv) < 2:
        fail("用法：train_worker.py <request.json>")
    try:
        raw = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except Exception as e:
        fail("读不了请求文件：%s" % e)
    req = normalize(raw)

    root = Path(NOW_DIR)
    exp_dir = root / "logs" / req["exp"]
    exp_dir.mkdir(parents=True, exist_ok=True)
    (root / "assets" / "weights").mkdir(parents=True, exist_ok=True)
    py = sys.executable

    n_stages = len(STAGES)
    emit(phase="start", exp=req["exp"], total_stages=n_stages,
         message="开始训练 %s" % req["exp"])

    # 续跑：已经有产物的前几步直接跳过。判据是产物目录非空 —— 比记状态文件
    # 可靠，用户手动删过目录也能自愈。
    have_slices = count_files(exp_dir / "1_16k_wavs") > 0
    have_f0 = count_files(exp_dir / "2a_f0") > 0
    have_feat = count_files(exp_dir / ("3_feature%d" % FEATURE_DIM)) > 0
    resume = bool(req["resume"] and have_slices)

    if resume:
        stored = infer_sr(exp_dir)
        if stored and stored != req["sample_rate"]:
            emit(
                phase="skip",
                stage="preprocess",
                message="沿用已有切片的采样率 %s（这次选的是 %s）" % (stored, req["sample_rate"]),
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
            emit(phase="skip", stage="preprocess", message="已有切片，跳过预处理")
        else:
            if not Path(req["dataset"]).is_dir():
                fail("数据集目录不存在：%s" % req["dataset"])
            stage_preprocess(req, exp_dir, py, n_stages)

        if resume and have_f0:
            emit(phase="skip", stage="f0", message="已有音高，跳过")
        else:
            stage_f0(req, exp_dir, py, n_stages)

        if resume and have_feat:
            emit(phase="skip", stage="feature", message="已有特征，跳过")
        else:
            stage_feature(req, exp_dir, py, n_stages)

        stage_train(req, exp_dir, py, root, n_stages)
        index_path = stage_index(req, exp_dir, py, n_stages)
    except KeyboardInterrupt:
        emit(phase="error", message="已取消")
        sys.exit(2)

    weights = root / "assets" / "weights" / ("%s.pth" % req["exp"])
    if not weights.is_file():
        fail("训练结束但没找到 %s。查看 logs/%s/train.log。" % (weights, req["exp"]))
    published = publish_voice(root, req, weights, index_path)
    msg = "训练完成" if index_path else "训练完成（索引没建成，音色仍可用）"
    emit(phase="done", weights=str(published or weights),
         index=str(index_path) if index_path else "",
         message=msg)


if __name__ == "__main__":
    main()
