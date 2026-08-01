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
  if (st.state === "error" && st.error) return String(st.error).slice(0, 48);
  if (st.message) return String(st.message).slice(0, 48);
  const delay = Number(st.delay_ms || 0);
  const infer = Number(st.infer_ms || 0);
  if (st.state === "running" && (delay > 0 || infer > 0)) {
    return `延迟 ${delay} ms · 推理 ${infer} ms`;
  }
  if (st.worker_alive) return "就绪";
  return "等待引擎启动";
}
