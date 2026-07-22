# -*- coding: utf-8 -*-
"""Install-path and User_Data writability checks (pre-flight)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from launcher.paths import ROOT, USER_DATA


def check_user_data_writable(root: Path | None = None) -> dict[str, Any]:
    """Try create + write under User_Data. Returns ok + message."""
    base = Path(root or ROOT)
    ud = base / "User_Data"
    out: dict[str, Any] = {
        "ok": False,
        "user_data": str(ud),
        "error": "",
        "path_has_space": " " in str(base),
        "path_non_ascii": any(ord(c) > 127 for c in str(base)),
    }
    try:
        ud.mkdir(parents=True, exist_ok=True)
        for sub in ("logs", "runtime_control", "models", "diagnostics"):
            (ud / sub).mkdir(parents=True, exist_ok=True)
        # write probe
        probe = ud / "logs" / ".write_probe"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink(missing_ok=True)  # type: ignore[arg-type]
        # tempfile in runtime_control
        fd, name = tempfile.mkstemp(prefix="tm_", dir=str(ud / "runtime_control"))
        os.close(fd)
        try:
            os.unlink(name)
        except OSError:
            pass
        out["ok"] = True
    except OSError as e:
        out["error"] = str(e)
        out["ok"] = False
    return out


def path_warnings(root: Path | None = None) -> list[str]:
    """Non-fatal warnings for support / UI."""
    base = Path(root or ROOT)
    tips: list[str] = []
    s = str(base)
    if " " in s:
        tips.append(
            f"安装路径含空格：{s}。一般可用；若 worker 异常可改到无空格路径（如 E:\\RVC_Fabric）。"
        )
    if any(ord(c) > 127 for c in s):
        tips.append(
            f"安装路径含中文/特殊字符：{s}。部分推理组件更稳妥在纯英文路径。"
        )
    w = check_user_data_writable(base)
    if not w.get("ok"):
        tips.append(
            "User_Data 不可写："
            + str(w.get("error") or "权限/只读")
            + "。请用管理员安装到可写目录，或关闭杀软占用后重试。"
        )
    return tips


def ensure_install_health(root: Path | None = None) -> dict[str, Any]:
    """Run all preflight checks; write log snippet when possible."""
    base = Path(root or ROOT)
    result = {
        "root": str(base),
        "writable": check_user_data_writable(base),
        "warnings": path_warnings(base),
    }
    try:
        from launcher.inuse_config import ensure_clean_inuse_config

        result["inuse_fixes"] = ensure_clean_inuse_config(base)
    except Exception as e:
        result["inuse_fixes"] = [f"inuse sanitize failed: {e}"]
    # best-effort log
    try:
        log = base / "User_Data" / "logs" / "install_health.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8", errors="replace") as f:
            f.write(f"root={base}\nwritable={result['writable']}\n")
            for w in result["warnings"]:
                f.write(f"warn: {w}\n")
            for n in result.get("inuse_fixes") or []:
                f.write(f"inuse: {n}\n")
            f.write("---\n")
    except Exception:
        pass
    return result
