/**
 * 音频工具前置依赖 / 「下载模型」入口。
 *
 * - **开启变声**：只查 Runtime，不走这里。
 * - **音频工具**（人声分离 / 训练 / 语音转换）：缺引擎资源时打开「下载模型」
 *   弹窗——先补 hubert/rmvpe/ffmpeg，再允许下分离/训练附加包。
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

type ModelsOpener = (opts?: OpenDownloadModelsOpts) => void;

let modelsOpener: ModelsOpener | null = null;

/** App 挂载时注册「下载模型」弹窗。 */
export function registerDownloadModelsOpener(fn: ModelsOpener | null): void {
  modelsOpener = fn;
}

/** 打开「其他 → 下载模型」（引擎资源卡 + 分离/训练列表）。 */
export function openDownloadModels(opts?: OpenDownloadModelsOpts): void {
  modelsOpener?.(opts);
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
 * 音频工具入口用：缺引擎资源则打开「下载模型」弹窗并返回 false；
 * 已就绪返回 true，调用方再打开工具窗。
 */
export async function ensureEngineCoreOrPrompt(
  reason: string,
): Promise<boolean> {
  if (await isEngineCoreReady()) return true;
  openDownloadModels({ reason });
  return false;
}
