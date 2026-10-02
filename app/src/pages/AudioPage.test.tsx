// @vitest-environment happy-dom
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n";
import { mount, tick, type Mounted } from "../test/dom";

const shell = vi.hoisted(() => ({
  invoke: vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>(),
}));
const dialogs = vi.hoisted(() => ({ askConfirm: vi.fn(async () => true) }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn(() => Promise.resolve(() => {})) }));
vi.mock("../lib/webDialog", () => ({ askConfirm: dialogs.askConfirm }));

import { AudioPage } from "./AudioPage";

const library = {
  revision: 1,
  sources: [
    { id: "source-1", path: "D:\\Music\\A", kind: "directory", mode: "reference", excludes: [] },
    { id: "source-2", path: "E:\\Music\\A", kind: "directory", mode: "reference", excludes: [] },
    { id: "source-3", path: "F:\\Lib\\C", kind: "directory", mode: "copy", excludes: [] },
  ],
  assets: [
    { id: "asset-1", path: "D:\\Music\\A\\good.wav", origin: "D:\\Music\\A\\good.wav", source_ids: ["source-1"], available: true, excluded_source_ids: [] },
    { id: "asset-2", path: "E:\\Music\\A\\lost.wav", origin: "E:\\Music\\A\\lost.wav", source_ids: ["source-2"], available: false, excluded_source_ids: [] },
  ],
  entries: [
    { id: "entry-1", asset_id: "asset-1", name: "可试听", number: 10001, start: 0, end: null },
    { id: "entry-2", asset_id: "asset-2", name: "失联", number: 20002, start: 0, end: null },
  ],
};

const mounts: Mounted[] = [];

