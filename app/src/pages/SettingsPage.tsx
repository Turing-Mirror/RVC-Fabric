import { useState, memo } from "react";
import { invoke } from "@tauri-apps/api/core";
import { SegmentControl } from "../components/SegmentControl";
import { Block, Btn, HelpMark, PagePad } from "../components/ui";
import { Field, Select, Slider, Toggle } from "../components/controls";
import { useConfig } from "../hooks/useConfig";
import { TIPS } from "../lib/config";
import type { EngineStatus } from "../lib/engine";

const TABS = [
  "设备与音频",
  "变声参数",
  "性能设置",
  "声音效果",
  "外观",
  "常规",
  "快捷键",
  "在线更新",
] as const;

type Tab = (typeof TABS)[number];

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

/** 与 `tools/dsp_fx.EQ_PRESETS` / `EQ_PRESET_LABELS` 一一对应。 */
const EQ_PRESETS: { id: string; label: string; gains: number[] }[] = [
  { id: "flat", label: "平直", gains: [0, 0, 0, 0, 0] },
  { id: "vocal_front", label: "人声前倾", gains: [-2, 1, 3, 2.5, 1] },
  { id: "warm", label: "温暖饱满", gains: [2, 1.5, 0, -1, -2] },
  { id: "bright", label: "清晰明亮", gains: [-1.5, 0, 1, 3, 2.5] },
  { id: "de_nasal", label: "消除鼻音", gains: [0, -3.5, -1, 1.5, 0.5] },
  { id: "thick", label: "低沉厚实", gains: [3, 1.5, 0, -0.5, -1.5] },
];

/** 存进配置的是长度 5 的数组；缺项补 0，别让下标越界变成 NaN 推给引擎。 */
function readGains(v: unknown): number[] {
  const arr = Array.isArray(v) ? v : [];
  return Array.from({ length: 5 }, (_, i) => {
    const n = Number(arr[i]);
    return Number.isFinite(n) ? n : 0;
  });
}

