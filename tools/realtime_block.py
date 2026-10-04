# -*- coding: utf-8 -*-
"""实时变声处理一块声音的全部步骤。实时链路和离线渲染共用这一份。

## 为什么单独成一个模块

调参要在离线状态下按实时的方式渲染几百组参数，再从中挑出一组给用户。如果离线
那边照着实时链路另写一份，两份迟早会走散，而且走散时没有任何征兆：渲染出来的
声音照样像那么回事，只是和用户实际听到的不是同一个声音，照着它调出来的参数到
用户电脑上就不对。

所以「进一块声音、出一块声音」的处理只写在这里：响应阈值、输入降噪、推理、
输出降噪、DSP 变声、修音链、音量包络、块与块的拼接、总音量、软限幅。`gui_v1`
的音频回调调它，离线渲染（`OfflineStream`）也调它。读写声卡、计时和换模型
留在 `gui_v1`。

## 状态放在调用方的对象上

这里的函数都收一个 `s`，它带着一条流的缓冲区和 `gui_config`、`rvc`、`config`
等字段。实时链路传的是 `GUI` 实例本身，离线渲染传 `OfflineStream`。这样 `gui_v1`
里其他用到这些缓冲区的地方（比如换模型时清空拼接缓冲）一行都不用改。

## 两边唯一的差别

实时链路在上一块处理超时后会跳过输入降噪，先赶上进度。这一步看
`s.last_infer_ms`，离线渲染里它始终是 0，也就是一律按来得及处理。

## 离线不支持的设置

`harvest` 音高算法要靠 `gui_v1` 主进程里的多进程工作者，离线渲染不支持它。
"""

from __future__ import annotations

import sys
import traceback
import types

import numpy as np


def _printt(strr, *args):
    if len(args) == 0:
        print(strr)
    else:
        print(strr % args)


def soft_clip_np(data: "np.ndarray", ceiling: float = 0.97) -> "np.ndarray":
    """Gentle peak soft-clip (cubic) then hard limit — less DAC harshness than bare clip."""
    x = np.asarray(data, dtype=np.float32)
    # slightly stronger soft knee than 0.12 — peaks a bit less brittle
    y = x - (x * x * x) * 0.15
    np.clip(y, -ceiling, ceiling, out=y)
    return y


