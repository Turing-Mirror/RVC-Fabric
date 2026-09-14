# -*- coding: utf-8 -*-
"""A-04 启动/命令链路测量基线（不开音频流）。

计时边界（与整改计划书 B3 验收的口径一致，但只测可自动化的部分）：

  spawn_ms        spawn → 首个 status.json 写入（pythonw 起来、pid 可见）
  ready_ms        首个 status → state=idle（torch/驱动导入 + 设备枚举完成）
  cmd_ack_ms      就绪后发 list_devices → status.last_cmd_seq 认领（命令链路）
  prewarm_ms      可选：就绪后发 prewarm → 日志出现「预热：完成」（模型读权重，
                  不开流；需要已选音色，且用 python.exe 捕获输出）

只测量，不开流：worker 停在 idle，不发 start。结束后发 quit 让它自己退出。

用法::

    python scripts\\dev\\measure_start_baseline.py            # 一次启动基线
    python scripts\\dev\\measure_start_baseline.py --prewarm  # 加测预热
    python scripts\\dev\\measure_start_baseline.py -n 3       # 连测 3 次

结果追加到 ``_local/perf_baseline.jsonl``（_local 不进 Git）。脚本不会动
别的软件的音频：它只 spawn 自己的 worker，测量期间不打开任何音频设备。
已在跑 worker（包括软件正开着）时拒绝执行 —— 不打扰正在使用的会话。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTROL = ROOT / "User_Data" / "runtime_control"
STATUS = CONTROL / "status.json"
COMMAND = CONTROL / "command.json"
SEQ = CONTROL / "command.seq"
WORKER_PID = CONTROL / "worker.pid"
OUT_LOG = ROOT / "_local" / "perf_baseline_worker.log"
RESULTS = ROOT / "_local" / "perf_baseline.jsonl"

_POLL_S = 0.05
_READY_TIMEOUT_S = 180.0
_ACK_TIMEOUT_S = 10.0
_QUIT_TIMEOUT_S = 15.0

_PY_ENV_DROP_PREFIXES = (
    "PYTHON",
    "CONDA_",
    "VIRTUAL_ENV",
    "PIP_",
    "UV_",
    "POETRY_",
    "MAMBA_",
    "PYENV_",
)
_PY_ENV_DROP_EXACT = {
    "_MEIPASS",
    "_PYI_APPLICATION_HOME_DIR",
    "_PYI_ARCHIVE_FILE",
    "TCL_LIBRARY",
    "TK_LIBRARY",
    "TIX_LIBRARY",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
}


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        # Windows: os.kill(pid, 0) 不结束进程，只做存在性检查。
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _worker_running() -> int:
    """已有 worker 在跑就返回它的 pid，否则 0。"""
    pids = [int(_read_json(STATUS).get("pid") or 0)]
    try:
        pids.append(int(WORKER_PID.read_text().strip() or 0))
    except (OSError, ValueError):
        pass
    for pid in pids:
        if pid > 0 and _pid_alive(pid):
            return pid
    return 0


def _env() -> dict:
    """与 worker.rs::env_for_runtime 同口径：洗掉 Python 环境污染。"""
    env = {}
    for k, v in os.environ.items():
        ku = k.upper()
        if ku in _PY_ENV_DROP_EXACT or any(ku.startswith(p) for p in _PY_ENV_DROP_PREFIXES):
            continue
        env[k] = v
    rt = str(ROOT / "Runtime")
    for k in env:
        if k.upper() == "PATH":
            env[k] = rt + ";" + str(ROOT) + ";" + env[k]
            break
    else:
        env["PATH"] = rt + ";" + str(ROOT)
    env.update(
        {
            "TM_VOICE_ROOT": str(ROOT),
            "TM_REALTIME_WORKER": "1",
            "TM_WORKER_KIND": "rvc",
            "PYTHONUNBUFFERED": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "weight_root": "assets/weights",
            "weight_uvr5_root": "assets/uvr5_weights",
            "index_root": "logs",
            "outside_index_root": "assets/indices",
            "rmvpe_root": "assets/rmvpe",
            "TEMP": str(ROOT / "TEMP"),
            "TMP": str(ROOT / "TEMP"),
            "TMPDIR": str(ROOT / "TEMP"),
            "TM_ACCEL": os.environ.get("TM_ACCEL", "auto"),
        }
    )
    (ROOT / "TEMP").mkdir(exist_ok=True)
    return env


def _wait(pred, timeout_s: float) -> tuple[dict, float] | tuple[None, float]:
    """轮询 status.json 直到 pred 为真或超时。返回 (status, 等待秒数)。"""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        st = _read_json(STATUS)
        if pred(st):
            return st, time.monotonic() - t0
        time.sleep(_POLL_S)
    return None, time.monotonic() - t0


def _send_command(cmd: str) -> int:
    """与 Rust write_command 同协议：command.seq 递增，command.json 原子写。"""
    cur = 0
    if SEQ.is_file():
        try:
            cur = int(SEQ.read_text().strip() or 0)
        except ValueError:
            cur = 0
    seq = cur + 1
    SEQ.write_text(str(seq))
    tmp = COMMAND.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"seq": seq, "cmd": cmd, "ts": time.time()}, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(tmp, COMMAND)
    return seq


def _wait_log_token(path: Path, token: str, timeout_s: float) -> float | None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        try:
            if token in path.read_text(encoding="utf-8", errors="replace"):
                return time.monotonic() - t0
        except OSError:
            pass
        time.sleep(0.2)
    return None


def run_once(idx: int, *, prewarm: bool) -> dict:
    """测一次：spawn → ready →（可选 prewarm）→ 命令往返 → quit。"""
    rec: dict = {"ts": datetime.now().isoformat(timespec="seconds"), "run": idx}
    # 清掉上一轮残留的信箱，并把 status 重置成 starting —— 与壳层
    # start_worker_kind 一样先写启动标记，否则读到的是上次会话留下的
    # idle/pid，spawn_ms 会秒回 0。
    try:
        COMMAND.unlink()
    except OSError:
        pass
    CONTROL.mkdir(parents=True, exist_ok=True)
    st_old = _read_json(STATUS)
    st_old.update(
        {
            "state": "starting",
            "pid": 0,
            "worker_boot_ts": 0,
            "last_cmd_seq": 0,
            "error": "",
            "ts": time.time(),
        }
    )
    tmp = STATUS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st_old, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, STATUS)

    # prewarm 完成只在日志里出现（"预热：完成"），需要可见输出 → python.exe；
    # 纯启动基线用 pythonw.exe，和真实路径一致。
    exe = ROOT / "Runtime" / ("python.exe" if prewarm else "pythonw.exe")
    if not exe.is_file():
        exe = Path(sys.executable)
    out = open(OUT_LOG, "ab", buffering=0) if prewarm else subprocess.DEVNULL

    t0 = time.monotonic()
    proc = subprocess.Popen(
        [str(exe), str(ROOT / "tools" / "realtime_worker.py")],
        cwd=str(ROOT),
        env=_env(),
        stdin=subprocess.DEVNULL,
        stdout=out if prewarm else subprocess.DEVNULL,
        stderr=out if prewarm else subprocess.DEVNULL,
    )
    rec["worker_pid"] = proc.pid
    try:
        st, rec["spawn_ms"] = _wait(lambda s: int(s.get("pid") or 0) > 0, _READY_TIMEOUT_S)
        if st is None:
            rec["error"] = "timeout waiting first status"
            return rec
        rec["spawn_ms"] *= 1000
        st, wait_ready = _wait(lambda s: s.get("state") == "idle", _READY_TIMEOUT_S)
        rec["ready_ms"] = (rec["spawn_ms"] / 1000 + wait_ready) * 1000
        if st is None:
            rec["error"] = "timeout waiting idle"
            return rec

        if prewarm:
            t1 = time.monotonic()
            _send_command("prewarm")
            done = _wait_log_token(OUT_LOG, "预热：完成", 120.0)
            if done is None:
                # 没预热也可能是不该预热（没选音色 / DSP 模式）——记失败原因看日志。
                tail = OUT_LOG.read_text(encoding="utf-8", errors="replace")[-800:]
                rec["prewarm_ms"] = None
                rec["prewarm_note"] = tail.strip().splitlines()[-1] if tail.strip() else "no log"
            else:
                rec["prewarm_ms"] = round(done * 1000)

        seq = _send_command("list_devices")
        t1 = time.monotonic()
        st, wait = _wait(
            lambda s: int(s.get("last_cmd_seq") or 0) >= seq, _ACK_TIMEOUT_S
        )
        rec["cmd_ack_ms"] = round(wait * 1000) if st else None
        rec["devices_seen"] = bool(
            (st or {}).get("input_devices") and (st or {}).get("hostapis")
        )
    finally:
        try:
            _send_command("quit")
        except OSError:
            pass
        try:
            proc.wait(timeout=_QUIT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        if hasattr(out, "close"):
            out.close()
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description="启动/命令链路测量基线（不开流）")
    ap.add_argument("-n", type=int, default=1, help="连测次数（默认 1）")
    ap.add_argument("--prewarm", action="store_true", help="就绪后加测预热（需已选音色）")
    args = ap.parse_args()

    if _worker_running():
        pid = _worker_running()
        print(f"已有 worker 在跑（pid={pid}）：为了不打扰正在使用的会话，本次不测。")
        print("请先退出软件/停掉 worker 再运行。")
        return 2
    if not (ROOT / "Runtime").is_dir():
        print("找不到 Runtime/ —— 基线要用打包同款的嵌入式 Python。")
        return 3

    RESULTS.parent.mkdir(exist_ok=True)
    for i in range(1, args.n + 1):
        rec = run_once(i, prewarm=args.prewarm)
        RESULTS.open("a", encoding="utf-8").write(
            json.dumps(rec, ensure_ascii=False) + "\n"
        )
        line = (
            f"#{i} spawn={rec.get('spawn_ms', 0):.0f}ms "
            f"ready={rec.get('ready_ms', 0):.0f}ms "
            f"cmd_ack={rec.get('cmd_ack_ms')}ms"
        )
        if args.prewarm:
            line += f" prewarm={rec.get('prewarm_ms')}ms"
        if rec.get("error"):
            line += f"  [error] {rec['error']}"
        print(line)

    print(f"\n记录已追加到 {RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
