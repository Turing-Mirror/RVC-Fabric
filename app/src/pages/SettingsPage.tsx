import { useEffect, useMemo, useState, memo } from "react";
import { invoke } from "@tauri-apps/api/core";
import { SegmentControl } from "../components/SegmentControl";
import { Block, Btn, HelpMark, PagePad } from "../components/ui";
import { Field, Select, Slider, Toggle } from "../components/controls";
import { useConfig } from "../hooks/useConfig";
import { tips } from "../lib/config";
import { HOTKEYS } from "../lib/hotkeys";
import type { EngineStatus } from "../lib/engine";
import { t, LOCALES, useI18n, type LocaleCode } from "../i18n";

const TAB_KEYS = [
  "device",
  "voice",
  "perf",
  "fx",
  "appearance",
  "general",
  "hotkeys",
  "update",
] as const;

type TabKey = (typeof TAB_KEYS)[number];

type Props = {
  status?: EngineStatus;
  onReloadDevices?: () => void;
  /** True while the worker is re-enumerating. */
  devicesBusy?: boolean;
  /** False until the worker finishes its cold start, which is when device
   *  names first exist. Drives the empty-state line below. */
  workerAlive?: boolean;
  onCheckUpdate?: () => void;
  updateLine?: string;
  updateBusy?: boolean;
  /** 跳到说明页。设备这一套（虚拟声卡怎么连）的解释全在那边，
   *  这里只放一个入口，不把同一段话再抄一遍。 */
  onOpenHelp?: () => void;
};

/** Device names the worker reported; empty until the worker has been up once. */
function deviceOptions(list: unknown): { id: string; label: string }[] {
  if (!Array.isArray(list)) return [];
  return list
    .map((d) =>
      typeof d === "string" ? d : String((d as { name?: string })?.name ?? ""),
    )
    .filter(Boolean)
    .map((n) => ({ id: n, label: n }));
}

const CARD =
  "bg-[var(--group)] rounded-[var(--r)] px-5 py-[22px] flex flex-col gap-6";

/** 五段 EQ 的中心频率，必须和 `tools/dsp_fx.EQ_LABELS` 一致（引擎按下标取值）。 */
const EQ_BANDS = ["60Hz", "250Hz", "1kHz", "4kHz", "8kHz"] as const;

/** 与 `tools/dsp_fx.EQ_PRESETS` / `EQ_PRESET_LABELS` 一一对应。标签必须在调用时 t()，不可模块级冻结。 */
function eqPresets(): { id: string; label: string; gains: number[] }[] {
  return [
    { id: "flat", label: t("s.64ca1ffc2e"), gains: [0, 0, 0, 0, 0] },
    { id: "vocal_front", label: t("s.0df76209a8"), gains: [-2, 1, 3, 2.5, 1] },
    { id: "warm", label: t("s.80d341c40a"), gains: [2, 1.5, 0, -1, -2] },
    { id: "bright", label: t("s.7b470c4e5f"), gains: [-1.5, 0, 1, 3, 2.5] },
    { id: "de_nasal", label: t("s.89dd7d9dec"), gains: [0, -3.5, -1, 1.5, 0.5] },
    { id: "thick", label: t("s.c8e3bafbb7"), gains: [3, 1.5, 0, -0.5, -1.5] },
  ];
}

/** 存进配置的是长度 5 的数组；缺项补 0，别让下标越界变成 NaN 推给引擎。 */
function readGains(v: unknown): number[] {
  const arr = Array.isArray(v) ? v : [];
  return Array.from({ length: 5 }, (_, i) => {
    const n = Number(arr[i]);
    return Number.isFinite(n) ? n : 0;
  });
}

/**
 * 调后端，没有后端就当没这回事。
 *
 * 浏览器预览里 `window.__TAURI_INTERNALS__` 不存在，`invoke` 是**同步抛**的，
 * 不是返回一个失败的 promise —— 挂在后面的 `.catch()` 根本轮不到执行，异常
 * 一路冒到 ErrorBoundary，整个设置页变成一行红字。
 */
function safeInvoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T | null> {
  try {
    return invoke<T>(cmd, args).catch(() => null);
  } catch {
    return Promise.resolve(null);
  }
}

