import multiprocessing
import os
import sys
import traceback

from scipy import signal

now_dir = os.getcwd()
sys.path.append(now_dir)

import librosa
import numpy as np
from scipy.io import wavfile

from infer.lib.audio import load_audio
from infer.lib.slicer2 import Slicer

# 跟 train_worker.AUDIO_EXT 保持一致：子目录里的歌也要扫到。
_AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"}

_log = None


def println(strr):
    print(strr)
    if _log is None:
        return
    try:
        _log.write("%s\n" % strr)
        _log.flush()
    except Exception:
        pass


def iter_audio(inp_root):
    """递归收集音频。只扫文件、不把子目录当输入（旧 listdir 会把文件夹喂给 load_audio）。"""
    infos = []
    idx = 0
    for dirpath, _dirs, files in os.walk(inp_root):
        for name in sorted(files):
            ext = os.path.splitext(name)[1].lower()
            if ext not in _AUDIO_EXT:
                continue
            infos.append((os.path.join(dirpath, name), idx))
            idx += 1
    return infos


class PreProcess:
    def __init__(self, sr, exp_dir, per=3.7):
        self.slicer = Slicer(
            sr=sr,
            threshold=-42,
            min_length=1500,
            min_interval=400,
            hop_size=15,
            max_sil_kept=500,
        )
        self.sr = sr
        self.bh, self.ah = signal.butter(N=5, Wn=48, btype="high", fs=self.sr)
        self.per = per
        self.overlap = 0.3
        self.tail = self.per + self.overlap
        self.max = 0.9
        self.alpha = 0.75
        self.exp_dir = exp_dir
        self.gt_wavs_dir = "%s/0_gt_wavs" % exp_dir
        self.wavs16k_dir = "%s/1_16k_wavs" % exp_dir
        os.makedirs(self.exp_dir, exist_ok=True)
        os.makedirs(self.gt_wavs_dir, exist_ok=True)
        os.makedirs(self.wavs16k_dir, exist_ok=True)

    def norm_write(self, tmp_audio, idx0, idx1):
        tmp_max = np.abs(tmp_audio).max()
        if tmp_max > 2.5:
            print("%s-%s-%s-filtered" % (idx0, idx1, tmp_max))
            return
        tmp_audio = (tmp_audio / tmp_max * (self.max * self.alpha)) + (
            1 - self.alpha
        ) * tmp_audio
        wavfile.write(
            "%s/%s_%s.wav" % (self.gt_wavs_dir, idx0, idx1),
            self.sr,
            tmp_audio.astype(np.float32),
        )
        tmp_audio = librosa.resample(
            tmp_audio, orig_sr=self.sr, target_sr=16000
        )  # , res_type="soxr_vhq"
        wavfile.write(
            "%s/%s_%s.wav" % (self.wavs16k_dir, idx0, idx1),
            16000,
            tmp_audio.astype(np.float32),
        )

    def pipeline(self, path, idx0):
        try:
            audio = load_audio(path, self.sr)
            # zero phased digital filter cause pre-ringing noise...
            # audio = signal.filtfilt(self.bh, self.ah, audio)
            audio = signal.lfilter(self.bh, self.ah, audio)

            idx1 = 0
            for audio in self.slicer.slice(audio):
                i = 0
                while 1:
                    start = int(self.sr * (self.per - self.overlap) * i)
                    i += 1
                    if len(audio[start:]) > self.tail * self.sr:
                        tmp_audio = audio[start : start + int(self.per * self.sr)]
                        self.norm_write(tmp_audio, idx0, idx1)
                        idx1 += 1
                    else:
                        tmp_audio = audio[start:]
                        idx1 += 1
                        break
                self.norm_write(tmp_audio, idx0, idx1)
            println("%s\t-> Success" % path)
        except:
            println("%s\t-> %s" % (path, traceback.format_exc()))

    def pipeline_mp(self, infos):
        for path, idx0 in infos:
            self.pipeline(path, idx0)

    def pipeline_mp_inp_dir(self, inp_root, n_p, noparallel=False):
        try:
            infos = iter_audio(inp_root)
            if not infos:
                println("no-audio-in-%s" % inp_root)
                return
            if noparallel:
                for i in range(n_p):
                    self.pipeline_mp(infos[i::n_p])
            else:
                ps = []
                for i in range(n_p):
                    p = multiprocessing.Process(
                        target=self.pipeline_mp, args=(infos[i::n_p],)
                    )
                    ps.append(p)
                    p.start()
                for i in range(n_p):
                    ps[i].join()
        except:
            println("Fail. %s" % traceback.format_exc())


def preprocess_trainset(inp_root, sr, n_p, exp_dir, per, noparallel=False):
    global _log
    os.makedirs(exp_dir, exist_ok=True)
    _log = open(
        os.path.join(exp_dir, "preprocess.log"),
        "a+",
        encoding="utf-8",
        errors="replace",
    )
    try:
        pp = PreProcess(sr, exp_dir, per)
        println("start preprocess")
        pp.pipeline_mp_inp_dir(inp_root, n_p, noparallel=noparallel)
        println("end preprocess")
    finally:
        try:
            _log.close()
        except Exception:
            pass
        _log = None


if __name__ == "__main__":
    # argv 只能在这里读。Windows 下 multiprocessing 用 spawn 会重新 import
    # 本模块，子进程的 sys.argv 是 `-c from multiprocessing.spawn…`，
    # 放在模块顶层会把子进程直接砸死，切片数为 0。
    print(*sys.argv[1:])
    inp_root = sys.argv[1]
    sr = int(sys.argv[2])
    n_p = int(sys.argv[3])
    exp_dir = sys.argv[4]
    noparallel = sys.argv[5] == "True"
    per = float(sys.argv[6])
    preprocess_trainset(inp_root, sr, n_p, exp_dir, per, noparallel=noparallel)
