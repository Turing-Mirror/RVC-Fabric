import { invoke } from "@tauri-apps/api/core";
import { t } from "../i18n/t";

export type Config = Record<string, unknown>;

export type ConfigWrite = {
  config: Config;
  hot: Record<string, unknown>;
  /** Cold keys in this patch — the stream must be restarted for them. */
  needs_restart: string[];
};

export async function getConfig(): Promise<Config> {
  return await invoke<Config>("config_get");
}

export async function setConfig(patch: Config): Promise<ConfigWrite> {
  return await invoke<ConfigWrite>("config_set", { patch });
}

/** 设置页乐观写入时立刻通知底栏等订阅方，不等 220ms 落盘。 */
const patchListeners = new Set<(patch: Config) => void>();

export function onConfigPatch(fn: (patch: Config) => void): () => void {
  patchListeners.add(fn);
  return () => {
    patchListeners.delete(fn);
  };
}

export function notifyConfigPatch(patch: Config): void {
  if (!Object.keys(patch).length) return;
  patchListeners.forEach((fn) => fn(patch));
}

/**
 * Detailed help behind every ? on the settings page.
 * Must be a function: top-level t() freezes the default (zh-CN) locale at import.
 * Accept the hook translator when a React view needs a memoised, locale-aware
 * snapshot instead of relying on the module-level locale side effect.
 */
export function tips(translate: (key: string) => string = t): Record<string, string> {
  return {
    sg_hostapi: translate("s.384eef0c3e"),
    sg_input_device: translate("s.7a24f480cf"),
    in_gain_db: translate("s.25d87929cc"),
    sg_output_device: translate("s.ef8cc2df41"),
    out_gain_db: translate("s.outGainTip"),
    monitor_self: translate("s.c2b9d351f6"),
    monitor_device: translate("s.594eba5310"),
    sg_wasapi_exclusive: translate("s.c1614d68d8"),
    sr_type: translate("s.91910f2b7b"),
    threhold: translate("s.ae27797e12"),
    pitch: translate("s.d7f3306fcc"),
    formant: translate("s.b584d38db8"),
    index_rate: translate("s.49e4ba4794"),
    rms_mix_rate: translate("s.445b04ec19"),
    f0method: translate("s.ff175008d6"),
    block_time: translate("s.1ca9f4246d"),
    crossfade_length: translate("s.b9d060e4f5"),
    extra_time: translate("s.22dda461eb"),
    n_cpu: translate("s.d291f67ac8"),
    cuda_graph: translate("s.4e22f58ed9"),
    I_noise_reduce: translate("s.6482fd1cfe"),
    O_noise_reduce: translate("s.5488b0c4b0"),
    use_pv: translate("s.b02cb49ebf"),
    fx_enabled: translate("s.1da56dd72c"),
    fx_eq_enabled: translate("s.579ea14ab7"),
    fx_eq_preset: translate("s.5acba95590"),
    fx_gate_enabled: translate("s.1cd12cf03d"),
    fx_gate_threshold_db: translate("s.0f843238e9"),
    fx_comp_enabled: translate("s.d0cb2f3a1b"),
    fx_comp_threshold_db: translate("s.f5b3cef9e1"),
    fx_comp_ratio: translate("s.6c488bda4d"),
    fx_out_gain_db: translate("s.59f6a509e7"),
    theme_mode: translate("s.ffa02ab8a7"),
    wallpaper_path: translate("s.f06f8d2041"),
    wallpaper_blur: translate("s.f069ff33fd"),
    wallpaper_opacity: translate("s.6e2aba9d02"),
    home_banner_text: translate("settings.bannerTextTip"),
    home_banner_sub: translate("settings.bannerSubTip"),
    home_banner_opacity: translate("settings.bannerOpacityTip"),
    close_action: translate("s.a22a5eeab1"),
    hotkeys_enabled: translate("s.6e382d3bef"),
    telemetry_opt_in: translate("s.a97cbce3c5"),
  };
}