function SettingsPageImpl({
  status,
  onReloadDevices,
  devicesBusy = false,
  workerAlive = false,
  onCheckUpdate,
  updateLine,
  updateBusy = false,
  onOpenHelp,
}: Props = {}) {
  const { t, locale, setLocale } = useI18n();
  // Must re-resolve on locale change — module-level t() freezes zh-CN at import.
  const TIPS = useMemo(() => tips(), [locale]);
  const tabLabels = useMemo(
    () =>
      Object.fromEntries(
        TAB_KEYS.map((k) => [k, t(`settings.tabs.${k}`)]),
      ) as Record<TabKey, string>,
    [t],
  );
  const [tab, setTab] = useState<TabKey>("device");
  const c = useConfig();
  // 开机自启：状态以注册表为准（autostart_get），不进 app_config。
  const [autoStart, setAutoStart] = useState(false);
  const [autoStartBusy, setAutoStartBusy] = useState(false);
  useEffect(() => {
    let alive = true;
    void safeInvoke<{ enabled: boolean }>("autostart_get").then((s) => {
      if (alive && s) setAutoStart(s.enabled);
    });
    return () => {
      alive = false;
    };
  }, []);
  // 「在线更新」里那行当前版本。和「其他」页读的是同一个命令，也就是同一个
  // APP_VERSION —— 两处显示不一致的话，一定是有人又手写了版本号。
  const [appVersion, setAppVersion] = useState("");
  useEffect(() => {
    let alive = true;
    void safeInvoke<string>("shell_version").then(
      (v) => alive && setAppVersion(v || ""),
    );
    return () => {
      alive = false;
    };
  }, []);

  /**
   * 改一条快捷键：**先把配置写进盘里，再让 Rust 重新注册**。
   *
   * Rust 那边的 `apply_hotkeys` 是从配置文件里读组合键的，不是从参数里拿的。
   * 所以这两步的顺序不能反 —— 反了就注册到旧值上，界面写着 F2、真正能用的
   * 还是上一次那个 F1，而且每改一次就再错一次，永远差一步。
   */
  const saveHotkey = async (key: string, v: unknown) => {
    await c.set(key, v, true);
    await safeInvoke("hotkeys_apply", { enabled: c.bool("hotkeys_enabled") });
  };

  /**
   * 录组合键的这段时间里，把已经注册的全局快捷键**整个摘掉**。
   *
   * 全局快捷键是系统级的：录制框拿到的只是 webview 里的 keydown，拦不住系统
   * 那一层。于是用户为了确认现在是哪个组合而按一下 Ctrl+F2，变声就真的被打开
   * 了 —— 他只是想改个键，结果软件开始出声。松开录制就按当前配置装回去。
   */
  const setRecordingHotkey = (active: boolean) => {
    void safeInvoke("hotkeys_apply", {
      enabled: active ? false : c.bool("hotkeys_enabled"),
    });
  };

  const fxOn = c.bool("fx_enabled");
  const eqGains = readGains(c.cfg["fx_eq_gains"]);
  // 拖一根推子只改那一段，其余原样送回去 —— 引擎收的是整条数组。
  const setBand = (i: number, v: number) => {
    const next = eqGains.slice();
    next[i] = v;
    c.set("fx_eq_gains", next);
    // 手动改过就不再是任何预设了。留着旧预设名，下次开设置页会以为还是那个音色。
    if (c.str("fx_eq_preset", "flat") !== "custom") {
      c.set("fx_eq_preset", "custom");
    }
  };
  const applyPreset = (id: string) => {
    const p = eqPresets().find((x) => x.id === id);
    if (!p) return;
    c.set("fx_eq_preset", id, true);
    c.set("fx_eq_gains", p.gains.slice(), true);
  };

  const raw = status as unknown as Record<string, unknown> | undefined;
  const inputs = deviceOptions(raw?.input_devices);
  const outputs = deviceOptions(raw?.output_devices);
  const hostapis = deviceOptions(raw?.hostapis);
  // Device names come from the worker, and the worker needs 20-40s to boot
  // torch on a cold start. Until then every dropdown here is an empty box with
  // no explanation, which reads as broken rather than as "not yet".
  const devicesReady = inputs.length > 0 || outputs.length > 0;
  const deviceHint = devicesBusy
    ? t("s.abd52d0c37")
    : devicesReady
      ? ""
      : workerAlive
        ? t("s.1831f7eb53")
        : t("s.95af7bd399");

  return (
    <div>
      <div className="px-[30px] pt-4 max-[1020px]:px-[22px] max-[720px]:px-4 overflow-x-auto">
        <SegmentControl
          options={TAB_KEYS.map((k) => ({ id: k, label: tabLabels[k] }))}
          value={tab}
          onChange={setTab}
          className="!inline-flex !ml-0 max-w-full"
        />
      </div>

      <PagePad>
        {c.error ? (
          <p className="text-[12.5px] text-[#b8534f] mt-4 mb-0">{c.error}</p>
        ) : null}

        {c.restartKeys.length ? (
          <div className="mt-4 rounded-[var(--rs)] bg-[color-mix(in_srgb,var(--notify)_14%,transparent)] px-3.5 py-2.5 flex items-center gap-3 flex-wrap">
            <span className="text-[12.5px] text-[var(--ink-muted)]">{t("s.63bb17a9d2")}</span>
            <Btn className="!ml-auto" onClick={c.clearRestartNotice}>{t("s.cb63c62e50")}</Btn>
          </div>
        ) : null}

        {!c.loaded ? (
          <p className="text-[12.5px] text-[var(--meta)] mt-6">{t("s.49fd445d8b")}</p>
        ) : null}

        {c.loaded && tab === "device" ? (
          <Block
            title={t("s.9bef06a1f5")}
            className="!mt-6"
            action={
              onOpenHelp ? (
                <Btn onClick={onOpenHelp}>{t("s.004a3a2b67")}</Btn>
              ) : undefined
            }
          >
            <p className="text-[12.5px] text-[var(--help)] leading-relaxed m-0 mb-4 max-w-[76ch]">{t("s.d4b9d6c80f")}<br />{t("s.6c4698ee82")}</p>
            <div className={CARD}>
              <Field
                label={t("s.47a991d18c")}
                tip={TIPS.sg_hostapi}
                control={
                  <Select
                    full
                    value={c.str("sg_hostapi")}
                    options={hostapis}
                    onChange={(v) => c.set("sg_hostapi", v, true)}
                  />
                }
                note={t("s.b663153cef", { v0: inputs.length, v1: outputs.length })}
              />
              <Field
                label={t("s.c15e33676a")}
                tip={TIPS.sg_input_device}
                control={
                  <Select
                    full
                    value={c.str("sg_input_device")}
                    options={inputs}
                    onChange={(v) => c.set("sg_input_device", v, true)}
                  />
                }
              />
              <Field
                label={t("s.02942ba343")}
                tip={TIPS.in_gain_db}
                control={
                  <Slider
                    value={c.num("in_gain_db")}
                    min={-12}
                    max={24}
                    step={0.5}
                    onChange={(v) => c.set("in_gain_db", v)}
                    format={(v) => v.toFixed(2)}
                  />
                }
              />
              <Field
                label={t("s.3aa83c304c")}
                tip={TIPS.sg_output_device}
                control={
                  <Select
                    full
                    value={c.str("sg_output_device")}
                    options={outputs}
                    onChange={(v) => c.set("sg_output_device", v, true)}
                  />
                }
              />
              <Toggle
                label={t("s.dcf690b953")}
                tip={TIPS.monitor_self}
                checked={c.bool("monitor_self")}
                onChange={(v) => c.set("monitor_self", v, true)}
              />
              <Field
                label={t("s.550c08627b")}
                tip={TIPS.monitor_device}
                desc={t("s.1bce2ccca4")}
                control={
                  <Select
                    full
                    value={c.str("monitor_device")}
                    options={outputs}
                    onChange={(v) => c.set("monitor_device", v, true)}
                  />
                }
              />
              <div className="flex items-center gap-[11px] flex-wrap">
                <Toggle
                  label={t("s.1747a288fd")}
                  tip={TIPS.sg_wasapi_exclusive}
                  checked={c.bool("sg_wasapi_exclusive")}
                  onChange={(v) => c.set("sg_wasapi_exclusive", v, true)}
                />
                <span className="ml-auto flex items-center gap-2.5 flex-wrap">
                  <span className="text-[12.5px] text-[var(--meta)]">{t("s.ab4dae189d")}</span>
                  <HelpMark title={TIPS.sr_type} />
                  <Select
                    width={140}
                    value={c.str("sr_type", "sr_device")}
                    options={[
                      { id: "sr_device", label: t("s.71ea75cd1f") },
                      { id: "sr_model", label: t("s.ca872f619e") },
                    ]}
                    onChange={(v) => c.set("sr_type", v, true)}
                  />
                  <Btn onClick={onReloadDevices} disabled={devicesBusy}>
                    {devicesBusy ? t("s.f950213ab7") : t("s.966b701690")}
                  </Btn>
                </span>
              </div>
              {deviceHint ? (
                <div className="text-[12.5px] text-[var(--help)]">{deviceHint}</div>
              ) : null}
            </div>
          </Block>
        ) : null}

        {c.loaded && tab === "voice" ? (
          <Block title={t("s.ae7cbbecbc")} note={t("s.d48a0bf3c8")} className="!mt-6">
            <p className="text-[12.5px] text-[var(--help)] leading-relaxed m-0 mb-4 max-w-[80ch]">{t("s.a9e4eb7a51")}</p>
            <div className={CARD}>
              <Field
                label={t("s.75e7326c34")}
                tip={TIPS.threhold}
                control={
                  <Slider
                    value={c.num("threhold", -60)}
                    min={-60}
                    max={0}
                    step={1}
                    onChange={(v) => c.set("threhold", v)}
                  />
                }
              />
              <Field
                label={t("s.bda11a3c2d")}
                tip={TIPS.pitch}
                control={
                  <Slider
                    value={c.num("pitch")}
                    min={-24}
                    max={24}
                    step={1}
                    defaultValue={0}
                    onChange={(v) => c.set("pitch", v)}
                    format={(v) => (v > 0 ? `+${v}` : `${v}`)}
                  />
                }
              />
              <Field
                label={t("s.7c4a58ca1b")}
                tip={TIPS.formant}
                control={
                  <Slider
                    value={c.num("formant")}
                    min={-2}
                    max={2}
                    step={0.05}
                    defaultValue={0}
                    onChange={(v) => c.set("formant", v)}
                    format={(v) => v.toFixed(2)}
                  />
                }
              />
              <Field
                label={t("s.389bc211b2")}
                tip={TIPS.index_rate}
                control={
                  <Slider
                    value={c.num("index_rate", 0.75)}
                    min={0}
                    max={1}
                    step={0.01}
                    defaultValue={0.75}
                    onChange={(v) => c.set("index_rate", v)}
                    format={(v) => v.toFixed(2)}
                  />
                }
              />
              <Field
                label={t("s.02791c87b8")}
                tip={TIPS.rms_mix_rate}
                control={
                  <Slider
                    value={c.num("rms_mix_rate", 0.25)}
                    min={0}
                    max={1}
                    step={0.01}
                    defaultValue={0.25}
                    onChange={(v) => c.set("rms_mix_rate", v)}
                    format={(v) => v.toFixed(2)}
                  />
                }
              />
              <Field
                label={t("s.3579ac474b")}
                tip={TIPS.f0method}
                inline
                control={
                  <Select
                    width={150}
                    value={c.str("f0method", "rmvpe")}
                    options={[
                      { id: "rmvpe", label: "rmvpe" },
                      { id: "harvest", label: "harvest" },
                      { id: "pm", label: "pm" },
                      { id: "fcpe", label: "fcpe" },
                      { id: "crepe", label: "crepe" },
                    ]}
                    onChange={(v) => c.set("f0method", v, true)}
                  />
                }
              />
            </div>
          </Block>
        ) : null}

        {c.loaded && tab === "perf" ? (
          <Block title={t("s.eb1f3e5ef6")} note={t("s.9ad8c4b79c")} className="!mt-6">
            <div className={CARD}>
              <Field
                label={t("s.2f2caa6a62")}
                tip={TIPS.block_time}
                control={
                  <Slider
                    value={c.num("block_time", 0.25)}
                    min={0.05}
                    max={1}
                    step={0.01}
                    defaultValue={0.25}
                    onChange={(v) => c.set("block_time", v)}
                    format={(v) => `${v.toFixed(2)} s`}
                  />
                }
              />
              <Field
                label={t("s.98454ca754")}
                tip={TIPS.crossfade_length}
                control={
                  <Slider
                    value={c.num("crossfade_length", 0.08)}
                    min={0.01}
                    max={0.5}
                    step={0.01}
                    defaultValue={0.08}
                    onChange={(v) => c.set("crossfade_length", v)}
                    format={(v) => `${v.toFixed(2)} s`}
                  />
                }
              />
              <Field
                label={t("s.5ecc71c141")}
                tip={TIPS.extra_time}
                control={
                  <Slider
                    value={c.num("extra_time", 2.5)}
                    min={0.5}
                    max={5}
                    step={0.1}
                    defaultValue={2.5}
                    onChange={(v) => c.set("extra_time", v)}
                    format={(v) => `${v.toFixed(1)} s`}
                  />
                }
              />
              <Field
                label={t("s.1e48570a18")}
                tip={TIPS.n_cpu}
                control={
                  <Slider
                    value={c.num("n_cpu", 4)}
                    min={1}
                    max={16}
                    step={1}
                    defaultValue={4}
                    onChange={(v) => c.set("n_cpu", v)}
                  />
                }
              />
              <Toggle
                label={t("s.5b833d9334")}
                tip={TIPS.cuda_graph}
                checked={c.bool("cuda_graph")}
                onChange={(v) => c.set("cuda_graph", v)}
              />
            </div>
          </Block>
        ) : null}

        {c.loaded && tab === "fx" ? (
          <Block title={t("s.d66ab479e1")} note={t("s.eb434c8c24")} className="!mt-6">
            <div className={CARD}>
              <Toggle
                label={t("s.18b35795d9")}
                tip={TIPS.I_noise_reduce}
                checked={c.bool("I_noise_reduce")}
                onChange={(v) => c.set("I_noise_reduce", v, true)}
              />
              <Toggle
                label={t("s.b5b981b099")}
                tip={TIPS.O_noise_reduce}
                checked={c.bool("O_noise_reduce")}
                onChange={(v) => c.set("O_noise_reduce", v, true)}
              />
              <Toggle
                label={t("s.9e03f8df04")}
                tip={TIPS.use_pv}
                checked={c.bool("use_pv")}
                onChange={(v) => c.set("use_pv", v, true)}
              />
            </div>

            {/* 变声后的 DSP 链。引擎侧一直有，迁到 Tauri 时壳层漏掉了整节。 */}
            <div className={`${CARD} mt-4`}>
              <Toggle
                label={t("s.19e933ad2a")}
                tip={TIPS.fx_enabled}
                checked={c.bool("fx_enabled")}
                onChange={(v) => c.set("fx_enabled", v, true)}
              />
              {fxOn ? (
                <>
                  <Field
                    label={t("s.c193661369")}
                    tip={TIPS.fx_eq_enabled}
                    inline
                    control={
                      <Toggle
                        label=""
                        checked={c.bool("fx_eq_enabled")}
                        onChange={(v) => c.set("fx_eq_enabled", v, true)}
                      />
                    }
                  />
                  <Field
                    label={t("s.65d7aca5f1")}
                    tip={TIPS.fx_eq_preset}
                    control={
                      <Select
                        value={c.str("fx_eq_preset", "flat")}
                        options={[
                          ...eqPresets().map((p) => ({
                            id: p.id,
                            label: p.label,
                          })),
                          // 只用来显示「推子被手动动过了」。选它不做任何事，
                          // applyPreset 找不到就直接返回。引擎那边 gains 优先于
                          // preset，所以 custom 传下去也不会被当成 flat 复位。
                          ...(c.str("fx_eq_preset", "flat") === "custom"
                            ? [{ id: "custom", label: t("s.c493338e8c") }]
                            : []),
                        ]}
                        onChange={applyPreset}
                      />
                    }
                  />
                  {EQ_BANDS.map((band, i) => (
                    <Field
                      key={band}
                      label={band}
                      control={
                        <Slider
                          value={eqGains[i]}
                          min={-12}
                          max={12}
                          step={0.5}
                          onChange={(v) => setBand(i, v)}
                          format={(v) =>
                            `${v > 0 ? "+" : ""}${v.toFixed(1)} dB`
                          }
                        />
                      }
                    />
                  ))}
                  <Field
                    label={t("s.038c681d8c")}
                    tip={TIPS.fx_gate_enabled}
                    inline
                    control={
                      <Toggle
                        label=""
                        checked={c.bool("fx_gate_enabled")}
                        onChange={(v) => c.set("fx_gate_enabled", v, true)}
                      />
                    }
                  />
                  <Field
                    label={t("s.55adfb8c3f")}
                    tip={TIPS.fx_gate_threshold_db}
                    control={
                      <Slider
                        value={c.num("fx_gate_threshold_db", -50)}
                        min={-80}
                        max={-20}
                        step={1}
                        onChange={(v) => c.set("fx_gate_threshold_db", v)}
                        format={(v) => `${v} dB`}
                      />
                    }
                  />
                  <Field
                    label={t("s.690ac0b101")}
                    tip={TIPS.fx_comp_enabled}
                    inline
                    control={
                      <Toggle
                        label=""
                        checked={c.bool("fx_comp_enabled")}
                        onChange={(v) => c.set("fx_comp_enabled", v, true)}
                      />
                    }
                  />
                  <Field
                    label={t("s.ecf753d9da")}
                    tip={TIPS.fx_comp_threshold_db}
                    control={
                      <Slider
                        value={c.num("fx_comp_threshold_db", -20)}
                        min={-60}
                        max={0}
                        step={1}
                        onChange={(v) => c.set("fx_comp_threshold_db", v)}
                        format={(v) => `${v} dB`}
                      />
                    }
                  />
                  <Field
                    label={t("s.3a23a85820")}
                    tip={TIPS.fx_comp_ratio}
                    control={
                      <Slider
                        value={c.num("fx_comp_ratio", 4)}
                        min={1}
                        max={20}
                        step={0.5}
                        onChange={(v) => c.set("fx_comp_ratio", v)}
                        format={(v) => `${v.toFixed(1)} : 1`}
                      />
                    }
                  />
                  <Field
                    label={t("s.60e69dd480")}
                    tip={TIPS.fx_out_gain_db}
                    control={
                      <Slider
                        value={c.num("fx_out_gain_db", 0)}
                        min={-12}
                        max={12}
                        step={0.5}
                        onChange={(v) => c.set("fx_out_gain_db", v)}
                        format={(v) =>
                          `${v > 0 ? "+" : ""}${v.toFixed(1)} dB`
                        }
                      />
                    }
                  />
                </>
              ) : null}
            </div>
          </Block>
        ) : null}

        {c.loaded && tab === "appearance" ? (
          <Block title={tabLabels.appearance} className="!mt-6">
            <div className={CARD}>
              <Field
                label={t("settings.language")}
                tip={t("settings.languageTip")}
                inline
                control={
                  <Select
                    width={150}
                    value={locale}
                    options={LOCALES.map((l) => ({
                      id: l.id,
                      label: t(l.labelKey),
                    }))}
                    onChange={(v) => {
                      // LOCALES 已列全量；非法值忽略
                      if (LOCALES.some((l) => l.id === v)) {
                        setLocale(v as LocaleCode);
                        c.set("ui_locale", v, true);
                        // 设置里改过语言也算确认过，避免误触发首次引导。
                        c.set("ui_locale_picked", true, true);
                      }
                    }}
                  />
                }
              />
              <Field
                label={t("settings.theme")}
                tip={TIPS.theme_mode}
                inline
                control={
                  <Select
                    width={150}
                    value={c.str("theme_mode", "system")}
                    options={[
                      { id: "system", label: t("settings.themeSystem") },
                      { id: "light", label: t("settings.themeLight") },
                      { id: "dark", label: t("settings.themeDark") },
                    ]}
                    onChange={(v) => {
                      c.set("theme_mode", v, true);
                      const el = document.documentElement;
                      if (v === "system") el.removeAttribute("data-theme");
                      else el.setAttribute("data-theme", v);
                    }}
                  />
                }
              />
              <Field
                label={t("s.e5c12c3be5")}
                tip={TIPS.wallpaper_path}
                desc={t("s.3451ca742f")}
                control={
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <Btn onClick={() => void pickWallpaper(c.set)}>{t("s.18104edf89")}</Btn>
                    {c.str("wallpaper_path") ? (
                      <>
                        <span className="text-[12.5px] text-[var(--meta)] max-w-[280px] truncate">
                          {c.str("wallpaper_path")}
                        </span>
                        <Btn onClick={() => c.set("wallpaper_path", "", true)}>{t("s.7b15e5e8e7")}</Btn>
                      </>
                    ) : (
                      <span className="text-[12.5px] text-[var(--meta)]">{t("s.55a04b58cd")}</span>
                    )}
                  </div>
                }
              />
              <Field
                label={t("s.910adcad16")}
                tip={TIPS.wallpaper_blur}
                control={
                  <Slider
                    value={c.num("wallpaper_blur", 40)}
                    min={0}
                    max={100}
                    step={1}
                    onChange={(v) => c.set("wallpaper_blur", v)}
                    format={(v) => `${v}%`}
                  />
                }
              />
              <Field
                label={t("s.b4efb6cdcf")}
                tip={TIPS.wallpaper_opacity}
                control={
                  <Slider
                    value={c.num("wallpaper_opacity", 70)}
                    min={0}
                    max={100}
                    step={1}
                    onChange={(v) => c.set("wallpaper_opacity", v)}
                    format={(v) => `${v}%`}
                  />
                }
              />
            </div>
          </Block>
        ) : null}

        {c.loaded && tab === "general" ? (
          <Block title={t("s.f1484fa78b")} className="!mt-6">
            <div className={CARD}>
              <Field
                label={t("s.f0ace6ccbe")}
                tip={TIPS.close_action}
                inline
                control={
                  <Select
                    width={170}
                    value={c.str("close_action", "ask")}
                    options={[
                      { id: "ask", label: t("s.393704c0f8") },
                      { id: "tray", label: t("s.aea56dcdfe") },
                      { id: "exit", label: t("s.0dd68a51dd") },
                    ]}
                    onChange={(v) => c.set("close_action", v, true)}
                  />
                }
              />
              <Field
                label={t("settings.autoStart")}
                tip={t("settings.autoStartTip")}
                control={
                  <Toggle
                    label={autoStart ? t("settings.autoStartOn") : t("settings.autoStartOff")}
                    checked={autoStart}
                    onChange={(v) => {
                      if (autoStartBusy) return;
                      setAutoStartBusy(true);
                      try {
                        invoke("autostart_set", { enabled: v })
                          .then(() => setAutoStart(v))
                          // 写失败（权限/注册表异常）回读真实状态，开关跟着
                          // 注册表走，不假装改成了。
                          .catch(() => {
                            void invoke<{ enabled: boolean }>("autostart_get").then((s) =>
                              setAutoStart(s.enabled),
                            );
                          })
                          .finally(() => setAutoStartBusy(false));
                      } catch {
                        // 浏览器预览没有 Tauri 后端，开关保持原样即可。
                        setAutoStartBusy(false);
                      }
                    }}
                  />
                }
              />
              <Field
                label={t("s.3ff3e5ff9b")}
                tip={TIPS.telemetry_opt_in}
                desc={t("s.dc3f6fc6fd")}
                control={
                  <Toggle
                    label={c.cfg.telemetry_opt_in === true ? t("s.a056bc39f4") : t("s.ef92935b07")}
                    checked={c.cfg.telemetry_opt_in === true}
                    onChange={(v) => c.set("telemetry_opt_in", v, true)}
                  />
                }
              />
              <Field
                label={t("settings.hfEndpoint")}
                tip={t("settings.hfEndpointTip")}
                inline
                control={
                  <Select
                    width={220}
                    value={(() => {
                      const v = c.str("hf_endpoint", "");
                      if (
                        v === "" ||
                        v === "https://hf-mirror.com" ||
                        v === "https://hf-cdn.sufy.com"
                      ) {
                        return v;
                      }
                      // 旧自定义值仍可选中显示
                      return v;
                    })()}
                    options={[
                      { id: "", label: t("settings.hfEndpointDefault") },
                      { id: "https://hf-cdn.sufy.com", label: "hf-cdn.sufy.com" },
                      { id: "https://hf-mirror.com", label: "hf-mirror.com" },
                      // 若用户 app_config 里有非预设值，补进列表避免 Select 空白
                      ...(() => {
                        const v = c.str("hf_endpoint", "");
                        if (
                          v &&
                          v !== "https://hf-mirror.com" &&
                          v !== "https://hf-cdn.sufy.com"
                        ) {
                          return [{ id: v, label: v }];
                        }
                        return [] as { id: string; label: string }[];
                      })(),
                    ]}
                    onChange={(v) => c.set("hf_endpoint", v, true)}
                  />
                }
              />
            </div>
          </Block>
        ) : null}

        {c.loaded && tab === "hotkeys" ? (
          <Block title={t("s.31e3310765")} className="!mt-6">
            <div className={CARD}>
              <Toggle
                label={t("s.8ef23e2698")}
                tip={TIPS.hotkeys_enabled}
                checked={c.bool("hotkeys_enabled")}
                onChange={(v) => {
                  void c
                    .set("hotkeys_enabled", v, true)
                    .then(() => safeInvoke("hotkeys_apply", { enabled: v }));
                }}
              />
              <div className="flex flex-col">
                {HOTKEYS.map((h) => (
                  <HotkeyRow
                    key={h.key}
                    label={hotkeyLabels()[h.action] ?? h.action}
                    value={c.str(h.key, h.fallback)}
                    onChange={(v) => void saveHotkey(h.key, v)}
                    global={c.cfg[`${h.key}_global`] !== false}
                    onGlobalChange={(v) => void saveHotkey(`${h.key}_global`, v)}
                    onRecording={setRecordingHotkey}
                  />
                ))}
              </div>
              <p className="text-xs text-[var(--help)] m-0">
                <b>{t("s.d15328af87")}</b>：<br />{t("s.b8d74a5e97")}<br />{t("s.d7278f3458")}<br />{t("s.5ece668b53")}<br />{t("s.e6eed3ec41")}</p>
            </div>
          </Block>
        ) : null}

        {c.loaded && tab === "update" ? (
          <Block title={t("s.f0332ff72a")} className="!mt-6">
            <div className={CARD}>
              {/* 当前版本单独一行，常驻。
                  以前这一整块只有一个按钮，点完什么都不变（desc 被 inline 版
                  吞了），于是「我到底是不是最新的」这个问题在设置页里根本
                  没有答案。版本号摆出来，起码有一半答案是白纸黑字的。 */}
              <Field
                label={t("s.46e66f6321")}
                inline
                control={
                  <span className="text-[13px] text-[var(--ink-muted)] tabular-nums">
                    {appVersion || "—"}
                  </span>
                }
              />
              <Field
                label={t("s.a6df38586d")}
                desc={updateLine || t("s.1fd4658c44")}
                inline
                control={
                  <Btn onClick={onCheckUpdate} disabled={updateBusy}>
                    {updateBusy ? t("s.5fc65af5b3") : t("s.72523c6421")}
                  </Btn>
                }
              />
              <p className="text-xs text-[var(--help)] m-0 leading-[1.75]">{t("s.5fe7a5211b")}<br />{t("s.6c26ecbfb3")}</p>
            </div>
          </Block>
        ) : null}
      </PagePad>
    </div>
  );
}

