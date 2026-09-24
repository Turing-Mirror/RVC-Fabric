// @vitest-environment happy-dom
import { act } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { I18nProvider, tStatic } from "../i18n";
import { mount, tick, type Mounted } from "../test/dom";
import type { AudioHotkeyBinding } from "../lib/hotkeys";

const shell = vi.hoisted(() => ({
  invoke: vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>(),
}));
vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn(() => Promise.resolve(() => {})) }));

import { AudioHotkeyEditor } from "./AudioHotkeyEditor";

let mounted: Mounted | null;
let bindings: AudioHotkeyBinding[];

beforeEach(() => {
  bindings = [];
  shell.invoke.mockReset();
  shell.invoke.mockImplementation(async (command, args) => {
    if (command === "audio_hotkeys_get") return bindings;
    if (command === "audio_hotkeys_status") return [];
    if (command === "config_get") return { hotkeys_enabled: true };
    if (command === "audio_hotkeys_set") {
      bindings = (args as { bindings: AudioHotkeyBinding[] }).bindings;
      return {};
    }
    if (command === "hotkeys_apply") return { registered: [] };
    return null;
  });
});

afterEach(() => {
  mounted?.unmount();
  mounted = null;
});

it("saves entry bindings by stable entry id", async () => {
  mounted = mount(<I18nProvider><AudioHotkeyEditor entryId="entry-7" entries={[{ id: "entry-7", name: "片段" }]} /></I18nProvider>);
  await tick();
  const add = Array.from(mounted.container.querySelectorAll("button"))
    .find((button) => button.textContent === "添加绑定");
  expect(add).toBeDefined();
  act(() => add!.click());
  await tick();
  expect(bindings).toMatchObject([{ action: "play-entry", target_entry_id: "entry-7", combo: "", scope: "window" }]);
});

it("does not arm recording while a global shortcut remains registered", async () => {
  bindings = [{ binding_id: "one", action: "stop-all", target_entry_id: null,
    combo: "F12", scope: "global", enabled: true, mode: null }];
  shell.invoke.mockImplementation(async (command) => {
    if (command === "audio_hotkeys_get") return bindings;
    if (command === "audio_hotkeys_status") return [{ binding_id: "one", state: "registered" }];
    if (command === "config_get") return { hotkeys_enabled: true };
    if (command === "audio_library_get") return { entries: [] };
    if (command === "hotkeys_apply") return { registered: ["F12"] };
    return null;
  });
  mounted = mount(<I18nProvider><AudioHotkeyEditor /></I18nProvider>);
  await tick();
  await tick();
  const record = mounted.container.querySelector<HTMLButtonElement>("[data-hotkey-recorder]");
  expect(record).not.toBeNull();
  act(() => record!.click());
  await tick();
  expect(mounted.container.textContent).not.toContain("请按组合键");
  expect(mounted.container.querySelector("[role=alert]")).not.toBeNull();
});

it("splits playback and numbered-entry bindings and filters both by the query", async () => {
  bindings = [
    { binding_id: "stop", action: "stop-all", target_entry_id: null, combo: "F10", scope: "window", enabled: true, mode: null },
    { binding_id: "horn", action: "play-entry", target_entry_id: "e1", combo: "F11", scope: "window", enabled: true, mode: "replace" },
  ];
  const entries = [{ id: "e1", name: "喇叭", number: 3 }];
  mounted = mount(<I18nProvider>
    <div data-group="playback"><AudioHotkeyEditor group="playback" entries={entries} /></div>
    <div data-group="entries"><AudioHotkeyEditor group="entries" entries={entries} query="喇叭" /></div>
  </I18nProvider>);
  await tick();
  await tick();
  const playback = mounted.container.querySelector("[data-group=playback]")!;
  const numbered = mounted.container.querySelector("[data-group=entries]")!;
  expect(playback.querySelectorAll("[data-hotkey-recorder]")).toHaveLength(1);
  expect(playback.textContent).toContain("F10");
  expect(numbered.querySelectorAll("[data-hotkey-recorder]")).toHaveLength(1);
  expect(numbered.textContent).toContain("F11");
  mounted.unmount();
  mounted = mount(<I18nProvider><AudioHotkeyEditor group="entries" entries={entries} query="nothing" /></I18nProvider>);
  await tick();
  await tick();
  expect(mounted.container.querySelectorAll("[data-hotkey-recorder]")).toHaveLength(0);
});

it("applies an edit to the saved list so a second editor's change is kept", async () => {
  bindings = [
    { binding_id: "stop", action: "stop-all", target_entry_id: null, combo: "F10", scope: "window", enabled: true, mode: null },
  ];
  mounted = mount(<I18nProvider><AudioHotkeyEditor group="playback" entries={[]} /></I18nProvider>);
  await tick();
  await tick();
  // Another editor saved meanwhile; this one still shows the old list.
  bindings = [...bindings, { binding_id: "other", action: "play-entry", target_entry_id: "e1", combo: "F9",
    scope: "window", enabled: true, mode: "replace" }];
  const clear = Array.from(mounted.container.querySelectorAll("button")).find((b) => b.textContent === tStatic("audio.hotkeyClear"));
  act(() => clear!.click());
  await tick();
  await tick();
  expect(bindings.map((b) => [b.binding_id, b.combo])).toEqual([["stop", ""], ["other", "F9"]]);
});
