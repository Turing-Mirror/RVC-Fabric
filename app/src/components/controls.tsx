import { useEffect, useRef, useState, type ReactNode } from "react";
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
          <div className="flex items-center gap-[9px] text-sm leading-none">
            <span className="leading-normal">{label}</span>
            {tip ? <HelpMark title={tip} /> : null}
          </div>
          <div className="ml-auto">{control}</div>
        </div>
        {/* inline 版以前**不画 desc**，传了也当没传。「在线更新」正是这么栽的：
            点完「立即检查」，「已是最新（1.3.5）」写进了 desc，然后被这里默默
            吞掉 —— 界面上一个字都没变，看着就像按钮坏了。少画一个 prop 不会
            报错，所以这种漏洞只能靠不留死角来防。 */}
        {desc ? (
          <div className="text-[12.5px] text-[var(--help)] mt-[7px] leading-relaxed">
            {desc}
          </div>
        ) : null}
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
      <div className="flex items-center gap-[9px] text-sm mb-[9px] leading-none">
        <span className="leading-normal">{label}</span>
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
 * 松手之后位移用的过渡：点轨道、按方向键、切档案带来的跳变，还有松手时把手
 * 从光标位置归到刻度上的那一下。
 *
 * 拖动中**没有过渡**，一帧都不留 —— 见下面 dragPct 的说明。
 */
const GLIDE_IDLE_MS = 190;

/**
 * 数值条。一条较粗的轨道 + 一个把手，把手推到哪里就是多少。
 *
 * 位置算法：把手左边缘 = `pct% - KNOB_W*pct/100`。这样 0% 时贴左边、100% 时
 * 贴右边，中间线性 —— 把手永远不会探出轨道。
 *
 * 填充条画到**把手的中心线**为止，右端是直角（rounded-l-full，右边不倒角）。
 * 这两件事必须一起成立，缺一个就露馅：
 *
 * - 右端倒角 + 画到中心：填充的圆头半径 13（轨道高的一半）比把手的 10.5 大，
 *   两段圆弧对不上，把手上下各露出一小块填充色 —— 最早那条「缝」。
 * - 右端直角 + 画到把手右边缘：把手右侧是个半圆，最右那一点高度为零，而填充
 *   是个满高的方块，于是方块从把手的圆弧外面探出来，绕着把手右半边糊一圈蓝色
 *   —— 就是「蓝色超过推子、溢出到后半段」。
 *
 * 直角 + 画到中心线才是对的：中心线正好是把手最宽的地方，满高的方块边正好被
 * 把手完全盖住。看到的边界只有「把手 | 轨道」这一条。
 *
 * 0% 时填充宽度是半个把手，被把手完全盖住，不会在最左边留一坨色。
 *
 * 把手和填充必须用**同一套过渡**。以前把手有 100ms 的 left 过渡、填充的
 * width 一点过渡都没有：点一下轨道，颜色瞬间到位、把手还在慢慢挪，两者
 * 分家；拖动时反过来，颜色跟着光标、把手拖在后面。
 *
 * **跟手是靠位置和数值解耦做到的，不是靠调过渡时长。**
 *
 * 数值是量化的（音高一步一个半音），可把手要跟着手指走。这两件事没法用同一个
 * 数表示：让把手画在量化后的位置上，粗步长的条子就一格一格地跳；给它加个过渡
 * 把跳格抹平，把手就永远落在光标后面 —— 之前那个 70ms 就是在这两个毛病之间
 * 各挨一半。
 *
 * 现在拖动时把手画在**光标的真实位置**（dragPct），过渡时长为 0，一帧都不差；
 * 抛给外面的仍然是量化后的值。松手时 dragPct 清空，把手用 GLIDE_IDLE_MS 那条
 * 曲线滑到刻度上 —— 这一下「归位」本身就是在告诉用户「实际取到的是这一格」。
 *
 * 真正接受输入的是盖在上面那个透明的原生 range：键盘、触屏、无障碍、以及数值
 * 的量化全都由它负责。我们只是额外记一下光标在哪，用来画把手。
 */
