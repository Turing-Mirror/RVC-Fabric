import { useEffect, useState } from "react";

/** 退场动画的时长。index.css 里 *-out 那几条动画用的是同一个数。 */
export const EXIT_MS = 180;

/**
 * 让一个元素在「不该显示」之后再多留一小段，把退场动画放完再卸掉。
 *
 * - mounted：还要不要画它。
 * - leaving：正在退场。组件据此换成退场的那一套样式。
 */
export function useExit(show: boolean, ms = EXIT_MS) {
  const [mounted, setMounted] = useState(show);
  if (show && !mounted) setMounted(true);
  useEffect(() => {
    if (show) return;
    const id = window.setTimeout(() => setMounted(false), ms);
    return () => window.clearTimeout(id);
  }, [show, ms]);
  return { mounted: show || mounted, leaving: !show && mounted };
}
