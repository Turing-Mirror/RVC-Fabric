/**
 * 焦点环只给用键盘的人。
 *
 * `:focus-visible` 交给浏览器判断，有几种情况它会判错：窗口切走再切回来、弹窗关闭后
 * 把焦点还给原来的按钮。这时 Chromium（WebView2）会给刚用鼠标点过的按钮也画上焦点环，
 * 看上去像按钮卡在了选中状态。
 *
 * 这里记下最近一次输入来自指针还是键盘，写在 `<html data-input>` 上；index.css 在
 * `data-input="pointer"` 时不画焦点环。按 Tab、方向键等导航键后恢复。
 */

/** 只有这些键算「在用键盘走焦点」。打字不算，免得在输入框里打字时周围冒出焦点环。 */
const NAV_KEYS = new Set([
  "Tab", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
  "Home", "End", "PageUp", "PageDown", "Enter", " ", "Escape",
]);

export function trackInputModality(root: HTMLElement = document.documentElement): () => void {
  const set = (v: "pointer" | "keyboard") => {
    if (root.dataset.input !== v) root.dataset.input = v;
  };
  const onPointer = () => set("pointer");
  const onKey = (e: KeyboardEvent) => {
    if (NAV_KEYS.has(e.key)) set("keyboard");
  };
  set("pointer");
  window.addEventListener("pointerdown", onPointer, true);
  window.addEventListener("keydown", onKey, true);
  return () => {
    window.removeEventListener("pointerdown", onPointer, true);
    window.removeEventListener("keydown", onKey, true);
  };
}