export function RangeBar({
  value,
  min,
  max,
  step,
  onChange,
  ariaLabel,
}: {
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  /**
   * @deprecated 不再绘制刻度/初始值标记；保留参数以免调用方报错。
   */
  ticks?: number;
  /**
   * @deprecated 不再绘制初始值竖线；保留参数以免调用方报错。
   */
  defaultValue?: number;
  ariaLabel?: string;
}) {
  const span = max - min || 1;
  const pct = Math.min(100, Math.max(0, ((value - min) / span) * 100));

  const trackRef = useRef<HTMLDivElement>(null);
  // 拖动中光标所在的百分比。null = 没在拖，把手画在量化后的位置上。
  const [dragPct, setDragPct] = useState<number | null>(null);
  const dragging = dragPct !== null;

  // 光标落在轨道哪儿（0..100）。把手中心的行程比轨道窄一个把手宽，所以要
  // 按「可走的那段」换算，否则推到两头时把手和光标会差半个把手。
  const pctFromClientX = (clientX: number): number => {
    const r = trackRef.current?.getBoundingClientRect();
    if (!r || r.width <= KNOB_W) return 0;
    const travel = r.width - KNOB_W;
    const x = clientX - r.left - KNOB_W / 2;
    return Math.min(100, Math.max(0, (x / travel) * 100));
  };

  // 光标在条子外面松开时，pointerup 不一定回到这个元素上（原生 range 会捕获
  // 指针，但触屏被打断、窗口失焦这些情况不保证）。挂一个窗口级的兜底，否则
  // 一次意外就把把手永久钉在光标最后出现的地方，再也不跟着数值走。
  useEffect(() => {
    if (!dragging) return;
    const move = (e: PointerEvent) => setDragPct(pctFromClientX(e.clientX));
    const stop = () => setDragPct(null);
    // 在 window 上跟，不在元素上：手指拖出条子外面之后仍然算数，
    // 这是所有原生推子的行为。
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    window.addEventListener("blur", stop);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      window.removeEventListener("blur", stop);
    };
  }, [dragging]);

  // 一份过渡，两个元素共用 —— 这是「连贯」的全部内容。
  //
  // 拖动中时长为 0：把手画的就是光标位置，再加过渡只会让它追不上自己。
  //
  // 把手走 left 不走 transform：transform 的百分比是按**自己的宽度**算的
  // （21px），不是按轨道宽度，translateX(50%) 只有 10.5px，位置全错。
  // 这里只有一个绝对定位的小元素在动，动 left 的开销可以接受。
  const glide = {
    transitionProperty: "left, width, box-shadow",
    transitionDuration: dragging ? "0ms" : `${GLIDE_IDLE_MS}ms`,
    transitionTimingFunction: "var(--ease)",
  } as const;

  // 画在哪：拖动中用光标位置，其余时候用数值算出来的位置。
  const draw = dragPct ?? pct;
  const knobX = `calc(${draw}% - ${(KNOB_W * draw) / 100}px)`;
  const fillW = `calc(${draw}% - ${(KNOB_W * draw) / 100 - KNOB_W / 2}px)`;

  return (
    <div
      ref={trackRef}
      className="relative w-full rounded-md bg-[color-mix(in_srgb,var(--ink)_7%,transparent)] overflow-hidden"
      style={{ height: TRACK_H }}
    >
      {/* 渐变从左到右由浅到深：越推到右边颜色越实，一眼能看出推到了哪。
          右端直角：那一截在把手底下，圆角只会在把手边切出弧。 */}
      <div
        aria-hidden
        className="absolute inset-y-0 left-0 rounded-l-md bg-[linear-gradient(90deg,color-mix(in_srgb,var(--accent)_24%,transparent),color-mix(in_srgb,var(--accent)_66%,transparent))]"
        style={{ width: fillW, ...glide }}
      />
      {/* 圆角方块把手（不是椭圆/胶囊）。不画刻度点 / 初始值竖线：界面更干净。 */}
      <div
        aria-hidden
        className={[
          "absolute inset-y-0 rounded-md bg-[var(--knob)]",
          "shadow-[0_1px_3px_rgba(0,0,0,.2),inset_0_0_0_1px_color-mix(in_srgb,var(--ink)_12%,transparent)]",
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
        onPointerDown={(e) => setDragPct(pctFromClientX(e.clientX))}
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
  defaultValue: _defaultValue,
}: {
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  format?: (v: number) => string;
  /** @deprecated 不再绘制初始值标记；保留以免调用方报错。 */
  defaultValue?: number;
}) {
  void _defaultValue;
  const shown = format ? format(value) : String(value);
  return (
    <div className="flex items-center gap-[15px] w-full">
      {/* 条子占满整行，不设上限：一格数值分到的像素最多，最好精调，看着也
          大方。右边只留数值那一列。以前卡了 460px 上限，宽窗口下条子缩在
          左半边，右边空一大片，反而显得小家子气。 */}
      <div className="flex-1">
        <RangeBar
          value={value}
          min={min}
          max={max}
          step={step}
          onChange={onChange}
        />
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
