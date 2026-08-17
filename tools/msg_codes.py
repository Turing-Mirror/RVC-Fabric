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
# engine.launching 由 shell 侧写（spawn 之前那一下），worker 自己不发；
# 登记在这里是为了这张表就是所有状态码的清单，不用两处对照着看。
ENGINE_LAUNCHING = "engine.launching"
ENGINE_STARTING = "engine.starting"
ENGINE_IMPORTING = "engine.importing"
ENGINE_DSP_STARTING = "engine.dsp_starting"
ENGINE_MISSING_GUI = "engine.missing_gui"
ENGINE_CRASH_LOAD = "engine.crash_load"
ENGINE_READY = "engine.ready"
ENGINE_IDLE = "engine.idle"

# runtime / provision (also used by shell-side checks)
RUNTIME_NOT_READY = "runtime.not_ready"
RUNTIME_MISSING_PYTHON = "runtime.missing_python"

ENGINE_STOPPED = "engine.stopped"
ENGINE_QUIT = "engine.quit"
ENGINE_LOOP_ERROR = "engine.loop_error"

# devices
DEV_REFRESHED = "dev.refreshed"
DEV_LIST_FAILED = "dev.list_failed"
DEV_INVALID = "dev.invalid"

# voice conversion
VC_NEED_MODEL = "vc.need_model"
VC_LOADING_MODEL = "vc.loading_model"
VC_LOADING_INDEX = "vc.loading_index"
VC_LOADING_HUBERT = "vc.loading_hubert"
VC_LOADING_NET = "vc.loading_net"
VC_WARMUP = "vc.warmup"
VC_OPENING_STREAM = "vc.opening_stream"
VC_SWAPPING = "vc.swapping"
VC_SWAP_FAILED = "vc.swap_failed"
VC_PTH_MISSING = "vc.pth_missing"
VC_RUNNING = "vc.running"
VC_BAD_SETTINGS = "vc.bad_settings"
VC_START_FAILED = "vc.start_failed"
VC_STOP_FAILED = "vc.stop_failed"
VC_PARAMS_APPLIED = "vc.params_applied"
VC_UNKNOWN_CMD = "vc.unknown_cmd"

# Chinese fallbacks (zh-CN). Must match app/i18n/locales/zh-CN.json msg.*
_FALLBACK_ZH: dict[str, str] = {
    ENGINE_LAUNCHING: "正在启动引擎进程…",
    ENGINE_STARTING: "引擎进程已启动，正在加载运行库…",
    ENGINE_IMPORTING: "正在导入推理库（可能需要十几秒）…",
    ENGINE_DSP_STARTING: "正在启动 DSP 变声…",
    ENGINE_MISSING_GUI: "安装不完整：缺少引擎主程序",
    ENGINE_CRASH_LOAD: "引擎加载时崩溃，详见日志",
    ENGINE_READY: "引擎就绪",
    ENGINE_IDLE: "待命",
    ENGINE_STOPPED: "已停止",
    ENGINE_QUIT: "已退出",
    ENGINE_LOOP_ERROR: "引擎内部错误，详见日志",
    RUNTIME_NOT_READY: "运行时未就绪，请先完成补全",
    RUNTIME_MISSING_PYTHON: "找不到 Runtime\\python.exe",
    DEV_REFRESHED: "设备列表已刷新",
    DEV_LIST_FAILED: "读取设备失败",
    DEV_INVALID: "设备无效：{detail}",
    VC_NEED_MODEL: "请选择音色，或先选用一个 DSP 预设",
    VC_LOADING_MODEL: "正在加载音色模型…",
    VC_LOADING_INDEX: "正在加载检索库…",
    VC_LOADING_HUBERT: "正在加载特征模型（Hubert）…",
    VC_LOADING_NET: "正在加载合成器权重…",
    VC_WARMUP: "正在预热引擎（首次较慢）…",
    VC_OPENING_STREAM: "正在打开音频设备…",
    VC_SWAPPING: "正在切换音色，请稍候…",
    VC_SWAP_FAILED: "切换失败，仍在使用上一音色",
    VC_PTH_MISSING: "pth 文件不存在：{path}",
    VC_RUNNING: "变声中",
    VC_BAD_SETTINGS: "设置无效，无法开始变声",
    VC_START_FAILED: "启动失败",
    VC_STOP_FAILED: "停止失败",
    VC_PARAMS_APPLIED: "参数已应用",
    VC_UNKNOWN_CMD: "无法识别的指令：{action}",
}


def fallback_message(code: str, params: dict | None = None) -> str:
    """zh-CN 兜底文案。带 `{名字}` 占位的按 params 填。

    填不上就把占位原样留着 —— 与其抛异常把整条状态写没了，不如让人看见
    「设备无效：{detail}」并顺着这行去查是哪个调用忘了传参。
    """
    text = _FALLBACK_ZH.get(code, code)
    if params:
        for k, v in params.items():
            text = text.replace("{" + k + "}", str(v))
    return text


def status_fields(code: str, params: dict | None = None, **extra):
    """Fields to merge into write_status(..., **status_fields(CODE)).

    `params` 里的值会随状态一起写进 `message_params`，壳层按当前界面语言把
    同一个 `{名字}` 填进译文里 —— 所以带变量的消息也能翻译，不用退回中文。
    """
    out = {
        "message_code": code,
        "message": fallback_message(code, params),
    }
    if params:
        out["message_params"] = params
    out.update(extra)
    return out
