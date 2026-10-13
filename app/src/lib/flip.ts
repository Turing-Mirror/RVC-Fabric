/**
 * FLIP 位置过渡（C-04）：key 稳定的列表换序时，让卡片从旧位置滑到新位置，
 * 而不是瞬移。位移和尺寸共用一轮 transform，子项不再另外过渡布局尺寸。
 *
 * 位置一律用 offsetLeft/offsetTop 量（布局值，不受 transform 干扰），
 * 所以容器必须有一个定位祖先（本页卡片容器就是 relative）。
 * 普通重绘不重播；真正再次换位时读取当前位移和缩放，取消旧动画后接续。
 */
import { useLayoutEffect, useRef, type RefObject } from "react";

export type XY = { x: number; y: number };
export type FlipBox = XY & { width: number; height: number };
export type FlipTransform = XY & { scaleX: number; scaleY: number };

/** 新 delta = 旧布局位 − 新布局位 + 动画残余位移。 */
export function flipDelta(prev: XY, cur: XY, residual: XY): XY {
  return { x: prev.x - cur.x + residual.x, y: prev.y - cur.y + residual.y };
}

/** 读元素当前生效的位移与缩放（含正在播的 WAAPI 动画）。 */
export function readResidualTransform(el: HTMLElement): FlipTransform {
  return parseTransform(getComputedStyle(el).transform);
}

/** 本组件的 transform 只有位移和缩放，旋转由更内层的元素负责。 */
export function parseTransform(m: string | null | undefined): FlipTransform {
  const identity = { x: 0, y: 0, scaleX: 1, scaleY: 1 };
  if (!m || m === "none") return identity;
  // translate(x, y)：部分环境（happy-dom、未合成时）直接回这个形态
  const tr = m.match(/translate\(([^)]+)\)/);
  if (tr) {
    const v = tr[1].split(",").map((s) => Number.parseFloat(s));
    return { ...identity, x: v[0] || 0, y: v[1] || 0 };
  }
  // matrix(a,b,c,d,tx,ty) 或 matrix3d(...)（只取 x/y 平移）
  const parts = m.match(/matrix3?d?\(([^)]+)\)/);
  if (!parts) return identity;
  const v = parts[1].split(",").map((s) => Number(s.trim()));
  if (v.length === 6) return { x: v[4], y: v[5], scaleX: v[0], scaleY: v[3] };
  if (v.length === 16) return { x: v[12], y: v[13], scaleX: v[0], scaleY: v[5] };
  return identity;
}

/** 用上次布局和当前动画残量，还原切换前这一帧的视觉矩形。 */
export function flipTransform(prev: FlipBox, cur: FlipBox, residual: FlipTransform): FlipTransform {
  return {
    ...flipDelta(prev, cur, residual),
    scaleX: prev.width * residual.scaleX / cur.width,
    scaleY: prev.height * residual.scaleY / cur.height,
  };
}

const DURATION_MS = 300;
const EASING = "cubic-bezier(0.34, 1.42, 0.64, 1)"; // = --spring

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * 挂到列表容器上（容器须 position:relative 或更内层定位）。
 * 每次提交只比较布局矩形。状态/封面刷新不改变矩形，就让原动画继续完成。
 * 尺寸由 DOM 一次落到终态，视觉上的缩放和换位由这一轮动画共同完成。
 */
export function useFlipRow<T extends HTMLElement>(): RefObject<T | null> {
  const ref = useRef<T>(null);
  const layout = useRef(new Map<string, FlipBox>());
  const animations = useRef(new Map<HTMLElement, Animation>());

  useLayoutEffect(() => {
    const active = animations.current;
    return () => {
      active.forEach((animation) => animation.cancel());
      active.clear();
      layout.current.clear();
    };
  }, []);

  useLayoutEffect(() => {
    const box = ref.current;
    const active = animations.current;
    if (!box) {
      active.forEach((animation) => animation.cancel());
      active.clear();
      layout.current.clear();
      return;
    }
    const next = new Map<string, FlipBox>();
    const nodes = new Set(box.querySelectorAll<HTMLElement>("[data-flip]"));
    const reduce = prefersReducedMotion();
    // 先读所有布局和残量，再取消/启动动画，避免读写交错造成重复布局。
    const moves = Array.from(nodes, (node) => {
      const key = node.dataset.flip || "";
      if (!key) return null;
      const cur = {
        x: node.offsetLeft, y: node.offsetTop,
        width: node.offsetWidth, height: node.offsetHeight,
      };
      const prev = layout.current.get(key);
      next.set(key, cur);
      if (!prev || reduce ||
          (prev.x === cur.x && prev.y === cur.y && prev.width === cur.width && prev.height === cur.height)) return null;
      if (!prev.width || !prev.height || !cur.width || !cur.height) {
        active.get(node)?.cancel();
        active.delete(node);
        return null;
      }
      return { node, transform: flipTransform(prev, cur, readResidualTransform(node)) };
    });
    active.forEach((animation, node) => {
      if (!nodes.has(node) || reduce) {
        animation.cancel();
        active.delete(node);
      }
    });
    layout.current = next;
    moves.forEach((move) => {
      if (!move) return;
      const { node, transform: d } = move;
      active.get(node)?.cancel();
      active.delete(node);
      if (!d.x && !d.y && d.scaleX === 1 && d.scaleY === 1) return;
      const animation = node.animate(
        [
          { transform: `translate(${d.x}px, ${d.y}px) scale(${d.scaleX}, ${d.scaleY})`, transformOrigin: "0 0" },
          { transform: "none", transformOrigin: "0 0" },
        ],
        { duration: DURATION_MS, easing: EASING },
      );
      active.set(node, animation);
      const forget = () => {
        if (active.get(node) === animation) active.delete(node);
      };
      animation.onfinish = forget;
      animation.oncancel = forget;
    });
  });

  return ref;
}
