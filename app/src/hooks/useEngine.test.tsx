// @vitest-environment happy-dom
/**
 * R03 回归：80ms 防抖窗口内修改不同热参数不能丢字段。
 *
 * 修复前 scheduleHot 每次调用都 clearTimeout 重排，待发的是**那一次调用
 * 自己的 patch**：先改音高再改共鸣，最后只发出 {formant}，音高被丢。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { mountHook, type Mounted } from "../test/dom";

const tauri = vi.hoisted(() => ({
  invoke: vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>(),
  calls: [] as { cmd: string; args?: unknown }[],
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: tauri.invoke }));
vi.mock("../i18n", () => ({
  useI18n: () => ({ ready: true }),
  tStatic: (k: string) => k,
  t: (k: string) => k,
}));

import { useEngine } from "./useEngine";

describe("useEngine 热参数合并", () => {
  const mounts: Mounted[] = [];

  beforeEach(() => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    tauri.calls.length = 0;
    tauri.invoke.mockImplementation(async (cmd: string, args?: unknown) => {
      tauri.calls.push({ cmd, args });
      switch (cmd) {
        case "provision_status":
          return { runtime_ready: true };
        case "engine_set_hot":
          return 0;
        case "config_get":
          return {};
        default:
          return { state: "idle", worker_alive: true };
      }
    });
    vi.useFakeTimers();
  });

  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
    vi.useRealTimers();
    while (mounts.length) mounts.pop()?.unmount();
  });

  const hotCalls = () =>
    tauri.calls
      .filter((c) => c.cmd === "engine_set_hot")
      .map((c) => c.args);

  it("80ms 内改不同字段：合并成一次发送，不丢字段", async () => {
    const h = mountHook(() => useEngine());
    mounts.push(h);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    act(() => {
      h.result.current.onPitch(3);
      h.result.current.onFormant(1.5);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });
    expect(hotCalls()).toEqual([{ pitch: 3, formant: 1.5 }]);
  });

  it("同一字段连改只发最后一个值", async () => {
    const h = mountHook(() => useEngine());
    mounts.push(h);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    act(() => {
      h.result.current.onPitch(3);
      h.result.current.onPitch(4);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });
    expect(hotCalls()).toEqual([{ pitch: 4 }]);
  });

  it("防抖窗口外的改动各自发送", async () => {
    const h = mountHook(() => useEngine());
    mounts.push(h);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    act(() => h.result.current.onPitch(3));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });
    act(() => h.result.current.onFormant(2));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });
    expect(hotCalls()).toEqual([{ pitch: 3 }, { formant: 2 }]);
  });
});
