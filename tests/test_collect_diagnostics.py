# -*- coding: utf-8 -*-
"""tools/collect_diagnostics.py — support bundle assembly."""

import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.collect_diagnostics import (
    _MAX_PER_DIR,
    _MAX_PERF_REPORTS,
    collect,
    env_summary,
    gather_files,
)


def _make_tree(root):
    (root / "User_Data" / "logs").mkdir(parents=True)
    (root / "User_Data" / "perf_reports").mkdir(parents=True)
    (root / "User_Data" / "runtime_control").mkdir(parents=True)
    (root / "configs" / "inuse").mkdir(parents=True)
    (root / "User_Data" / "logs" / "worker.log").write_text("log line")
    (root / "User_Data" / "perf_reports" / "perf_1.json").write_text("{}")
    (root / "User_Data" / "runtime_control" / "status.json").write_text("{}")
    (root / "User_Data" / "app_config.json").write_text("{}")
    (root / "configs" / "inuse" / "config.json").write_text("{}")


def test_gather_files_picks_expected(tmp_path):
    _make_tree(tmp_path)
    arcs = {a for a, _ in gather_files(str(tmp_path))}
    assert "User_Data/logs/worker.log" in arcs
    assert "User_Data/perf_reports/perf_1.json" in arcs
    assert "User_Data/runtime_control/status.json" in arcs
    assert "User_Data/app_config.json" in arcs
    assert "configs/inuse/config.json" in arcs
    # missing optional files are simply skipped
    assert not any(a.endswith("package_meta.json") for a in arcs)


def test_gather_caps_per_directory(tmp_path):
    _make_tree(tmp_path)
    for i in range(_MAX_PER_DIR + 7):
        (tmp_path / "User_Data" / "logs" / f"old_{i:02d}.log").write_text("x")
    arcs = [
        a for a, _ in gather_files(str(tmp_path)) if a.startswith("User_Data/logs/")
    ]
    assert len(arcs) == _MAX_PER_DIR


def test_gather_keeps_more_perf_reports_than_logs(tmp_path):
    """Perf samples (incl. bench_*.json) are the optimization dataset —
    they get a larger per-dir budget than logs."""
    _make_tree(tmp_path)
    pr = tmp_path / "User_Data" / "perf_reports"
    for i in range(_MAX_PERF_REPORTS + 5):
        (pr / f"perf_{i:03d}.json").write_text("{}")
    (pr / "bench_20260727_120000.json").write_text("{}")
    arcs = [
        a
        for a, _ in gather_files(str(tmp_path))
        if a.startswith("User_Data/perf_reports/")
    ]
    assert len(arcs) == _MAX_PERF_REPORTS
    assert _MAX_PERF_REPORTS > _MAX_PER_DIR


def test_gather_deduplicates_overlapping_entries(tmp_path):
    """Files in the explicit list that also land in the newest-N sweep
    (e.g. logs/install_health.log) must appear once, not twice."""
    _make_tree(tmp_path)
    (tmp_path / "User_Data" / "logs" / "install_health.log").write_text("ok")
    arcs = [a for a, _ in gather_files(str(tmp_path))]
    assert len(arcs) == len(set(arcs))
    assert "User_Data/logs/install_health.log" in arcs


def test_collect_builds_zip_with_env(tmp_path):
    _make_tree(tmp_path)
    zip_path = collect(str(tmp_path))
    assert os.path.isfile(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert "env.json" in names
        assert "User_Data/logs/worker.log" in names
        env = json.loads(zf.read("env.json"))
    assert env["python"]
    assert isinstance(env["root_ascii"], bool)


def test_env_summary_survives_missing_torch(tmp_path):
    info = env_summary(str(tmp_path))
    assert "torch" in info  # either a version or an 'unavailable: ...' marker


def test_env_summary_identifies_machine(tmp_path):
    """The bundle doubles as a per-machine perf sample: it must say what
    hardware class this is, not just the Python stack."""
    info = env_summary(str(tmp_path))
    assert "cpu" in info
    assert isinstance(info["cpu_count"], int) and info["cpu_count"] >= 1
    assert info["machine"]
