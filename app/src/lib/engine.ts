import { invoke } from "@tauri-apps/api/core";

/** Mirrors User_Data/runtime_control/status.json + shell extras. */
export type EngineStatus = {
  state?: string;
  error?: string;
  message?: string;
  delay_ms?: number;
  infer_ms?: number;
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
      message: "浏览器预览（引擎未接入）",
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
      error: "请在软件窗口中启动变声",
      worker_alive: false,
    };
  }
  return invoke<EngineStatus>("engine_start_vc");
}

export async function stopVc(force = true): Promise<EngineStatus> {
  if (!isTauri()) return getEngineStatus();
  return invoke<EngineStatus>("engine_stop_vc", { force });
}

export async function forceKillEngine(): Promise<EngineStatus> {
  if (!isTauri()) return getEngineStatus();
  return invoke<EngineStatus>("engine_force_kill");
}

export async function setHot(params: {
  pitch?: number;
  formant?: number;
  function?: "vc" | "bypass" | "im";
  threhold?: number;
  index_rate?: number;
  rms_mix_rate?: number;
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
      message: "浏览器预览无法探测运行时",
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
    return { ok: false, message: "浏览器预览无法下载运行时" };
  }
  return invoke("provision_start", { variant, force });
}

export async function cancelProvision(): Promise<void> {
  if (!isTauri()) return;
  await invoke("provision_cancel");
}

export function statusTitle(st: EngineStatus): string {
  const s = st.state || "idle";
  if (s === "running") return "变声中";
  if (s === "starting") return "启动中";
  if (s === "stopping") return "停止中";
  if (s === "error") return "引擎错误";
  if (st.worker_alive) return "引擎待命";
  return "引擎未启动";
}

export function statusSub(st: EngineStatus): string {
  // 变声跑起来之后，副标题的位置留给延迟读数 —— 标题那行已经写着「变声中」，
  // 再把 message 重复一遍就是浪费。status.json 是合并写的，message 会一直
  // 停在最后一次设置的值上，所以这条必须排在 message 前面，否则延迟永远
  // 显示不出来。
  const delay = Number(st.delay_ms || 0);
  const infer = Number(st.infer_ms || 0);
  if (st.state === "running" && (delay > 0 || infer > 0)) {
    return `延迟 ${delay} ms · 推理 ${infer} ms`;
  }
  // message 在前、error 在后。引擎的 error 里装的是 Python 异常原文
  // （`RuntimeError: CUDA out of memory` 之类），那是给日志和诊断包看的；
  // 用户在底栏该看到的是同一次失败对应的中文 message。两者都没有才退回
  // error —— 有原文总比一片空白强。
  if (st.message) return String(st.message).slice(0, 48);
  if (st.state === "error" && st.error) return String(st.error).slice(0, 48);
  if (st.worker_alive) return "就绪";
  return "等待引擎启动";
}
