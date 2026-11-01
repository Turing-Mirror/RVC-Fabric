import { useCallback, useEffect, useLayoutEffect, useRef, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";

export type SegmentOption<T extends string> = {
  id: T;
  label: ReactNode;
  title?: string;
  /** 这一项此时不能选：变淡，不接点击，滑块也不会停在上面。 */
  disabled?: boolean;
};

type Props<T extends string> = {
  options: SegmentOption<T>[];
  value: T;
  onChange: (id: T) => void;
  className?: string;
  /** 窄布局下不画滑块，退回逐项高亮。 */
  compact?: boolean;
  role?: "tablist" | "group";
};

/**
 * 液态玻璃分段控件：一个会滑动、可以用鼠标拖动的玻璃滑块。
 *
 * - 点一项：滑块以适中的力度弹过去，到达那一项上方时切换。
 * - 按住滑块拖动：滑块跟着鼠标走，宽度在相邻两项之间过渡；松手时按甩出的速度判断停在哪一项，
 *   松手即切换。用力甩向一端，滑块撞上边缘时会被压扁再弹回。
 * - 滑块下面的文字透过它被放大，像隔着一颗水珠看。做法是在滑块里放一份同样排版的文字，
 *   跟滑块反向移动、以滑块中心放大，所以文字始终清晰，不依赖只在部分浏览器可用的 SVG 滤镜。
 *
 * 运动用一个弹簧模拟（每帧按位置差与速度算加速度），不是固定时长的过渡：
 * 拖动、甩出、点击、中途改主意都从当前位置和速度接着走，不会跳。
 * 参考：shuding/liquid-glass、rdev/liquid-glass-react（I:\Other_Dev）。
 */
export function SegmentControl<T extends string>({ options, value, onChange, className = "", compact = false, role = "group" }: Props<T>) {
  const rootRef = useRef<HTMLDivElement>(null);
  const thumbRef = useRef<HTMLSpanElement>(null);
  const glassRef = useRef<HTMLSpanElement>(null);
  const lensRef = useRef<HTMLSpanElement>(null);
  const btnRefs = useRef<Map<T, HTMLButtonElement>>(new Map());
  const sim = useRef<Sim | null>(null);
  const latest = useRef({ options, value, onChange });
  latest.current = { options, value, onChange };

  /** 各项此刻的位置与宽度，按 options 的顺序。 */
  const slots = useCallback(() => {
    return latest.current.options.map((o) => {
      const el = btnRefs.current.get(o.id);
      return { id: o.id, x: el?.offsetLeft ?? 0, w: el?.offsetWidth ?? 0, disabled: Boolean(o.disabled) };
    });
  }, []);

  // 模拟器在第一次渲染时就建好：下面的布局阶段要用它把滑块放到位
  if (!sim.current) {
    sim.current = new Sim({
      paint: (p) => paint(p, thumbRef.current, glassRef.current, lensRef.current),
      slots,
      choose: (id) => {
        if (id !== latest.current.value) latest.current.onChange(id as T);
      },
    });
  }
  useEffect(() => () => sim.current?.stop(), []);

  // 选中项变了（点击、键盘、外面改了值）就弹过去；第一次与改了排版时直接放到位
  useLayoutEffect(() => {
    sim.current?.target(value, false);
  }, [value, compact]);
  useLayoutEffect(() => {
    sim.current?.settle();
  });
  useEffect(() => {
    const root = rootRef.current;
    if (!root || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => sim.current?.settle(true));
    ro.observe(root);
    for (const el of btnRefs.current.values()) ro.observe(el);
    return () => ro.disconnect();
  }, [options.length]);

  const drag = useRef<{ id: number; moved: boolean; px: number } | null>(null);
  const suppressClick = useRef(false);

  const finishPointer = useCallback((e: Pick<PointerEvent, "pointerId" | "timeStamp">) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    drag.current = null;
    // 拖过之后紧接着的 click 不算点击；根节点与 window 收到同一事件只收尾一次。
    suppressClick.current = d.moved;
    sim.current?.release(e.timeStamp);
  }, []);
  useEffect(() => {
    // 移动超过阈值前还没捕获指针，直接移出控件时也必须接住松手。
    window.addEventListener("pointerup", finishPointer);
    window.addEventListener("pointercancel", finishPointer);
    return () => {
      window.removeEventListener("pointerup", finishPointer);
      window.removeEventListener("pointercancel", finishPointer);
    };
  }, [finishPointer]);

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    const s = sim.current;
    const thumb = thumbRef.current;
    if (compact || !s || !thumb || e.button !== 0 || e.pointerType === "touch" && !e.isPrimary) return;
    const r = thumb.getBoundingClientRect();
    if (e.clientX < r.left || e.clientX > r.right) return;
    drag.current = { id: e.pointerId, moved: false, px: e.clientX };
    s.grab(e.clientX, e.timeStamp);
  };
  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    if (!d.moved && Math.abs(e.clientX - d.px) < 3) return;
    if (!d.moved) e.currentTarget.setPointerCapture(e.pointerId);
    d.moved = true;
    sim.current?.move(e.clientX, e.timeStamp);
  };
  const label = (opt: SegmentOption<T>) => <span className="block text-[13px] px-4 py-1.5 whitespace-nowrap">{opt.label}</span>;

  return (
    <div
      ref={rootRef}
      role={role}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={finishPointer}
      onPointerCancel={finishPointer}
      onLostPointerCapture={finishPointer}
      className={[
        // inline-flex + w-fit：块级的 flex 容器会撑满父元素，于是字变短之后
        // 药丸还是原来那么长（四个字的标签，条子却按八个字的宽度画）。
        "seg relative inline-flex w-fit p-[3px] rounded-full select-none touch-pan-y",
        "bg-[color-mix(in_srgb,var(--ink)_5%,transparent)]",
        className,
      ].join(" ")}
    >
      {options.map((opt) => {
        const on = opt.id === value;
        return (
          <button
            key={opt.id}
            type="button"
            role={role === "tablist" ? "tab" : undefined}
            aria-selected={role === "tablist" ? on : undefined}
            aria-pressed={role === "group" ? on : undefined}
            tabIndex={role === "tablist" ? (on || (!options.some((o) => o.id === value) && opt.id === options[0]?.id) ? 0 : -1) : undefined}
            onKeyDown={(e) => {
              if (role !== "tablist" || e.altKey || e.ctrlKey || e.metaKey) return;
              const current = options.findIndex((o) => o.id === opt.id);
              const next = e.key === "Home" ? 0 : e.key === "End" ? options.length - 1 : e.key === "ArrowRight" ? (current + 1) % options.length : e.key === "ArrowLeft" ? (current - 1 + options.length) % options.length : -1;
              if (next < 0) return;
              e.preventDefault();
              const id = options[next].id;
              btnRefs.current.get(id)?.focus();
              onChange(id);
            }}
            title={opt.title}
            disabled={opt.disabled}
            ref={(el) => {
              if (el) btnRefs.current.set(opt.id, el);
              else btnRefs.current.delete(opt.id);
            }}
            onClick={() => {
              if (suppressClick.current) {
                suppressClick.current = false;
                return;
              }
              if (opt.id === value) return;
              // 点击：滑块先弹过去，到达那一项上方时才切换；减弱动态效果时直接切换
              if (compact || !sim.current?.animated()) onChange(opt.id);
              else sim.current.target(opt.id, true);
            }}
            className={[
              "relative z-[1] border-0 bg-transparent p-0 cursor-pointer rounded-full",
              "text-[var(--ink-muted)] transition-[color,opacity] duration-200 ease-[var(--ease)]",
              "focus-visible:outline-2 focus-visible:outline-[var(--accent)] focus-visible:outline-offset-2",
              on ? "text-[var(--ink)]" : "hover:text-[var(--ink)]",
              "disabled:opacity-40 disabled:cursor-default disabled:hover:text-[var(--ink-muted)]",
              compact && on ? "bg-[var(--seg-thumb)] shadow-[var(--glass)]" : "",
            ].join(" ")}
          >
            {label(opt)}
          </button>
        );
      })}
      {!compact && (
        <span ref={thumbRef} aria-hidden className="seg-thumb absolute top-[3px] bottom-[3px] left-0 z-[2] pointer-events-none" style={{ width: 0, opacity: 0 }}>
          <span ref={glassRef} className="seg-glass absolute inset-0 rounded-full">
            <span className="absolute inset-0 rounded-full overflow-hidden">
              <span ref={lensRef} className="seg-lens absolute top-[-3px] flex p-[3px] text-[var(--ink)]">
                {options.map((opt) => (
                  <span key={opt.id} className="flex-none">
                    {label(opt)}
                  </span>
                ))}
              </span>
            </span>
          </span>
        </span>
      )}
    </div>
  );
}

