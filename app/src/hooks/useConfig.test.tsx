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

  it("写盘串行：前一次还没回来，后一次不能并发发出", async () => {
    const h = mountHook(() => useConfig());
    mounts.push(h);
    await tick();
    let resolveA!: (v: unknown) => void;
    let seq = 0;
    tauri.invoke.mockImplementation(async (cmd: string, args?: unknown) => {
      if (cmd === "config_set") {
        seq++;
        tauri.configSetCalls.push(
          (args as { patch: Record<string, unknown> }).patch,
        );
        if (seq === 1) return new Promise((res) => { resolveA = res; });
        return { config: {}, hot: {}, needs_restart: [] };
      }
      return {};
    });
    let pB!: Promise<void>;
    await act(async () => {
      void h.result.current.set("a", 1, true).catch(() => {});
      pB = h.result.current.set("b", 2, true);
      void pB.catch(() => {});
    });
    // 第一次写还在途：第二次必须排队，不许并发发出。
    expect(tauri.configSetCalls).toEqual([{ a: 1 }]);
    await act(async () => {
      resolveA({ config: { a: 1 }, hot: {}, needs_restart: [] });
      await pB;
    });
    expect(tauri.configSetCalls).toEqual([{ a: 1 }, { b: 2 }]);
  });

  it("三连写：排队任务在途时新写仍须排队，不得并发发出", async () => {
    const h = mountHook(() => useConfig());
    mounts.push(h);
    await tick();
    let resolveA!: (v: unknown) => void;
    let resolveB!: (v: unknown) => void;
    let seq = 0;
    tauri.invoke.mockImplementation(async (cmd: string, args?: unknown) => {
      if (cmd === "config_set") {
        seq++;
        tauri.configSetCalls.push(
          (args as { patch: Record<string, unknown> }).patch,
        );
        if (seq === 1) return new Promise((res) => { resolveA = res; });
        if (seq === 2) return new Promise((res) => { resolveB = res; });
        return { config: {}, hot: {}, needs_restart: [] };
      }
      return {};
    });
    await act(async () => {
      void h.result.current.set("a", 1, true).catch(() => {});
      void h.result.current.set("b", 2, true).catch(() => {});
    });
    expect(tauri.configSetCalls).toEqual([{ a: 1 }]);
    // 放出 A 并把微任务跑完：B 的 config_set 此时已在途但尚未落定。
    await act(async () => {
      resolveA({ config: { a: 1 }, hot: {}, needs_restart: [] });
      for (let i = 0; i < 5; i++) await Promise.resolve();
    });
    expect(tauri.configSetCalls).toEqual([{ a: 1 }, { b: 2 }]);
    // B 在途时写 C：串行链必须认得 B 还在跑，C 只能排队等它。
    let pC!: Promise<void>;
    await act(async () => {
      pC = h.result.current.set("c", 3, true);
      void pC.catch(() => {});
      for (let i = 0; i < 5; i++) await Promise.resolve();
    });
    expect(tauri.configSetCalls).toEqual([{ a: 1 }, { b: 2 }]);
    await act(async () => {
      resolveB({ config: { b: 2 }, hot: {}, needs_restart: [] });
      await pC;
    });
    expect(tauri.configSetCalls).toEqual([{ a: 1 }, { b: 2 }, { c: 3 }]);
  });

  it("重叠写盘：旧的成功不能把更新的失败错误清掉", async () => {
    const h = mountHook(() => useConfig());
    mounts.push(h);
    await tick();
    let resolveA!: (v: unknown) => void;
    let seq = 0;
    tauri.invoke.mockImplementation(async (cmd: string, args?: unknown) => {
      if (cmd === "config_set") {
        seq++;
        tauri.configSetCalls.push(
          (args as { patch: Record<string, unknown> }).patch,
        );
        if (seq === 1) return new Promise((res) => { resolveA = res; });
        if (seq === 2) throw new Error("disk full");
        return { config: {}, hot: {}, needs_restart: [] };
      }
      return {};
    });
    let pB!: Promise<void>;
    await act(async () => {
      void h.result.current.set("a", 1, true).catch(() => {});
      pB = h.result.current.set("b", 2, true);
      void pB.catch(() => {});
    });
    // 让在途的旧写成功回来 —— 它不得盖掉新写已经报的失败。
    await act(async () => {
      resolveA({ config: { a: 1 }, hot: {}, needs_restart: [] });
    });
    await expect(pB).rejects.toThrow("disk full");
    expect(h.result.current.error).toContain("disk full");
    // b 没写上：留在待写里，下一次写盘要带上它的最新值。
    await act(async () => {
      await h.result.current.set("c", 3, true);
    });
    expect(tauri.configSetCalls[tauri.configSetCalls.length - 1]).toEqual({
      b: 2,
      c: 3,
    });
    expect(h.result.current.error).toBe("");
  });

  it("初始加载晚到：不得把用户已经改过的值拽回旧快照", async () => {
    let resolveLoad!: (v: unknown) => void;
    tauri.invoke.mockImplementation(async (cmd: string, args?: unknown) => {
      if (cmd === "config_get") {
        return new Promise((res) => { resolveLoad = res; });
      }
      if (cmd === "config_set") {
        tauri.configSetCalls.push(
          (args as { patch: Record<string, unknown> }).patch,
        );
        return { config: {}, hot: {}, needs_restart: [] };
      }
      return {};
    });
    const h = mountHook(() => useConfig());
    mounts.push(h);
    // 加载还没回来，用户已经改了值 —— 乐观可见并进 pending。
    act(() => {
      void h.result.current.set("pitch", 9);
    });
    await act(async () => {
      resolveLoad({ pitch: 3 });
    });
    await tick();
    // 晚到的旧快照不许覆盖已表达的意图。
    expect(h.result.current.num("pitch", 0)).toBe(9);
  });

  it("初始加载比一次已完成的写盘还晚回来：不得拽回已写上的值", async () => {
    let resolveLoad!: (v: unknown) => void;
    tauri.invoke.mockImplementation(async (cmd: string, args?: unknown) => {
      if (cmd === "config_get") {
        return new Promise((res) => { resolveLoad = res; });
      }
      if (cmd === "config_set") {
        const patch = (args as { patch: Record<string, unknown> }).patch;
        tauri.configSetCalls.push(patch);
        // 后端落盘后回写的是合并后的整份配置。
        return { config: { ...patch }, hot: {}, needs_restart: [] };
      }
      return {};
    });
    const h = mountHook(() => useConfig());
    mounts.push(h);
    // 加载还没回来，用户改值并且**已经写盘成功** —— pending/inflight 都空了。
    await act(async () => {
      await h.result.current.set("pitch", 9, true);
    });
    expect(tauri.configSetCalls).toEqual([{ pitch: 9 }]);
    // 此刻初始快照才到：它比那次写盘旧，但照样不许回写界面。
    await act(async () => {
      resolveLoad({ pitch: 3 });
    });
    await tick();
    expect(h.result.current.num("pitch", 0)).toBe(9);
  });
});
