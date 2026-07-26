# -*- coding: utf-8 -*-
"""launcher/perf_bench.py — quick benchmark bridge for diagnostics bundles."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher.perf_bench import (
    bench_f0method,
    bench_python,
    bench_ready,
    build_bench_command,
    format_bench_summary,
    run_benchmark,
)


def _make_root(tmp_path, with_runtime=True):
    (tmp_path / "tools").mkdir(exist_ok=True)
    (tmp_path / "tools" / "benchmark_realtime.py").write_text("# stub")
    if with_runtime:
        (tmp_path / "Runtime").mkdir(exist_ok=True)
        (tmp_path / "Runtime" / "pythonw.exe").write_text("")
    pth = tmp_path / "voice.pth"
    pth.write_text("model")
    return str(pth)


def test_bench_python_prefers_windowed(tmp_path):
    (tmp_path / "Runtime").mkdir()
    (tmp_path / "Runtime" / "python.exe").write_text("")
    (tmp_path / "Runtime" / "pythonw.exe").write_text("")
    assert bench_python(tmp_path).endswith("pythonw.exe")


def test_bench_python_none_without_runtime(tmp_path):
    assert bench_python(tmp_path) is None


def test_bench_ready_reports_reason(tmp_path):
    pth = _make_root(tmp_path, with_runtime=False)
    ok, why = bench_ready(tmp_path, pth)
    assert not ok and "Runtime" in why
    pth = _make_root(tmp_path)
    ok, why = bench_ready(tmp_path, pth)
    assert ok and why == ""
    ok, why = bench_ready(tmp_path, str(tmp_path / "missing.pth"))
    assert not ok and "模型" in why


def test_f0method_falls_back_for_harvest():
    assert bench_f0method("harvest") == "fcpe"
    assert bench_f0method("") == "fcpe"
    assert bench_f0method("RMVPE") == "rmvpe"


def test_build_command_mirrors_user_settings(tmp_path):
    pth = _make_root(tmp_path)
    cfg = {
        "f0method": "rmvpe",
        "block_time": 0.12,
        "crossfade_length": 0.04,
        "extra_time": 1.5,
        "index_rate": 0.0,
    }
    cmd = build_bench_command("py.exe", tmp_path, pth, "", cfg, "out.json", 60)
    assert cmd[0] == "py.exe"
    assert cmd[1].endswith("benchmark_realtime.py")
    joined = " ".join(cmd)
    assert "--f0method rmvpe" in joined
    assert "--block-time 0.12" in joined
    assert "--extra-time 1.5" in joined
    assert "--n-blocks 60" in joined
    assert "--json-out out.json" in joined
    # index_rate 0 → no index args even if a path were given
    assert "--index" not in cmd


def test_build_command_includes_index_only_when_active(tmp_path):
    pth = _make_root(tmp_path)
    idx = tmp_path / "added.index"
    idx.write_text("idx")
    cfg = {"index_rate": 0.5}
    cmd = build_bench_command("py", tmp_path, pth, str(idx), cfg, "o.json")
    assert "--index" in cmd and "--index-rate" in cmd
    # missing file → dropped
    cmd = build_bench_command(
        "py", tmp_path, pth, str(tmp_path / "gone.index"), cfg, "o.json"
    )
    assert "--index" not in cmd


class _FakeProc:
    """Writes the --json-out payload on wait(), like the real benchmark."""

    def __init__(self, cmd, code=0, payload=None, hang=False):
        self.cmd = cmd
        self.code = code
        self.payload = payload
        self.hang = hang
        self.killed = False

    def wait(self, timeout=None):
        if self.hang:
            raise TimeoutError("fake timeout")
        if self.payload is not None:
            out = self.cmd[self.cmd.index("--json-out") + 1]
            with open(out, "w", encoding="utf-8") as f:
                json.dump(self.payload, f)
        return self.code

    def kill(self):
        self.killed = True


def test_run_benchmark_success(tmp_path):
    pth = _make_root(tmp_path)
    payload = {"summary": {"mean_ms": 55.6, "p95_ms": 61.9, "rtf": 0.22}}
    procs = []

    def popen(cmd):
        p = _FakeProc(cmd, payload=payload)
        procs.append(p)
        return p

    res = run_benchmark(tmp_path, pth, popen=popen)
    assert res["ok"] and res["error"] == ""
    assert res["summary"]["p95_ms"] == 61.9
    assert os.path.isfile(res["json_path"])
    assert os.path.dirname(res["json_path"]).endswith("perf_reports")
    assert os.path.basename(res["json_path"]).startswith("bench_")


def test_run_benchmark_without_runtime_fails_fast(tmp_path):
    pth = _make_root(tmp_path, with_runtime=False)
    called = []
    res = run_benchmark(tmp_path, pth, popen=lambda cmd: called.append(cmd))
    assert not res["ok"] and "Runtime" in res["error"]
    assert called == []


def test_run_benchmark_nonzero_exit(tmp_path):
    pth = _make_root(tmp_path)
    res = run_benchmark(tmp_path, pth, popen=lambda cmd: _FakeProc(cmd, code=1))
    assert not res["ok"] and "perf_bench.log" in res["error"]


def test_run_benchmark_timeout_kills(tmp_path):
    pth = _make_root(tmp_path)
    procs = []

    def popen(cmd):
        p = _FakeProc(cmd, hang=True)
        procs.append(p)
        return p

    res = run_benchmark(tmp_path, pth, timeout_s=1, popen=popen)
    assert not res["ok"] and "超时" in res["error"]
    assert procs[0].killed


def test_run_benchmark_wait_failure_is_not_reported_as_timeout(tmp_path):
    pth = _make_root(tmp_path)

    class _BrokenProc(_FakeProc):
        def wait(self, timeout=None):
            raise RuntimeError("boom")

    res = run_benchmark(tmp_path, pth, popen=lambda cmd: _BrokenProc(cmd))
    assert not res["ok"] and "等待失败" in res["error"]
    assert "超时" not in res["error"]


def test_format_bench_summary():
    line = format_bench_summary({"mean_ms": 55.6, "p95_ms": 61.9, "rtf": 0.223})
    assert "56ms" in line and "62ms" in line and "0.22" in line
    assert format_bench_summary({}) == ""
