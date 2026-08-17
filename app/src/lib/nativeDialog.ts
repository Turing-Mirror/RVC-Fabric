/**
 * 原生文件/目录对话框的统一入口。
 *
 * 这些命令在 Rust 侧是**同步**的（原生对话框要主线程），所以对话框开着的时候
 * 原生窗口的消息泵是停的 —— 用户点标题栏的关闭按钮（`win().close()` 走 IPC
 * 到 Rust）不会有任何反应。`shell_extras::dialog()` 已经把对话框挂到主窗口上，
 * Windows 会用「标题栏变灰 + 点父窗口时对话框闪动」表达这件事；这里再补一句
 * 人话，说明为什么点不动。
 *
 * 提示条刻意做成 `pointer-events-none`：
 *
 * 万一哪天 invoke 卡住不返回、`finally` 没跑到，留在屏幕上的也只是一条横幅，
 * 挡不住任何点击。加一个「解释卡住」的东西，不该带来「自己把界面弄死」的新
 * 风险 —— 那比原来的问题更糟。
 */

type Listener = (hint: string) => void;

let current = "";
const listeners = new Set<Listener>();

function publish(next: string) {
  current = next;
  listeners.forEach((fn) => fn(current));
}

export function subscribeNativeDialogHint(fn: Listener): () => void {
  listeners.add(fn);
  fn(current);
  return () => {
    listeners.delete(fn);
  };
}

/**
 * 调一个原生选择对话框，期间显示 `hint`。
 *
 * 返回值原样透传（用户取消时是 `null`）。抛错也原样抛出去 —— 调用方本来怎么
 * 处理还怎么处理，这一层只负责那条横幅的生死。
 */
export async function pickPath<T = string | null>(
  cmd: string,
  args: Record<string, unknown> | undefined,
  hint: string,
): Promise<T> {
  const { invoke } = await import("@tauri-apps/api/core");
  // 先渲染再 invoke：invoke 之后主线程就被对话框占住了，那时候才 setState
  // 已经晚了。WebView2 的渲染在独立进程，先画好的这一帧留得住。
  publish(hint);
  // 让浏览器真的把这一帧刷出去，再去发那条会阻塞的命令。
  await new Promise<void>((r) => requestAnimationFrame(() => r()));
  try {
    return await invoke<T>(cmd, args);
  } finally {
    publish("");
  }
}
