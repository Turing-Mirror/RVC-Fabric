import type { ReactNode } from "react";
import { HelpMark } from "./ui";

/**
 * Settings field: label (+ the detailed-help ?) above, control below.
 * No divider between fields — spacing does the separating.
 */
export function Field({
  label,
  tip,
  desc,
  note,
  inline = false,
  control,
}: {
  label: string;
  tip?: string;
  desc?: string;
  note?: string;
  inline?: boolean;
  control: ReactNode;
}) {
  if (inline) {
    return (
      <div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-[9px] text-sm">
            {label}
            {tip ? <HelpMark title={tip} /> : null}
          </div>
          <div className="ml-auto">{control}</div>
        </div>
        {note ? (
          <div className="text-xs text-[var(--help)] mt-[9px] leading-[1.75] whitespace-pre-line">
            {note}
          </div>
        ) : null}
      </div>
    );
  }
  return (
    <div>
      <div className="flex items-center gap-[9px] text-sm mb-[9px]">
        {label}
        {tip ? <HelpMark title={tip} /> : null}
      </div>
      {desc ? (
        <div className="text-[12.5px] text-[var(--help)] -mt-1 mb-[9px] leading-relaxed">
          {desc}
        </div>
      ) : null}
      {control}
      {note ? (
        <div className="text-xs text-[var(--help)] mt-[9px] leading-[1.75] whitespace-pre-line">
          {note}
        </div>
      ) : null}
    </div>
  );
}

export function Select({
  value,
  options,
  onChange,
  full = false,
  width,
  disabled = false,
}: {
  value: string;
  options: { id: string; label: string }[];
  onChange: (v: string) => void;
  full?: boolean;
  width?: number;
  disabled?: boolean;
}) {
  // A saved device that is not in the current list (unplugged, driver reset)
  // otherwise renders as a blank box: the row looks unset while the engine is
  // still configured to use it. Keep it visible and say what happened.
  const missing = Boolean(value) && !options.some((o) => o.id === value);
  return (
    <select
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      style={width ? { minWidth: width } : undefined}
      className={[
        "text-[13px] text-[var(--ink)] bg-transparent appearance-none cursor-pointer",
        "px-3.5 py-[7px] rounded-[var(--rs)] shadow-[inset_0_0_0_1px_var(--line)]",
        "outline-none focus:shadow-[inset_0_0_0_1px_var(--accent)] disabled:opacity-50",
        full ? "w-full" : "",
      ].join(" ")}
    >
      {options.length === 0 && !missing ? (
        <option value="">（无可用项）</option>
      ) : null}
      {missing ? <option value={value}>{value}（当前不可用）</option> : null}
      {options.map((o) => (
        <option key={o.id} value={o.id}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

/** 把手宽度。位置计算要用到它的具体数值，所以写死在这里而不是 CSS 里。 */
const KNOB_W = 26;

/**
 * 数值条。一条较粗的轨道 + 一个白色把手，把手推到哪里就是多少。
 *
 * 位置算法：把手左边缘 = `pct% - KNOB_W*pct/100`。这样 0% 时贴左边、100% 时
 * 贴右边，中间线性 —— 把手永远不会探出轨道。填充条的右边缘对齐把手中心，
 * 所以看上去是「推着走」而不是「拉一条线」。
 *
 * 真正接受输入的是盖在上面那个透明的原生 range：键盘、触屏、无障碍都由它
 * 负责，上面画的东西只是外观。
 */
export function RangeBar({
  value,
  min,
  max,
  step,
  onChange,
  ticks = 5,
  ariaLabel,
}: {
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  /** 轨道上的刻度点数量，0 表示不画。 */
  ticks?: number;
  ariaLabel?: string;
}) {
  const span = max - min || 1;
  const pct = Math.min(100, Math.max(0, ((value - min) / span) * 100));
  const knobLeft = `calc(${pct}% - ${(KNOB_W * pct) / 100}px)`;
  const fillW = `calc(${pct}% - ${(KNOB_W * pct) / 100 - KNOB_W / 2}px)`;

  return (
    <div className="relative h-[26px] w-full rounded-full bg-[color-mix(in_srgb,var(--ink)_7%,transparent)] overflow-hidden">
      <div
        aria-hidden
        className="absolute inset-y-0 left-0 rounded-full bg-[linear-gradient(90deg,color-mix(in_srgb,var(--accent)_10%,transparent),color-mix(in_srgb,var(--accent)_30%,transparent))]"
        style={{ width: fillW }}
      />
      {ticks > 0 ? (
        <div aria-hidden className="absolute inset-0 flex items-center justify-between px-[13px]">
          {Array.from({ length: ticks }, (_, i) => (
            <span
              key={i}
              className="w-[3px] h-[3px] rounded-full bg-[color-mix(in_srgb,var(--ink)_22%,transparent)]"
            />
          ))}
        </div>
      ) : null}
      <div
        aria-hidden
        className="absolute top-[3px] bottom-[3px] rounded-full bg-[var(--surface)] shadow-[0_1px_3px_rgba(0,0,0,.18)] transition-[left] duration-100 ease-out"
        style={{ left: knobLeft, width: KNOB_W }}
      />
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        aria-label={ariaLabel}
        onChange={(e) => onChange(Number(e.target.value))}
        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
      />
    </div>
  );
}

/** 设置页里的一行数值条：条子在左，数值在右。 */
export function Slider({
  value,
  min,
  max,
  step,
  onChange,
  format,
}: {
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  format?: (v: number) => string;
}) {
  const shown = format ? format(value) : String(value);
  return (
    <div className="flex items-center gap-[15px] w-full">
      {/* 窄一点：铺满整行的条子既难瞄准也不好看 */}
      <div className="flex-1 max-w-[300px]">
        <RangeBar value={value} min={min} max={max} step={step} onChange={onChange} />
      </div>
      <div className="text-[13px] min-w-[56px] text-right tabular-nums">{shown}</div>
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  tip,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  tip?: string;
}) {
  return (
    <label className="flex items-center gap-[11px] cursor-pointer select-none">
      {tip ? <HelpMark title={tip} /> : null}
      <span
        role="checkbox"
        aria-checked={checked}
        onClick={(e) => {
          e.preventDefault();
          onChange(!checked);
        }}
        className={[
          "w-[15px] h-[15px] rounded grid place-items-center flex-none transition-colors",
          checked
            ? "bg-[var(--accent)]"
            : "shadow-[inset_0_0_0_1px_var(--line)]",
        ].join(" ")}
      >
        {checked ? (
          <span className="text-[10px] leading-none text-[var(--accent-ink)]">✓</span>
        ) : null}
      </span>
      <input
        type="checkbox"
        className="sr-only"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="text-sm">{label}</span>
    </label>
  );
}
