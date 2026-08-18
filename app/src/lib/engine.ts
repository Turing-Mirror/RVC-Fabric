import { invoke } from "@tauri-apps/api/core";
import {  tStatic as t, tStatic  } from "../i18n";

/** Mirrors User_Data/runtime_control/status.json + shell extras. */
export type EngineStatus = {
  state?: string;
  error?: string;
  message?: string;
  message_code?: string;
  /** 0–100. <100 means a load/swap is in flight; 100 or missing means idle. */
  progress?: number | null;
  delay_ms?: number;
  /** 实测端到端延迟。delay_ms 是公式估算，这个是实际量出来的。 */
  real_delay_ms?: number;
  infer_ms?: number;
  /** 累计输出欠载次数。撕裂判据看它的增速，不看绝对值。 */
  underrun?: number;
  samplerate?: number;
  pid?: number;
  worker_alive?: boolean;
  product_root?: string;
  hostapis?: string[];
  input_devices?: string[];
  output_devices?: string[];
  sg_hostapi?: string;
  sg_input_device?: string;
  sg_output_device?: string;
  last_input_db?: number;
  meter_level?: number;
  threshold_meter?: number;
  threhold?: number;
  /** "fx" = 纯 DSP，不上 RVC。 */
  function?: string;
  dsp_only?: boolean;
  worker_kind?: string;
  [key: string]: unknown;
};

export type ProvisionStatus = {
  runtime_ready?: boolean;
  need_provision?: boolean;
  runtime_python?: string | null;
  worker_script_ok?: boolean;
  product_root?: string;
  gpus?: string[];
  /** 只含 N 卡，保持系统枚举顺序。下标就是 CUDA 序号，「主显卡」下拉用它。 */
  nvidia_gpus?: string[];
  recommended_variant?: string;
  recommend_reason?: string;
  recommended_label?: string;
  recommended_size_bytes?: number;
  recommended_size_label?: string;
  installed_variant?: string | null;
  download_supported?: boolean;
  busy?: boolean;
  /** Per-variant size so the start button tracks the user's selection. */
  variants?: {
    id: string;
    label: string;
    size_bytes?: number;
    size_label?: string;
  }[];
  message?: string;
};

export type ProvisionProgress = {
  phase?: string;
  done?: number;
  total?: number;
  percent?: number;
  /** Instantaneous / short-window bytes per second (when known). */
  speed_bps?: number;
  speed_label?: string;
  message?: string;
};

function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function getEngineStatus(): Promise<EngineStatus> {
  if (!isTauri()) {
    return {
      state: "idle",
      message: t("s.265e64c266"),
      worker_alive: false,
      meter_level: 0,
      threshold_meter: 0.25,
    };
  }
  return invoke<EngineStatus>("engine_status");
}

export async function ensureEngine(): Promise<EngineStatus> {
  if (!isTauri()) {
    return getEngineStatus();
  }
  return invoke<EngineStatus>("engine_ensure");
}

export async function startWorker(): Promise<EngineStatus> {
  if (!isTauri()) return getEngineStatus();
  return invoke<EngineStatus>("engine_start_worker");
}

export async function startVc(): Promise<EngineStatus> {
  if (!isTauri()) {
    return {
      state: "error",
      error: tStatic("engine.browserNoVc"),
      worker_alive: false,
    };
  }
  return invoke<EngineStatus>("engine_start_vc");
}

export async function stopVc(force = false): Promise<EngineStatus> {
  if (!isTauri()) return getEngineStatus();
  return invoke<EngineStatus>("engine_stop_vc", { force });
}

export async function forceKillEngine(): Promise<EngineStatus> {
  if (!isTauri()) return getEngineStatus();
  return invoke<EngineStatus>("engine_force_kill");
}

export async function activateDsp(id: string): Promise<void> {
  if (!isTauri()) return;
  await invoke("dsp_activate", { id });
}

export async function deactivateDsp(): Promise<void> {
  if (!isTauri()) return;
  await invoke("dsp_deactivate");
}

export async function setHot(params: {
  pitch?: number;
  formant?: number;
  /** "fx" = 无模型 DSP 变声，整条 RVC 都不走。 */
  function?: "vc" | "bypass" | "im" | "fx";
  threhold?: number;
  index_rate?: number;
  rms_mix_rate?: number;
  /** 无模型 DSP 变声。三个都是热键，换预设不重开流。 */
  dsp_enabled?: boolean;
  dsp_preset?: string;
  dsp_params?: Record<string, Record<string, number>>;
}): Promise<number> {
  if (!isTauri()) return 0;
  return invoke<number>("engine_set_hot", params);
}

/**
 * 变声中换音色，不重开流。
 *
 * 不传路径：要换成哪个，`voices_select` 刚写进配置里了，shell 自己读得到。
 * 引擎在两块音频之间把 RVC 实例换掉，设备、缓冲区、延迟设置一样不动。
 *
 * worker 没在跑时后端会报错 —— 那不是故障，是「没什么可热更新的」，
 * 调用方按无害处理。
 */
