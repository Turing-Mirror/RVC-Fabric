// @vitest-environment happy-dom
/**
 * R04 回归：配置持久化失败的语义。
 *
 * 修复前 flush 先清空 pending 再 await 写盘：写失败时改动直接丢，
 * 且 immediate 调用方拿到的 Promise 仍 resolve —— 「存完再做下一步」
 * 的调用方（如改完热键立刻 hotkeys_apply）无法知道保存其实失败了。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { mountHook, tick, type Mounted } from "../test/dom";

const tauri = vi.hoisted(() => ({
  invoke: vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>(),
  configSetCalls: [] as Record<string, unknown>[],
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: tauri.invoke }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(async () => () => {}),
}));
vi.mock("../lib/appearance", () => ({ applyAppearance: vi.fn() }));

import { useConfig } from "./useConfig";

describe("useConfig 持久化失败语义", () => {
  const mounts: Mounted[] = [];

  beforeEach(() => {
    tauri.configSetCalls.length = 0;
    tauri.invoke.mockImplementation(async (cmd: string, args?: unknown) => {
      if (cmd === "config_get") return {};
      if (cmd === "config_set") {
        tauri.configSetCalls.push(
          (args as { patch: Record<string, unknown> }).patch,
        );
        return { config: {}, hot: {}, needs_restart: [] };
      }
      return {};
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    while (mounts.length) mounts.pop()?.unmount();
  });

  it("immediate 写盘失败时 Promise 要拒绝，调用方才知道没存上", async () => {
    const h = mountHook(() => useConfig());
    mounts.push(h);
    await tick();
    tauri.invoke.mockImplementation(async (cmd: string) => {
      if (cmd === "config_set") throw new Error("disk full");
      return {};
    });
    let p!: Promise<void>;
    await act(async () => {
      p = h.result.current.set("pitch", 3, true);
      void p.catch(() => {});
    });
    await expect(p).rejects.toThrow("disk full");
  });

  it("写盘失败后待写字段不丢，下一次 flush 要带上", async () => {
    const h = mountHook(() => useConfig());
    mounts.push(h);
    await tick();
    let failed = false;
    tauri.invoke.mockImplementation(async (cmd: string, args?: unknown) => {
      if (cmd === "config_set") {
        if (!failed) {
          failed = true;
          throw new Error("disk full");
        }
        tauri.configSetCalls.push(
          (args as { patch: Record<string, unknown> }).patch,
        );
        return { config: {}, hot: {}, needs_restart: [] };
      }
      return {};
    });
    let p!: Promise<void>;
    await act(async () => {
      p = h.result.current.set("a", 1, true);
      void p.catch(() => {});
    });
    await expect(p).rejects.toThrow();
    await act(async () => {
      await h.result.current.set("b", 2, true);
    });
    // a 是用户已经表达过的意图，不能因为上次写盘失败就被静默丢掉
    expect(tauri.configSetCalls[tauri.configSetCalls.length - 1]).toEqual({ a: 1, b: 2 });
  });

  it("220ms 合并窗口内不同字段的改动一起写盘", async () => {
    vi.useFakeTimers();
    const h = mountHook(() => useConfig());
    mounts.push(h);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    act(() => {
      void h.result.current.set("x", 1);
      void h.result.current.set("y", 2);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(tauri.configSetCalls).toEqual([{ x: 1, y: 2 }]);
  });

  it("同一字段连改只写最后一个值", async () => {
    vi.useFakeTimers();
    const h = mountHook(() => useConfig());
    mounts.push(h);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    act(() => {
      void h.result.current.set("pitch", 3);
      void h.result.current.set("pitch", 4);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(tauri.configSetCalls).toEqual([{ pitch: 4 }]);
  });
});
