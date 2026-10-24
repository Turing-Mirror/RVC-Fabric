// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { mountHook, tick } from "../test/dom";

const tauri = vi.hoisted(() => ({ invoke: vi.fn(async () => true) }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: tauri.invoke }));

import { SLOW_START_MS, useSlowDiskHint } from "./useSlowDiskHint";

const step = (index: number) => ({ index, count: 5, labelKey: "x" });

describe("useSlowDiskHint", () => {
  afterEach(() => vi.useRealTimers());

  it("机械硬盘上读盘的步骤超时才提示", async () => {
    vi.useFakeTimers();
    const m = mountHook(() => useSlowDiskHint(step(1)));
    expect(m.result.current).toBe(false);
    await act(async () => {
      vi.advanceTimersByTime(SLOW_START_MS);
      await tick();
    });
    expect(m.result.current).toBe(true);
    m.unmount();
  });

  it("后面的步骤不提示", async () => {
    vi.useFakeTimers();
    const m = mountHook(() => useSlowDiskHint(step(3)));
    await act(async () => {
      vi.advanceTimersByTime(SLOW_START_MS * 2);
      await tick();
    });
    expect(m.result.current).toBe(false);
    m.unmount();
  });
});
