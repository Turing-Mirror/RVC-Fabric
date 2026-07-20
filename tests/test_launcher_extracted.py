# -*- coding: utf-8 -*-
"""Pure logic extracted out of main_app.py — presets, voice history, monitor pick."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher.app_presets import (
    PERF_PRESETS,
    format_latency_line,
    perf_preset_name,
    perf_preset_values,
)
from launcher.audio_devices import is_virtual_monitor_name, prefer_monitor_device
from launcher.voice_history import VoiceParamHistory


# --- app_presets ---------------------------------------------------------

def test_perf_preset_values_known_and_fallback():
    assert perf_preset_values("low_latency") == (0.12, 0.04, 1.5)
    assert perf_preset_values("stable") == (0.40, 0.08, 3.5)
    # unknown key falls back to balanced
    assert perf_preset_values("nope") == PERF_PRESETS["balanced"]


def test_perf_preset_name():
    assert perf_preset_name("low_latency") == "低延迟"
    assert perf_preset_name("weird") == "weird"


def test_format_latency_line_normal():
    assert format_latency_line(120, 55, "TM") == "延迟 120 ms · 推理 55 ms"


def test_format_latency_line_hides_sentinels():
    # >= 8000 delay reads as "measuring", absurd infer dropped
    assert format_latency_line(114514000, 30, "TM") == "延迟 测量中… · 推理 30 ms"
    assert format_latency_line(0, 0, "TM fallback") == "TM fallback"
    assert format_latency_line(90, 999999, "TM") == "延迟 90 ms"


# --- voice_history -------------------------------------------------------

def test_history_push_dedup_and_redo_clear():
    h = VoiceParamHistory(limit=5)
    assert h.push({"pitch": 0}) is True
    assert h.push({"pitch": 0}) is False  # consecutive dup ignored
    assert h.undo_len == 1


def test_history_undo_redo_roundtrip():
    h = VoiceParamHistory()
    h.push({"pitch": 0})
    h.push({"pitch": 2})
    # current is pitch 5; undo should hand back pitch 2, then pitch 0
    prev = h.undo({"pitch": 5})
    assert prev == {"pitch": 2}
    assert h.redo_len == 1
    prev2 = h.undo({"pitch": 2})
    assert prev2 == {"pitch": 0}
    # redo walks forward
    nxt = h.redo({"pitch": 0})
    assert nxt == {"pitch": 2}


def test_history_undo_empty_returns_none():
    h = VoiceParamHistory()
    assert h.undo({"pitch": 1}) is None
    assert h.redo({"pitch": 1}) is None


def test_history_limit_bounds_undo_stack():
    h = VoiceParamHistory(limit=3)
    for i in range(10):
        h.push({"pitch": i})
    assert h.undo_len == 3


def test_history_new_edit_forks_redo():
    h = VoiceParamHistory()
    h.push({"pitch": 0})
    h.undo({"pitch": 1})
    assert h.redo_len == 1
    h.push({"pitch": 9})  # a fresh edit drops the redo branch
    assert h.redo_len == 0


def test_history_snapshots_are_copied():
    h = VoiceParamHistory()
    snap = {"pitch": 1}
    h.push(snap)
    snap["pitch"] = 999  # mutating the caller's dict must not corrupt history
    assert h.undo({"pitch": 0}) == {"pitch": 1}


# --- audio_devices -------------------------------------------------------

def test_is_virtual_monitor_name():
    assert is_virtual_monitor_name("") is True
    assert is_virtual_monitor_name("CABLE Input (VB-Audio)") is True
    assert is_virtual_monitor_name("Steam Streaming Speakers") is True
    assert is_virtual_monitor_name("扬声器 (Realtek)") is False
    assert is_virtual_monitor_name("耳机 (USB Audio)") is False


def test_prefer_monitor_device_prefers_headphones():
    outs = ["CABLE Input", "扬声器 (Realtek)", "耳机 (USB)"]
    assert prefer_monitor_device(outs, "", "CABLE Input") == "耳机 (USB)"


def test_prefer_monitor_device_avoids_main_and_virtual():
    outs = ["CABLE Input", "CABLE Output", "扬声器 (Realtek)"]
    # main is a CABLE — avoid all CABLE endpoints, fall to the real speaker
    assert prefer_monitor_device(outs, "", "CABLE Input") == "扬声器 (Realtek)"


def test_prefer_monitor_device_keeps_usable_current():
    outs = ["扬声器 (Realtek)", "耳机 (USB)"]
    assert prefer_monitor_device(outs, "扬声器 (Realtek)", "CABLE Input") == "扬声器 (Realtek)"


def test_prefer_monitor_device_empty_returns_current():
    assert prefer_monitor_device([], "whatever") == "whatever"
