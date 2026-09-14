import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/**
 * 自己画的悬浮提示，替掉浏览器原生的 `title`。
 *
 * 原生 title 有三个治不好的毛病：
 *
 * 1. **要悬停一秒多才出来**，而且鼠标只要动一下计时就重来 —— 用户的体感是
 *    「有时候有有时候没有」。
 * 2. 样子是操作系统画的，深色模式下和我们的界面完全不搭，字号也改不了。
 * 3. 它挂在 `<span>` 上，而那个 span 常常在 `<label>` 里面。点一下问号，
 *    label 把这一下转给了它管的那个开关 —— 用户只是想看看说明，功能被开了
 *    或者关了。
 *
 * 这里三件事一起解决：移上去就出来（不设延迟）、用我们自己的底色和字号、
 * 问号是个真正的 `<button>` 并且吃掉自己的点击，不再传给外面的 label。
 */

/** 提示框离锚点的距离。留一点缝，贴着会像是从问号里长出来的。 */
const GAP = 9;
/** 离窗口边缘至少留这么多，免得贴边显得要掉出去。 */
const EDGE = 12;

type Pos = { left: number; top: number; below: boolean };

export function Tooltip({
  text,
  children,
}: {
  text: string;
  /** 触发提示的那个元素。整块都算悬停区。 */
  children: React.ReactNode;
}) {
  const anchor = useRef<HTMLSpanElement>(null);
  const bubble = useRef<HTMLDivElement>(null);
  // 悬停和聚焦是两条独立的「想看」通道：悬停走了但焦点还在，说明就还在 ——
  // 以前一份 open 状态，鼠标一离开就关，点了问号拿到的焦点根本留不住说明。
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const open = hovered || focused;
  const leaveTimer = useRef<number | null>(null);
  const [pos, setPos] = useState<Pos | null>(null);

  const place = useCallback(() => {
    const a = anchor.current?.getBoundingClientRect();
    const b = bubble.current?.getBoundingClientRect();
    if (!a || !b) return;
    // 默认放上面 —— 提示是对下面那一行的解释，压在它自己讲的东西上面
    // 会挡住上下文。上面放不下才翻到下面。
    const below = a.top - GAP - b.height < EDGE;
    const top = below ? a.bottom + GAP : a.top - GAP - b.height;
    // 水平居中对齐锚点，然后夹进窗口里。
    const raw = a.left + a.width / 2 - b.width / 2;
    const left = Math.min(
      Math.max(raw, EDGE),
      Math.max(EDGE, window.innerWidth - b.width - EDGE),
    );
    setPos({ left, top, below });
  }, []);

  // 先挂上去（不可见）量一次尺寸，再定位。直接用估算的高度会在长文案上偏。
  useLayoutEffect(() => {
    if (open) place();
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    const close = () => {
      setHovered(false);
      setFocused(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      close();
      // 焦点还在问号上的话一并放开，下一次点击/聚焦才能重新打开。
      const a = document.activeElement;
      if (a instanceof HTMLElement && anchor.current?.contains(a)) a.blur();
    };
    window.addEventListener("keydown", onKey);
    // 滚动和改窗口大小时直接收起，不追着锚点跑：追着跑要么卡，要么在
    // 内容滚出视野之后留下一个飘在半空的框。
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    window.addEventListener("blur", close);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
      window.removeEventListener("blur", close);
    };
  }, [open]);

  useEffect(
    () => () => {
      if (leaveTimer.current) window.clearTimeout(leaveTimer.current);
    },
    [],
  );

  return (
    <>
      <span
        ref={anchor}
        className="inline-flex items-center shrink-0 align-middle"
        onPointerEnter={() => {
          if (leaveTimer.current) {
            window.clearTimeout(leaveTimer.current);
            leaveTimer.current = null;
          }
          setHovered(true);
        }}
        onPointerLeave={() => {
          // 收起留一小段缓冲：鼠标朝说明挪的那一下不至于瞬间消失。
          leaveTimer.current = window.setTimeout(() => setHovered(false), 100);
        }}
        // 键盘走到这里也要看得到说明，不是只有鼠标用户配看。
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
      >
        {children}
      </span>
      {open
        ? createPortal(
            <div
              ref={bubble}
              role="tooltip"
              className={[
                "fixed z-[300] pointer-events-none max-w-[320px]",
                "rounded-[var(--rs)] bg-[var(--surface)] px-3 py-2",
                "shadow-[0_8px_24px_-10px_rgba(0,0,0,.45),inset_0_0_0_1px_var(--hairline)]",
                // 字号比正文的辅助文字大一档：这是用户特地凑过去看的东西，
                // 不该比他不看的说明文字还小。
                "text-[13.5px] leading-[1.65] text-[var(--ink)] whitespace-pre-line",
                "tooltip-in",
              ].join(" ")}
              style={{
                left: pos?.left ?? -9999,
                top: pos?.top ?? -9999,
                // 量尺寸的那一帧还没有位置，先藏着，免得左上角闪一下。
                visibility: pos ? "visible" : "hidden",
                transformOrigin: pos?.below ? "top center" : "bottom center",
              }}
            >
              {text}
            </div>,
            document.body,
          )
        : null}
    </>
  );
}

/**
 * 设置项旁边那个「?」。
 *
 * 是 `<button>` 不是 `<span>`：它在 `<label>` 里面，而 label 会把落在自己
 * 身上的点击转给它管的控件。以前点一下问号，「后期处理」这类开关就跟着被
 * 切了 —— 用户只想看说明，功能却被开关了一次。按钮自己吃掉这一下就没事了。
 */
export function HelpMark({ title }: { title: string }) {
  return (
    <Tooltip text={title}>
      <button
        type="button"
        aria-label={title}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          // 主动点击 = 想读说明：拿住焦点，由聚焦态把说明钉住，
          // 点到别处 / Escape / 滚动才收。
          e.currentTarget.focus();
        }}
        className={[
          // shrink-0 + align-middle：跟同行中文标题垂直居中，不被基线往下拽
          "relative shrink-0 align-middle",
          "w-[17px] h-[17px] p-0 border-0 bg-transparent rounded-full",
          "inline-flex items-center justify-center",
          "text-[var(--meta)] text-[11px] leading-none font-medium",
          "cursor-help shadow-[inset_0_0_0_1px_var(--line)]",
          "transition-[color,box-shadow,transform] duration-200 ease-[var(--spring)]",
          "hover:text-[var(--accent)] hover:shadow-[inset_0_0_0_1px_var(--accent)] hover:scale-110",
          "focus-visible:outline-2 focus-visible:outline-[var(--accent)] focus-visible:outline-offset-2",
        ].join(" ")}
      >
        {/* 「?」字形视觉重心偏低，微抬 1px 做光学居中 */}
        <span className="relative -top-px leading-none" aria-hidden>
          ?
        </span>
      </button>
    </Tooltip>
  );
}
