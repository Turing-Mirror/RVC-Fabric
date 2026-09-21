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
// toggleRun 里有个 await import("../lib/downloadModels") —— 顶层先引一次
// 让模块进缓存，测试里的动态导入一个微任务就回来，不用猜它跑多久。
import "../lib/downloadModels";

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

function deferred<T = unknown>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("useEngine 用户启动在途", () => {
  const mounts: Mounted[] = [];

  beforeEach(() => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    tauri.calls.length = 0;
    tauri.invoke.mockReset();
    vi.useFakeTimers();
  });

  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
    vi.useRealTimers();
    while (mounts.length) mounts.pop()?.unmount();
  });

  const baseInvoke = (
    start: { promise: Promise<unknown> },
    stop?: { promise: Promise<unknown> },
  ) =>
    tauri.invoke.mockImplementation(async (cmd: string, args?: unknown) => {
      tauri.calls.push({ cmd, args });
      switch (cmd) {
        case "provision_status":
          return { runtime_ready: true };
        case "config_get":
          return { pth_path: "m/a.pth" };
        case "assets_status":
          return { engine_core_ready: true };
        case "engine_start_vc":
          return start.promise;
        case "engine_stop_vc":
          return stop ? stop.promise : { state: "idle", worker_alive: true };
        default:
          return { state: "idle", worker_alive: true };
      }
    });

  it("start 在途：userStartPending 为真，awaitUserStart 拿到落定结果", async () => {
    const start = deferred<unknown>();
    baseInvoke(start);
    const h = mountHook(() => useEngine());
    mounts.push(h);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(h.result.current.userStartPending()).toBe(false);
    let runP!: Promise<void>;
    act(() => {
      runP = h.result.current.toggleRun();
    });
    // toggleRun 到 startVc 之间隔着 config_get + assets_status + 动态
    // import —— 等它真正发出去，不是猜几个微任务。
    await act(async () => {
      for (let i = 0; i < 30; i += 1) {
        if (tauri.calls.some((c) => c.cmd === "engine_start_vc")) return;
        await vi.advanceTimersByTimeAsync(5);
      }
    });
    expect(
      tauri.calls.some((c) => c.cmd === "engine_start_vc"),
    ).toBe(true);
    expect(h.result.current.userStartPending()).toBe(true);
    let settled: { state?: string; error?: string } = {};
    void h.result.current.awaitUserStart().then((s) => {
      settled = s;
    });
    await act(async () => {
      start.resolve({ state: "running" });
      await runP;
    });
    expect(settled?.state).toBe("running");
    expect(h.result.current.userStartPending()).toBe(false);
  });

  it("start 拒绝：等待者拿到 error 状态而不是永远挂着", async () => {
    const start = deferred<unknown>();
    baseInvoke(start);
    const h = mountHook(() => useEngine());
    mounts.push(h);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    let runP!: Promise<void>;
    act(() => {
      runP = h.result.current.toggleRun();
    });
    await act(async () => {
      for (let i = 0; i < 30; i += 1) {
        if (tauri.calls.some((c) => c.cmd === "engine_start_vc")) return;
        await vi.advanceTimersByTimeAsync(5);
      }
    });
    expect(h.result.current.userStartPending()).toBe(true);
    let settled: { state?: string; error?: string } = {};
    void h.result.current.awaitUserStart().then((s) => {
      settled = s;
    });
    await act(async () => {
      start.reject(new Error("引擎起不来"));
      await runP;
    });
    expect(settled?.state).toBe("error");
    expect(String(settled?.error)).toContain("引擎起不来");
    expect(h.result.current.userStartPending()).toBe(false);
  });

  it("没有在途启动：awaitUserStart 立刻给最近一次结果（没启动过是空对象）", async () => {
    const start = deferred<unknown>();
    baseInvoke(start);
    const h = mountHook(() => useEngine());
    mounts.push(h);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    await expect(h.result.current.awaitUserStart()).resolves.toEqual({});
    // 落定后迟到的等待也能拿到结果 —— 不许挂在已完结的启动上。
    let runP!: Promise<void>;
    act(() => {
      runP = h.result.current.toggleRun();
    });
    await act(async () => {
      for (let i = 0; i < 30; i += 1) {
        if (tauri.calls.some((c) => c.cmd === "engine_start_vc")) return;
        await vi.advanceTimersByTimeAsync(5);
      }
    });
    await act(async () => {
      start.resolve({ state: "running" });
      await runP;
    });
    await expect(h.result.current.awaitUserStart()).resolves.toEqual({
      state: "running",
    });
  });

  it("start 在途时心跳报 idle/running：都不能提前把操作落定", async () => {
    const start = deferred<unknown>();
    let state = "idle";
    tauri.invoke.mockImplementation(async (cmd: string, args?: unknown) => {
      tauri.calls.push({ cmd, args });
      switch (cmd) {
        case "provision_status":
          return { runtime_ready: true };
        case "config_get":
          return { pth_path: "m/a.pth" };
        case "assets_status":
          return { engine_core_ready: true };
        case "engine_start_vc":
          return start.promise;
        case "engine_status":
          return { state, worker_alive: true };
        default:
          return { state: "idle", worker_alive: true };
      }
    });
    const h = mountHook(() => useEngine());
    mounts.push(h);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    let runP!: Promise<void>;
    act(() => {
      runP = h.result.current.toggleRun();
    });
    await act(async () => {
      for (let i = 0; i < 30; i += 1) {
        if (tauri.calls.some((c) => c.cmd === "engine_start_vc")) return;
        await vi.advanceTimersByTimeAsync(5);
      }
    });
    expect(h.result.current.userStartPending()).toBe(true);
    let settled: { state?: string; error?: string } = {};
    void h.result.current.awaitUserStart().then((s) => {
      settled = s;
    });
    // 轮询在 start 落定前报 idle：旧代码在这里清掉 startingRef，
    // pending 直接变 false，此刻选音色会被当成「引擎空闲」。
    await act(async () => {
      await h.result.current.refresh();
    });
    expect(h.result.current.userStartPending()).toBe(true);
    expect(settled.state).toBeUndefined();
    // running 心跳同理：操作只能由 start 本身落定。
    state = "running";
    await act(async () => {
      await h.result.current.refresh();
    });
    expect(h.result.current.userStartPending()).toBe(true);
    expect(settled.state).toBeUndefined();
    await act(async () => {
      start.resolve({ state: "running" });
      await runP;
    });
    expect(settled.state).toBe("running");
  });

  it("准备期（config/assets 还没回来）按下就已 pending：选音色不会被当空闲", async () => {
    const cfg = deferred<unknown>();
    const start = deferred<unknown>();
    tauri.invoke.mockImplementation(async (cmd: string, args?: unknown) => {
      tauri.calls.push({ cmd, args });
      switch (cmd) {
        case "provision_status":
          return { runtime_ready: true };
        case "config_get":
          return cfg.promise;
        case "assets_status":
          return { engine_core_ready: true };
        case "engine_start_vc":
          return start.promise;
        default:
          return { state: "idle", worker_alive: true };
      }
    });
    const h = mountHook(() => useEngine());
    mounts.push(h);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    let runP!: Promise<void>;
    act(() => {
      runP = h.result.current.toggleRun();
    });
    // config_get 还没回来：意图已被认领，pending 必须当场为真。
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(h.result.current.userStartPending()).toBe(true);
    // 此刻第二次点击 = 取消这次启动，不是再来一次 start。
    let runP2!: Promise<void>;
    act(() => {
      runP2 = h.result.current.toggleRun();
    });
    await act(async () => {
      await runP2;
      await vi.advanceTimersByTimeAsync(0);
    });
    // 被取消的 op 落定成 idle；准备流程作废，engine_start_vc 不许发出。
    expect(tauri.calls.some((c) => c.cmd === "engine_start_vc")).toBe(false);
    cfg.resolve({ pth_path: "m/a.pth" });
    await act(async () => {
      await runP;
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(tauri.calls.some((c) => c.cmd === "engine_start_vc")).toBe(false);
    expect(h.result.current.userStartPending()).toBe(false);
    await expect(h.result.current.awaitUserStart()).resolves.toMatchObject({
      state: "idle",
    });
  });

  it("start 在途时第二次点击 = 停：等待者落定 idle，迟到的 start 结果不再结算", async () => {
    const start = deferred<unknown>();
    baseInvoke(start);
    const h = mountHook(() => useEngine());
    mounts.push(h);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    let runP!: Promise<void>;
    act(() => {
      runP = h.result.current.toggleRun();
    });
    await act(async () => {
      for (let i = 0; i < 30; i += 1) {
        if (tauri.calls.some((c) => c.cmd === "engine_start_vc")) return;
        await vi.advanceTimersByTimeAsync(5);
      }
    });
    let settled: { state?: string; error?: string } = {};
    void h.result.current.awaitUserStart().then((s) => {
      settled = s;
    });
    // 第二次点击：走停止分支，把在途启动的等待者落定成 idle。
    let stopP!: Promise<void>;
    act(() => {
      stopP = h.result.current.toggleRun();
    });
    await act(async () => {
      await stopP;
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(tauri.calls.some((c) => c.cmd === "engine_stop_vc")).toBe(true);
    expect(settled.state).toBe("idle");
    expect(h.result.current.userStartPending()).toBe(false);
    // 迟到的 start resolve 不许再结算一次（旧等待者不能复活）。
    await act(async () => {
      start.resolve({ state: "running" });
      await runP;
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(settled.state).toBe("idle");
  });

  it("已派发的 start 被取消：stop 没落定不许报 idle；stop 失败由 start 自己的结果结算", async () => {
    const start = deferred<unknown>();
    const stop = deferred<unknown>();
    baseInvoke(start, stop);
    const h = mountHook(() => useEngine());
    mounts.push(h);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    let runP!: Promise<void>;
    act(() => {
      runP = h.result.current.toggleRun();
    });
    await act(async () => {
      for (let i = 0; i < 30; i += 1) {
        if (tauri.calls.some((c) => c.cmd === "engine_start_vc")) return;
        await vi.advanceTimersByTimeAsync(5);
      }
    });
    let settled: { state?: string; error?: string } = {};
    void h.result.current.awaitUserStart().then((s) => {
      settled = s;
    });
    let stopP!: Promise<void>;
    act(() => {
      stopP = h.result.current.toggleRun();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(tauri.calls.some((c) => c.cmd === "engine_stop_vc")).toBe(true);
    // stop 还没回来：等待者不能先听到一句假的 idle。
    expect(settled.state).toBeUndefined();
    expect(h.result.current.userStartPending()).toBe(true);
    // stop 被拒：引擎状态不明，依然不许报 idle —— 结算权还在 start 手上。
    await act(async () => {
      stop.reject(new Error("stop refused"));
      await stopP;
    });
    expect(settled.state).toBeUndefined();
    expect(h.result.current.userStartPending()).toBe(true);
    // 在途 start 迟到的 resolve 才是这次启动的真实结局。
    await act(async () => {
      start.resolve({ state: "running" });
      await runP;
    });
    expect(settled.state).toBe("running");
    expect(h.result.current.userStartPending()).toBe(false);
  });

  it("取消 A 后又开 B：A 迟到的 resolve 不许盖 status、清 B 的标志位", async () => {
    const startA = deferred<unknown>();
    const startB = deferred<unknown>();
    let startCalls = 0;
    tauri.invoke.mockImplementation(async (cmd: string, args?: unknown) => {
      tauri.calls.push({ cmd, args });
      switch (cmd) {
        case "provision_status":
          return { runtime_ready: true };
        case "config_get":
          return { pth_path: "m/a.pth" };
        case "assets_status":
          return { engine_core_ready: true };
        case "engine_start_vc":
          startCalls += 1;
          return (startCalls === 1 ? startA : startB).promise;
        default:
          return { state: "idle", worker_alive: true };
      }
    });
    const h = mountHook(() => useEngine());
    mounts.push(h);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    // A 起 → 派发出去。
    act(() => {
      void h.result.current.toggleRun();
    });
    await act(async () => {
      for (let i = 0; i < 30; i += 1) {
        if (tauri.calls.some((c) => c.cmd === "engine_start_vc")) return;
        await vi.advanceTimersByTimeAsync(5);
      }
    });
    // 取消 A（stop 落定 idle），紧接着开 B。
    act(() => {
      void h.result.current.toggleRun();
    });
    await act(async () => {
      for (let i = 0; i < 30; i += 1) {
        if (tauri.calls.some((c) => c.cmd === "engine_stop_vc")) return;
        await vi.advanceTimersByTimeAsync(5);
      }
      await vi.advanceTimersByTimeAsync(0);
    });
    let runB!: Promise<void>;
    act(() => {
      runB = h.result.current.toggleRun();
    });
    await act(async () => {
      for (let i = 0; i < 30; i += 1) {
        if (tauri.calls.filter((c) => c.cmd === "engine_start_vc").length >= 2)
          return;
        await vi.advanceTimersByTimeAsync(5);
      }
    });
    expect(startCalls).toBe(2);
    expect(h.result.current.userStartPending()).toBe(true);
    // A 迟到 resolve running：是被取消那次的余响，不许写 status；
    // finally 也不许清掉 B 的 starting/busy。
    await act(async () => {
      startA.resolve({ state: "running" });
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(h.result.current.status.state).not.toBe("running");
    // B 还握着在途标志：A 的迟到 finally 不许清 busy/starting。
    expect(h.result.current.busy).toBe(true);
    expect(h.result.current.starting).toBe(true);
    expect(h.result.current.userStartPending()).toBe(true);
    // B 落定才是界面该显示的。
    await act(async () => {
      startB.resolve({ state: "running" });
      await runB;
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(h.result.current.status.state).toBe("running");
    expect(h.result.current.userStartPending()).toBe(false);
  });

  it("DSP 激活的 await 上被取消：startVc 不许再发出去", async () => {
    const act1 = deferred<unknown>();
    tauri.invoke.mockImplementation(async (cmd: string, args?: unknown) => {
      tauri.calls.push({ cmd, args });
      switch (cmd) {
        case "provision_status":
          return { runtime_ready: true };
        case "config_get":
          return { pth_path: "m/a.pth" };
        case "dsp_activate":
          return act1.promise;
        default:
          return { state: "idle", worker_alive: true };
      }
    });
    const h = mountHook(() => useEngine());
    mounts.push(h);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    let runP!: Promise<void>;
    act(() => {
      runP = h.result.current.toggleRun({ dspId: "preset-x" });
    });
    await act(async () => {
      for (let i = 0; i < 30; i += 1) {
        if (tauri.calls.some((c) => c.cmd === "dsp_activate")) return;
        await vi.advanceTimersByTimeAsync(5);
      }
    });
    expect(tauri.calls.some((c) => c.cmd === "dsp_activate")).toBe(true);
    // dsp_activate 还没回来就取消：op 落定 idle（还没派发 start）。
    let stopP!: Promise<void>;
    act(() => {
      stopP = h.result.current.toggleRun();
    });
    await act(async () => {
      await stopP;
      await vi.advanceTimersByTimeAsync(0);
    });
    // 激活随后才回来：派发前的再验必须拦住 startVc。
    await act(async () => {
      act1.resolve({});
      await runP;
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(tauri.calls.some((c) => c.cmd === "engine_start_vc")).toBe(false);
    expect(h.result.current.userStartPending()).toBe(false);
  });

  it("卸载时在途启动的等待者落定 idle，不成孤儿", async () => {
    const start = deferred<unknown>();
    baseInvoke(start);
    const h = mountHook(() => useEngine());
    // 故意不推进 mounts：这个用例自己管卸载时机。
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    act(() => {
      void h.result.current.toggleRun();
    });
    await act(async () => {
      for (let i = 0; i < 30; i += 1) {
        if (tauri.calls.some((c) => c.cmd === "engine_start_vc")) return;
        await vi.advanceTimersByTimeAsync(5);
      }
    });
    let settled: { state?: string } = {};
    void h.result.current.awaitUserStart().then((s) => {
      settled = s;
    });
    act(() => {
      h.unmount();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(settled.state).toBe("idle");
  });
});
