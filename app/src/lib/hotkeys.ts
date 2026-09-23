/**
 * 「只在软件内生效」的那些快捷键，由这里在前端接住。
 *
 * 全局快捷键是**独占**的：Ctrl+F7 被 Tauri 抢走之后，用户在别的软件里就再也
 * 按不出它原本的功能了。所以每个组合都可以单独取消「全局」——取消之后 Rust
 * 那边就不注册它，改由本文件在 RVC Fabric 是当前窗口时用 keydown 接住。
 *
 * 动作、键名和默认值来自 shared/hotkeys.json，与 Rust 端使用同一份目录。
 */

import catalog from "../../shared/hotkeys.json";

/** 一条快捷键：配置键名、动作名、默认组合。 */
export type HotkeySpec = { key: string; action: string; fallback: string };

export const HOTKEYS: HotkeySpec[] = catalog.legacy;
export const AUDIO_ACTIONS = catalog.audio_actions;

export type AudioHotkeyBinding = {
  binding_id: string;
  action: string;
  target_entry_id: string | null;
  combo: string;
  scope: "global" | "window";
  enabled: boolean;
  mode: "replace" | "overlay" | null;
};

/**
 * 把一个真实按键事件写成 Tauri 那套组合键字符串，好和配置直接比。
 *
 * 修饰键的顺序写死成 CmdOrCtrl → Alt → Shift，和设置页录制时用的顺序一致；
 * 顺序不一致的话同一个组合会有两种写法，比出来永远不相等。
 *
 * 录制和窗口内执行共用此规范化规则。
 */
export function comboFromEvent(e: KeyboardEvent): string {
    const mods: string[] = [];
    if (e.isComposing || e.getModifierState?.("AltGraph")) return "";
    const mac = /Mac|iPhone|iPad/.test(navigator.platform);
    if (mac) {
      if (e.metaKey) mods.push("CmdOrCtrl");
      if (e.ctrlKey) mods.push("Ctrl");
    } else {
      if (e.ctrlKey) mods.push("CmdOrCtrl");
      if (e.metaKey) mods.push("Super");
    }
    if (e.altKey) mods.push("Alt");
    if (e.shiftKey) mods.push("Shift");

    const code = e.code;
    let main = "";
    if (/^Key[A-Z]$/.test(code)) main = code.slice(3);
    else if (/^Digit[0-9]$/.test(code)) main = code.slice(5);
    else if (/^F([1-9]|1[0-9]|2[0-4])$/.test(code)) main = code;
    else if (/^Numpad([0-9]|Add|Decimal|Divide|Enter|Equal|Multiply|Subtract)$/.test(code)) main = code;
    else if (/^(Arrow(Up|Down|Left|Right)|Backquote|Backslash|BracketLeft|BracketRight|Comma|Equal|Minus|Period|Quote|Semicolon|Slash|Backspace|Enter|Space|Tab|Delete|End|Home|Insert|PageDown|PageUp|PrintScreen|ScrollLock|Pause|NumLock|AudioVolume(Down|Up|Mute)|Media(Play|Pause|PlayPause|Stop|TrackNext|TrackPrevious))$/.test(code)) main = code;
    if (!main) return "";
    return [...mods, main].join("+");
}

export function localAudioHotkeyMap(cfg: Record<string, unknown>): Map<string, AudioHotkeyBinding> {
  const out = new Map<string, AudioHotkeyBinding>();
  if (cfg.hotkeys_enabled !== true || !Array.isArray(cfg.audio_hotkeys)) return out;
  for (const item of cfg.audio_hotkeys) {
    if (!item || typeof item !== "object") continue;
    const binding = item as AudioHotkeyBinding;
    if (binding.enabled && binding.scope === "window" && binding.combo) {
      out.set(binding.combo, binding);
    }
  }
  return out;
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
    const combo = typeof cfg[h.key] === "string" ? String(cfg[h.key]).trim() : h.fallback;
    if (!combo) continue;
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
  if (el.closest?.("[data-hotkey-recorder]")) return true;
  const tag = el.tagName.toLowerCase();
  return (
    tag === "input" ||
    tag === "textarea" ||
    tag === "select" ||
    el.isContentEditable === true
  );
}
