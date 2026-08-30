# -*- coding: utf-8 -*-
"""Stable status message codes for the realtime worker.

The shell (Tauri) localizes these via ``app/i18n/locales/*/msg`` keys.
Worker may still write a Chinese ``message`` as fallback for old shells /
log readers; when ``message_code`` is present the shell prefers the locale
string.

Keep codes short, dotted, and stable — never renumber for wording tweaks.
"""

from __future__ import annotations

import json

# process lifecycle
# engine.launching 由 shell 侧写（spawn 之前那一下），worker 自己不发；
# 登记在这里是为了这张表就是所有状态码的清单，不用两处对照着看。
ENGINE_LAUNCHING = "engine.launching"
ENGINE_STARTING = "engine.starting"
ENGINE_IMPORTING = "engine.importing"
ENGINE_DSP_STARTING = "engine.dsp_starting"
ENGINE_MISSING_GUI = "engine.missing_gui"
ENGINE_CRASH_LOAD = "engine.crash_load"
# 引擎 .py 在用户盘上被改坏（杀软挑走内容 / 断电后零填充），重启救不了，
# 界面要直接说「重跑安装包覆盖修复」。
ENGINE_FILES_CORRUPT = "engine.files_corrupt"
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
VC_NON_ASCII_PATH = "vc.non_ascii_path"
VC_RUNNING = "vc.running"
VC_BAD_SETTINGS = "vc.bad_settings"
VC_START_FAILED = "vc.start_failed"
VC_STOP_FAILED = "vc.stop_failed"
VC_PARAMS_APPLIED = "vc.params_applied"
VC_UNKNOWN_CMD = "vc.unknown_cmd"

# ---------------------------------------------------------------------------
# 一次性任务 worker（分离 / 训练 / STS / ckpt）
#
# 这几个不写 status.json，是把 JSON 行打到 stdout 由壳读。壳侧
# `i18n::t_worker_msg` 认 message_code + message_params，按界面语言取译文；
# 没有 code 或语言包里查不到时，回退到这里的中文 —— 所以新增消息时先加码，
# 忘了翻译也只是显示中文，不会变成空白或者一串 msg.xxx。
#
# 占位符一律用 {名字}，别用 %s：译文里语序会变，位置参数对不上。
# ---------------------------------------------------------------------------

# 人声分离
SEP_NO_REQUEST = "sep.no_request"
SEP_BAD_REQUEST = "sep.bad_request"
SEP_EMPTY_FIELDS = "sep.empty_fields"
SEP_FAILED = "sep.failed"

# ckpt 工具（改信息 / 融合 / 提取小模型 / 导出 ONNX）
CKPT_NAME_EMPTY = "ckpt.name_empty"
CKPT_NAME_BAD_CHARS = "ckpt.name_bad_chars"
CKPT_NAME_INVALID = "ckpt.name_invalid"
CKPT_MISSING_MODEL = "ckpt.missing_model"
CKPT_MISSING_MODEL_A = "ckpt.missing_model_a"
CKPT_MISSING_MODEL_B = "ckpt.missing_model_b"
CKPT_MISSING_BIG_MODEL = "ckpt.missing_big_model"
CKPT_INFO_SAVED = "ckpt.info_saved"
CKPT_BAD_SAMPLE_RATE = "ckpt.bad_sample_rate"
CKPT_MERGED = "ckpt.merged"
CKPT_EXTRACTED = "ckpt.extracted"
CKPT_MKDIR_FAILED = "ckpt.mkdir_failed"
CKPT_ONNX_MISSING_DEPS = "ckpt.onnx_missing_deps"
CKPT_ONNX_FAILED = "ckpt.onnx_failed"
CKPT_USAGE = "ckpt.usage"
CKPT_BAD_REQUEST = "ckpt.bad_request"
CKPT_STARTING = "ckpt.starting"
CKPT_UNKNOWN_ACTION = "ckpt.unknown_action"