export async function swapModel(): Promise<number> {
  if (!isTauri()) return 0;
  return invoke<number>("engine_swap_model");
}

export async function listDevices(): Promise<EngineStatus> {
  if (!isTauri()) return getEngineStatus();
  return invoke<EngineStatus>("engine_list_devices");
}

export async function getProvisionStatus(): Promise<ProvisionStatus> {
  if (!isTauri()) {
    return {
      runtime_ready: false,
      need_provision: true,
      message: tStatic("engine.browserNoRuntime"),
      download_supported: false,
    };
  }
  return invoke<ProvisionStatus>("provision_status");
}

export async function startProvision(
  variant: string,
  force = false,
): Promise<{ ok?: boolean; message?: string; variant?: string }> {
  if (!isTauri()) {
    return { ok: false, message: tStatic("engine.browserNoDownload") };
  }
  return invoke("provision_start", { variant, force });
}

export async function cancelProvision(): Promise<void> {
  if (!isTauri()) return;
  await invoke("provision_cancel");
}

const LOAD_CODES = new Set([
  "engine.starting",
  "engine.importing",
  "vc.loading_model",
  "vc.loading_index",
  "vc.loading_hubert",
  "vc.loading_net",
  "vc.warmup",
  "vc.opening_stream",
  "vc.swapping",
]);

const BOOT_CODES = new Set([
  "engine.launching",
  "engine.starting",
  "engine.importing",
]);

export function loadProgress(st: EngineStatus): number | null {
  const p = Number(st.progress);
  if (Number.isFinite(p) && p >= 0 && p < 100) return p;
  return null;
}

export function isLoadPhase(st: EngineStatus): boolean {
  const code = String(st.message_code || "");
  // 开机导入推理库的码会粘在 status.json 里。引擎已经 idle 之后
  // 不能再当成「启动中」，否则底栏一直写着「正在导入推理库」。
  if (BOOT_CODES.has(code)) return st.state === "starting";
  if (LOAD_CODES.has(code)) return true;
  if (st.state === "starting") return true;
  return loadProgress(st) != null;
}

export function statusTitle(st: EngineStatus): string {
  const s = st.state || "idle";
  const code = String(st.message_code || "");
  if (code === "vc.swapping" || (s === "running" && isLoadPhase(st))) {
    return tStatic("dock.switching");
  }
  if (s === "running") return tStatic("dock.converting");
  if (s === "starting" || isLoadPhase(st)) return tStatic("dock.starting");
  if (s === "stopping") return tStatic("dock.stopping");
  if (s === "error") return tStatic("dock.engineError");
  if (st.worker_alive) return tStatic("dock.engineReady");
  return tStatic("dock.engineDown");
}

export function statusSub(st: EngineStatus): string {
  const code = String(st.message_code || "");
  const staleBoot =
    BOOT_CODES.has(code) && st.state !== "starting";
  // 加载/切换时优先展示分阶段说明，不要被延迟读数盖掉。
  if (!staleBoot && isLoadPhase(st) && st.message) {
    return String(st.message).slice(0, 80);
  }
  if (String(st.message_code || "") === "vc.swap_failed" && st.message) {
    return String(st.message).slice(0, 80);
  }
  // 变声跑起来之后，副标题的位置留给延迟读数 —— 标题那行已经写着「变声中」，
  // 再把 message 重复一遍就是浪费。status.json 是合并写的，message 会一直
  // 停在最后一次设置的值上，所以这条必须排在 message 前面，否则延迟永远
  // 显示不出来。
  // 有实测值就用实测的：公式那个假设推理总能在一个块内跑完，跟不上时
  // 真实延迟涨了它却纹丝不动 —— 用户看到「延迟 180ms」却觉得慢半拍。
  const delay = Number(st.real_delay_ms || st.delay_ms || 0);
  const infer = Number(st.infer_ms || 0);
  if (st.state === "running" && (delay > 0 || infer > 0)) {
    const dsp =
      st.dsp_only === true ||
      st.function === "fx" ||
      st.worker_kind === "dsp";
    return tStatic(dsp ? "dock.delayLineDsp" : "dock.delayLine", {
      delay,
      infer,
    });
  }
  // Prefer shell-localized message (worker message_code resolved in Rust).
  // Fallback to raw message / error / idle labels.
  // Skip duplicate "engine ready" as subtitle — title already says it.
  if (st.message && !staleBoot) {
    const msg = String(st.message).slice(0, 80);
    const ready = tStatic("dock.engineReady");
    const readyMsg = tStatic("msg.engine.ready");
    if (
      st.state !== "running" &&
      st.state !== "error" &&
      (msg === ready ||
        msg === readyMsg ||
        msg === "引擎就绪" ||
        msg === "Engine ready")
    ) {
      return tStatic("dock.engineIdle");
    }
    return msg;
  }
  if (st.state === "error" && st.error) return String(st.error).slice(0, 80);
  if (st.worker_alive) return tStatic("dock.engineIdle");
  return tStatic("dock.waitStart");
}
