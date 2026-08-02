/**
 * 「只在软件内生效」的那些快捷键，由这里在前端接住。
 *
 * 全局快捷键是**独占**的：Ctrl+F7 被 Tauri 抢走之后，用户在别的软件里就再也
 * 按不出它原本的功能了。所以每个组合都可以单独取消「全局」——取消之后 Rust
 * 那边就不注册它，改由本文件在 RVC Fabric 是当前窗口时用 keydown 接住。
 *
 * 顺序、键名、默认值必须和 `shell_extras::HOTKEYS` 对得上；`_global` 后缀的
 * 配置键也是那边定的。
 */

/** 一条快捷键：配置键名、动作名、默认组合。 */
export type HotkeySpec = { key: string; action: string; fallback: string };

export const HOTKEYS: HotkeySpec[] = [
  { key: "hotkey_toggle_vc", action: "toggle-vc", fallback: "CmdOrCtrl+F2" },
  { key: "hotkey_toggle_mode", action: "toggle-mode", fallback: "CmdOrCtrl+F3" },
  { key: "hotkey_prev_voice", action: "prev-voice", fallback: "CmdOrCtrl+F5" },
  { key: "hotkey_next_voice", action: "next-voice", fallback: "CmdOrCtrl+F6" },
  { key: "hotkey_pitch_up", action: "pitch-up", fallback: "CmdOrCtrl+F7" },
  { key: "hotkey_pitch_down", action: "pitch-down", fallback: "CmdOrCtrl+F8" },
  {
    key: "hotkey_toggle_monitor",
    action: "toggle-monitor",
    fallback: "CmdOrCtrl+F9",
  },
  { key: "hotkey_toggle_fx", action: "toggle-fx", fallback: "CmdOrCtrl+F10" },
  {
    key: "hotkey_toggle_window",
    action: "toggle-window",
    fallback: "CmdOrCtrl+F11",
  },
];

/**
 * 把一个真实按键事件写成 Tauri 那套组合键字符串，好和配置直接比。
 *
 * 修饰键的顺序写死成 CmdOrCtrl → Alt → Shift，和设置页录制时用的顺序一致；
 * 顺序不一致的话同一个组合会有两种写法，比出来永远不相等。
 *
 * 只认字母、数字和 F1~F24 —— 和录制时能录到的范围一样。别的键（中文输入法的
 * 候选键、小键盘、媒体键）返回空串，调用方当作没按。
 */
export function comboFromEvent(e: KeyboardEvent): string {
    const mods: string[] = [];
    if (e.ctrlKey || e.metaKey) mods.push("CmdOrCtrl");
    if (e.altKey) mods.push("Alt");
    if (e.shiftKey) mods.push("Shift");

    const code = e.code;
    let main = "";
    if (/^Key[A-Z]$/.test(code)) main = code.slice(3);
    else if (/^Digit[0-9]$/.test(code)) main = code.slice(5);
    else if (/^F([1-9]|1[0-9]|2[0-4])$/.test(code)) main = code;
    if (!main) return "";
    return [...mods, main].join("+");
}

/**
 * 当前配置下，哪些组合该由前端自己接。
 *
 * 返回 `组合 → 动作`。`_global` 为 false 的才进来 —— 全局的那些 Rust 已经
 * 注册过了，前端再接一遍就是按一次触发两次。
 *
 * `hotkeys_enabled` 是总开关，关了就一个都不接。
 */
export function localHotkeyMap(
  cfg: Record<string, unknown>,
): Map<string, string> {
  const out = new Map<string, string>();
  if (cfg.hotkeys_enabled === false) return out;
  for (const h of HOTKEYS) {
    if (cfg[`${h.key}_global`] !== false) continue;
    const combo = String(cfg[h.key] ?? "").trim() || h.fallback;
    out.set(combo, h.action);
  }
  return out;
}

/**
 * 正在打字的时候不要触发快捷键。
 *
 * 设置页里录制组合键的那个按钮、搜索框、音色改名的输入框都算 —— 在那些地方
 * 按 Ctrl+F6 是想输入或录制，不是想切音色。
 */
export function typingInto(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el || !el.tagName) return false;
  const tag = el.tagName.toLowerCase();
  return (
    tag === "input" ||
    tag === "textarea" ||
    tag === "select" ||
    el.isContentEditable === true
  );
}
