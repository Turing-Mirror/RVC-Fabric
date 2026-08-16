import { SegmentControl } from "./SegmentControl";
import { RangeBar } from "./controls";
import { HelpMark } from "./ui";
import { dspTips } from "../lib/dspTips";
import { useI18n } from "../i18n";

export type OutputMode = "vc" | "bypass";

type Props = {
  voiceName?: string;
  /** 生效中的 DSP 预设名；空 = 没开。 */
  dspName?: string;
  /** 点一下关掉 DSP。 */
  onStopDsp?: () => void;
  voiceTag?: string;
  voiceIndex?: string;
  profileSummary?: string;
  pitch: number;
  formant: number;
  onPitch: (v: number) => void;
  onFormant: (v: number) => void;
  mode: OutputMode;
  onMode: (m: OutputMode) => void;
  running: boolean;
  onToggleRun: () => void;
  statusTitle?: string;
  statusSub?: string;
  /** 0–99 while the engine is loading or switching; null to hide the bar. */
  progress?: number | null;
  /** True while starting or switching without a numeric percent yet. */
  loading?: boolean;
  /** Mic level in dBFS from the worker; null when the engine is idle. */
  micDb?: number | null;
  /** Response gate in dBFS. Bar stays muted until the level reaches it. */
  thresholdDb?: number;
};

/**
 * Persistent bottom dock (voice summary, mode, pitch/formant, start/stop).
 * Wired to Runtime worker via Tauri when available.
 */
