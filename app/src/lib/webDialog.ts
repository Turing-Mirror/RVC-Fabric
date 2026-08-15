/**
 * 居中的应用内确认 / 输入框。WebView2 的 window.confirm / prompt 贴在窗口顶上，
 * 长文案还截断；这里跟关闭询问同一套卡片。
 */

export type ConfirmRequest = {
  kind: "confirm";
  message: string;
  resolve: (ok: boolean) => void;
};

export type PromptRequest = {
  kind: "prompt";
  message: string;
  def: string;
  resolve: (value: string | null) => void;
};

export type DialogRequest = ConfirmRequest | PromptRequest;

type Handler = (req: DialogRequest) => void;

let handler: Handler | null = null;
const pending: DialogRequest[] = [];

export function registerDialogHandler(fn: Handler | null): void {
  handler = fn;
  if (!fn) return;
  while (pending.length) {
    const req = pending.shift();
    if (req) fn(req);
  }
}

export function askConfirm(message: string): Promise<boolean> {
  return new Promise((resolve) => {
    const req: ConfirmRequest = { kind: "confirm", message, resolve };
    if (handler) handler(req);
    else pending.push(req);
  });
}

export function askPrompt(message: string, def = ""): Promise<string | null> {
  return new Promise((resolve) => {
    const req: PromptRequest = { kind: "prompt", message, def, resolve };
    if (handler) handler(req);
    else pending.push(req);
  });
}
