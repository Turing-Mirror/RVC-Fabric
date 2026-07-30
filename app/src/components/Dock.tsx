import { useState } from "react";
import { SegmentControl } from "./SegmentControl";

export type OutputMode = "vc" | "bypass";

type Props = {
  voiceName?: string;
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
  /** 0..1 mock meter until worker is wired (stage 2). */
  meterLevel?: number;
  threshold?: number;
};

/**
 * Persistent bottom dock — layout matches handoff preview.
 * Engine actions are stubs until stage 2 (worker bridge).
 */
export function Dock({
  voiceName = "Anon",
  voiceTag = "少女音",
  voiceIndex = "1/3",
  profileSummary = "开黑日常 · 音高 +15 共鸣 1.20",
  pitch,
  formant,
  onPitch,
  onFormant,
  mode,
  onMode,
  running,
  onToggleRun,
  statusTitle = "引擎待命",
  statusSub = "就绪",
  meterLevel = 0.2,
  threshold = 0.26,
}: Props) {
  return (
    <footer className="flex-none relative px-[30px] py-4 flex items-center gap-[30px] flex-wrap max-[1020px]:px-[22px] max-[1020px]:gap-[22px] max-[720px]:px-4 max-[720px]:gap-4">
      {/* Hairline: inset ends, not full-width border-top */}
      <div
        aria-hidden
        className="absolute top-0 left-[30px] right-[30px] h-px bg-[var(--hairline)] max-[1020px]:left-[22px] max-[1020px]:right-[22px] max-[720px]:left-4 max-[720px]:right-4"
      />

      <div className="min-w-[190px] max-w-[240px] max-[720px]:min-w-0 max-[720px]:max-w-none max-[720px]:flex-1 max-[720px]:basis-full">
        <div className="text-[15px] font-semibold">当前：{voiceName}</div>
        <div className="text-xs text-[var(--meta)] mt-0.5">
          {voiceTag} · {voiceIndex}
        </div>
        <div
          className="text-[11.5px] text-[var(--meta)] mt-0.5 overflow-hidden text-ellipsis whitespace-nowrap"
          title={profileSummary}
        >
          {profileSummary}
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <SegmentControl
          options={[
            {
              id: "vc" as const,
              label: "输出变声",
              title: "麦克风 → 变成所选音色再输出（日常开黑）",
            },
            {
              id: "bypass" as const,
              label: "原声旁路",
              title: "不改变声音，只输出麦克风原声，用来测麦 / 连接",
            },
          ]}
          value={mode}
          onChange={onMode}
          className="!ml-0"
        />
        <div className="flex items-center gap-2.5">
          <span className="text-[11.5px] text-[var(--meta)]">麦克风</span>
          <div
            className="relative w-[152px] h-1.5 rounded-sm overflow-hidden bg-[color-mix(in_srgb,var(--ink)_10%,transparent)]"
            title="麦克风电平；竖线为响应阈值"
          >
            <div
              className="absolute inset-y-0 left-0 bg-[var(--accent)] rounded-sm transition-[width] duration-75 linear"
              style={{ width: `${Math.round(meterLevel * 100)}%` }}
            />
            <div
              className="absolute top-0 bottom-0 w-px bg-[color-mix(in_srgb,var(--ink)_45%,transparent)]"
              style={{ left: `${Math.round(threshold * 100)}%` }}
            />
          </div>
        </div>
      </div>

      <div className="flex gap-[30px] flex-[1_1_250px] min-w-[210px] max-[860px]:flex-[1_1_100%] max-[860px]:order-3">
        <SliderTile
          label="音高"
          display={pitch >= 0 ? `+${pitch}` : `${pitch}`}
          min={-24}
          max={24}
          step={1}
          value={pitch}
          onChange={onPitch}
        />
        <SliderTile
          label="共鸣"
          display={formant >= 0 ? `+${formant.toFixed(2)}` : formant.toFixed(2)}
          min={-2}
          max={2}
          step={0.05}
          value={formant}
          onChange={onFormant}
        />
      </div>

      <div className="ml-auto flex items-center gap-[18px] max-[860px]:order-4">
        <div className="text-right">
          <div className="text-[13px] font-semibold text-[var(--ink-muted)]">
            {statusTitle}
          </div>
          <div className="text-[11.5px] text-[var(--meta)] mt-0.5">
            {statusSub}
          </div>
        </div>
        <button
          type="button"
          onClick={onToggleRun}
          className={[
            "border-0 rounded-[var(--rs)] px-7 py-3 cursor-pointer whitespace-nowrap",
            "text-sm font-semibold bg-[var(--accent)] text-[var(--accent-ink)]",
            "shadow-[0_1px_3px_color-mix(in_srgb,var(--accent)_30%,transparent)]",
            "transition-[transform,background,box-shadow] duration-200 ease-[var(--spring)]",
            "hover:shadow-[0_4px_14px_color-mix(in_srgb,var(--accent)_34%,transparent)] hover:-translate-y-px",
            "active:scale-[0.965]",
            "focus-visible:outline-2 focus-visible:outline-[var(--accent)] focus-visible:outline-offset-2",
          ].join(" ")}
        >
          {running ? "停止变声" : "开启变声"}
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
}: {
  label: string;
  display: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (v: number) => void;
}) {
  const [hover, setHover] = useState(false);
  const pct = ((value - min) / (max - min)) * 100;

  return (
    <div className="flex-1 min-w-[100px]">
      <div className="flex justify-between items-baseline mb-2.5">
        <span className="text-xs text-[var(--meta)]">{label}</span>
        <b className="text-[15px] font-semibold">{display}</b>
      </div>
      <div
        className="flex items-center gap-3 w-full"
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
      >
        <div className="relative flex-1 h-[3px] rounded-sm bg-[color-mix(in_srgb,var(--ink)_11%,transparent)]">
          <div
            className="absolute inset-y-0 left-0 bg-[var(--accent)] rounded-sm"
            style={{ width: `${pct}%` }}
          />
          <div
            className="absolute top-1/2 w-3 h-3 -mt-1.5 -ml-1.5 rounded-full bg-[var(--surface)] shadow-[0_1px_4px_rgba(0,0,0,.24),inset_0_0_0_1px_var(--line)] transition-transform duration-300 ease-[var(--spring)]"
            style={{
              left: `${pct}%`,
              transform: hover ? "scale(1.3)" : "scale(1)",
            }}
          />
          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={value}
            onChange={(e) => onChange(Number(e.target.value))}
            className="absolute inset-0 w-full opacity-0 cursor-pointer"
            aria-label={label}
          />
        </div>
      </div>
    </div>
  );
}
