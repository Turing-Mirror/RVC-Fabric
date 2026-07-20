# -*- coding: utf-8 -*-
"""tools/benchmark_realtime.py — geometry must mirror gui_v1.start_vc exactly."""

import os
import sys

import pytest

np = pytest.importorskip("numpy")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.benchmark_realtime import block_geometry, build_parser, synth_input


def test_geometry_40k_default_params():
    g = block_geometry(sr=40000, block_time=0.25, crossfade_time=0.05, extra_time=2.5)
    assert g["zc"] == 400
    assert g["block_frame"] == 10000
    assert g["block_frame_16k"] == 4000
    assert g["crossfade_frame"] == 2000
    assert g["sola_buffer_frame"] == 1600  # capped at 4*zc
    assert g["sola_search_frame"] == 400
    assert g["extra_frame"] == 100000
    assert g["input_frames"] == 112400
    assert g["input_res_len"] == 44960
    assert g["skip_head"] == 250
    assert g["return_length"] == 30


def test_geometry_48k_16k_domain_invariant():
    # 16k-domain sizes must not depend on the model sample rate
    g40 = block_geometry(sr=40000, block_time=0.25, crossfade_time=0.05, extra_time=2.5)
    g48 = block_geometry(sr=48000, block_time=0.25, crossfade_time=0.05, extra_time=2.5)
    assert g48["block_frame_16k"] == g40["block_frame_16k"] == 4000
    assert g48["input_res_len"] == g40["input_res_len"] == 44960
    assert g48["skip_head"] == g40["skip_head"]
    assert g48["return_length"] == g40["return_length"]


def test_geometry_block_frames_are_zc_multiples():
    for sr in (32000, 40000, 48000):
        for bt in (0.1, 0.25, 0.5):
            g = block_geometry(sr=sr, block_time=bt, crossfade_time=0.05, extra_time=2.5)
            assert g["block_frame"] % g["zc"] == 0
            assert g["extra_frame"] % g["zc"] == 0
            assert g["block_frame_16k"] % 160 == 0


def test_parser_defaults_and_required_pth():
    p = build_parser()
    args = p.parse_args(["--pth", "x.pth"])
    assert args.f0method == "fcpe"
    assert args.block_time == 0.25
    assert args.n_blocks == 200
    assert args.warmup == 10
    assert args.index == ""
    with pytest.raises(SystemExit):
        p.parse_args([])


def test_synth_input_is_sane():
    sig = synth_input(16000)
    assert sig.shape == (16000,)
    assert sig.dtype == np.float32
    assert np.max(np.abs(sig)) <= 1.0
    assert np.max(np.abs(sig)) > 0.1  # actually voiced, not silence
