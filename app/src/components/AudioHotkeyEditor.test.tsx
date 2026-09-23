// @vitest-environment happy-dom
import { act } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n";
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
