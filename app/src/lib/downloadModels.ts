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
import { getCurrentWindow } from "@tauri-apps/api/window";
import type { ExtrasFilter } from "../components/ExtrasDialog";

export type AssetsStatus = {
  engine_core_ready?: boolean;
  engine_core_missing?: string[];
  audio_tools_ready?: boolean;
  audio_tools_size_bytes?: number;
  vbcable_pack_ready?: boolean;
  vbcable_installed?: boolean;
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
  // 工具窗是独立 webview。以前只要模块里挂过 opener（或 hash 丢了误挂
  // 整棵 App）就会在小窗里 setPage("plaza")，看起来像旧的「下载分离模型」
  // 弹窗，主窗口广场根本没动。不是主窗就一律绕回主窗口。
  let isMain = false;
  try {
    isMain = getCurrentWindow().label === "main";
  } catch {
    isMain = !/^#\/tool\//.test(window.location.hash || "");
  }
  if (isMain && modelsOpener) {
    modelsOpener(opts);
    return;
  }
  void invoke("tools_open_downloads", {
    reason: opts?.reason || "",
    filter: opts?.filter || "",
  }).catch(() => {
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
 * 下载音频组件（ffmpeg / ffprobe）。安装包不带它们；已有时后端直接返回。
 * 同一时刻只跑一次：提示窗关掉后下载照常继续，再打开时接上同一个任务。
 */
let audioToolsJob: Promise<void> | null = null;

export function ensureAudioTools(): Promise<void> {
  if (!audioToolsJob) {
    audioToolsJob = invoke("assets_ensure_audio_tools")
      .then(() => undefined)
      .finally(() => {
        audioToolsJob = null;
      });
  }
  return audioToolsJob;
}

export function audioToolsDownloading(): boolean {
  return audioToolsJob !== null;
}

type AudioToolsPrompt = (opts?: { force?: boolean; then?: () => void }) => void;
let audioToolsPrompt: AudioToolsPrompt | null = null;

/** App 挂载时注册「音频组件」提示窗。 */
export function registerAudioToolsPrompt(fn: AudioToolsPrompt | null): void {
  audioToolsPrompt = fn;
}

/**
 * 缺音频组件时弹提示窗，让用户决定下不下。已就绪则直接执行 then。
 * 不带 force 时每次启动只问一次，用户点了「稍后」就不再追着问。
 */
export function promptAudioTools(opts?: { force?: boolean; then?: () => void }): void {
  if (audioToolsPrompt) audioToolsPrompt(opts);
  else opts?.then?.();
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