/** 一帧要画的样子：滑块左边、宽度、速度、被按住、撞墙压扁的量。 */
type Frame = { x: number; w: number; v: number; held: boolean; squash: number };

/** 镜片放大倍数：平时与按住时。 */
const LENS = { rest: 1.08, held: 1.16 };

function paint(p: Frame, thumb: HTMLElement | null, glass: HTMLElement | null, lens: HTMLElement | null) {
  if (!thumb || !glass || !lens) return;
  thumb.style.opacity = p.w > 0 ? "1" : "0";
  thumb.style.width = `${p.w}px`;
  thumb.style.transform = `translate3d(${p.x}px, 0, 0)`;
  // 速度越快拉得越长、压得越扁；按住时整体微微鼓起；撞墙时横向被压、纵向鼓出
  const speed = Math.min(Math.abs(p.v) / 2600, 1);
  const lift = p.held ? 1.05 : 1;
  const sx = lift * (1 + speed * 0.16) * (1 - p.squash * 0.5);
  const sy = lift * (1 - speed * 0.12) * (1 + p.squash * 0.35);
  glass.style.transform = `scale(${sx.toFixed(4)}, ${sy.toFixed(4)})`;
  const k = p.held ? LENS.held : LENS.rest;
  lens.style.left = `${-p.x}px`;
  lens.style.transformOrigin = `${p.x + p.w / 2}px 50%`;
  lens.style.transform = `scale(${k / sx}, ${k / sy})`;
}

