/** Distance from the top of `pane` to `el`, ignoring CSS transforms. */
export function offsetTopInPane(el: HTMLElement, pane: HTMLElement): number {
  let y = 0;
  let node: HTMLElement | null = el;
  while (node && node !== pane) {
    y += node.offsetTop;
    const parent = node.offsetParent;
    if (parent && parent !== node && "offsetTop" in parent) {
      node = parent as HTMLElement;
      continue;
    }
    break;
  }
  if (node === pane) return y;
  const er = el.getBoundingClientRect();
  const pr = pane.getBoundingClientRect();
  return pane.scrollTop + (er.top - pr.top);
}

/**
 * Scroll the nearest `.overflow-y-auto` ancestor so `id` sits near the top.
 *
 * Do not use `scrollIntoView` after a page change: PageHost animates the pane
 * with a transform, and scrollIntoView follows the moving box.
 */
export function scrollPaneToId(id: string, pad = 12): boolean {
  const el = document.getElementById(id);
  if (!el) return false;
  const pane = el.closest(".overflow-y-auto");
  if (pane && pane instanceof HTMLElement) {
    pane.scrollTop = Math.max(0, offsetTopInPane(el, pane) - pad);
    return true;
  }
  el.scrollIntoView({ block: "start" });
  return true;
}

/**
 * PageHost restores a kept page's scroll position in useLayoutEffect when the
 * page id changes. A same-frame scroll is overwritten; wait a tick, then try
 * once more after accordions have had a chance to open.
 *
 * `onDone` fires on the first scroll. Kept pages re-run their effects on every
 * return, so callers record the handled request there and skip it next time.
 */
export function scheduleScrollToId(id: string, pad = 12, onDone?: () => void): () => void {
  let cancelled = false;
  let reported = false;
  const run = () => {
    if (cancelled) return;
    scrollPaneToId(id, pad);
    if (!reported) {
      reported = true;
      onDone?.();
    }
  };
  const a = window.setTimeout(run, 80);
  const b = window.setTimeout(run, 280);
  return () => {
    cancelled = true;
    window.clearTimeout(a);
    window.clearTimeout(b);
  };
}
