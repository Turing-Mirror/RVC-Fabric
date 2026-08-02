import { useEffect, useState, type ReactNode } from "react";
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

/** 轨道高度。把手上下贴齐轨道，所以两者共用这一个数。 */
const TRACK_H = 26;
/** 把手宽度。位置计算要用到它的具体数值，所以写死在这里而不是 CSS 里。
 *  比轨道高度窄一截：又高又细的竖条不好看，也不好瞄。 */
const KNOB_W = 21;

/**
 * 拖动中的过渡时长。
 *
 * 拖动时不能用长过渡：把手会落在光标后面，手感像拖着一块橡皮。但也不能干脆
 * 关掉 —— 步长粗的条子（比如音高，−12~+12 在 460px 上一步就是 19px）会一格
 * 一格地跳。70ms 只够抹平这个跳格，短到看不出滞后。
 */
const GLIDE_DRAG_MS = 70;
/** 松手后的位移：点轨道、按方向键、切档案带来的跳变，走这条长一点的曲线。 */
const GLIDE_IDLE_MS = 190;

/**
 * 数值条。一条较粗的轨道 + 一个把手，把手推到哪里就是多少。
 *
 * 位置算法：把手左边缘 = `pct% - KNOB_W*pct/100`。这样 0% 时贴左边、100% 时
 * 贴右边，中间线性 —— 把手永远不会探出轨道。填充条的右边缘对齐把手中心，
 * 所以看上去是「推着走」而不是「拉一条线」。
 *
 * 把手和填充必须用**同一套过渡**。以前把手有 100ms 的 left 过渡、填充的
 * width 一点过渡都没有：点一下轨道，颜色瞬间到位、把手还在慢慢挪，两者
 * 分家；拖动时反过来，颜色跟着光标、把手拖在后面。看着就是「推动和颜色
 * 走得不连贯」。
 *
 * 把手走 transform 不走 left：transform 由合成器处理，不会每帧触发布局。
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
  const knobX = `calc(${pct}% - ${(KNOB_W * pct) / 100}px)`;
  const fillW = `calc(${pct}% - ${(KNOB_W * pct) / 100 - KNOB_W / 2}px)`;

  const [dragging, setDragging] = useState(false);
  // 光标在条子外面松开时，pointerup 不一定回到这个元素上（原生 range 会
  // 捕获指针，但触屏被打断、窗口失焦这些情况不保证）。挂一个窗口级的兜底，
  // 否则一次意外就把条子永久锁在「拖动中」的短过渡上。
  useEffect(() => {
    if (!dragging) return;
    const stop = () => setDragging(false);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    window.addEventListener("blur", stop);
    return () => {
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      window.removeEventListener("blur", stop);
    };
  }, [dragging]);

  // 一份过渡，两个元素共用 —— 这是「连贯」的全部内容。
  //
  // 把手走 left 不走 transform：transform 的百分比是按**自己的宽度**算的
  // （21px），不是按轨道宽度，translateX(50%) 只有 10.5px，位置全错。
  // 这里只有一个绝对定位的小元素在动，动 left 的开销可以接受。
  const glide = {
    transitionProperty: "left, width, box-shadow",
    transitionDuration: `${dragging ? GLIDE_DRAG_MS : GLIDE_IDLE_MS}ms`,
    transitionTimingFunction: dragging
      ? "linear"
      : "var(--ease)",
  } as const;

  return (
    <div
      className="relative w-full rounded-full bg-[color-mix(in_srgb,var(--ink)_7%,transparent)] overflow-hidden"
      style={{ height: TRACK_H }}
    >
      {/* 渐变从左到右由浅到深：越推到右边颜色越实，一眼能看出推到了哪。
          原来两端分别是 10% / 30%，整条淡得几乎看不出是填充。 */}
      <div
        aria-hidden
        className="absolute inset-y-0 left-0 rounded-full bg-[linear-gradient(90deg,color-mix(in_srgb,var(--accent)_24%,transparent),color-mix(in_srgb,var(--accent)_66%,transparent))]"
        style={{ width: fillW, ...glide }}
      />
      {/* 左右各留半个把手宽，刻度才和把手中心的行程对齐。 */}
      {ticks > 0 ? (
        <div
          aria-hidden
          className="absolute inset-0 flex items-center justify-between"
          style={{ paddingInline: KNOB_W / 2 }}
        >
          {Array.from({ length: ticks }, (_, i) => (
            <span
              key={i}
              className="w-[3px] h-[3px] rounded-full bg-[color-mix(in_srgb,var(--ink)_22%,transparent)]"
            />
          ))}
        </div>
      ) : null}
      {/* 上下贴齐轨道外框。以前上下各缩 3px，把手看着又细又短，
          而且缩进那两条把轨道背景露出来，边缘显脏。 */}
      <div
        aria-hidden
        className={[
          "absolute inset-y-0 rounded-full bg-[var(--knob)]",
          "shadow-[0_1px_3px_rgba(0,0,0,.2),inset_0_0_0_1px_color-mix(in_srgb,var(--ink)_12%,transparent)]",
          // 抓住的时候压深一点影子。只有这一点反馈，不放大不变色 ——
          // 一个会长大的把手在密密麻麻的设置页里只会显得聒噪。
          dragging ? "!shadow-[0_2px_7px_rgba(0,0,0,.32)]" : "",
        ].join(" ")}
        style={{ left: knobX, width: KNOB_W, ...glide }}
      />
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        aria-label={ariaLabel}
        onChange={(e) => onChange(Number(e.target.value))}
        onPointerDown={() => setDragging(true)}
        onPointerUp={() => setDragging(false)}
        onPointerCancel={() => setDragging(false)}
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
      {/* 条子越长，同样的一格数值占的像素越多，越好精调。上限放宽到 460，
          窄窗口下 flex-1 自己会缩。 */}
      <div className="flex-1 max-w-[460px]">
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