# 语音转换（STS：批量转文件）
STS_NO_REQUEST = "sts.no_request"
STS_BAD_REQUEST = "sts.bad_request"
STS_F0_CURVE_MISSING = "sts.f0_curve_missing"
STS_EMPTY_FIELDS = "sts.empty_fields"
STS_MODEL_MISSING = "sts.model_missing"
STS_NO_AUDIO = "sts.no_audio"
STS_LOAD_FAILED = "sts.load_failed"
STS_ALL_FAILED = "sts.all_failed"
STS_DONE = "sts.done"
# 「热路径接不上，请走冷路径」的信号，不是终端错误。壳靠这个码把它归成
# HotError::Unavailable 并自动回退；归错了用户就会看到一句面向开发的状态。
STS_HOT_UNAVAILABLE = "sts.hot_unavailable"
# 同样是「请走冷路径」，但原因不是没加载音色，而是显卡后端缺算子。分成两个
# 码是为了让用户看到的那句话是真的：热路径的模型是实时引擎的，不能挪到 CPU，
# 冷路径的 worker 自己拥有模型，退 CPU 重试是安全的。
STS_HOT_DML_FALLBACK = "sts.hot_dml_fallback"
# 选到的是训练存档（G_/D_ 开头）而不是音色模型。单独立码是因为壳侧能给它配
# 一个「打开训练窗」的按钮 —— 那份存档得先在「模型提取」里转成音色才能用。
STS_MODEL_IS_ARCHIVE = "sts.model_is_archive"
# 降质回退：这一次转换退到了阶梯的哪一档、为什么。
#
# **降质是自动的，但不能是无声的。** 用户看到的是「怎么这么慢」，
# 而真正发生的是显存不够、退到了 CPU —— 不说出来他会以为软件坏了，
# 说出来他知道该关掉别的占显卡的程序，或者换个更小的档。
#
# 只在「根本出不来结果」时才退（显存不足、后端缺算子），**不因为慢而退**：
# 慢没有客观门限，误判的代价是把用户特意选的高质量选项改掉。
STS_DEGRADED = "sts.degraded"

# 训练
TRAIN_STEP_FAILED = "train.step_failed"
TRAIN_PREPROCESS_FAILED = "train.preprocess_failed"
TRAIN_F0_FAILED = "train.f0_failed"
TRAIN_FEATURE_FAILED = "train.feature_failed"
TRAIN_TRAIN_FAILED = "train.train_failed"
TRAIN_NO_SLICES = "train.no_slices"
TRAIN_RMVPE_MISSING = "train.rmvpe_missing"
TRAIN_EXTRACT_F0 = "train.extract_f0"
TRAIN_NO_F0 = "train.no_f0"
TRAIN_EXTRACT_FEATURE = "train.extract_feature"
TRAIN_NO_FEATURE = "train.no_feature"
TRAIN_NO_SAMPLES = "train.no_samples"
TRAIN_MUTE_MISSING = "train.mute_missing"
TRAIN_CONFIG_MISSING = "train.config_missing"
TRAIN_PRETRAINED_MISSING = "train.pretrained_missing"
TRAIN_COLLECT_FEATURE = "train.collect_feature"
TRAIN_NO_FEATURE_DIR = "train.no_feature_dir"
TRAIN_NO_FEATURE_FILE = "train.no_feature_file"
TRAIN_KMEANS = "train.kmeans"
TRAIN_KMEANS_FAILED = "train.kmeans_failed"
TRAIN_BUILD_INDEX = "train.build_index"
TRAIN_INDEX_DONE = "train.index_done"
TRAIN_INDEX_FAILED = "train.index_failed"
TRAIN_NAME_INVALID = "train.name_invalid"
TRAIN_BAD_SAMPLE_RATE = "train.bad_sample_rate"
TRAIN_BAD_F0_METHOD = "train.bad_f0_method"
TRAIN_USAGE = "train.usage"
TRAIN_BAD_REQUEST = "train.bad_request"
TRAIN_STARTED = "train.started"
TRAIN_EPOCH = "train.epoch"
TRAIN_PREPROCESS = "train.preprocess"
TRAIN_PREPARING = "train.preparing"
TRAIN_REUSE_SR = "train.reuse_sr"
TRAIN_SKIP_PREPROCESS = "train.skip_preprocess"
TRAIN_DATASET_MISSING = "train.dataset_missing"
TRAIN_SKIP_F0 = "train.skip_f0"
TRAIN_SKIP_FEATURE = "train.skip_feature"
TRAIN_CANCELLED = "train.cancelled"
TRAIN_NO_WEIGHT = "train.no_weight"
TRAIN_OOM = "train.oom"
TRAIN_PREPROCESS_PARTIAL = "train.preprocess_partial"
TRAIN_RESUME_F0_PARTIAL = "train.resume_f0_partial"
TRAIN_RESUME_FEATURE_PARTIAL = "train.resume_feature_partial"


