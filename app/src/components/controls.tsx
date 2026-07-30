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
      {options.length === 0 ? <option value="">（无可用项）</option> : null}
      {options.map((o) => (
        <option key={o.id} value={o.id}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

/** Full-width slider with the value on the right, matching the Tk shell. */
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
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="flex-1 accent-[var(--accent)] cursor-pointer"
      />
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