/** 每个动作在设置页里怎么称呼。键名和默认组合来自 `lib/hotkeys`，
 *  那份表和 `shell_extras::HOTKEYS` 一一对应 —— 三处抄三遍迟早对不上。
 *  必须调用时 t()，模块级会冻成默认中文。 */
function hotkeyLabels(): Record<string, string> {
  return {
    "toggle-vc": t("s.de2b71244c"),
    "toggle-mode": t("s.3848444f8c"),
    "prev-voice": t("s.6053ffffee"),
    "next-voice": t("s.5b6259b315"),
    "pitch-up": t("s.9f97186ee0"),
    "pitch-down": t("s.9c74c2a45e"),
    "toggle-monitor": t("s.6eb438dd5b"),
    "toggle-fx": t("s.bfdefad36e"),
    "toggle-window": t("s.22067787e1"),
  };
}

/** 把组合键写成用户读得懂的样子：CmdOrCtrl+F2 → Ctrl + F2。 */
function prettyCombo(v: string): string {
  return v
    .split("+")
    .map((p) => (p === "CmdOrCtrl" ? "Ctrl" : p === "Super" ? "Win" : p))
    .join(" + ");
}

/**
 * 按一下开始录，再按组合键就存下来。
 *
 * 只按修饰键不算 —— 按 Ctrl 的那一刻就存下「Ctrl」的话，用户永远录不出
 * Ctrl+F2：手指还没够到 F2 就已经存完了。
 */
