# -*- coding: utf-8 -*-
"""Stable status message codes for the realtime worker.

The shell (Tauri) localizes these via ``app/i18n/locales/*/msg`` keys.
Worker may still write a Chinese ``message`` as fallback for old shells /
log readers; when ``message_code`` is present the shell prefers the locale
string.

Keep codes short, dotted, and stable — never renumber for wording tweaks.
"""

from __future__ import annotations

# process lifecycle
ENGINE_STARTING = "engine.starting"
ENGINE_MISSING_GUI = "engine.missing_gui"
ENGINE_CRASH_LOAD = "engine.crash_load"
ENGINE_READY = "engine.ready"
ENGINE_IDLE = "engine.idle"

# runtime / provision (also used by shell-side checks)
RUNTIME_NOT_READY = "runtime.not_ready"
RUNTIME_MISSING_PYTHON = "runtime.missing_python"

# voice conversion
VC_NEED_MODEL = "vc.need_model"
VC_LOADING_MODEL = "vc.loading_model"

# Chinese fallbacks (zh-CN). Must match app/i18n/locales/zh-CN.json msg.*
_FALLBACK_ZH: dict[str, str] = {
    ENGINE_STARTING: "引擎进程已启动，正在加载…",
    ENGINE_MISSING_GUI: "安装不完整：缺少引擎主程序",
    ENGINE_CRASH_LOAD: "引擎加载时崩溃，详见日志",
    ENGINE_READY: "引擎就绪",
    ENGINE_IDLE: "待命",
    RUNTIME_NOT_READY: "运行时未就绪，请先完成补全",
    RUNTIME_MISSING_PYTHON: "找不到 Runtime\\python.exe",
    VC_NEED_MODEL: "请先选择音色模型",
    VC_LOADING_MODEL: "正在加载音色模型…",
}


def fallback_message(code: str) -> str:
    return _FALLBACK_ZH.get(code, code)


def status_fields(code: str, **extra):
    """Fields to merge into write_status(..., **status_fields(CODE))."""
    out = {
        "message_code": code,
        "message": fallback_message(code),
    }
    out.update(extra)
    return out