export function Dock({
  // No invented defaults for voice — empty means not selected.
  voiceName,
  dspName,
  onStopDsp,
  voiceTag = "",
  voiceIndex = "",
  profileSummary,
  pitch,
  formant,
  onPitch,
  onFormant,
  mode,
  onMode,
  running,
  onToggleRun,
  statusTitle,
  statusSub,
  progress = null,
  loading = false,
  micDb = null,
  thresholdDb = -60,
}: Props) {
  const { t } = useI18n();
  const name = voiceName?.trim()
    ? voiceName
    : dspName?.trim()
      ? dspName
      : t("dock.noVoice");
  const profile = profileSummary ?? t("dock.none");
  const title = statusTitle ?? t("dock.engineReady");
  const sub = statusSub ?? t("dock.engineIdle");

  // Same mapping as the Tk shell's _draw_mic_meter: -60..0 dBFS over the bar.
  const frac = (db: number) =>
    (Math.max(-60, Math.min(0, db)) + 60) / 60;
  const levelPct = micDb === null ? 0 : Math.round(frac(micDb) * 100);
  const gatePct = Math.round(frac(thresholdDb) * 100);
  // Below the gate the input is treated as silence and not converted — show
  // that by keeping the bar muted until it crosses the marker.
  const over = micDb !== null && micDb >= thresholdDb;

  return (
    <footer className="flex-none relative px-[30px] py-4 flex items-center gap-[30px] flex-wrap max-[1020px]:px-[22px] max-[1020px]:gap-[22px] max-[720px]:px-4 max-[720px]:gap-4">
      {/* Hairline: inset ends, not full-width border-top */}
      <div
        aria-hidden
        className="absolute top-0 left-[30px] right-[30px] h-px bg-[var(--hairline)] max-[1020px]:left-[22px] max-[1020px]:right-[22px] max-[720px]:left-4 max-[720px]:right-4"
      />

      <div className="min-w-[190px] max-w-[240px] max-[720px]:min-w-0 max-[720px]:max-w-none max-[720px]:flex-1 max-[720px]:basis-full">
        <div className="text-[15px] font-semibold">
          {t("dock.current", { name })}
        </div>
        {dspName ? (
          <div className="mt-1 flex items-center gap-1.5 font-mono text-[11.5px] text-[var(--meta)]">
            <HelpMark title={dspTips().stack} />
            <button
              type="button"
              onClick={onStopDsp}
              title={t("dock.dspStopHint")}
              className="truncate max-w-[92px] underline decoration-dotted underline-offset-2 hover:text-[var(--ink)]"
            >
              {dspName}
            </button>
          </div>
        ) : null}
        {voiceTag || voiceIndex ? (
          <div className="text-xs text-[var(--meta)] mt-0.5">
            {[voiceTag, voiceIndex].filter(Boolean).join(" · ")}
          </div>
        ) : null}
        <div
          className="text-[11.5px] text-[var(--meta)] mt-0.5 overflow-hidden text-ellipsis whitespace-nowrap"
          title={profile}
        >
          {profile}
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <SegmentControl
          options={[
            {
              id: "vc" as const,
              label: t("dock.modeVc"),
              title: t("dock.modeVcTip"),
            },
            {
              id: "bypass" as const,
              label: t("dock.modeBypass"),
              title: t("dock.modeBypassTip"),
            },
          ]}
          value={mode}
          onChange={onMode}
          className="!ml-0"
        />
        <div className="flex items-center gap-2.5">
          <span className="text-[11.5px] text-[var(--meta)]">{t("dock.mic")}</span>
          <div
            className="relative w-[152px] h-1.5 rounded-sm overflow-hidden bg-[color-mix(in_srgb,var(--ink)_10%,transparent)]"
            title={t("dock.micLevelTip")}
          >
            <div
              className={
                "absolute inset-y-0 left-0 rounded-sm transition-[width,background-color] duration-75 linear " +
                (over
                  ? "bg-[var(--accent)]"
                  : "bg-[color-mix(in_srgb,var(--ink)_28%,transparent)]")
              }
              style={{ width: `${levelPct}%` }}
            />
            <div
              className="absolute top-0 bottom-0 w-px bg-[var(--notify)]"
              style={{ left: `${gatePct}%` }}
            />
          </div>
        </div>
      </div>

      <div className="flex gap-[30px] flex-[1_1_250px] min-w-[210px] max-[860px]:flex-[1_1_100%] max-[860px]:order-3">
        <SliderTile
          label={t("dock.pitch")}
          display={pitch >= 0 ? `+${pitch}` : `${pitch}`}
          min={-24}
          max={24}
          step={1}
          value={pitch}
          defaultValue={0}
          onChange={onPitch}
        />
        <SliderTile
          label={t("dock.formant")}
          display={formant >= 0 ? `+${formant.toFixed(2)}` : formant.toFixed(2)}
          min={-2}
          max={2}
          step={0.05}
          value={formant}
          defaultValue={0}
          onChange={onFormant}
        />
      </div>

      <div className="ml-auto flex items-center gap-[18px] max-[860px]:order-4">
        <div className="text-right min-w-[148px]">
          <div className="text-[13px] font-semibold text-[var(--ink-muted)]">
            {title}
          </div>
          <div className="text-[11.5px] text-[var(--meta)] mt-0.5">
            {sub}
          </div>
          {progress != null ? (
            <div
              className="ml-auto mt-1.5 h-1 w-[132px] overflow-hidden rounded-sm bg-[color-mix(in_srgb,var(--ink)_10%,transparent)]"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(progress)}
            >
              <div
                className="h-full bg-[var(--accent)] transition-[width] duration-200 ease-out"
                style={{ width: `${Math.max(4, Math.min(100, progress))}%` }}
              />
            </div>
          ) : loading ? (
            <div className="relative ml-auto mt-1.5 h-1 w-[132px] overflow-hidden rounded-sm bg-[color-mix(in_srgb,var(--ink)_10%,transparent)]">
              <div className="absolute inset-y-0 w-1/3 bg-[var(--accent)] dock-bar-indeterminate" />
            </div>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onToggleRun}
          className={[
            "border-0 rounded-[var(--rs)] px-7 py-3 cursor-pointer whitespace-nowrap",
            "text-sm font-semibold bg-[var(--accent)] text-[var(--accent-ink)]",
            // 不加彩色光晕。悬停只是稍微压暗一点 —— 按钮周围散出一圈强调色的
            // 光是纯装饰，跟状态没有任何关系。
            "transition-[transform,filter] duration-200 ease-[var(--spring)]",
            "hover:brightness-95",
            "active:scale-[0.965]",
            "focus-visible:outline-2 focus-visible:outline-[var(--accent)] focus-visible:outline-offset-2",
          ].join(" ")}
        >
          {running ? t("dock.stop") : t("dock.start")}
        </button>
      </div>
    </footer>
  );
}

function SliderTile({
  label,
  display,
  min,
  max,
  step,
  value,
  onChange,
  defaultValue,
}: {
  label: string;
  display: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (v: number) => void;
  /** 中性/初始值位置（音高 0、共鸣 0）。 */
  defaultValue?: number;
}) {
  return (
    // 上限从 210 放到 300：音高一整条是 −24~+24 共 49 格，210px 下一格 4px，
    // 拖过去基本靠猜。宽窗口下这一档能吃到 300px，一格 6px，好瞄不少。
    // 还是留个上限 —— 底栏右边还有状态和「开启变声」，条子无限长会把它们挤走。
    <div className="flex-1 min-w-[100px] max-w-[300px]">
      <div className="flex justify-between items-baseline mb-2">
        <span className="text-xs text-[var(--meta)]">{label}</span>
        <b className="text-[15px] font-semibold tabular-nums">{display}</b>
      </div>
      <RangeBar
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={onChange}
        defaultValue={defaultValue}
        ariaLabel={label}
      />
    </div>
  );
}