type Slot = { id: string; x: number; w: number; disabled: boolean };

/** 弹簧参数：刚度与阻尼比。阻尼比略小于 1，到位时有一点点回弹。 */
const SPRING = { k: 420, zeta: 0.74 };
/** 松手后按速度往前「看」多远来决定停在哪一项，秒。 */
const PROJECT = 0.16;
/** 拖出两端时的阻力：越拖越拖不动。 */
const RUBBER = 0.32;

/**
 * 滑块的运动。位置 x 与宽度 w 各是一个弹簧；拖动时 x 直接跟手，w 按位置在相邻两项之间插值。
 * 每帧把结果交给 paint，不经过 React 重渲染。
 */
class Sim {
  private x = 0;
  private v = 0;
  private w = 0;
  private vw = 0;
  private tx = 0;
  private tw = 0;
  private goal: string | null = null;
  /** 点击后要在到达时才切换的那一项。 */
  private pending: string | null = null;
  private held = false;
  private grabAt = { px: 0, x: 0 };
  private samples: { x: number; t: number }[] = [];
  private raf = 0;
  private last = 0;
  private placed = false;
  private reduce = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  constructor(private io: { paint: (f: Frame) => void; slots: () => Slot[]; choose: (id: string) => void }) {}

  animated() {
    return !this.reduce;
  }

  stop() {
    cancelAnimationFrame(this.raf);
    this.raf = 0;
  }

  private bounds() {
    const s = this.io.slots();
    const first = s[0];
    const end = s[s.length - 1];
    return { s, min: first?.x ?? 0, max: end ? end.x + end.w : 0 };
  }

  /** 弹向某一项。fromClick：点击触发，到达时才切换。 */
  target(id: string, fromClick: boolean) {
    const slot = this.io.slots().find((s) => s.id === id);
    // 量不到位置（藏在看不见的地方）时不做动画；点击照样立即切换
    if (!slot || slot.w === 0) {
      if (fromClick) this.io.choose(id);
      return;
    }
    this.goal = id;
    this.pending = fromClick ? id : null;
    this.tx = slot.x;
    this.tw = slot.w;
    if (!this.placed || this.reduce) {
      this.placed = true;
      this.x = this.tx;
      this.w = this.tw;
      this.v = this.vw = 0;
      if (this.pending) this.arrive();
      this.draw();
      return;
    }
    this.kick();
  }

  /** 排版变了（字数、窗口、语言）：目标重新量一次；没在动的话直接放到位。 */
  settle(force = false) {
    if (!this.goal) return;
    const slot = this.io.slots().find((s) => s.id === this.goal);
    if (!slot) return;
    if (slot.x === this.tx && slot.w === this.tw && !force) return;
    this.tx = slot.x;
    this.tw = slot.w;
    if (!this.raf && !this.held) {
      this.x = this.tx;
      this.w = this.tw;
      this.draw();
    }
  }

  grab(px: number, t: number) {
    this.held = true;
    this.pending = null;
    this.grabAt = { px, x: this.x };
    this.samples = [{ x: px, t }];
    this.kick();
  }

