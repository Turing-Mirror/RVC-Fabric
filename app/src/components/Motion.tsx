/**
 * 页内切换的动效：子页签、筛选结果、翻页。旧内容很快淡出、朝来处让一小步，
 * 新内容从去向那一侧浮上来，二者交叠，不是这边一灭、那边一亮。
 * 时长与 index.css 里 .swap-in、.swap-out 一致。
 */
import { memo, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { useExit } from "../hooks/useExit";

/** 旧内容留多久：等淡出放完。与 index.css 的 .swap-out 一致。 */
export const SWAP_OUT_MS = 180;
/** 依次浮现时相邻两项的间隔与最多排几项。 */
const STAGGER = { step: 24, max: 12 };

/** 第 i 项依次浮现的延迟。 */
export function stagger(i: number): CSSProperties {
  return { animationDelay: `${Math.min(i, STAGGER.max) * STAGGER.step}ms` };
}

/** 淡出中的旧内容原样留着，不跟着外面重绘。 */
const Frozen = memo(function Frozen({ node }: { node: ReactNode }) {
  return <>{node}</>;
});

/**
 * 同一处内容换了一批。k 变了，旧的淡出、新的浮上来；dir 为 1 从右边来，-1 从左边来，
 * 0 只有一点纵向的浮动。哪怕新旧是同一项、或只剩一项，也照样有这一下。
 */
export function Swap({ k, dir = 0, children, className = "" }: { k: string; dir?: -1 | 0 | 1; children: ReactNode; className?: string }) {
  const [cur, setCur] = useState({ k, node: children, seq: 0 });
  const [old, setOld] = useState<{ node: ReactNode; seq: number } | null>(null);
  if (cur.k !== k) {
    setOld({ node: cur.node, seq: cur.seq });
    setCur({ k, node: children, seq: cur.seq + 1 });
  } else if (cur.node !== children) {
    setCur({ ...cur, node: children });
  }
  useEffect(() => {
    if (!old) return;
    const id = window.setTimeout(() => setOld(null), SWAP_OUT_MS);
    return () => window.clearTimeout(id);
  }, [old]);
  const vars = { "--swap-dx": `${dir * 18}px`, "--swap-ox": `${dir * -10}px` } as CSSProperties;
  return (
    <div className={`relative ${className}`} style={vars}>
      <div key={cur.seq} className={cur.seq ? "swap-in" : ""}>
        {cur.node}
      </div>
      {/* 旧的一层排在新的后面：正在淡出的内容压在上面放完，按文档顺序找控件时先找到的是新的 */}
      {old ? (
        <div key={`out-${old.seq}`} inert aria-hidden className="swap-out absolute inset-x-0 top-0 pointer-events-none">
          <Frozen node={old.node} />
        </div>
      ) : null}
    </div>
  );
}

/** 流动列表、滚字共用的时长。与 index.css 的 --flow-ms 一致。 */
export const FLOW_MS = 420;

function curve(token: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(token).trim() || "ease-out";
}

const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

type FlowEntry<T> = { key: string; item: T; phase: "enter" | "stay" | "leave" };

/**
 * 流动列表：同一份列表换了筛选、排序或展开了更多时，整块不重载。
 * 留下的项从旧位置滑到新位置，离开的项原地收拢，新来的项撑开。
 * 列表的间距写在每一项里面（例如 py-3），不要用 gap：收拢的项仍占着一份 gap。
 */
export function FlowList<T>({ items, keyOf, render, className = "", itemClassName = "" }: { items: readonly T[]; keyOf: (item: T) => string; render: (item: T, i: number) => ReactNode; className?: string; itemClassName?: string }) {
  const [list, setList] = useState<FlowEntry<T>[]>(() => items.map((item) => ({ key: keyOf(item), item, phase: "stay" })));
  // 按 key 的顺序判断列表变没变。父组件每次重绘都会传来新数组（filter、slice），
  // 只看数组是不是同一个，就会把每次重绘都当成换了列表，用旧位置再滑一遍
  const sig = items.map(keyOf).join("\n");
  const [src, setSrc] = useState(sig);
  const box = useRef<HTMLDivElement>(null);
  const tops = useRef(new Map<string, number>());
  // 上一次量位置时对应的那份列表。收尾那次重绘（卸下离开的项、新来的项转常驻）列表没变，只记位置不放动画
  const measured = useRef(sig);

  if (src !== sig) {
    setSrc(sig);
    const next = new Set(items.map(keyOf));
    const prev = list.filter((e) => e.phase !== "leave" || !next.has(e.key));
    const had = new Map(prev.filter((e) => e.phase !== "leave").map((e) => [e.key, e]));
    const merged: FlowEntry<T>[] = [];
    // 离开的项留在它原来的前一项后面，原地收拢
    let pi = 0;
    for (const item of items) {
      const key = keyOf(item);
      while (pi < prev.length && !next.has(prev[pi].key)) {
        merged.push({ ...prev[pi], phase: "leave" });
        pi++;
      }
      if (pi < prev.length && prev[pi].key === key) pi++;
      merged.push({ key, item, phase: had.get(key)?.phase ?? "enter" });
    }
    for (; pi < prev.length; pi++) if (!next.has(prev[pi].key)) merged.push({ ...prev[pi], phase: "leave" });
    setList(merged);
  }

  // 留下的项：量出新旧位置的差，先倒推回旧位置再放开（FLIP）
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const quiet = reduced() || measured.current === src;
    measured.current = src;
    // 位置量的是相对列表本身（列表是定位容器），外层整体移动不算这几项换了位置
    const easing = curve("--ease-nav");
    const now = new Map<string, number>();
    el.querySelectorAll<HTMLElement>(":scope > [data-flow]").forEach((node) => {
      const key = node.dataset.flow ?? "";
      const top = node.offsetTop;
      now.set(key, top);
      const was = tops.current.get(key);
      if (quiet || was === undefined || was === top || node.dataset.phase !== "stay") return;
      node.animate([{ transform: `translate3d(0, ${was - top}px, 0)` }, { transform: "none" }], { duration: FLOW_MS, easing });
    });
    tops.current = now;
  });

  // 撑开、收拢放完之后：新来的项转为常驻，离开的项卸下。多等两帧，确保动画已经停在终点
  const moving = list.some((e) => e.phase !== "stay");
  useEffect(() => {
    if (!moving) return;
    const id = window.setTimeout(() => setList((l) => l.filter((e) => e.phase !== "leave").map((e) => (e.phase === "enter" ? { ...e, phase: "stay" } : e))), FLOW_MS + 40);
    return () => window.clearTimeout(id);
  }, [moving, list]);

  // 条目内容（点赞数之类）随时可能更新：在场的项一律按 key 取最新的那份来画，离开的项照原样画完
  const current = new Map(items.map((it) => [keyOf(it), it]));
  let shown = 0;
  return (
    <div ref={box} className={`relative ${className}`}>
      {list.map((e) => (
        <div key={e.key} data-flow={e.key} data-phase={e.phase} inert={e.phase === "leave"} className={`flow-item ${e.phase === "leave" ? "flow-leave" : e.phase === "enter" ? "flow-enter" : ""}`}>
          {/* 间距放在里层：外层收拢到零时内边距跟着一起收，不会最后一下才跳没 */}
          <div className="flow-body">
            <div className={itemClassName}>{render(e.phase === "leave" ? e.item : (current.get(e.key) ?? e.item), e.phase === "leave" ? -1 : shown++)}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * 滚字：同一处的文字换了，旧字向下滑出，新字从上方滑入，宽度随之过渡。
 * 用在标题、计数、当前项名称这类「同一个位置换了内容」的地方。
 */
export function Roll({ value, className = "" }: { value: string; className?: string }) {
  const [cur, setCur] = useState({ value, seq: 0 });
  const [old, setOld] = useState<{ value: string; seq: number } | null>(null);
  if (cur.value !== value) {
    setOld({ value: cur.value, seq: cur.seq });
    setCur({ value, seq: cur.seq + 1 });
  }
  useEffect(() => {
    if (!old) return;
    const id = window.setTimeout(() => setOld(null), FLOW_MS);
    return () => window.clearTimeout(id);
  }, [old]);
  return (
    <span className={`roll ${className}`}>
      {old ? (
        <span key={`o${old.seq}`} aria-hidden className="roll-out">
          {old.value}
        </span>
      ) : null}
      <span key={cur.seq} className={cur.seq ? "roll-in" : ""}>
        {cur.value}
      </span>
    </span>
  );
}

/**
 * 拉幕：内容第一次出现时从上往下展开，之后内容更新时底板不动；
 * 内容没了就照最后的样子从下往上收回，收完再显示 fallback。
 */
export function Curtain({ children, fallback, className = "" }: { children: ReactNode; fallback: ReactNode; className?: string }) {
  const present = children !== null && children !== undefined && children !== false;
  const { mounted } = useExit(present, FLOW_MS);
  const last = useRef<ReactNode>(null);
  if (present) last.current = children;
  // 每出现一次换一个 key：重新出现时再拉开一次，出现期间内容更新不重放
  const [round, setRound] = useState({ present, n: 0 });
  if (round.present !== present) setRound({ present, n: present ? round.n + 1 : round.n });
  if (present) return <div key={`c${round.n}`} className={`curtain-in ${className}`}>{children}</div>;
  if (mounted) return (
    <div key={`o${round.n}`} inert aria-hidden className={`curtain-out ${className}`}>
      <Frozen node={last.current} />
    </div>
  );
  return <div key="empty" className={`rise ${className}`}>{fallback}</div>;
}
