/**
 * 「下载模型」统一入口：引擎资源（hubert / rmvpe / ffmpeg）按需补全也挂在这里。
 *
 * 首页 / 其他页的音频工具、底栏开启变声若发现缺引擎资源，会跳到「其他」并打开
 * 本对话框，而不是把几百 MB 绑在首次 Runtime 补全里。
 */

import { invoke } from "@tauri-apps/api/core";
import type { ExtrasFilter } from "../components/ExtrasDialog";

export type AssetsStatus = {
  engine_core_ready?: boolean;
  engine_core_missing?: string[];
  vbcable_pack_ready?: boolean;
};

export type OpenDownloadModelsOpts = {
  /** 顶部提示，例如「使用语音转换前需先下载引擎资源」。 */
  reason?: string;
  filter?: ExtrasFilter;
};

type Opener = (opts?: OpenDownloadModelsOpts) => void;

let opener: Opener | null = null;

/** App 挂载时注册，卸载时清掉。 */
export function registerDownloadModelsOpener(fn: Opener | null): void {
  opener = fn;
}

/** 跳到「其他」页并打开「下载模型」弹窗（由 App 注册的实现负责）。 */
export function openDownloadModels(opts?: OpenDownloadModelsOpts): void {
  opener?.(opts);
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

/** 缺引擎资源时打开下载模型页并返回 false；已就绪返回 true。 */
export async function ensureEngineCoreOrPrompt(
  reason: string,
): Promise<boolean> {
  if (await isEngineCoreReady()) return true;
  openDownloadModels({ reason });
  return false;
}
