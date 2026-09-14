/**
 * FLIP 位置过渡（C-04）：key 稳定的列表换序时，让卡片从旧位置滑到新位置，
 * 而不是瞬移。只补 translate；尺寸变化仍由卡片自己的 CSS 过渡负责。
 *
 * 位置一律用 offsetLeft/offsetTop 量（布局值，不受 transform 干扰），
 * 所以容器必须有一个定位祖先（本页卡片容器就是 relative）。
 * 动画中的卡片再次换序：getComputedStyle().transform 含当前残余位移，
 * 叠进新 delta 即可从中途接续，不跳位。
 */
import { useLayoutEffect, useRef, type RefObject } from "react";

export type XY = { x: number; y: number };

/** 新 delta = 旧布局位 − 新布局位 + 动画残余位移。 */
export function flipDelta(prev: XY, cur: XY, residual: XY): XY {
  return { x: prev.x - cur.x + residual.x, y: prev.y - cur.y + residual.y };
}

/** 读元素当前生效的 translate（含正在播的 WAAPI 动画）。 */
export function readResidualTransform(el: HTMLElement): XY {
  return parseTransform(getComputedStyle(el).transform);
}

/** 把 getComputedStyle().transform 的值解成 x/y 位移。 */
export function parseTransform(m: string | null | undefined): XY {
  if (!m || m === "none") return { x: 0, y: 0 };
  // translate(x, y)：部分环境（happy-dom、未合成时）直接回这个形态
  const tr = m.match(/translate\(([^)]+)\)/);
  if (tr) {
    const v = tr[1].split(",").map((s) => Number.parseFloat(s));
    return { x: v[0] || 0, y: v[1] || 0 };
  }
  // matrix(a,b,c,d,tx,ty) 或 matrix3d(...)（只取 x/y 平移）
  const parts = m.match(/matrix3?d?\(([^)]+)\)/);
  if (!parts) return { x: 0, y: 0 };
  const v = parts[1].split(",").map((s) => Number(s.trim()));
  if (v.length === 6) return { x: v[4] || 0, y: v[5] || 0 };
  if (v.length === 16) return { x: v[12] || 0, y: v[13] || 0 };
  return { x: 0, y: 0 };
}

const DURATION_MS = 300; // 与卡片自身的 duration-300 一致
const EASING = "cubic-bezier(0.34, 1.42, 0.64, 1)"; // = --spring

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * 挂到列表容器上（容器须 position:relative 或更内层定位）。
 * 每次提交后量一遍 data-flip 子项的布局位，位移非零就播补间动画。
 * 无依赖数组 —— 三次测量成本可忽略，少记一次就丢一帧。
 */
export function useFlipRow<T extends HTMLElement>(): RefObject<T | null> {
  const ref = useRef<T>(null);
  const layout = useRef(new Map<string, XY>());

  useLayoutEffect(() => {
    const box = ref.current;
    if (!box) return;
    const next = new Map<string, XY>();
    const nodes = box.querySelectorAll<HTMLElement>("[data-flip]");
    nodes.forEach((node) => {
      const key = node.dataset.flip || "";
      if (!key) return;
      const cur = { x: node.offsetLeft, y: node.offsetTop };
      const prev = layout.current.get(key);
      next.set(key, cur);
      if (!prev || prefersReducedMotion()) return;
      const d = flipDelta(prev, cur, readResidualTransform(node));
      if (!d.x && !d.y) return;
      node.animate(
        [
          { transform: `translate(${d.x}px, ${d.y}px)` },
          { transform: "none" },
        ],
        { duration: DURATION_MS, easing: EASING },
      );
    });
    layout.current = next;
  });

  return ref;
}