function SettingsPageImpl({
  status,
  onReloadDevices,
  devicesBusy = false,
  workerAlive = false,
  onCheckUpdate,
  updateLine,
  updateBusy = false,
}: Props = {}) {
  const [tab, setTab] = useState<Tab>("设备与音频");
  const c = useConfig();

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
    const p = EQ_PRESETS.find((x) => x.id === id);
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
    ? "正在读取设备…"
    : devicesReady
      ? ""
      : workerAlive
        ? "还没读到设备，点右边「重载设备列表」以重试"
        : "引擎正在启动，设备列表稍后出现";

  return (
    <div>
      <div className="px-[30px] pt-4 max-[1020px]:px-[22px] max-[720px]:px-4 overflow-x-auto">
        <SegmentControl
          options={TABS.map((t) => ({ id: t, label: t }))}
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
            <span className="text-[12.5px] text-[var(--ink-muted)]">
              设备与性能类改动需要重新「开启变声」才会生效。
            </span>
            <Btn className="!ml-auto" onClick={c.clearRestartNotice}>
              知道了
            </Btn>
          </div>
        ) : null}

        {!c.loaded ? (
          <p className="text-[12.5px] text-[var(--meta)] mt-6">读取设置…</p>
        ) : null}

        {c.loaded && tab === "设备与音频" ? (
          <Block title="设备与音频" className="!mt-6">
            <p className="text-[12.5px] text-[var(--help)] leading-relaxed m-0 mb-4 max-w-[76ch]">
              输入选你的麦克风，输出选 CABLE Input，再把游戏里的麦克风设成 CABLE Output。
              <br />
              勾选「变声时监听自己」并选耳机，可以一边开黑一边听自己的变声效果。
            </p>
            <div className={CARD}>
              <Field
                label="设备类型"
                tip={TIPS.sg_hostapi}
                control={
                  <Select
                    full
                    value={c.str("sg_hostapi")}
                    options={hostapis}
                    onChange={(v) => c.set("sg_hostapi", v, true)}
                  />
                }
                note={`读到 ${inputs.length} 个录音设备、${outputs.length} 个播放设备`}
              />
              <Field
                label="输入设备"
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
                label="麦克风增益 dB"
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
                label="输出设备"
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
                label="变声时监听自己"
                tip={TIPS.monitor_self}
                checked={c.bool("monitor_self")}
                onChange={(v) => c.set("monitor_self", v, true)}
              />
              <Field
                label="监听设备"
                tip={TIPS.monitor_device}
                desc="关闭时只走「输出设备」（通常 CABLE）；开启后在耳机里听变声"
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
                  label="WASAPI 独占（一般无需开启，只在你清楚自己在做什么时开启）"
                  tip={TIPS.sg_wasapi_exclusive}
                  checked={c.bool("sg_wasapi_exclusive")}
                  onChange={(v) => c.set("sg_wasapi_exclusive", v, true)}
                />
                <span className="ml-auto flex items-center gap-2.5 flex-wrap">
                  <span className="text-[12.5px] text-[var(--meta)]">采样率</span>
                  <HelpMark title={TIPS.sr_type} />
                  <Select
                    width={140}
                    value={c.str("sr_type", "sr_device")}
                    options={[
                      { id: "sr_device", label: "跟随设备" },
                      { id: "sr_model", label: "跟随模型" },
                    ]}
                    onChange={(v) => c.set("sr_type", v, true)}
                  />
                  <Btn onClick={onReloadDevices} disabled={devicesBusy}>
                    {devicesBusy ? "读取中…" : "重载设备列表"}
                  </Btn>
                </span>
              </div>
              {deviceHint ? (
                <div className="text-[12.5px] text-[var(--help)]">{deviceHint}</div>
              ) : null}
            </div>
          </Block>
        ) : null}

        {c.loaded && tab === "变声参数" ? (
          <Block title="变声参数" note="运行中可热更新 · 按音色保存" className="!mt-6">
            <p className="text-[12.5px] text-[var(--help)] leading-relaxed m-0 mb-4 max-w-[80ch]">
              这里的调整会跟着当前音色一起记住，下次选回这个音色就是你上次调好的样子。
              底栏也能快速调音高和共鸣。
            </p>
            <div className={CARD}>
              <Field
                label="响应阈值"
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
                label="音高"
                tip={TIPS.pitch}
                control={
                  <Slider
                    value={c.num("pitch")}
                    min={-24}
                    max={24}
                    step={1}
                    onChange={(v) => c.set("pitch", v)}
                    format={(v) => (v > 0 ? `+${v}` : `${v}`)}
                  />
                }
              />
              <Field
                label="共鸣"
                tip={TIPS.formant}
                control={
                  <Slider
                    value={c.num("formant")}
                    min={-2}
                    max={2}
                    step={0.05}
                    onChange={(v) => c.set("formant", v)}
                    format={(v) => v.toFixed(2)}
                  />
                }
              />
              <Field
                label="检索强度"
                tip={TIPS.index_rate}
                control={
                  <Slider
                    value={c.num("index_rate", 0.75)}
                    min={0}
                    max={1}
                    step={0.01}
                    onChange={(v) => c.set("index_rate", v)}
                    format={(v) => v.toFixed(2)}
                  />
                }
              />
              <Field
                label="响度包络"
                tip={TIPS.rms_mix_rate}
                control={
                  <Slider
                    value={c.num("rms_mix_rate", 0.25)}
                    min={0}
                    max={1}
                    step={0.01}
                    onChange={(v) => c.set("rms_mix_rate", v)}
                    format={(v) => v.toFixed(2)}
                  />
                }
              />
              <Field
                label="音高算法"
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

        {c.loaded && tab === "性能设置" ? (
          <Block title="性能设置" note="改后需重新「开启变声」" className="!mt-6">
            <div className={CARD}>
              <Field
                label="采样块时长"
                tip={TIPS.block_time}
                control={
                  <Slider
                    value={c.num("block_time", 0.25)}
                    min={0.05}
                    max={1}
                    step={0.01}
                    onChange={(v) => c.set("block_time", v)}
                    format={(v) => `${v.toFixed(2)} s`}
                  />
                }
              />
              <Field
                label="交叉淡化"
                tip={TIPS.crossfade_length}
                control={
                  <Slider
                    value={c.num("crossfade_length", 0.08)}
                    min={0.01}
                    max={0.5}
                    step={0.01}
                    onChange={(v) => c.set("crossfade_length", v)}
                    format={(v) => `${v.toFixed(2)} s`}
                  />
                }
              />
              <Field
                label="额外推理时长"
                tip={TIPS.extra_time}
                control={
                  <Slider
                    value={c.num("extra_time", 2.5)}
                    min={0.5}
                    max={5}
                    step={0.1}
                    onChange={(v) => c.set("extra_time", v)}
                    format={(v) => `${v.toFixed(1)} s`}
                  />
                }
              />
              <Field
                label="CPU 线程数"
                tip={TIPS.n_cpu}
                control={
                  <Slider
                    value={c.num("n_cpu", 4)}
                    min={1}
                    max={16}
                    step={1}
                    onChange={(v) => c.set("n_cpu", v)}
                  />
                }
              />
              <Toggle
                label="CUDA Graph 加速（仅 N 卡）"
                tip={TIPS.cuda_graph}
                checked={c.bool("cuda_graph")}
                onChange={(v) => c.set("cuda_graph", v)}
              />
            </div>
          </Block>
        ) : null}

        {c.loaded && tab === "声音效果" ? (
          <Block title="声音效果" note="变声后 · 可选" className="!mt-6">
            <div className={CARD}>
              <Toggle
                label="输入降噪"
                tip={TIPS.I_noise_reduce}
                checked={c.bool("I_noise_reduce")}
                onChange={(v) => c.set("I_noise_reduce", v, true)}
              />
              <Toggle
                label="输出降噪"
                tip={TIPS.O_noise_reduce}
                checked={c.bool("O_noise_reduce")}
                onChange={(v) => c.set("O_noise_reduce", v, true)}
              />
              <Toggle
                label="相位声码器"
                tip={TIPS.use_pv}
                checked={c.bool("use_pv")}
                onChange={(v) => c.set("use_pv", v, true)}
              />
            </div>

            {/* 变声后的 DSP 链。引擎侧一直有，迁到 Tauri 时壳层漏掉了整节。 */}
            <div className={`${CARD} mt-4`}>
              <Toggle
                label="后期处理"
                tip={TIPS.fx_enabled}
                checked={c.bool("fx_enabled")}
                onChange={(v) => c.set("fx_enabled", v, true)}
              />
              {fxOn ? (
                <>
                  <Field
                    label="音色均衡"
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
                    label="均衡预设"
                    tip={TIPS.fx_eq_preset}
                    control={
                      <Select
                        value={c.str("fx_eq_preset", "flat")}
                        options={[
                          ...EQ_PRESETS.map((p) => ({
                            id: p.id,
                            label: p.label,
                          })),
                          // 只用来显示「推子被手动动过了」。选它不做任何事，
                          // applyPreset 找不到就直接返回。引擎那边 gains 优先于
                          // preset，所以 custom 传下去也不会被当成 flat 复位。
                          ...(c.str("fx_eq_preset", "flat") === "custom"
                            ? [{ id: "custom", label: "自定义" }]
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
                    label="噪声门"
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
                    label="噪声门阈值"
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
                    label="压缩器"
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
                    label="压缩阈值"
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
                    label="压缩比"
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
                    label="输出增益"
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

        {c.loaded && tab === "外观" ? (
          <Block title="外观" className="!mt-6">
            <div className={CARD}>
              <Field
                label="界面配色"
                tip={TIPS.theme_mode}
                inline
                control={
                  <Select
                    width={150}
                    value={c.str("theme_mode", "system")}
                    options={[
                      { id: "system", label: "跟随系统" },
                      { id: "light", label: "浅色" },
                      { id: "dark", label: "深色" },
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
                label="背景图"
                tip={TIPS.wallpaper_path}
                desc="静态图，最大 20 MB，最长边 4096"
                control={
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <Btn onClick={() => void pickWallpaper(c.set)}>选择图片</Btn>
                    {c.str("wallpaper_path") ? (
                      <>
                        <span className="text-[12.5px] text-[var(--meta)] max-w-[280px] truncate">
                          {c.str("wallpaper_path")}
                        </span>
                        <Btn onClick={() => c.set("wallpaper_path", "", true)}>清除</Btn>
                      </>
                    ) : (
                      <span className="text-[12.5px] text-[var(--meta)]">未设置</span>
                    )}
                  </div>
                }
              />
              <Field
                label="磨砂强度"
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
                label="不透明度"
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

        {c.loaded && tab === "常规" ? (
          <Block title="常规" className="!mt-6">
            <div className={CARD}>
              <Field
                label="关闭窗口时"
                tip={TIPS.close_action}
                inline
                control={
                  <Select
                    width={170}
                    value={c.str("close_action", "ask")}
                    options={[
                      { id: "ask", label: "每次询问" },
                      { id: "tray", label: "最小化到托盘" },
                      { id: "exit", label: "直接退出" },
                    ]}
                    onChange={(v) => c.set("close_action", v, true)}
                  />
                }
              />
              <Field
                label="参与用户统计"
                tip={TIPS.telemetry_opt_in}
                desc="只发送随机匿名编号、软件版本、显卡加速方式；不发送账号、音色、录音或任何能定位到你的信息"
                control={
                  <Toggle
                    label={c.cfg.telemetry_opt_in === true ? "已参与" : "未参与"}
                    checked={c.cfg.telemetry_opt_in === true}
                    onChange={(v) => c.set("telemetry_opt_in", v, true)}
                  />
                }
              />
            </div>
          </Block>
        ) : null}

        {c.loaded && tab === "快捷键" ? (
          <Block title="快捷键" className="!mt-6">
            <div className={CARD}>
              <Toggle
                label="启用全局快捷键"
                tip={TIPS.hotkeys_enabled}
                checked={c.bool("hotkeys_enabled")}
                onChange={(v) => {
                  c.set("hotkeys_enabled", v, true);
                  void invoke("hotkeys_apply", { enabled: v });
                }}
              />
              <div className="flex flex-col">
                {HOTKEYS.map((h) => (
                  <HotkeyRow
                    key={h.key}
                    label={h.label}
                    value={c.str(h.key, h.fallback)}
                    onChange={(v) => {
                      c.set(h.key, v, true);
                      void invoke("hotkeys_apply", {
                        enabled: c.bool("hotkeys_enabled"),
                      });
                    }}
                  />
                ))}
              </div>
              <p className="text-xs text-[var(--help)] m-0">
                点右侧的组合键再按新的键就能改。可以带 Ctrl / Alt / Shift。
                被别的软件占用的组合会注册失败，换一个即可。
              </p>
            </div>
          </Block>
        ) : null}

        {c.loaded && tab === "在线更新" ? (
          <Block title="在线更新" className="!mt-6">
            <div className={CARD}>
              <Field
                label="检查更新"
                desc={updateLine || "检查是否有新版本"}
                inline
                control={
                  <Btn onClick={onCheckUpdate} disabled={updateBusy}>
                    {updateBusy ? "检查中…" : "立即检查"}
                  </Btn>
                }
              />
              <p className="text-xs text-[var(--help)] m-0 leading-[1.75]">
                有新版本时会自动下载并安装，重启软件后生效。
              </p>
            </div>
          </Block>
        ) : null}
      </PagePad>
    </div>
  );
}

const HOTKEYS = [
  { key: "hotkey_toggle_vc", label: "开启 / 停止变声", fallback: "CmdOrCtrl+F2" },
  { key: "hotkey_toggle_mode", label: "变声 / 原声", fallback: "CmdOrCtrl+F3" },
  { key: "hotkey_prev_voice", label: "上一个音色", fallback: "CmdOrCtrl+F5" },
  { key: "hotkey_next_voice", label: "下一个音色", fallback: "CmdOrCtrl+F6" },
];

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
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  const [recording, setRecording] = useState(false);

  const onKeyDown = (e: React.KeyboardEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.key === "Escape") {
      setRecording(false);
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

    setRecording(false);
    onChange([...mods, main].join("+"));
  };

  return (
    <div className="flex items-center py-2.5 border-b border-[var(--hairline)] last:border-b-0">
      <span className="text-[13px]">{label}</span>
      <button
        type="button"
        onClick={() => setRecording(true)}
        onBlur={() => setRecording(false)}
        onKeyDown={recording ? onKeyDown : undefined}
        className={[
          "ml-auto px-2.5 py-1 rounded-[var(--rs)] border-0 cursor-pointer",
          "text-[12.5px] tabular-nums bg-transparent",
          "shadow-[inset_0_0_0_1px_var(--line)] transition-colors duration-200",
          "focus-visible:outline-2 focus-visible:outline-[var(--accent)] focus-visible:outline-offset-2",
          recording
            ? "text-[var(--accent)] shadow-[inset_0_0_0_1px_var(--accent)]"
            : "text-[var(--meta)] hover:text-[var(--ink)]",
        ].join(" ")}
      >
        {recording ? "按下组合键…" : prettyCombo(value)}
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
