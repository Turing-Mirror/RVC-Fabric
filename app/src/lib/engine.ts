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

function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function getEngineStatus(): Promise<EngineStatus> {
  if (!isTauri()) {
    return {
      state: "idle",
      message: "浏览器预览（无 worker）",
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
    return { state: "error", error: "请在 Tauri 窗口中启动变声", worker_alive: false };
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
  if (st.error) return String(st.error).slice(0, 48);
  if (st.message) return String(st.message).slice(0, 48);
  const delay = Number(st.delay_ms || 0);
  const infer = Number(st.infer_ms || 0);
  if (st.state === "running" && (delay > 0 || infer > 0)) {
    return `延迟 ${delay} ms · 推理 ${infer} ms`;
  }
  if (st.worker_alive) return "就绪";
  return "等待 Runtime worker";
}
