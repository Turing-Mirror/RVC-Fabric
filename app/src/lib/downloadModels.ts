/**
 * 引擎资源 / 下载模型 入口分流。
 *
 * - **引擎资源**（hubert / rmvpe / ffmpeg）：开启变声、打开音频工具时若缺失，
 *   弹专用「补全引擎资源」窗，不跳「其他」、不进训练底模列表。
 * - **下载模型**：用户主动点「其他 → 下载模型」时打开 ExtrasDialog
 *   （引擎资源卡 + 分离/训练模型列表）。
 */

import { invoke } from "@tauri-apps/api/core";
import type { ExtrasFilter } from "../components/ExtrasDialog";

export type AssetsStatus = {
  engine_core_ready?: boolean;
  engine_core_missing?: string[];
  vbcable_pack_ready?: boolean;
};

export type OpenDownloadModelsOpts = {
  reason?: string;
  filter?: ExtrasFilter;
};

export type OpenEngineCoreOpts = {
  reason?: string;
};

type ModelsOpener = (opts?: OpenDownloadModelsOpts) => void;
type EngineOpener = (opts?: OpenEngineCoreOpts) => void;

let modelsOpener: ModelsOpener | null = null;
let engineOpener: EngineOpener | null = null;

/** App 挂载时注册「下载模型」弹窗。 */
export function registerDownloadModelsOpener(fn: ModelsOpener | null): void {
  modelsOpener = fn;
}

/** App 挂载时注册「仅引擎资源」弹窗。 */
export function registerEngineCoreOpener(fn: EngineOpener | null): void {
  engineOpener = fn;
}

/** 打开「其他 → 下载模型」（含分离/训练列表）。 */
export function openDownloadModels(opts?: OpenDownloadModelsOpts): void {
  modelsOpener?.(opts);
}

/** 打开「补全引擎资源」专用窗（不切页、不展示训练底模）。 */
export function openEngineCorePrompt(opts?: OpenEngineCoreOpts): void {
  if (engineOpener) {
    engineOpener(opts);
    return;
  }
  // 兜底：旧壳只注册了下载模型时，至少别静默失败。
  modelsOpener?.({ reason: opts?.reason });
}

export async function getAssetsStatus(): Promise<AssetsStatus> {
  try {
    return await invoke<AssetsStatus>("assets_status");
  } catch {
    return { engine_core_ready: true };
  }
}

export async function isEngineCoreReady(): Promise<boolean> {
  const st = await getAssetsStatus();
  return st.engine_core_ready !== false;
}

/**
 * 缺引擎资源时弹「补全引擎资源」窗并返回 false；已就绪返回 true。
 * 给开启变声 / 打开音频工具用，不要进下载模型页。
 */
export async function ensureEngineCoreOrPrompt(
  reason: string,
): Promise<boolean> {
  if (await isEngineCoreReady()) return true;
  openEngineCorePrompt({ reason });
  return false;
}
