// @vitest-environment happy-dom
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n";
import { mount, tick, type Mounted } from "../test/dom";

const shell = vi.hoisted(() => ({
  invoke: vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>(),
}));
vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn(() => Promise.resolve(() => {})) }));

import { AudioPage } from "./AudioPage";

const library = {
  revision: 1,
  sources: [
    { id: "source-1", path: "D:\\Music\\A", kind: "directory", mode: "reference", excludes: [] },
    { id: "source-2", path: "E:\\Music\\A", kind: "directory", mode: "reference", excludes: [] },
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
    shell.invoke.mockImplementation(async (cmd) => {
      if (cmd === "config_get") return { ui_locale: "zh-CN", audio_preview_device_id: "speaker" };
      if (cmd === "audio_library_get") return library;
      if (cmd === "audio_preview_devices") return [{ id: "speaker", name: "Speakers" }];
      if (cmd === "audio_preview_status") return { state: "idle", name: "", played_frames: 0, length_frames: 0, sample_rate: 48000 };
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

  it("重新定位失联文件时按稳定资产 ID 提交", async () => {
    shell.invoke.mockImplementation(async (cmd) => {
      if (cmd === "config_get") return { ui_locale: "zh-CN" };
      if (cmd === "audio_library_get") return library;
      if (cmd === "audio_preview_devices") return [];
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
});
