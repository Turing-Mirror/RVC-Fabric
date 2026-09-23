// @vitest-environment happy-dom
import { afterEach, expect, it, vi } from "vitest";
import { comboFromEvent, localAudioHotkeyMap, localHotkeyMap, typingInto } from "./hotkeys";

afterEach(() => vi.restoreAllMocks());

it("keeps numpad and navigation keys distinct from main digits", () => {
  const numpad = new KeyboardEvent("keydown", { code: "Numpad7", ctrlKey: true });
  const digit = new KeyboardEvent("keydown", { code: "Digit7", ctrlKey: true });
  expect(comboFromEvent(numpad)).not.toBe(comboFromEvent(digit));
  expect(comboFromEvent(numpad)).toContain("Numpad7");
  expect(comboFromEvent(new KeyboardEvent("keydown", { code: "ArrowLeft" }))).toBe("ArrowLeft");
});

it("does not restore a legacy default after an explicit clear", () => {
  const map = localHotkeyMap({ hotkeys_enabled: true, hotkey_toggle_vc_global: false, hotkey_toggle_vc: "" });
  expect([...map.values()]).not.toContain("toggle-vc");
});

it("only dispatches enabled window-scoped audio bindings locally", () => {
  const binding = { binding_id: "one", action: "stop-all", target_entry_id: null,
    combo: "F12", scope: "window", enabled: true, mode: null };
  const map = localAudioHotkeyMap({ hotkeys_enabled: true, audio_hotkeys: [
    binding, { ...binding, binding_id: "two", combo: "F11", scope: "global" },
    { ...binding, binding_id: "three", combo: "F10", enabled: false },
  ] });
  expect([...map.keys()]).toEqual(["F12"]);
});

it("ignores shortcuts while a binding recorder has focus", () => {
  const button = document.createElement("button");
  button.dataset.hotkeyRecorder = "";
  expect(typingInto(button)).toBe(true);
  expect(typingInto(document.createElement("div"))).toBe(false);
});
