# -*- coding: utf-8 -*-
"""tools/perf_report.py — local perf collector used by gui_v1."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.perf_report import _KEEP_REPORTS, PerfCollector, _prune


def test_empty_collector_saves_nothing(tmp_path):
    c = PerfCollector({"block_time": 0.25})
    assert c.summary() == {"n": 0}
    assert c.save(str(tmp_path)) == ""
    assert list(tmp_path.iterdir()) == []


def test_summary_stats_and_budget():
    c = PerfCollector({"block_time": 0.1})
    for ms in [50, 60, 70, 80, 90, 100, 110, 120, 130, 140]:
        c.add(ms / 1000.0)
    s = c.summary()
    assert s["n"] == 10
    assert s["mean_ms"] == 95.0
    assert s["max_ms"] == 140.0
    assert s["block_ms"] == 100.0
    assert s["over_budget_blocks"] == 4  # 110..140 exceed the 100ms budget
    assert s["p50_ms"] <= s["p95_ms"] <= s["max_ms"]
    assert len(s["worst10_ms"]) == 10


def test_save_writes_valid_json(tmp_path):
    c = PerfCollector({"block_time": 0.25, "gpu": "Test GPU"})
    c.add(0.05)
    c.add(0.06)
    path = c.save(str(tmp_path))
    assert os.path.isfile(path)
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    assert payload["meta"]["gpu"] == "Test GPU"
    assert payload["summary"]["n"] == 2
    assert not path.endswith(".tmp")
    assert len(list(tmp_path.glob("*.tmp"))) == 0


def test_prune_keeps_newest(tmp_path):
    for i in range(_KEEP_REPORTS + 5):
        (tmp_path / f"perf_20260101_{i:06d}.json").write_text("{}")
    (tmp_path / "other.txt").write_text("keep me")
    _prune(str(tmp_path))
    reports = sorted(p.name for p in tmp_path.glob("perf_*.json"))
    assert len(reports) == _KEEP_REPORTS
    # oldest were removed, newest kept
    assert reports[0] == "perf_20260101_000005.json"
    assert (tmp_path / "other.txt").exists()