  move(px: number, t: number) {
    if (!this.held) return;
    const { s, min, max } = this.bounds();
    let x = this.grabAt.x + (px - this.grabAt.px);
    const w = widthAt(s, x + this.w / 2) ?? this.w;
    // 拖出两端：只走一部分距离，像拉着一根橡皮筋
    if (x < min) x = min - (min - x) * RUBBER;
    if (x + w > max) x = max - w + (x + w - max) * RUBBER;
    this.x = x;
    this.tw = w;
    this.samples.push({ x: px, t });
    if (this.samples.length > 6) this.samples.shift();
  }

  release(t: number) {
    if (!this.held) return;
    this.held = false;
    const a = this.samples[0];
    const b = this.samples[this.samples.length - 1];
    const dt = Math.max(1, (b?.t ?? t) - (a?.t ?? t)) / 1000;
    // 最后一次移动之后停了一会儿再松手，就不算甩
    const stale = t - (b?.t ?? t) > 80;
    this.v = stale || !a || !b ? 0 : (b.x - a.x) / dt;
    const { s } = this.bounds();
    const center = this.x + this.w / 2 + this.v * PROJECT;
    const pick = nearest(s, center);
    if (!pick) return;
    this.goal = pick.id;
    this.tx = pick.x;
    this.tw = pick.w;
    // 松手即切换
    this.io.choose(pick.id);
    this.kick();
  }

  private arrive() {
    const id = this.pending;
    this.pending = null;
    if (id) this.io.choose(id);
  }

  private kick() {
    if (this.raf) return;
    this.last = performance.now();
    const step = (now: number) => {
      const dt = Math.min(0.032, (now - this.last) / 1000);
      this.last = now;
      this.tick(dt);
      this.draw();
      const resting = !this.held && Math.abs(this.x - this.tx) < 0.3 && Math.abs(this.v) < 4 && Math.abs(this.w - this.tw) < 0.3 && Math.abs(this.vw) < 4;
      if (resting) {
        this.x = this.tx;
        this.w = this.tw;
        this.v = this.vw = 0;
        this.draw();
        this.raf = 0;
        return;
      }
      this.raf = requestAnimationFrame(step);
    };
    this.raf = requestAnimationFrame(step);
  }

  private tick(dt: number) {
    const c = 2 * Math.sqrt(SPRING.k) * SPRING.zeta;
    // 宽度一直是弹簧；位置在拖动时跟手，速度由跟手的位移算出
    const aw = -SPRING.k * (this.w - this.tw) - c * this.vw;
    this.vw += aw * dt;
    this.w += this.vw * dt;
    if (this.held) return;
    const ax = -SPRING.k * (this.x - this.tx) - c * this.v;
    this.v += ax * dt;
    this.x += this.v * dt;
    // 点击：滑块中心进入目标那一项的范围时就切换，不等它完全停稳
    if (this.pending) {
      const slot = this.io.slots().find((s) => s.id === this.pending);
      const mid = this.x + this.w / 2;
      if (!slot || (mid >= slot.x && mid <= slot.x + slot.w)) this.arrive();
    }
  }

  private draw() {
    const { min, max } = this.bounds();
    // 撞墙：越过边缘的部分不再往外走，而是把滑块压扁
    let x = this.x;
    let w = this.w;
    let over = 0;
    if (x < min) {
      over = min - x;
      w = Math.max(this.w * 0.6, w - over);
      x = min;
    } else if (x + w > max) {
      over = x + w - max;
      w = Math.max(this.w * 0.6, w - over);
      x = max - w;
    }
    const squash = this.w ? Math.min(over / this.w, 0.4) : 0;
    this.io.paint({ x, w, v: this.v, held: this.held, squash });
  }
}

/** 拖到 center 这个位置时滑块该有的宽度：在相邻两项的宽度之间按距离插值。 */
function widthAt(s: Slot[], center: number): number | null {
  if (!s.length) return null;
  const mids = s.map((o) => o.x + o.w / 2);
  if (center <= mids[0]) return s[0].w;
  for (let i = 0; i < s.length - 1; i++) {
    if (center <= mids[i + 1]) {
      const f = (center - mids[i]) / (mids[i + 1] - mids[i]);
      return s[i].w + (s[i + 1].w - s[i].w) * f;
    }
  }
  return s[s.length - 1].w;
}

/** 离 center 最近、而且可以选的那一项。 */
function nearest(s: Slot[], center: number): Slot | null {
  let best: Slot | null = null;
  let d = Infinity;
  for (const o of s) {
    if (o.disabled) continue;
    const dd = Math.abs(o.x + o.w / 2 - center);
    if (dd < d) {
      d = dd;
      best = o;
    }
  }
  return best;
}
