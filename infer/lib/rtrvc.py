from io import BytesIO
import os
import sys
import traceback
from infer.lib import jit
from infer.lib.jit.get_synthesizer import get_synthesizer
from time import time as ttime
import fairseq
from infer.lib import dml_compat
from infer.lib.faiss_io import NonAsciiPathError, read_index, require_ascii_path
import numpy as np
import parselmouth
import pyworld
import scipy.signal as signal
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchcrepe
from torchaudio.transforms import Resample

from tools.cuda_graph import configure_cuda_graph, run_cuda_graph

now_dir = os.getcwd()
sys.path.append(now_dir)
from multiprocessing import Manager as M

from configs.config import Config

# config = Config()

# Lazy Manager — import-time Manager() spawns a Windows child process.
# Only harvest multi-cpu path needs the shared dict.
_mm = None


def _shared_mm():
    global _mm
    if _mm is None:
        try:
            from tools.worker_protocol import force_windowed_multiprocessing

            force_windowed_multiprocessing()
        except Exception:
            pass
        _mm = M()
    return _mm


def printt(strr, *args):
    if len(args) == 0:
        print(strr)
    else:
        print(strr % args)


# config.device=torch.device("cpu")########强制cpu测试
# config.is_half=False########强制cpu测试
class RVC:
    def __init__(
        self,
        key,
        formant,
        pth_path,
        index_path,
        index_rate,
        n_cpu,
        inp_q,
        opt_q,
        config: Config,
        last_rvc=None,
        on_progress=None,
    ) -> None:
        """
        初始化
        """
        def _progress(code: str, pct: int) -> None:
            if on_progress is None:
                return
            try:
                on_progress(code, pct)
            except Exception:
                pass

        try:
            # DirectML 上 fairseq 的 GradMultiply 会抛 PrivateUse1，补丁收在
            # infer/lib/dml_compat 里，实时 / 离线 / 训练三条路共用一份。
            dml_compat.apply_for(config)
            # global config
            self.config = config
            self.inp_q = inp_q
            self.opt_q = opt_q
            # device="cpu"########强制cpu测试
            self.device = config.device
            # 探测 CUDA Graph 可用性。gui_v1 会先按用户设置把 RVC_CUDA_GRAPH
            # 置 0/1；置 0 时这里直接返回，run_cuda_graph 退化成普通调用。
            # 非 N 卡（DirectML / CPU）恒为关，探测本身也不会跑。
            try:
                on = configure_cuda_graph(self.device)
                printt("cuda graph: %s", "启用" if on else "关闭")
            except Exception:
                traceback.print_exc()
            self.f0_up_key = key
            self.formant_shift = formant
            # 加载失败时 except 会吞掉异常。先给上这两个，调用方用
            # getattr(rvc, "tgt_sr", 0) 就能认出半截实例，不会 AttributeError
            # （diag 26.8.16：空 pth 留下没 tgt_sr 的 RVC，开启变声全军覆没）。
            self.tgt_sr = 0
            self.net_g = None
            self.f0_min = 50
            self.f0_max = 1100
            self.f0_mel_min = 1127 * np.log(1 + self.f0_min / 700)
            self.f0_mel_max = 1127 * np.log(1 + self.f0_max / 700)
            self.n_cpu = n_cpu
            self.use_jit = self.config.use_jit
            self.is_half = config.is_half

            # Realtime shapes are fixed per stream: let cudnn autotune conv kernels,
            # and allow TF32 so any fp32 matmul path keeps tensor-core speed.
            if "cuda" in str(self.device):
                try:
                    torch.backends.cudnn.benchmark = True
                    torch.backends.cuda.matmul.allow_tf32 = True
                    torch.backends.cudnn.allow_tf32 = True
                except Exception:
                    pass

            # 中文路径 faiss 读不了，必须让用户换目录，不能静默丢掉检索库。
            require_ascii_path(pth_path)
            require_ascii_path(index_path)
            # Missing / wrong index must not kill the process (common for catalog models)
            if index_rate != 0 and index_path and os.path.isfile(index_path):
                _progress("vc.loading_index", 32)
                try:
                    self.index = read_index(index_path)
                    self.big_npy = self.index.reconstruct_n(0, self.index.ntotal)
                    printt("Index search enabled")
                    self._init_index_bank()
                except NonAsciiPathError:
                    raise
                except Exception as e:
                    printt("Index load failed, continue without index: %s", e)
                    index_rate = 0
            elif index_rate != 0:
                printt("Index file missing, continue without index: %s", index_path)
                index_rate = 0
            self.pth_path: str = pth_path
            self.index_path = index_path
            self.index_rate = index_rate
            self.cache_pitch: torch.Tensor = torch.zeros(
                1024, device=self.device, dtype=torch.long
            )
            self.cache_pitchf = torch.zeros(
                1024, device=self.device, dtype=torch.float32
            )

            self.resample_kernel = {}

            if last_rvc is None:
                _progress("vc.loading_hubert", 42)
                models, _, _ = fairseq.checkpoint_utils.load_model_ensemble_and_task(
                    ["assets/hubert/hubert_base.pt"],
                    suffix="",
                )
                hubert_model = models[0]
                hubert_model = hubert_model.to(self.device)
                if self.is_half:
                    hubert_model = hubert_model.half()
                else:
                    hubert_model = hubert_model.float()
                hubert_model.eval()
                self.model = hubert_model
            else:
                self.model = last_rvc.model

            self.net_g: nn.Module = None

            def set_default_model():
                self.net_g, cpt = get_synthesizer(self.pth_path, self.device)
                self.tgt_sr = cpt["config"][-1]
                cpt["config"][-3] = cpt["weight"]["emb_g.weight"].shape[0]
                self.if_f0 = cpt.get("f0", 1)
                self.version = cpt.get("version", "v1")
                if self.is_half:
                    self.net_g = self.net_g.half()
                else:
                    self.net_g = self.net_g.float()

            def set_jit_model():
                jit_pth_path = self.pth_path.rstrip(".pth")
                jit_pth_path += ".half.jit" if self.is_half else ".jit"
                reload = False
                if str(self.device) == "cuda":
                    self.device = torch.device("cuda:0")
                if os.path.exists(jit_pth_path):
                    cpt = jit.load(jit_pth_path)
                    model_device = cpt["device"]
                    if model_device != str(self.device):
                        reload = True
                else:
                    reload = True

                if reload:
                    cpt = jit.synthesizer_jit_export(
                        self.pth_path,
                        "script",
                        None,
                        device=self.device,
                        is_half=self.is_half,
                    )

                self.tgt_sr = cpt["config"][-1]
                self.if_f0 = cpt.get("f0", 1)
                self.version = cpt.get("version", "v1")
                self.net_g = torch.jit.load(
                    BytesIO(cpt["model"]), map_location=self.device
                )
                self.net_g.infer = self.net_g.forward
                self.net_g.eval().to(self.device)

            def set_synthesizer():
                if self.use_jit and not config.dml:
                    if self.is_half and "cpu" in str(self.device):
                        printt(
                            "Use default Synthesizer model. \
                                    Jit is not supported on the CPU for half floating point"
                        )
                        set_default_model()
                    else:
                        set_jit_model()
                else:
                    set_default_model()

            if last_rvc is None or last_rvc.pth_path != self.pth_path:
                _progress("vc.loading_net", 58)
                set_synthesizer()
            else:
                prev_sr = int(getattr(last_rvc, "tgt_sr", 0) or 0)
                if not prev_sr:
                    _progress("vc.loading_net", 58)
                    set_synthesizer()
                else:
                    self.tgt_sr = prev_sr
                    self.if_f0 = getattr(last_rvc, "if_f0", 1)
                    self.version = getattr(last_rvc, "version", "v1")
                    self.is_half = last_rvc.is_half
                    if last_rvc.use_jit != self.use_jit:
                        set_synthesizer()
                    else:
                        self.net_g = last_rvc.net_g

            if last_rvc is not None and hasattr(last_rvc, "model_rmvpe"):
                self.model_rmvpe = last_rvc.model_rmvpe
            if last_rvc is not None and hasattr(last_rvc, "model_fcpe"):
                self.device_fcpe = last_rvc.device_fcpe
                self.model_fcpe = last_rvc.model_fcpe
        except NonAsciiPathError:
            raise
        except:
            printt(traceback.format_exc())

    def change_key(self, new_key):
        self.f0_up_key = new_key

    def change_formant(self, new_formant):
        self.formant_shift = new_formant

    def change_index_rate(self, new_index_rate):
        if new_index_rate != 0 and self.index_rate == 0:
            if self.index_path and os.path.isfile(self.index_path):
                try:
                    self.index = read_index(self.index_path)
                    self.big_npy = self.index.reconstruct_n(0, self.index.ntotal)
                    printt("Index search enabled")
                    self._init_index_bank()
                except NonAsciiPathError:
                    raise
                except Exception as e:
                    printt("Index load failed: %s", e)
                    new_index_rate = 0
            else:
                printt("Index file missing: %s", self.index_path)
                new_index_rate = 0
        self.index_rate = new_index_rate

    # Block geometry is fixed while a stream runs, so the small control tensors
    # passed to hubert / net_g are identical every block — rebuilding them costs
    # allocations + host-to-device copies on the hot path.
    def _padding_mask_for(self, shape):
        mask = getattr(self, "_padding_mask", None)
        if mask is None or tuple(mask.shape) != tuple(shape):
            mask = torch.zeros(tuple(shape), dtype=torch.bool, device=self.device)
            self._padding_mask = mask
        return mask

    def _long_dev(self, value):
        cache = getattr(self, "_long_dev_cache", None)
        if cache is None:
            cache = self._long_dev_cache = {}
        t = cache.get(value)
        if t is None:
            t = cache[value] = torch.LongTensor([value]).to(self.device)
        return t

    def _long_cpu(self, value):
        cache = getattr(self, "_long_cpu_cache", None)
        if cache is None:
            cache = self._long_cpu_cache = {}
        t = cache.get(value)
        if t is None:
            t = cache[value] = torch.LongTensor([value])
        return t

    # Exact top-8 retrieval on the GPU replaces the per-block CPU faiss search:
    # it removes a forced GPU→CPU sync every block, and exact search is at least
    # as accurate as the IVF approximation faiss uses. CPU faiss remains the
    # fallback (dml / cpu devices, oversized banks, or TM_INDEX_GPU=0).
    def _init_index_bank(self):
        self._index_bank = None
        self._index_bank_sq = None
        big = getattr(self, "big_npy", None)
        if big is None or getattr(big, "ndim", 0) != 2:
            return
        if "cuda" not in str(self.device):
            return
        if os.environ.get("TM_INDEX_GPU", "1") == "0":
            return
        # Match the model dtype: fp16 halves memory + matches feats on half-precision
        # cards; fp32 keeps full accuracy and avoids Pascal's crippled fp16 matmul
        # on cards forced to fp32 (e.g. GTX 10xx).
        bank_dtype = torch.float16 if self.is_half else torch.float32
        itemsize = 2 if self.is_half else 4
        est_bytes = int(big.shape[0]) * int(big.shape[1]) * itemsize
        if est_bytes > 512 * 1024 * 1024:  # keep >512 MB banks on CPU faiss
            printt(
                "Index bank too large for GPU search (%d rows, ~%d MB), using CPU faiss",
                big.shape[0],
                est_bytes // (1024 * 1024),
            )
            return
        try:
            self._index_bank = torch.from_numpy(big).to(self.device, dtype=bank_dtype)
            self._index_bank_sq = torch.from_numpy(
                np.square(big.astype(np.float32)).sum(axis=1)
            ).to(self.device, dtype=torch.float32)
            printt(
                "Index search on GPU (%d rows, %s)",
                big.shape[0],
                "fp16" if self.is_half else "fp32",
            )
        except Exception as e:
            self._index_bank = None
            self._index_bank_sq = None
            printt("GPU index init failed, using CPU faiss: %s", e)

    def _index_blend_gpu(self, tail):
        """Top-8 neighbour blend of the feats tail; same weighting as the CPU path."""
        q = tail.to(self._index_bank.dtype)
        sim = q @ self._index_bank.T
        d = (
            q.float().pow(2).sum(1, keepdim=True)
            + self._index_bank_sq.unsqueeze(0)
            - 2.0 * sim.float()
        )
        score, ix = torch.topk(d, 8, dim=1, largest=False)  # squared L2, small = near
        weight = (1.0 / score.clamp_min(1e-4)).square()
        weight = weight / (weight.sum(dim=1, keepdim=True) + 1e-8)
        neigh = self._index_bank[ix].float()  # (n, 8, dim)
        return (neigh * weight.unsqueeze(2)).sum(dim=1)

    def get_f0_post(self, f0):
        if not torch.is_tensor(f0):
            f0 = torch.from_numpy(f0)
        f0 = f0.float().to(self.device).squeeze()
        f0_mel = 1127 * torch.log(1 + f0 / 700)
        # branch-free mel scaling: masked tensor assignment forces a host sync
        # on the hot path every block
        scaled = (f0_mel - self.f0_mel_min) * 254 / (
            self.f0_mel_max - self.f0_mel_min
        ) + 1
        f0_mel = torch.where(f0_mel > 0, scaled, f0_mel).clamp_(min=1, max=255)
        f0_coarse = torch.round(f0_mel).long()
        return f0_coarse, f0

    def _bench_sync(self):
        # opt-in (benchmark --sync-stages): truthful per-stage timings on async devices
        if getattr(self, "bench_sync", False) and "cuda" in str(self.device):
            torch.cuda.synchronize()

    def get_f0(self, x, f0_up_key, n_cpu, method="harvest"):
        n_cpu = int(n_cpu)
        if method == "crepe":
            return self.get_f0_crepe(x, f0_up_key)
        if method == "rmvpe":
            return self.get_f0_rmvpe(x, f0_up_key)
        if method == "fcpe":
            return self.get_f0_fcpe(x, f0_up_key)
        x = x.cpu().numpy()
        if method == "pm":
            p_len = x.shape[0] // 160 + 1
            f0_min = 65
            l_pad = int(np.ceil(1.5 / f0_min * 16000))
            r_pad = l_pad + 1
            s = parselmouth.Sound(np.pad(x, (l_pad, r_pad)), 16000).to_pitch_ac(
                time_step=0.01,
                voicing_threshold=0.6,
                pitch_floor=f0_min,
                pitch_ceiling=1100,
            )
            assert np.abs(s.t1 - 1.5 / f0_min) < 0.001
            f0 = s.selected_array["frequency"]
            if len(f0) < p_len:
                f0 = np.pad(f0, (0, p_len - len(f0)))
            f0 = f0[:p_len]
            f0 *= pow(2, f0_up_key / 12)
            return self.get_f0_post(f0)
        if n_cpu == 1:
            f0, t = pyworld.harvest(
                x.astype(np.double),
                fs=16000,
                f0_ceil=1100,
                f0_floor=50,
                frame_period=10,
            )
            f0 = signal.medfilt(f0, 3)
            f0 *= pow(2, f0_up_key / 12)
            return self.get_f0_post(f0)
        f0bak = np.zeros(x.shape[0] // 160 + 1, dtype=np.float64)
        length = len(x)
        part_length = 160 * ((length // 160 - 1) // n_cpu + 1)
        n_cpu = (length // 160 - 1) // (part_length // 160) + 1
        ts = ttime()
        res_f0 = _shared_mm().dict()
        for idx in range(n_cpu):
            tail = part_length * (idx + 1) + 320
            if idx == 0:
                self.inp_q.put((idx, x[:tail], res_f0, n_cpu, ts))
            else:
                self.inp_q.put(
                    (idx, x[part_length * idx - 320 : tail], res_f0, n_cpu, ts)
                )
        while 1:
            res_ts = self.opt_q.get()
            if res_ts == ts:
                break
        f0s = [i[1] for i in sorted(res_f0.items(), key=lambda x: x[0])]
        for idx, f0 in enumerate(f0s):
            if idx == 0:
                f0 = f0[:-3]
            elif idx != n_cpu - 1:
                f0 = f0[2:-3]
            else:
                f0 = f0[2:]
            f0bak[part_length * idx // 160 : part_length * idx // 160 + f0.shape[0]] = (
                f0
            )
        f0bak = signal.medfilt(f0bak, 3)
        f0bak *= pow(2, f0_up_key / 12)
        return self.get_f0_post(f0bak)

    def get_f0_crepe(self, x, f0_up_key):
        if "privateuseone" in str(
            self.device
        ):  ###不支持dml，cpu又太慢用不成，拿fcpe顶替
            return self.get_f0(x, f0_up_key, 1, "fcpe")
        # printt("using crepe,device:%s"%self.device)
        f0, pd = torchcrepe.predict(
            x.unsqueeze(0).float(),
            16000,
            160,
            self.f0_min,
            self.f0_max,
            "full",
            batch_size=512,
            # device=self.device if self.device.type!="privateuseone" else "cpu",###crepe不用半精度全部是全精度所以不愁###cpu延迟高到没法用
            device=self.device,
            return_periodicity=True,
        )
        pd = torchcrepe.filter.median(pd, 3)
        f0 = torchcrepe.filter.mean(f0, 3)
        f0[pd < 0.1] = 0
        f0 *= pow(2, f0_up_key / 12)
        return self.get_f0_post(f0)

    def get_f0_rmvpe(self, x, f0_up_key):
        if hasattr(self, "model_rmvpe") == False:
            from infer.lib.rmvpe import RMVPE

            printt("Loading rmvpe model")
            self.model_rmvpe = RMVPE(
                "assets/rmvpe/rmvpe.pt",
                is_half=self.is_half,
                device=self.device,
                use_jit=self.config.use_jit,
            )
        f0 = self.model_rmvpe.infer_from_audio(x, thred=0.03)
        f0 *= pow(2, f0_up_key / 12)
        return self.get_f0_post(f0)

    def get_f0_fcpe(self, x, f0_up_key):
        if hasattr(self, "model_fcpe") == False:
            from torchfcpe import spawn_bundled_infer_model

            printt("Loading fcpe model")
            if "privateuseone" in str(self.device):
                self.device_fcpe = "cpu"
            else:
                self.device_fcpe = self.device
            self.model_fcpe = spawn_bundled_infer_model(self.device_fcpe)
        f0 = self.model_fcpe.infer(
            x.to(self.device_fcpe).unsqueeze(0).float(),
            sr=16000,
            decoder_mode="local_argmax",
            # slightly more sensitive than 0.006 — fewer pitch dropouts on soft speech
            threshold=0.005,
        )
        f0 *= pow(2, f0_up_key / 12)
        return self.get_f0_post(f0)

    def skip_block(self, block_frame_16k) -> None:
        """整块静音、外面没调 `infer` 时，替它把音高历史往前推一格。

        `cache_pitch` / `cache_pitchf` 是滚动的历史，**只在 `infer` 里面挪**
        （见下面那两行 `cache_pitch[:-shift] = cache_pitch[shift:]`）。壳为了
        省显卡会跳过静音块不调 `infer` —— 那样这段历史就既不挪也不填，停在
        用户上一次说话的结尾上。

        于是他停顿两秒再开口，模型拿到的音高轨迹还是两秒前那句话的收尾，位置
        上却被当成「紧挨着现在」。起音处音高对不上，听感就是每句话前几个字发糊。

        新腾出来的位置填 0：0 在 RVC 里就是清音，静音本来就该是清音，跟推理
        正常跑过静音段时填进去的值一致，不会引入新的怪声。
        """
        if self.if_f0 != 1:
            return
        shift = int(block_frame_16k) // 160
        if shift <= 0:
            return
        if shift >= self.cache_pitch.shape[0]:
            self.cache_pitch.zero_()
            self.cache_pitchf.zero_()
            return
        self.cache_pitch[:-shift] = self.cache_pitch[shift:].clone()
        self.cache_pitchf[:-shift] = self.cache_pitchf[shift:].clone()
        self.cache_pitch[-shift:] = 0
        self.cache_pitchf[-shift:] = 0

    def infer(
        self,
        input_wav: torch.Tensor,
        block_frame_16k,
        skip_head,
        return_length,
        f0method,
    ) -> np.ndarray:
        t1 = ttime()
        with torch.no_grad():
            if self.config.is_half:
                feats = input_wav.half().view(1, -1)
            else:
                feats = input_wav.float().view(1, -1)
            padding_mask = self._padding_mask_for(feats.shape)
            layer = 9 if self.version == "v1" else 12
            # 每个 block 的形状都一样，正好是 CUDA Graph 的适用场景：把整段
            # kernel 序列录下来重放，省掉每次几百次 kernel launch 的开销。
            # output_layer 是 int，不能当图输入，闭包捕获，同时进 key。
            def _hubert(source, mask):
                return self.model.extract_features(
                    source=source, padding_mask=mask, output_layer=layer
                )[0]

            logits0 = run_cuda_graph(
                self.model, "rtrvc-hubert-%s" % layer, _hubert, feats, padding_mask
            )
            feats = self.model.final_proj(logits0) if self.version == "v1" else logits0
            feats = torch.cat((feats, feats[:, -1:, :]), 1)
        self._bench_sync()
        t2 = ttime()
        try:
            if hasattr(self, "index") and self.index_rate != 0:
                # slightly soft blend: keep a bit more of live features for naturalness
                rate = float(np.clip(self.index_rate, 0.0, 1.0))
                if getattr(self, "_index_bank", None) is not None:
                    tail = feats[0][skip_head // 2 :]
                    blended = self._index_blend_gpu(tail).to(feats.dtype)
                    feats[0][skip_head // 2 :] = blended * rate + (1.0 - rate) * tail
                else:
                    npy = (
                        feats[0][skip_head // 2 :]
                        .cpu()
                        .numpy()
                        .astype("float32", copy=False)
                    )
                    score, ix = self.index.search(npy, k=8)
                    if (ix >= 0).all():
                        # floor scores to avoid 1/score blow-ups (unstable "metallic" voice)
                        weight = np.square(1.0 / np.maximum(score, 1e-4))
                        weight /= weight.sum(axis=1, keepdims=True) + 1e-8
                        npy = np.sum(
                            self.big_npy[ix] * np.expand_dims(weight, axis=2), axis=1
                        )
                        if self.config.is_half:
                            npy = npy.astype("float16")
                        feats[0][skip_head // 2 :] = (
                            torch.from_numpy(npy).unsqueeze(0).to(self.device) * rate
                            + (1.0 - rate) * feats[0][skip_head // 2 :]
                        )
                    else:
                        if not getattr(self, "_warned_bad_index", False):
                            printt(
                                "Invalid index. You MUST use added_xxxx.index but not trained_xxxx.index!"
                            )
                            self._warned_bad_index = True
            # else: index disabled — no per-block log (was spam + cost)
        except Exception:
            # degrade to the CPU faiss path on any GPU-search failure (e.g. OOM)
            self._index_bank = None
            if not getattr(self, "_warned_index_exc", False):
                traceback.print_exc()
                printt("Index search FAILED (will not re-spam)")
                self._warned_index_exc = True
        self._bench_sync()
        t3 = ttime()
        p_len = input_wav.shape[0] // 160
        factor = pow(2, self.formant_shift / 12)
        return_length2 = int(np.ceil(return_length * factor))
        if self.if_f0 == 1:
            f0_extractor_frame = block_frame_16k + 800
            if f0method == "rmvpe":
                f0_extractor_frame = 5120 * ((f0_extractor_frame - 1) // 5120 + 1) - 160
            pitch, pitchf = self.get_f0(
                input_wav[-f0_extractor_frame:], self.f0_up_key - self.formant_shift, self.n_cpu, f0method
            )
            shift = block_frame_16k // 160
            self.cache_pitch[:-shift] = self.cache_pitch[shift:].clone()
            self.cache_pitchf[:-shift] = self.cache_pitchf[shift:].clone()
            self.cache_pitch[4 - pitch.shape[0] :] = pitch[3:-1]
            self.cache_pitchf[4 - pitch.shape[0] :] = pitchf[3:-1]
            cache_pitch = self.cache_pitch[None, -p_len:]
            cache_pitchf = self.cache_pitchf[None, -p_len:] * return_length2 / return_length
        self._bench_sync()
        t4 = ttime()
        feats = F.interpolate(feats.permute(0, 2, 1), scale_factor=2).permute(0, 2, 1)
        feats = feats[:, :p_len, :]
        p_len = self._long_dev(p_len)
        sid = self._long_dev(0)
        # 这三个是块几何，一个流跑起来之后就不变了。原样保留张量形式给 eager
        # 路径（TorchScript 的签名认张量），另外留一份 int 进 CUDA Graph 的
        # key —— 几何一变就重新录一张图，不会拿旧图算错。
        head_i, ret_i, ret2_i = int(skip_head), int(return_length), int(return_length2)
        skip_head = self._long_cpu(skip_head)
        return_length2 = self._long_cpu(return_length2)
        return_length = self._long_cpu(return_length)
        with torch.no_grad():
            if self.if_f0 == 1:

                def _net_g_f0(phone, lengths, coarse, continuous, speaker):
                    return self.net_g.infer(
                        phone,
                        lengths,
                        coarse,
                        continuous,
                        speaker,
                        skip_head,
                        return_length,
                        return_length2,
                    )[0]

                infered_audio = run_cuda_graph(
                    self.net_g,
                    "rtrvc-f0-%s-%s-%s" % (head_i, ret_i, ret2_i),
                    _net_g_f0,
                    feats,
                    p_len,
                    cache_pitch,
                    cache_pitchf,
                    sid,
                )
            else:

                def _net_g_nof0(phone, lengths, speaker):
                    return self.net_g.infer(
                        phone, lengths, speaker, skip_head, return_length, return_length2
                    )[0]

                infered_audio = run_cuda_graph(
                    self.net_g,
                    "rtrvc-nof0-%s-%s-%s" % (head_i, ret_i, ret2_i),
                    _net_g_nof0,
                    feats,
                    p_len,
                    sid,
                )
        infered_audio = infered_audio.squeeze(1).float()
        upp_res = int(np.floor(factor * self.tgt_sr // 100))
        if upp_res != self.tgt_sr // 100:
            if upp_res not in self.resample_kernel:
                self.resample_kernel[upp_res] = Resample(
                    orig_freq=upp_res,
                    new_freq=self.tgt_sr // 100,
                    dtype=torch.float32,
                ).to(self.device)
            infered_audio = self.resample_kernel[upp_res](
                infered_audio[:, : return_length * upp_res]
            )
        self._bench_sync()
        t5 = ttime()
        # per-stage seconds for the benchmark / perf tooling (fea, index, f0, model)
        self.last_stage_times = (t2 - t1, t3 - t2, t4 - t3, t5 - t4)
        # Hot-path: only log timing occasionally (every ~2s of wall time)
        now = t5
        last = getattr(self, "_last_timing_log", 0.0)
        if now - last > 2.0:
            self._last_timing_log = now
            printt(
                "Spent time: fea = %.3fs, index = %.3fs, f0 = %.3fs, model = %.3fs",
                t2 - t1,
                t3 - t2,
                t4 - t3,
                t5 - t4,
            )
        return infered_audio.squeeze()