describe("音频库页面", () => {
  beforeEach(() => {
    shell.invoke.mockReset();
    dialogs.askConfirm.mockClear();
    dialogs.askConfirm.mockResolvedValue(true);
    shell.invoke.mockImplementation(async (cmd) => {
      if (cmd === "config_get") return { ui_locale: "zh-CN", audio_preview_device_id: "speaker" };
      if (cmd === "audio_library_get") return library;
      if (cmd === "audio_preview_devices") return [{ id: "speaker", name: "Speakers" }];
      if (cmd === "audio_voice_devices") return [];
      if (cmd === "audio_hotkeys_get") return [];
      if (cmd === "audio_hotkeys_status") return [];
      if (cmd === "audio_voice_instances") return [];
      if (cmd === "audio_preview_status") return { state: "idle", name: "", played_frames: 0, length_frames: 0, sample_rate: 48000 };
      if (cmd === "audio_library_refresh" || cmd === "audio_library_remove_source") return library;
      return null;
    });
  });

  afterEach(() => {
    while (mounts.length) mounts.pop()?.unmount();
  });

  it("区分同名来源，并禁止试听失联文件", async () => {
    const mounted = mount(<I18nProvider><AudioPage /></I18nProvider>);
    mounts.push(mounted);
    await tick();
    await tick();
    expect(mounted.container.textContent).toContain("D: / Music / A");
    expect(mounted.container.textContent).toContain("E: / Music / A");
    const lost = Array.from(mounted.container.querySelectorAll("button"))
      .find((button) => button.textContent?.includes("失联"));
    expect(lost).toBeDefined();
    act(() => lost!.click());
    const preview = Array.from(mounted.container.querySelectorAll("button"))
      .find((button) => button.textContent === "试听选区");
    expect(preview?.disabled).toBe(true);
    expect(shell.invoke.mock.calls.some(([cmd]) => cmd === "ensure_engine")).toBe(false);
  });

  it("语音音频总音量滑块与静音使用独立的原生控制", async () => {
    const original = shell.invoke.getMockImplementation()!;
    shell.invoke.mockImplementation(async (cmd, args) => {
      if (cmd === "audio_voice_volume_get") return { volume: 0.8, muted: false };
      if (cmd === "audio_voice_volume_set") return { volume: 0.6, muted: false };
      if (cmd === "audio_voice_volume_toggle") return { volume: 0.6, muted: true };
      return original(cmd, args);
    });
    const mounted = mount(<I18nProvider><AudioPage /></I18nProvider>);
    mounts.push(mounted);
    await tick();
    expect(mounted.container.textContent).toContain("音频总音量");
    expect(mounted.container.textContent).toContain("80");
    const range = mounted.container.querySelector<HTMLInputElement>("input[type=range]")!;
    expect(range).toBeTruthy();
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    act(() => {
      setValue.call(range, "60");
      range.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await tick();
    expect(shell.invoke).toHaveBeenCalledWith("audio_voice_volume_set", { volume: 0.6 });
    const button = (label: string) => Array.from(mounted.container.querySelectorAll("button"))
      .find((item) => item.textContent === label)!;
    act(() => button("静音").click());
    await tick();
    expect(shell.invoke).toHaveBeenCalledWith("audio_voice_volume_toggle", undefined);
    expect(mounted.container.textContent).toContain("取消静音");
  });

  it("重新定位失联文件时按稳定资产 ID 提交", async () => {
    shell.invoke.mockImplementation(async (cmd) => {
      if (cmd === "config_get") return { ui_locale: "zh-CN" };
      if (cmd === "audio_library_get") return library;
      if (cmd === "audio_preview_devices") return [];
      if (cmd === "audio_voice_devices") return [];
      if (cmd === "audio_hotkeys_get") return [];
      if (cmd === "audio_hotkeys_status") return [];
      if (cmd === "audio_voice_instances") return [];
      if (cmd === "audio_preview_status") return { state: "idle", name: "", played_frames: 0, length_frames: 0, sample_rate: 48000 };
      if (cmd === "audio_library_pick_replacement") return "E:\\Moved\\lost.wav";
      if (cmd === "audio_library_relink_asset") return library;
      return null;
    });
    const mounted = mount(<I18nProvider><AudioPage /></I18nProvider>);
    mounts.push(mounted);
    await tick();
    const lost = Array.from(mounted.container.querySelectorAll("button"))
      .find((button) => button.textContent?.includes("失联"));
    act(() => lost!.click());
    const relink = Array.from(mounted.container.querySelectorAll("button"))
      .find((button) => button.textContent === "重新定位文件");
    expect(relink).toBeDefined();
    act(() => relink!.click());
    await tick();
    await tick();
    expect(shell.invoke).toHaveBeenCalledWith("audio_library_relink_asset", {
      assetId: "asset-2",
      replacement: "E:\\Moved\\lost.wav",
      replaceScannedDuplicate: false,
    });
  });

  it("试听使用当前草稿范围而非已保存范围", async () => {
    shell.invoke.mockImplementation(async (cmd) => {
      if (cmd === "config_get") return { ui_locale: "zh-CN", audio_preview_device_id: "speaker" };
      if (cmd === "audio_library_get") return library;
      if (cmd === "audio_preview_devices") return [{ id: "speaker", name: "Speakers" }];
      if (cmd === "audio_voice_devices") return [];
      if (cmd === "audio_hotkeys_get") return [];
      if (cmd === "audio_hotkeys_status") return [];
      if (cmd === "audio_voice_instances") return [];
      if (cmd === "audio_preview_status") return { state: "idle", name: "", played_frames: 0, length_frames: 0, sample_rate: 48000 };
      if (cmd === "audio_waveform_get") return { duration: 10, peaks: [0, 120, 255] };
      if (cmd === "audio_preview_start") return { state: "playing", name: "可试听", played_frames: 0, length_frames: 48000, sample_rate: 48000 };
      return null;
    });
    const mounted = mount(<I18nProvider><AudioPage /></I18nProvider>);
    mounts.push(mounted);
    await tick();
    const entry = Array.from(mounted.container.querySelectorAll("button"))
      .find((button) => button.textContent?.includes("可试听"));
    act(() => entry!.click());
    await tick();
    const start = Array.from(mounted.container.querySelectorAll("label"))
      .find((label) => label.textContent?.includes("开始时间（秒）"))?.querySelector("input");
    const end = Array.from(mounted.container.querySelectorAll("label"))
      .find((label) => label.textContent?.includes("结束时间（秒"))?.querySelector("input");
    expect(start).toBeDefined();
    expect(end).toBeDefined();
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      setter.call(start, "1.25");
      start!.dispatchEvent(new Event("input", { bubbles: true }));
      setter.call(end, "2.75");
      end!.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const preview = Array.from(mounted.container.querySelectorAll("button"))
      .find((button) => button.textContent === "试听选区");
    act(() => preview!.click());
    await tick();
    expect(shell.invoke).toHaveBeenCalledWith("audio_preview_start", {
      entryId: "entry-1", deviceId: "speaker", start: 1.25, end: 2.75,
    });
  });

  it("语音输出使用已保存条目和明确选择的设备，不依赖引擎", async () => {
    shell.invoke.mockImplementation(async (cmd) => {
      if (cmd === "config_get") return { ui_locale: "zh-CN", audio_voice_device_id: "cable" };
      if (cmd === "audio_library_get") return library;
      if (cmd === "audio_preview_devices") return [];
      if (cmd === "audio_voice_devices") return [{ id: "cable", name: "CABLE Input" }];
      if (cmd === "audio_hotkeys_get") return [];
      if (cmd === "audio_hotkeys_status") return [];
      if (cmd === "audio_voice_instances") return [];
      if (cmd === "audio_preview_status" || cmd === "audio_voice_status") return { state: "idle", name: "", played_frames: 0, length_frames: 0, sample_rate: 0 };
      if (cmd === "audio_voice_start") return { state: "playing", name: "可试听", played_frames: 0, length_frames: 48000, sample_rate: 48000 };
      return null;
    });
    const mounted = mount(<I18nProvider><AudioPage /></I18nProvider>);
    mounts.push(mounted);
    await tick();
    const missing = Array.from(mounted.container.querySelectorAll("button"))
      .find((button) => button.textContent?.includes("失联"));
    act(() => missing!.click());
    expect(Array.from(mounted.container.querySelectorAll("button"))
      .find((button) => button.textContent === "播放到语音")?.disabled).toBe(true);
    const available = Array.from(mounted.container.querySelectorAll("button"))
      .find((button) => button.textContent?.includes("可试听"));
    act(() => available!.click());
    const play = Array.from(mounted.container.querySelectorAll("button"))
      .find((button) => button.textContent === "播放到语音");
    act(() => play!.click());
    await tick();
    expect(shell.invoke).toHaveBeenCalledWith("audio_voice_start", { entryId: "entry-1", deviceId: "cable", mode: "replace" });
    const overlay = Array.from(mounted.container.querySelectorAll("button"))
      .find((button) => button.textContent === "叠加播放到语音");
    act(() => overlay!.click());
    await tick();
    expect(shell.invoke).toHaveBeenCalledWith("audio_voice_start", { entryId: "entry-1", deviceId: "cable", mode: "overlay" });
    expect(shell.invoke.mock.calls.some(([cmd]) => cmd === "engine_start_vc")).toBe(false);
  });

  it("叠加实例可以分别暂停和停止，也可以一次停止全部", async () => {
    const first = { state: "playing", name: "第一段", played_frames: 12000, length_frames: 48000,
      sample_rate: 48000, instance_id: 11, active_count: 2 };
    const second = { ...first, name: "第二段", instance_id: 12 };
    shell.invoke.mockImplementation(async (cmd) => {
      if (cmd === "config_get") return { ui_locale: "zh-CN", audio_voice_device_id: "cable" };
      if (cmd === "audio_library_get") return library;
      if (cmd === "audio_preview_devices") return [];
      if (cmd === "audio_voice_devices") return [{ id: "cable", name: "CABLE Input" }];
      if (cmd === "audio_hotkeys_get") return [];
      if (cmd === "audio_hotkeys_status") return [];
      if (cmd === "audio_preview_status") return { state: "idle", name: "", played_frames: 0, length_frames: 0, sample_rate: 0 };
      if (cmd === "audio_voice_status") return second;
      if (cmd === "audio_voice_instances") return [second, first];
      if (cmd === "audio_voice_pause" || cmd === "audio_voice_replay" || cmd === "audio_voice_stop_instance") return first;
      if (cmd === "audio_voice_stop") return { ...first, state: "idle", active_count: 0, instance_id: null };
      return null;
    });
    const mounted = mount(<I18nProvider><AudioPage /></I18nProvider>);
    mounts.push(mounted);
    await tick();
    const list = mounted.container.querySelector('[aria-label="正在语音输出的音频"]');
    expect(list?.textContent).toContain("第一段");
    expect(list?.textContent).toContain("第二段");
    const buttons = list!.querySelectorAll("button");
    act(() => buttons[0].click());
    await tick();
    expect(shell.invoke).toHaveBeenCalledWith("audio_voice_pause", { paused: true, instanceId: 12 });
    act(() => buttons[1].click());
    await tick();
    expect(shell.invoke).toHaveBeenCalledWith("audio_voice_replay", { instanceId: 12 });
    const firstCard = Array.from(list!.children).find((card) => card.textContent?.includes("第一段"))!;
    const stopFirst = Array.from(firstCard.querySelectorAll("button"))
      .find((button) => button.textContent === "停止")!;
    act(() => stopFirst.click());
    await tick();
    expect(shell.invoke).toHaveBeenCalledWith("audio_voice_stop_instance", { instanceId: 11 });
    const stopAll = Array.from(mounted.container.querySelectorAll("button"))
      .find((button) => button.textContent === "停止全部音频");
    act(() => stopAll!.click());
    await tick();
    expect(shell.invoke).toHaveBeenCalledWith("audio_voice_stop");
  });

  const menuOf = (container: HTMLElement, sourcePath: string) => {
    const row = Array.from(container.querySelectorAll<HTMLElement>(".group.relative"))
      .find((el) => el.querySelector("button")?.getAttribute("aria-label") === sourcePath);
    expect(row).toBeDefined();
    return row!.querySelector<HTMLButtonElement>("[data-source-menu]")!;
  };

  it("来源菜单按被点开的来源刷新，不用左侧当前筛选", async () => {
    const mounted = mount(<I18nProvider><AudioPage /></I18nProvider>);
    mounts.push(mounted);
    await tick();
    const trigger = menuOf(mounted.container, "E:\\Music\\A");
    act(() => trigger.click());
    await tick();
    const menu = mounted.container.querySelector<HTMLElement>("[role=menu]");
    expect(menu).toBeTruthy();
    expect(menu?.textContent).toContain("刷新来源");
    expect(menu?.textContent).toContain("重新定位来源");
    expect(menu?.textContent).toContain("移出音频库");
    const refresh = Array.from(menu!.querySelectorAll<HTMLButtonElement>("[role=menuitem]"))
      .find((b) => b.textContent === "刷新来源")!;
    act(() => refresh.click());
    await tick();
    expect(shell.invoke).toHaveBeenCalledWith("audio_library_refresh", { sourceId: "source-2" });
    // 菜单关上了，焦点回到打开它的 ⋯。
    expect(mounted.container.querySelector("[role=menu]")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("重新定位来源只在引用模式出现，并按稳定 ID 提交", async () => {
    shell.invoke.mockImplementation(async (cmd) => {
      if (cmd === "audio_library_pick_replacement") return "E:\\Moved\\A";
      if (cmd === "audio_library_relink_source") return library;
      if (cmd === "config_get") return { ui_locale: "zh-CN" };
      if (cmd === "audio_library_get") return library;
      if (cmd === "audio_preview_devices" || cmd === "audio_voice_devices") return [];
      if (cmd === "audio_hotkeys_get" || cmd === "audio_hotkeys_status") return [];
      if (cmd === "audio_voice_instances") return [];
      if (cmd === "audio_preview_status" || cmd === "audio_voice_status") return { state: "idle", name: "", played_frames: 0, length_frames: 0, sample_rate: 0 };
      return null;
    });
    const mounted = mount(<I18nProvider><AudioPage /></I18nProvider>);
    mounts.push(mounted);
    await tick();
    // 复制模式的来源不提供「重新定位来源」。
    act(() => menuOf(mounted.container, "F:\\Lib\\C").click());
    await tick();
    let menu = mounted.container.querySelector<HTMLElement>("[role=menu]")!;
    expect(menu.textContent).not.toContain("重新定位来源");
    // Esc 关闭菜单。
    act(() => {
      menu.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    });
    await tick();
    expect(mounted.container.querySelector("[role=menu]")).toBeNull();
    // 行上右键同样打开菜单，且绑定的是那一条来源。
    const row = Array.from(mounted.container.querySelectorAll<HTMLElement>(".group.relative"))
      .find((el) => el.querySelector("button")?.getAttribute("aria-label") === "E:\\Music\\A")!;
    act(() => {
      row.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: 60, clientY: 120 }));
    });
    await tick();
    menu = mounted.container.querySelector<HTMLElement>("[role=menu]")!;
    expect(menu.textContent).toContain("重新定位来源");
    const relink = Array.from(menu.querySelectorAll<HTMLButtonElement>("[role=menuitem]"))
      .find((b) => b.textContent === "重新定位来源")!;
    act(() => relink.click());
    await tick();
    await tick();
    expect(shell.invoke).toHaveBeenCalledWith("audio_library_relink_source", {
      sourceId: "source-2",
      replacement: "E:\\Moved\\A",
    });
  });

  it("移除来源先确认；只清掉被移除来源的筛选", async () => {
    const mounted = mount(<I18nProvider><AudioPage /></I18nProvider>);
    mounts.push(mounted);
    await tick();
    // 先选中 source-1 作为左侧筛选。
    const first = Array.from(mounted.container.querySelectorAll<HTMLButtonElement>(".group.relative > button"))
      .find((b) => b.getAttribute("aria-label") === "D:\\Music\\A")!;
    act(() => first.click());
    await tick();
    // 开 source-2 的菜单点移除：确认过一次才提交，提交后 source-1 的筛选保持。
    act(() => menuOf(mounted.container, "E:\\Music\\A").click());
    await tick();
    const remove = Array.from(mounted.container.querySelectorAll<HTMLButtonElement>("[role=menuitem]"))
      .find((b) => b.textContent === "移出音频库")!;
    dialogs.askConfirm.mockResolvedValueOnce(false);
    act(() => remove.click());
    await tick();
    expect(dialogs.askConfirm).toHaveBeenCalledTimes(1);
    expect(shell.invoke.mock.calls.some(([cmd]) => cmd === "audio_library_remove_source")).toBe(false);
    // 再开一次点移除并确认。
    act(() => menuOf(mounted.container, "E:\\Music\\A").click());
    await tick();
    const remove2 = Array.from(mounted.container.querySelectorAll<HTMLButtonElement>("[role=menuitem]"))
      .find((b) => b.textContent === "移出音频库")!;
    act(() => remove2.click());
    await tick();
    await tick();
    expect(shell.invoke).toHaveBeenCalledWith("audio_library_remove_source", { sourceId: "source-2" });
    // 没移除的 source-1 仍是当前筛选（按钮保持按下状态）。
    expect(first.getAttribute("aria-pressed")).toBe("true");
  });

  it("点菜单之外任意处关闭菜单", async () => {
    const mounted = mount(<I18nProvider><AudioPage /></I18nProvider>);
    mounts.push(mounted);
    await tick();
    act(() => menuOf(mounted.container, "D:\\Music\\A").click());
    await tick();
    expect(mounted.container.querySelector("[role=menu]")).toBeTruthy();
    act(() => {
      document.body.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await tick();
    expect(mounted.container.querySelector("[role=menu]")).toBeNull();
  });
});