# Chinese fallbacks (zh-CN). Must match app/i18n/locales/zh-CN.json msg.*
_FALLBACK_ZH: dict[str, str] = {
    SEP_NO_REQUEST: "缺请求文件参数",
    SEP_BAD_REQUEST: "无法读取请求文件：{error}",
    SEP_EMPTY_FIELDS: "模型 / 输入 / 输出 都不能为空",
    SEP_FAILED: "分离失败，详见日志",
    CKPT_NAME_EMPTY: "保存名不能为空",
    CKPT_NAME_BAD_CHARS: "保存名不能含 \\ / : * ? \" < > |",
    CKPT_NAME_INVALID: "保存名不合法",
    CKPT_MISSING_MODEL: "模型不存在：{path}",
    CKPT_MISSING_MODEL_A: "A 模型不存在：{path}",
    CKPT_MISSING_MODEL_B: "B 模型不存在：{path}",
    CKPT_MISSING_BIG_MODEL: "大模型不存在：{path}",
    CKPT_INFO_SAVED: "已改模型信息",
    CKPT_BAD_SAMPLE_RATE: "不支持的采样率：{sample_rate}",
    CKPT_MERGED: "融合完成",
    CKPT_EXTRACTED: "已提取小模型",
    CKPT_MKDIR_FAILED: "无法创建输出目录：{error}",
    CKPT_ONNX_MISSING_DEPS: "当前 Runtime 没有 ONNX 导出依赖（onnx / onnxsim）：{error}",
    CKPT_ONNX_FAILED: "ONNX 导出失败：{error}",
    CKPT_USAGE: "用法：ckpt_worker.py <request.json>",
    CKPT_BAD_REQUEST: "无法读取请求文件：{error}",
    CKPT_STARTING: "开始…",
    CKPT_UNKNOWN_ACTION: "未知操作：{action}",
    STS_NO_REQUEST: "缺请求文件参数",
    STS_BAD_REQUEST: "无法读取请求文件：{error}",
    STS_F0_CURVE_MISSING: "找不到 F0 曲线文件：{path}",
    STS_EMPTY_FIELDS: "输入 / 输出 / 音色模型 都不能为空",
    STS_MODEL_MISSING: "找不到音色模型：{model}",
    STS_NO_AUDIO: "没有找到可转换的音频（支持 wav/mp3/flac/ogg/m4a 等）",
    STS_LOAD_FAILED: "加载模型失败：{error}",
    STS_ALL_FAILED: "{total} 个文件全部转换失败。第一个原因：{first}",
    STS_DONE: "完成 {done} 个，跳过 {skipped} 个",
    STS_HOT_UNAVAILABLE: "实时引擎里没有已加载的音色，改用独立进程转换（会慢一些）。",
    STS_HOT_DML_FALLBACK: "显卡后端（DirectML）不支持这一步，改用独立进程转换（会慢一些）。",
    STS_DEGRADED: "这台机器跑不动原来那档（{why}），已自动降到「{rung}」继续，会慢一些。",
    STS_MODEL_IS_ARCHIVE: (
        "选到的是训练存档（G_ / D_ 开头那种），不能直接当音色用。\n"
        "请先在训练窗「进阶设置 → 模型提取」里把它转成音色模型，再来转换。"
    ),
    TRAIN_STEP_FAILED: "该步骤失败（退出码 {code}），详情见 {log}",
    TRAIN_PREPROCESS_FAILED: "数据预处理失败（退出码 {code}），详情见 {log}",
    TRAIN_F0_FAILED: "音高提取失败（退出码 {code}），详情见 {log}",
    TRAIN_FEATURE_FAILED: "特征提取失败（退出码 {code}），详情见 {log}",
    TRAIN_TRAIN_FAILED: "训练失败（退出码 {code}），详情见 {log}",
    TRAIN_NO_SLICES: "预处理没有产出任何切片。检查数据集里是不是没有可读的音频文件。",
    TRAIN_RMVPE_MISSING: "缺少 assets/rmvpe/rmvpe.pt，请先补全引擎资源。",
    TRAIN_EXTRACT_F0: "提取音高…",
    TRAIN_NO_F0: "音高提取没有产出。换一种音高算法再试。",
    TRAIN_EXTRACT_FEATURE: "提取音色特征…",
    TRAIN_NO_FEATURE: "特征提取没有产出。通常为 assets/hubert/hubert_base.pt 缺失或损坏。",
    TRAIN_NO_SAMPLES: "四类训练产物的条目无法对应，没有可用的训练样本。建议清空该实验后重新开始。",
    TRAIN_MUTE_MISSING: "缺少 logs/mute 静音样本，安装不完整。",
    TRAIN_CONFIG_MISSING: "缺少 configs/{name}",
    TRAIN_PRETRAINED_MISSING: "缺少 {sample_rate} 的底模（assets/pretrained_v2/f0G{sample_rate}.pth）。从零训练需要数十小时与上百小时的素材，本软件不支持该方式，请先下载对应底模。",
    TRAIN_COLLECT_FEATURE: "收集特征…",
    TRAIN_NO_FEATURE_DIR: "没有特征目录，跳过索引",
    TRAIN_NO_FEATURE_FILE: "没有特征文件，跳过索引",
    TRAIN_KMEANS: "特征过多，先聚类到 1 万个中心…",
    TRAIN_KMEANS_FAILED: "聚类失败，改用全量特征：{error}",
    TRAIN_BUILD_INDEX: "训练索引（{count} 条特征）…",
    TRAIN_INDEX_DONE: "索引完成",
    TRAIN_INDEX_FAILED: "索引构建失败（{error}）。音色模型已训练完成，仍可正常使用。",
    TRAIN_NAME_INVALID: "音色名不能为空，也不能含 \\ / : * ? \" < > |",
    TRAIN_BAD_SAMPLE_RATE: "不支持的采样率：{sample_rate}",
    TRAIN_BAD_F0_METHOD: "不支持的音高算法：{method}",
    TRAIN_USAGE: "用法：train_worker.py <request.json>",
    TRAIN_BAD_REQUEST: "无法读取请求文件：{error}",
    TRAIN_STARTED: "开始训练 {exp}",
    TRAIN_EPOCH: "第 {epoch} / {total} 轮",
    TRAIN_PREPROCESS: "切片与重采样…",
    TRAIN_PREPARING: "准备训练（{count} 条样本）…",
    TRAIN_REUSE_SR: "沿用已有切片的采样率 {actual}（这次选的是 {picked}）",
    TRAIN_SKIP_PREPROCESS: "已有切片，跳过预处理",
    TRAIN_DATASET_MISSING: "数据集目录不存在：{path}",
    TRAIN_SKIP_F0: "已有音高，跳过",
    TRAIN_SKIP_FEATURE: "已有特征，跳过",
    TRAIN_CANCELLED: "已取消",
    TRAIN_NO_WEIGHT: "训练结束但没找到 {name}。查看 logs/{exp}/train.log。",
    TRAIN_OOM: "显存不足，训练中断。可以把批大小（当前 {batch}）调小、关掉其他占显存的程序后重试。详情见 {log}",
    TRAIN_PREPROCESS_PARTIAL: "{failed} 个音频没能读取（共 {total} 个），只用成功的 {ok} 个继续。详情见 {log}",
    TRAIN_RESUME_F0_PARTIAL: "上次音高只提取了 {done}/{total}，这次把剩下的补齐。",
    TRAIN_RESUME_FEATURE_PARTIAL: "上次特征只提取了 {done}/{total}，这次把剩下的补齐。",
    ENGINE_LAUNCHING: "正在启动引擎进程…",
    ENGINE_STARTING: "引擎进程已启动，正在加载运行库…",
    ENGINE_IMPORTING: "正在导入推理库（可能需要十几秒）…",
    ENGINE_DSP_STARTING: "正在启动 DSP 变声…",
    ENGINE_MISSING_GUI: "安装不完整：缺少引擎主程序",
    ENGINE_CRASH_LOAD: "引擎加载时崩溃，详见日志",
    ENGINE_FILES_CORRUPT: "引擎程序文件损坏（{files}）。重新运行安装包覆盖安装即可修复，音色与运行时会保留",
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
    VC_NON_ASCII_PATH: "路径含有中文或其他非英文字符，检索库无法读取。请把软件或音色移到纯英文文件夹（例如 D:\\RVCFabric）后再试。",
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


def _jsonable(v):
    """把参数值收敛成能进 JSON 的东西。

    调用点传进来的常常是异常对象、`Path`、numpy 的整数 —— 以前这些值是被
    f-string / `%` 就地拼进句子里的，从来没单独出现过；改成 `message_params`
    之后它们要自己走一趟 `json.dumps`，而 `Exception` 和 `Path` 都不可序列化，
    结果是整条消息连同它要报告的那个错误一起炸掉。
    """
    if isinstance(v, bool) or isinstance(v, str):
        return v
    if isinstance(v, int) or isinstance(v, float):
        # numpy 的 int64/float64 不是 int/float 的子类的场景也有，靠下面兜底。
        try:
            json.dumps(v)
            return v
        except (TypeError, ValueError):
            return str(v)
    return str(v)


def status_fields(code: str, params: dict | None = None, **extra):
    """Fields to merge into write_status(..., **status_fields(CODE)).

    `params` 里的值会随状态一起写进 `message_params`，壳层按当前界面语言把
    同一个 `{名字}` 填进译文里 —— 所以带变量的消息也能翻译，不用退回中文。
    """
    clean = {k: _jsonable(v) for k, v in params.items()} if params else None
    out = {
        "message_code": code,
        "message": fallback_message(code, clean),
    }
    if clean:
        out["message_params"] = clean
    out.update(extra)
    return out


def msg_fields(code: str, params: dict | None = None) -> dict:
    """Fields to splat into a one-shot worker's ``emit(phase=…, **msg_fields(CODE))``.

    和 `status_fields` 同一件事，只是这几个 worker 不写 status.json，而是把
    JSON 行打到 stdout。分开命名是为了别让人以为这里会落盘。

    壳侧按 `message_code` + `message_params` 取当前语言的译文；查不到就用这里
    生成的中文 `message` 兜底，所以新增消息忘了翻译只是显示中文，不会开天窗。
    """
    return status_fields(code, params)