function HotkeyRow({
  label,
  value,
  onChange,
  global: isGlobal,
  onGlobalChange,
  onRecording,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  /** 抢成全局（任何软件在前台都生效），还是只在本软件窗口里生效。 */
  global: boolean;
  onGlobalChange: (v: boolean) => void;
  /** 进入 / 退出录制。录制期间全局快捷键要摘掉，否则按一下就真触发了。 */
  onRecording: (active: boolean) => void;
}) {
  const [recording, setRecording] = useState(false);

  const stopRecording = () => {
    setRecording(false);
    onRecording(false);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.key === "Escape") {
      stopRecording();
      return;
    }
    const mods: string[] = [];
    if (e.ctrlKey || e.metaKey) mods.push("CmdOrCtrl");
    if (e.altKey) mods.push("Alt");
    if (e.shiftKey) mods.push("Shift");

    const code = e.code;
    let main = "";
    if (/^Key[A-Z]$/.test(code)) main = code.slice(3);
    else if (/^Digit[0-9]$/.test(code)) main = code.slice(5);
    else if (/^F([1-9]|1[0-9]|2[0-4])$/.test(code)) main = code;
    if (!main) return; // 还只按着修饰键，继续等

    // 只 setRecording(false)，不走 stopRecording：onChange 存完盘会自己按新
    // 配置重装一遍，这里再装一次是拿旧值多注册一轮。
    setRecording(false);
    onChange([...mods, main].join("+"));
  };

  return (
    <div className="flex items-center py-2.5 border-b border-[var(--hairline)] last:border-b-0">
      <span className="text-[13px]">{label}</span>
      {/* 「全局」逐个可关。全局快捷键是**独占**的：Ctrl+F7 被我们抢走之后，
          用户在别的软件里就再也按不出它原本的功能了。关掉之后这个组合只在
          RVC Fabric 是当前窗口时有效，机器上其他软件照常用得着。 */}
      <label className="ml-auto mr-3 flex items-center gap-1.5 text-[12px] text-[var(--meta)] cursor-pointer select-none">
        <input
          type="checkbox"
          checked={isGlobal}
          onChange={(e) => onGlobalChange(e.target.checked)}
          className="accent-[var(--accent)] w-[13px] h-[13px]"
        />{t("s.a5644f4bbf")}</label>
      <button
        type="button"
        onClick={() => {
          setRecording(true);
          onRecording(true);
        }}
        onBlur={stopRecording}
        onKeyDown={recording ? onKeyDown : undefined}
        className={[
          "px-2.5 py-1 rounded-[var(--rs)] border-0 cursor-pointer",
          "text-[12.5px] tabular-nums bg-transparent",
          "shadow-[inset_0_0_0_1px_var(--line)] transition-colors duration-200",
          "focus-visible:outline-2 focus-visible:outline-[var(--accent)] focus-visible:outline-offset-2",
          recording
            ? "text-[var(--accent)] shadow-[inset_0_0_0_1px_var(--accent)]"
            : "text-[var(--meta)] hover:text-[var(--ink)]",
        ].join(" ")}
      >
        {recording ? t("s.31469944aa") : prettyCombo(value)}
      </button>
    </div>
  );
}

/** Open a native picker and store the chosen image path. */
async function pickWallpaper(set: (k: string, v: unknown, now?: boolean) => void) {
  try {
    const p = await invoke<string | null>("pick_wallpaper");
    if (p) set("wallpaper_path", p, true);
  } catch {
    /* cancelled */
  }
}

/**
 * Memoised: App re-renders on every engine status tick (2.5x a second while
 * converting). Without this the whole page tree was rebuilt each time for a
 * mic-level change that only the dock cares about.
 */
export const SettingsPage = memo(SettingsPageImpl);