def rms_db_frames(y, frame_length, hop_length):
    """librosa.feature.rms(center=True) + amplitude_to_db 的直接等价实现。

    每个音频块都要过一次；去掉 librosa 的封装层（valid_audio / frame /
    pad_mode 分支）实测每块省约 60µs。数值等价（含 top_db=80 相对裁剪）
    由 tests/test_rms_db_gate.py 对照 librosa 保证。
    """
    yp = np.pad(np.asarray(y, dtype=np.float32), frame_length // 2)
    n = 1 + (len(yp) - frame_length) // hop_length
    if n <= 0:
        return np.empty(0, dtype=np.float32)
    frames = np.lib.stride_tricks.as_strided(
        yp, shape=(n, frame_length), strides=(hop_length * yp.strides[0], yp.strides[0])
    )
    rms = np.sqrt(np.mean(np.square(frames), axis=1))
    db = 20.0 * np.log10(np.maximum(rms, 1e-5))
    return np.maximum(db, db.max() - 80.0)


def phase_vocoder(a, b, fade_out, fade_in):
    import torch

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


# ---------------------------------------------------------------- 一条流的缓冲


def build_stream(s) -> None:
    """按 `s.gui_config` 的采样率和三个时长，建好一条流要用的全部缓冲。

    读：`gui_config.samplerate / block_time / crossfade_time / extra_time`、
    `s._io_device`、`s.rvc`（可为 None）、`s.config.device`。
    """
    import torch
    import torchaudio.transforms as tat

    from tools.torchgate import TorchGate

    # 分块几何统一从 tools/block_geometry.py 取。
    #
    # 这段算术原来在 gui_v1（两处）、benchmark_realtime.py，以及离线渲染器里
    # 各写一份。几份必须完全一致，而**不一致时没有任何征兆**：渲染出来的声音
    # 听着像那么回事，只是和用户实际听到的差了半个块，照着它调出来的参数到用户
    # 机器上就不对。所以只留一份。
    from tools.block_geometry import geometry

    _geo = geometry(
        s.gui_config.samplerate,
        s.gui_config.block_time,
        s.gui_config.crossfade_time,
        s.gui_config.extra_time,
    )
    s.zc = _geo["zc"]
    s.block_frame = _geo["block_frame"]
    s.block_frame_16k = _geo["block_frame_16k"]
    s.crossfade_frame = _geo["crossfade_frame"]
    s.sola_buffer_frame = _geo["sola_buffer_frame"]
    s.sola_search_frame = _geo["sola_search_frame"]
    s.extra_frame = _geo["extra_frame"]
    io_dev = s._io_device
    s.input_wav = torch.zeros(
        s.extra_frame
        + s.crossfade_frame
        + s.sola_search_frame
        + s.block_frame,
        device=io_dev,
        dtype=torch.float32,
    )
    s.input_wav_denoise = s.input_wav.clone()
    s.input_wav_res = torch.zeros(
        160 * s.input_wav.shape[0] // s.zc,
        device=io_dev,
        dtype=torch.float32,
    )
    s.rms_buffer = np.zeros(4 * s.zc, dtype="float32")
    s.sola_buffer = torch.zeros(
        s.sola_buffer_frame, device=io_dev, dtype=torch.float32
    )
    s.nr_buffer = s.sola_buffer.clone()
    s.output_buffer = s.input_wav.clone()
    s.skip_head = s.extra_frame // s.zc
    s.return_length = (
        s.block_frame + s.sola_buffer_frame + s.sola_search_frame
    ) // s.zc
    s.fade_in_window = (
        torch.sin(
            0.5
            * np.pi
            * torch.linspace(
                0.0,
                1.0,
                steps=s.sola_buffer_frame,
                device=io_dev,
                dtype=torch.float32,
            )
        )
        ** 2
    )
    s.fade_out_window = 1 - s.fade_in_window
    s.resampler = tat.Resample(
        orig_freq=s.gui_config.samplerate,
        new_freq=16000,
        dtype=torch.float32,
    ).to(io_dev)
    # DSP 模式没有模型，也就没有 tgt_sr，输入输出同一个采样率。
    rvc_sr = getattr(s.rvc, "tgt_sr", None) if s.rvc is not None else None
    if rvc_sr and rvc_sr != s.gui_config.samplerate:
        s.resampler2 = tat.Resample(
            orig_freq=s.rvc.tgt_sr,
            new_freq=s.gui_config.samplerate,
            dtype=torch.float32,
        ).to(s.config.device)
    else:
        s.resampler2 = None
    s.tg = TorchGate(
        sr=s.gui_config.samplerate, n_fft=4 * s.zc, prop_decrease=0.9
    ).to(io_dev)


# ---------------------------------------------------------------- 音效链


def rebuild_voice_chain(s) -> None:
    """建 / 更新 DSP 变声链。参数热改，不重建实例——重建会清掉延迟线。"""
    gc = s.gui_config
    params = gc.dsp_params if isinstance(getattr(gc, "dsp_params", None), dict) else {}
    preset = str(getattr(gc, "dsp_preset", "") or "").strip()
    if preset and not params:
        try:
            from tools.dsp_presets import get_preset

            got = get_preset(preset)
            if got and isinstance(got.get("params"), dict):
                params = got["params"]
                gc.dsp_params = params
        except Exception:
            traceback.print_exc()
    if not params and not bool(getattr(gc, "dsp_enabled", False)):
        s._voice_chain = None
        return
    try:
        from tools.dsp_voice import VoiceChain

        if not params:
            s._voice_chain = None
            return
        if s._voice_chain is None:
            s._voice_chain = VoiceChain(params)
        else:
            s._voice_chain.apply(params)
    except Exception:
        traceback.print_exc()
        s._voice_chain = None


def apply_voice_chain(s, wav):
    """DSP 变声跑在最后一块上（前面是 SOLA 要的重叠历史）。"""
    import torch

    if s._voice_chain is None:
        rebuild_voice_chain(s)
    if s._voice_chain is None:
        return wav
    sr = int(getattr(s.gui_config, "samplerate", 48000) or 48000)
    n = int(getattr(s, "block_frame", 0) or 0)
    if n <= 0 or wav.numel() < n:
        x = wav.cpu().numpy()
        y = s._voice_chain.process(x, sr)
        return torch.from_numpy(np.asarray(y, dtype=np.float32)).to(
            wav.device
        ).type_as(wav)
    head = wav[:-n]
    tail = wav[-n:].cpu().numpy()
    y = s._voice_chain.process(tail, sr)
    tail_t = torch.from_numpy(np.asarray(y, dtype=np.float32)).to(
        wav.device
    ).type_as(wav)
    return torch.cat([head, tail_t], dim=0)


def fx_config_dict(gc) -> dict:
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


def apply_out_gain(gc, y):
    """出声前的总音量。RVC 和 DSP 两条路都走这里，软限幅之前。

    放在软限幅之前而不是之后：限幅是为了不削爆，加完增益再限才有意义；
    反过来先限后加，加多了照样爆出去。
    """
    g = float(getattr(gc, "out_gain_db", 0.0) or 0.0)
    if abs(g) < 0.05:
        return y
    return (y * np.float32(10.0 ** (g / 20.0))).astype(np.float32)


def rebuild_fx_chain(s) -> None:
    try:
        from tools.dsp_fx import RealtimeFxChain

        if s._fx_chain is None:
            s._fx_chain = RealtimeFxChain(fx_config_dict(s.gui_config))
        else:
            s._fx_chain.apply_config(fx_config_dict(s.gui_config))
    except Exception:
        traceback.print_exc()
        s._fx_chain = None


def apply_fx_chain(s, infer_wav):
    """Run numpy DSP on last block_frame samples of infer_wav (device tensor)."""
    import torch

    if s._fx_chain is None:
        rebuild_fx_chain(s)
    if s._fx_chain is None or not s._fx_chain.enabled:
        return infer_wav
    sr = int(getattr(s.gui_config, "samplerate", 40000) or 40000)
    n = int(getattr(s, "block_frame", 0) or 0)
    if n <= 0 or infer_wav.numel() < n:
        # process whole tensor — .cpu() already detaches + copies
        x = infer_wav.cpu().numpy()
        y = s._fx_chain.process(x, sr)
        return torch.from_numpy(np.asarray(y, dtype=np.float32)).to(
            infer_wav.device
        ).type_as(infer_wav)
    # only shape the newest block (rest is overlap history for SOLA)
    head = infer_wav[:-n]
    tail = infer_wav[-n:]
    x = tail.cpu().numpy()
    y = s._fx_chain.process(x, sr)
    tail_t = torch.from_numpy(np.asarray(y, dtype=np.float32)).to(
        infer_wav.device
    ).type_as(infer_wav)
    return torch.cat([head, tail_t], dim=0)


# ---------------------------------------------------------------- 一块


def process_block(s, indata):
    """一块输入（单声道 float32，设备采样率，长 `s.block_frame`）进，一块输出出。

    返回单声道 float32，长 `s.block_frame`，已经过总音量和软限幅。
    整块静音时返回 None：调用方自己补一块静音，这一块不碰显卡。
    """
    import librosa
    import torch
    import torch.nn.functional as F

    log = getattr(s, "rt_log", None) or _printt
    # Mic pre-gain (dB) before meter/gate so both see the boosted signal
    in_gain_db = float(getattr(s.gui_config, "in_gain_db", 0.0) or 0.0)
    if abs(in_gain_db) >= 0.05:
        indata = indata * np.float32(10.0 ** (in_gain_db / 20.0))
        np.clip(indata, -1.0, 1.0, out=indata)
    # Block input level in dB for the launcher's mic meter (cheap)
    try:
        _rms = float(np.sqrt(np.mean(np.square(indata))) + 1e-9)
        s.last_input_db = float(max(-90.0, 20.0 * np.log10(_rms)))
    except Exception:
        pass
    if s.gui_config.threhold > -60:
        indata = np.append(s.rms_buffer, indata)
        db_all = rms_db_frames(indata, 4 * s.zc, s.zc)
        s.rms_buffer[:] = indata[-4 * s.zc :]
        indata = indata[2 * s.zc - s.zc // 2 :]
        db_threhold = db_all[2:] < s.gui_config.threhold
        for i in range(db_threhold.shape[0]):
            if db_threhold[i]:
                indata[i * s.zc : (i + 1) * s.zc] = 0
        indata = indata[s.zc // 2 :]
    io_dev = s.input_wav.device
    s.input_wav[: -s.block_frame] = s.input_wav[
        s.block_frame :
    ].clone()
    s.input_wav[-indata.shape[0] :] = torch.from_numpy(indata).to(io_dev)

    peak = float(np.max(np.abs(indata))) if indata.size else 0.0
    # 起音诊断：静音之后的头两块单独记一行。
    try:
        if peak < 2e-5:
            s._onset_left = 2
        elif int(getattr(s, "_onset_left", 0) or 0) > 0:
            s._onset_left = int(s._onset_left) - 1
            log(
                "onset peak=%.4f in_db=%.1f gate=%s infer_ms=%s q=%.0f",
                peak,
                float(getattr(s, "last_input_db", -90.0)),
                float(getattr(s.gui_config, "threhold", -60) or -60),
                int(getattr(s, "last_infer_ms", 0) or 0),
                float(getattr(s, "_queue_frames", 0.0) or 0.0),
            )
    except Exception:
        pass

    if s.function == "vc" and peak < 2e-5:
        # Quiet block: do not touch the GPU. TorchGate + skip_block +
        # SOLA on DirectML wait for the game's 3D queue — that is the
        # 17s Infer time with no Spent time in diag 26.8.21/1.
        s.input_wav_res[: -s.block_frame_16k] = s.input_wav_res[
            s.block_frame_16k :
        ].clone()
        s.input_wav_res[-s.block_frame_16k :] = 0
        s._pitch_skip_blocks = int(
            getattr(s, "_pitch_skip_blocks", 0) or 0
        ) + 1
        try:
            s.sola_buffer.mul_(0.88)
        except Exception:
            pass
        return None

    s.input_wav_res[: -s.block_frame_16k] = s.input_wav_res[
        s.block_frame_16k :
    ].clone()
    # Skip denoise when already late — catching the deadline matters
    # more than one block of spectral gating.
    budget_ms = float(getattr(s.gui_config, "block_time", 0.25) or 0.25) * 850.0
    behind = int(getattr(s, "last_infer_ms", 0) or 0) > budget_ms
    denoise = bool(s.gui_config.I_noise_reduce) and not behind
    if denoise:
        s.input_wav_denoise[: -s.block_frame] = s.input_wav_denoise[
            s.block_frame :
        ].clone()
        input_wav = s.input_wav[-s.sola_buffer_frame - s.block_frame :]
        input_wav = s.tg(
            input_wav.unsqueeze(0), s.input_wav.unsqueeze(0)
        ).squeeze(0)
        input_wav[: s.sola_buffer_frame] *= s.fade_in_window
        input_wav[: s.sola_buffer_frame] += (
            s.nr_buffer * s.fade_out_window
        )
        s.input_wav_denoise[-s.block_frame :] = input_wav[
            : s.block_frame
        ]
        s.nr_buffer[:] = input_wav[s.block_frame :]
        s.input_wav_res[-s.block_frame_16k - 160 :] = s.resampler(
            s.input_wav_denoise[-s.block_frame - 2 * s.zc :]
        )[160:]
    else:
        s.input_wav_res[-160 * (indata.shape[0] // s.zc + 1) :] = (
            s.resampler(s.input_wav[-indata.shape[0] - 2 * s.zc :])[
                160:
            ]
        )
    # infer
    if s.function == "vc":
        nskip = int(getattr(s, "_pitch_skip_blocks", 0) or 0)
        if nskip:
            # 静音时没动 GPU 上的音高历史。开口这一块一次性补上，
            # 否则模型拿着几秒前的音高轨迹解码，前几个字发糊。
            try:
                s.rvc.skip_block(s.block_frame_16k * nskip)
            except Exception:
                traceback.print_exc()
            s._pitch_skip_blocks = 0
        feat16 = s.input_wav_res
        if getattr(s, "_dml", False):
            feat16 = feat16.to(s.config.device)
        infer_wav = s.rvc.infer(
            feat16,
            s.block_frame_16k,
            s.skip_head,
            s.return_length,
            s.gui_config.f0method,
        )
        if s.resampler2 is not None:
            infer_wav = s.resampler2(infer_wav)
        if getattr(s, "_dml", False):
            infer_wav = infer_wav.to(io_dev)
    elif s.gui_config.I_noise_reduce:
        infer_wav = s.input_wav_denoise[s.extra_frame :].clone()
    else:
        infer_wav = s.input_wav[s.extra_frame :].clone()
    # 后面的 SOLA 和输出装填都按「至少一个块 + 交叉淡化 + 搜索窗」的
    # 长度在切。个别后端（26.8.16 那台 Intel 核显的 DirectML）会偶发
    # 返回短一截的输出，短了就是一句
    # 「The expanded size of the tensor (1764) must match the existing
    # size (954)」把整条变声流带走。不足的部分补静音：这一块听着空
    # 一点，比整条流断掉强。
    _need = s.block_frame + s.sola_buffer_frame + s.sola_search_frame
    if infer_wav.shape[0] < _need:
        _pad = torch.zeros(
            _need - infer_wav.shape[0],
            device=infer_wav.device,
            dtype=infer_wav.dtype,
        )
        infer_wav = torch.cat([infer_wav, _pad], dim=0)
    # output noise reduction
    if s.gui_config.O_noise_reduce and s.function == "vc":
        s.output_buffer[: -s.block_frame] = s.output_buffer[
            s.block_frame :
        ].clone()
        s.output_buffer[-s.block_frame :] = infer_wav[-s.block_frame :]
        infer_wav = s.tg(
            infer_wav.unsqueeze(0), s.output_buffer.unsqueeze(0)
        ).squeeze(0)
    # DSP 变声。function=fx 时只要链还在就处理，不额外看 dsp_enabled：
    # 热推可能把开关写丢，链在就该出声。
    if s.function == "fx":
        try:
            infer_wav = apply_voice_chain(s, infer_wav)
        except Exception:
            traceback.print_exc()
    # DSP 修音链（gate / 压缩 / EQ）—— numpy on CPU
    if (
        s.function in ("vc", "fx")
        and bool(getattr(s.gui_config, "fx_enabled", False))
    ):
        try:
            infer_wav = apply_fx_chain(s, infer_wav)
        except Exception:
            traceback.print_exc()
    # volume envelop mixing
    if s.gui_config.rms_mix_rate < 1 and s.function == "vc":
        if denoise:
            input_wav = s.input_wav_denoise[s.extra_frame :]
        else:
            input_wav = s.input_wav[s.extra_frame :]
        mix_dev = infer_wav.device
        rms1 = librosa.feature.rms(
            y=input_wav[: infer_wav.shape[0]].detach().cpu().numpy(),
            frame_length=4 * s.zc,
            hop_length=s.zc,
        )
        rms1 = torch.from_numpy(rms1).to(mix_dev)
        rms1 = F.interpolate(
            rms1.unsqueeze(0),
            size=infer_wav.shape[0] + 1,
            mode="linear",
            align_corners=True,
        )[0, 0, :-1]
        rms2 = librosa.feature.rms(
            y=infer_wav[:].detach().cpu().numpy(),
            frame_length=4 * s.zc,
            hop_length=s.zc,
        )
        rms2 = torch.from_numpy(rms2).to(mix_dev)
        rms2 = F.interpolate(
            rms2.unsqueeze(0),
            size=infer_wav.shape[0] + 1,
            mode="linear",
            align_corners=True,
        )[0, 0, :-1]
        rms2 = torch.max(rms2, torch.zeros_like(rms2) + 2e-3)
        # Clamp envelope gain — avoids rare sudden loud pops when rms2 dips
        exp = float(1.0 - s.gui_config.rms_mix_rate)
        gain = torch.pow(rms1 / rms2, exp)
        gain = torch.clamp(gain, 0.15, 3.5)
        infer_wav *= gain
    # SOLA algorithm from https://github.com/yxlllc/DDSP-SVC
    conv_input = infer_wav[
        None, None, : s.sola_buffer_frame + s.sola_search_frame
    ]
    cor_nom = F.conv1d(conv_input, s.sola_buffer[None, None, :])
    cor_den = torch.sqrt(
        F.conv1d(
            conv_input**2,
            torch.ones(
                1, 1, s.sola_buffer_frame, device=s.sola_buffer.device
            ),
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
    if "privateuseone" in str(s.config.device) or not s.gui_config.use_pv:
        infer_wav[: s.sola_buffer_frame] *= s.fade_in_window
        infer_wav[: s.sola_buffer_frame] += (
            s.sola_buffer * s.fade_out_window
        )
    else:
        infer_wav[: s.sola_buffer_frame] = phase_vocoder(
            s.sola_buffer,
            infer_wav[: s.sola_buffer_frame],
            s.fade_out_window,
            s.fade_in_window,
        )
    s.sola_buffer[:] = infer_wav[
        s.block_frame : s.block_frame + s.sola_buffer_frame
    ]
    out = infer_wav[: s.block_frame].cpu().numpy()
    out = apply_out_gain(s.gui_config, out)
    return soft_clip_np(out)


# ---------------------------------------------------------------- 离线


#: 引擎读的设置和它们在 app_config 里的键、默认值。默认值与 gui_v1 的
#: `_values_from_config_file` 一致。
_SETTING_KEYS = (
    # (gui_config 字段, app_config 键, 默认值, 转换)
    ("sr_type", "sr_type", "sr_model", str),
    ("threhold", "threhold", -60, None),
    ("in_gain_db", "in_gain_db", 0.0, float),
    ("out_gain_db", "out_gain_db", 0.0, float),
    ("pitch", "pitch", 0, None),
    ("formant", "formant", 0.0, None),
    ("index_rate", "index_rate", 0, None),
    ("rms_mix_rate", "rms_mix_rate", 0, None),
    ("f0_repair", "f0_repair", False, bool),
    ("block_time", "block_time", 0.25, None),
    ("crossfade_time", "crossfade_length", 0.05, None),
    ("extra_time", "extra_time", 2.5, None),
    ("I_noise_reduce", "I_noise_reduce", False, bool),
    ("O_noise_reduce", "O_noise_reduce", False, bool),
    ("use_pv", "use_pv", False, bool),
    ("f0method", "f0method", "fcpe", str),
    ("fx_enabled", "fx_enabled", False, bool),
    ("fx_gate_enabled", "fx_gate_enabled", True, bool),
    ("fx_gate_threshold_db", "fx_gate_threshold_db", -50, float),
    ("fx_gate_release_ms", "fx_gate_release_ms", 50, float),
    ("fx_gate_hold_ms", "fx_gate_hold_ms", 20, float),
    ("fx_gate_range_db", "fx_gate_range_db", 20, float),
    ("fx_comp_enabled", "fx_comp_enabled", True, bool),
    ("fx_comp_threshold_db", "fx_comp_threshold_db", -20, float),
    ("fx_comp_ratio", "fx_comp_ratio", 4, float),
    ("fx_comp_attack_ms", "fx_comp_attack_ms", 5, float),
    ("fx_comp_release_ms", "fx_comp_release_ms", 100, float),
    ("fx_comp_makeup_db", "fx_comp_makeup_db", 0, float),
    ("fx_eq_enabled", "fx_eq_enabled", True, bool),
    ("fx_eq_preset", "fx_eq_preset", "flat", str),
    ("fx_out_gain_db", "fx_out_gain_db", 0, float),
    ("dsp_enabled", "dsp_enabled", False, bool),
    ("dsp_preset", "dsp_preset", "", str),
)


def settings_from_config(cfg: dict, samplerate: int = 48000) -> types.SimpleNamespace:
    """把 app_config 的键换成引擎读的 `gui_config` 字段，只取影响声音的部分。

    `samplerate` 是设备采样率，只在 `sr_type` 为 `sr_device` 时用到；
    默认的 `sr_model` 下流的采样率就是模型的采样率。
    """
    gc = types.SimpleNamespace()
    for attr, key, default, conv in _SETTING_KEYS:
        v = cfg.get(key, default)
        if v is None or (conv is not None and conv is not bool and v == ""):
            v = default
        setattr(gc, attr, conv(v) if conv is not None else v)
    gains = cfg.get("fx_eq_gains") or [0, 0, 0, 0, 0]
    gc.fx_eq_gains = [float(x) for x in list(gains)[:5]] if isinstance(gains, (list, tuple)) else []
    while len(gc.fx_eq_gains) < 5:
        gc.fx_eq_gains.append(0.0)
    params = cfg.get("dsp_params")
    gc.dsp_params = params if isinstance(params, dict) else {}
    gc.samplerate = int(samplerate)
    gc.channels = 1
    return gc


class OfflineStream:
    """离线按实时的方式跑一条流。调参用它渲染候选参数。

    不碰声卡、不计时。缓冲区和每一步处理都和实时链路是同一份代码。
    `rvc` 由调用方建好（`infer.lib.rtrvc.RVC`），音高、共鸣、检索率在那里定。
    """

    function = "vc"

    def __init__(self, rvc, settings, config):
        self.rvc = rvc
        self.config = config
        self.gui_config = settings
        self._dml = False
        self._io_device = config.device
        self.last_infer_ms = 0
        self._voice_chain = None
        self._fx_chain = None
        if settings.sr_type == "sr_model":
            settings.samplerate = rvc.tgt_sr
        rvc.f0_repair = bool(getattr(settings, "f0_repair", False))
        # 和 start_vc 同一顺序：先建音效链，再建缓冲。
        try:
            rebuild_fx_chain(self)
            if self._fx_chain is not None:
                self._fx_chain.reset()
            rebuild_voice_chain(self)
            if self._voice_chain is not None:
                self._voice_chain.reset()
        except Exception:
            traceback.print_exc()
        build_stream(self)

    @staticmethod
    def rt_log(*_args) -> None:
        """离线渲染不写起音诊断。"""

    @property
    def samplerate(self) -> int:
        return int(self.gui_config.samplerate)

    def feed(self, block: np.ndarray) -> np.ndarray:
        """喂一块（长 `block_frame`，流的采样率），拿回同样长的一块。"""
        y = process_block(self, np.array(block, dtype=np.float32, copy=True))
        if y is None:
            return np.zeros(int(self.block_frame), dtype=np.float32)
        return y

    def render(self, audio: np.ndarray) -> np.ndarray:
        """整段音频（流的采样率）按块喂完。末尾不足一块的部分补静音。"""
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        n = int(self.block_frame)
        blocks = int(np.ceil(len(audio) / n)) if len(audio) else 0
        x = np.pad(audio, (0, blocks * n - len(audio)))
        out = [self.feed(x[i * n:(i + 1) * n]) for i in range(blocks)]
        return np.concatenate(out) if out else np.zeros(0, dtype=np.float32)
