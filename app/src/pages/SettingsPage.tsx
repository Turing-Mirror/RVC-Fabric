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

function SettingsPageImpl({
  status,
  onReloadDevices,
  devicesBusy = false,
  workerAlive = false,
  onCheckUpdate,
  updateLine,
}: Props = {}) {
  const [tab, setTab] = useState<Tab>("设备与音频");
  const c = useConfig();

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
        ? "还没读到设备，点右边「重载设备列表」"
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
              输入＝真实麦克风 · 输出＝CABLE Input · 游戏麦克风＝CABLE Output。
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
                note={`Worker：${status?.worker_alive ? "在线" : "离线"} · 输入 ${inputs.length} / 输出 ${outputs.length}`}
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
                  label="WASAPI 独占（一般不要勾）"
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
                      { id: "sr_device", label: "sr_device" },
                      { id: "sr_model", label: "sr_model" },
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
              音高 / 共鸣 / 阈值 / Index / 响度 / 算法会写入当前音色目录的
              config.json；切换音色时自动恢复该音色上次的参数。底栏可快速调节。
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
                label="音高 Pitch"
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
                label="共鸣 Formant"
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
                label="Index 检索强度"
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
              <div className="flex flex-col gap-3 text-[13px] text-[var(--ink-muted)]">
                <div className="flex items-center">
                  <span>开启 / 停止变声</span>
                  <span className="ml-auto tabular-nums text-[var(--meta)]">Ctrl + F2</span>
                </div>
                <div className="flex items-center">
                  <span>输出变声 / 原声旁路</span>
                  <span className="ml-auto tabular-nums text-[var(--meta)]">Ctrl + F3</span>
                </div>
                <div className="flex items-center">
                  <span>上一个 / 下一个音色</span>
                  <span className="ml-auto tabular-nums text-[var(--meta)]">
                    Ctrl + F5 / F6
                  </span>
                </div>
              </div>
              <p className="text-xs text-[var(--help)] m-0">
                组合键暂不可自定义，与旧版保持一致。
              </p>
            </div>
          </Block>
        ) : null}

        {c.loaded && tab === "在线更新" ? (
          <Block title="在线更新" className="!mt-6">
            <div className={CARD}>
              <Field
                label="检查更新"
                desc={updateLine || "从 CNB 检查是否有新版本"}
                inline
                control={<Btn onClick={onCheckUpdate}>立即检查</Btn>}
              />
              <p className="text-xs text-[var(--help)] m-0 leading-[1.75]">
                界面更新会替换安装目录下的 frontend 文件夹，重启程序即生效；
                涉及程序本体的更新需要重新下载安装包。
              </p>
            </div>
          </Block>
        ) : null}
      </PagePad>
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
