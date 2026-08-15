/**
 * 引擎资源 / 「下载模型」入口。
 *
 * 实时变声（rtrvc）与离线工具都依赖 hubert / rmvpe（及 ffmpeg）。
 * 缺了就打开「下载模型」弹窗：先补引擎资源，再允许下分离/训练附加包。
 *
 * - 底栏「开启变声」：Runtime 就绪后，若缺引擎资源 → 跳转广场「下载模型」
 * - 音频工具入口：同上
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

/**
 * 打开「广场 → 下载模型」。
 *
 * 主窗口里有注册好的 opener，直接跳广场。工具窗口（人声分离 / 训练音色 /
 * 语音转换）是独立的 webview，没有广场也没有 App —— 那边改成把主窗口叫到
 * 前面再跳，而不是就地弹一个塞不下的框。
 */
export function openDownloadModels(opts?: OpenDownloadModelsOpts): void {
  if (modelsOpener) {
    modelsOpener(opts);
    return;
  }
  void invoke("tools_open_downloads", { reason: opts?.reason || "" }).catch(() => {
    /* 浏览器预览里没有 shell */
  });
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
 * 缺引擎资源则打开「下载模型」弹窗并返回 false；已就绪返回 true。
 */
export async function ensureEngineCoreOrPrompt(
  reason: string,
): Promise<boolean> {
  if (await isEngineCoreReady()) return true;
  openDownloadModels({ reason });
  return false;
}
