/**
 * Tauri `unlisten` 在插件已经把这条监听拆掉之后会抛
 * `Cannot read properties of undefined (reading 'handlerId')`
 * （diag 26.8.29/210251：连点工具窗、新 webview 起来那几百毫秒）。
 * 这个异常进 ErrorBoundary 就是整页白屏。注销失败等于监听已经没了，忽略。
 */
export function dropListen(fn?: (() => void) | null): void {
  if (!fn) return;
  try {
    const ret = fn() as unknown;
    if (ret && typeof (ret as Promise<unknown>).catch === "function") {
      void (ret as Promise<unknown>).catch(() => {});
    }
  } catch {
    /* plugin already dropped it */
  }
}
