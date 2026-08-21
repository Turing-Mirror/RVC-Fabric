# -*- coding: utf-8 -*-
"""tools/perf_report.py — local perf collector used by gui_v1."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.perf_report import (
    _KEEP_REPORTS,
    PerfCollector,
    _prune,
    load_latest,
    should_save,
)


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


def test_should_save_throttles_occasional_sampling(tmp_path):
    # empty (or missing) dir → save
    assert should_save(str(tmp_path)) is True
    assert should_save(str(tmp_path / "nope")) is True
    # fresh report → skip
    report = tmp_path / "perf_20260101_000000.json"
    report.write_text("{}")
    assert should_save(str(tmp_path), min_interval_s=1800) is False
    # old report → save again
    old = os.path.getmtime(report) - 4000
    os.utime(report, (old, old))
    assert should_save(str(tmp_path), min_interval_s=1800) is True
    # non-report files don't count
    (tmp_path / "notes.txt").write_text("x")
    assert should_save(str(tmp_path), min_interval_s=1800) is True


def test_load_latest(tmp_path):
    assert load_latest(str(tmp_path)) is None            # empty dir
    assert load_latest(str(tmp_path / "nope")) is None   # missing dir
    (tmp_path / "perf_20260101_000000.json").write_text('{"summary": {"n": 1}}')
    (tmp_path / "perf_20260202_000000.json").write_text('{"summary": {"n": 2}}')
    latest = load_latest(str(tmp_path))
    assert latest["summary"]["n"] == 2                    # newest by name
    # corrupt newest → None
    (tmp_path / "perf_20260303_000000.json").write_text("{ broken")
    assert load_latest(str(tmp_path)) is None


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


# ---------------------------------------------------------------------------
# unittest 桥。这个文件是 pytest 风格（模块级 test_ 函数 + tmp_path 夹具），但
# 产品的跑法是 `python -m unittest discover`（scripts/run_tests.bat），后者两样
# 都不认 —— 守卫一直没在跑。挂到 TestCase 上，声明了 tmp_path 的发一个临时
# 目录，两种跑法都能执行。
# ---------------------------------------------------------------------------
import inspect
import pathlib
import tempfile
import unittest


def _bridge(fn):
    if "tmp_path" in inspect.signature(fn).parameters:
        def run(self):
            with tempfile.TemporaryDirectory() as td:
                fn(tmp_path=pathlib.Path(td))
    else:
        def run(self):
            fn()
    return run


class _UnittestBridge(unittest.TestCase):
    pass


for _name in [n for n in list(globals()) if n.startswith("test_")]:
    setattr(_UnittestBridge, _name, _bridge(globals()[_name]))

if __name__ == "__main__":
    unittest.main()
