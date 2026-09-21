// @vitest-environment happy-dom
/**
 * B2 回归：音色选择的引擎侧应用判定。
 *
 * - 空闲 / 预热（不是用户在启动）时选音色绝不能碰音频流；
 * - 在跑的 RVC worker 走 swapModel，reject 如实透出；
 * - 纯 DSP worker 走 startVc —— 它返回 status 对象，`state:"error"` 的
 *   resolve 必须当失败（哪怕 status 里粘着旧 model_apply/model_active
 *   字段也不许当真成功）；
 * - 用户启动在途时选音色要等启动落定再热换最新目标，启动失败即失败。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const tauri = vi.hoisted(() => ({
  invoke: vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>(),
  calls: [] as { cmd: string; args?: unknown }[],
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: tauri.invoke }));

import { applyVoiceToEngine, vcApplyError, type VoiceApplyEngine } from "./voiceApply";
import type { EngineStatus } from "./engine";

function eng(partial: Partial<VoiceApplyEngine>): VoiceApplyEngine {
  return {
    running: false,
    status: {},
    userStartPending: () => false,
    awaitUserStart: () => Promise.resolve({}),
    ...partial,
  };
}

const invoked = (cmd: string) => tauri.calls.filter((c) => c.cmd === cmd);

describe("applyVoiceToEngine", () => {
  beforeEach(() => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    tauri.calls.length = 0;
    tauri.invoke.mockReset();
    tauri.invoke.mockImplementation(async (cmd: string) => {
      tauri.calls.push({ cmd });
      if (cmd === "engine_start_vc") return { state: "running" };
      if (cmd === "engine_swap_model") return 7;
      return {};
    });
  });

  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
  });

  it("引擎空闲：只是记选择，不碰音频流", async () => {
    await expect(applyVoiceToEngine(eng({}))).resolves.toBe("idle");
    expect(tauri.calls).toEqual([]);
  });

  it("预热/boot 的 starting 不算用户在启动：同样不碰音频流", async () => {
    const e = eng({
      status: { state: "starting", message_code: "engine.importing" },
    });
    await expect(applyVoiceToEngine(e)).resolves.toBe("idle");
    expect(invoked("engine_start_vc")).toEqual([]);
    expect(invoked("engine_swap_model")).toEqual([]);
  });

  it("在跑的 RVC worker：swapModel 的 resolve 即已应用", async () => {
    const e = eng({ running: true, status: { state: "running" } });
    await expect(applyVoiceToEngine(e)).resolves.toBe("applied");
    expect(invoked("engine_swap_model")).toHaveLength(1);
    expect(invoked("engine_start_vc")).toEqual([]);
  });

  it("swapModel 被 reject：错误如实透出", async () => {
    tauri.invoke.mockImplementation(async (cmd: string) => {
      tauri.calls.push({ cmd });
      if (cmd === "engine_swap_model") throw new Error("worker 换入失败");
      return {};
    });
    const e = eng({ running: true, status: { state: "running" } });
    await expect(applyVoiceToEngine(e)).rejects.toThrow("worker 换入失败");
  });

  it("DSP worker：startVc 回 state:error 即失败 —— 哪怕粘着旧的合约字段", async () => {
    // 回归点：旧逻辑看到 model_apply/model_active 字段在就当「已证实」。
    // status.json 是合并写的，上一次成功换模型的记录会粘在里面 ——
    // 字段在 ≠ 这次成功。
    tauri.invoke.mockImplementation(async (cmd: string) => {
      tauri.calls.push({ cmd });
      if (cmd === "engine_start_vc") {
        return {
          state: "error",
          error: "流没起来",
          model_apply: { seq: 3, pth_path: "a.pth", phase: "committed" },
          model_active: { pth_path: "a.pth" },
        };
      }
      return {};
    });
    const e = eng({
      running: true,
      status: { state: "running", dsp_only: true },
    });
    await expect(applyVoiceToEngine(e)).rejects.toThrow("流没起来");
  });

  it("DSP worker：startVc 回到 running 才算应用", async () => {
    const e = eng({
      running: true,
      status: { state: "running", worker_kind: "dsp" },
    });
    await expect(applyVoiceToEngine(e)).resolves.toBe("applied");
    expect(invoked("engine_start_vc")).toHaveLength(1);
  });

  it("DSP worker：startVc 回非 running 非 error 也是失败", async () => {
    tauri.invoke.mockImplementation(async (cmd: string) => {
      tauri.calls.push({ cmd });
      if (cmd === "engine_start_vc") return { state: "idle" };
      return {};
    });
    const e = eng({
      running: true,
      status: { state: "running", dsp_only: true },
    });
    await expect(applyVoiceToEngine(e)).rejects.toThrow();
  });

  it("用户启动在途时选音色：等启动落定再把最新选择热换进去", async () => {
    const e = eng({
      running: false,
      status: { state: "starting" },
      userStartPending: () => true,
      awaitUserStart: () => Promise.resolve({ state: "running" }),
    });
    await expect(applyVoiceToEngine(e)).resolves.toBe("applied");
    // 落定后是 RVC running → 补 swap，把最新选择顶进去（同目标时是合约内 no-op）
    expect(invoked("engine_swap_model")).toHaveLength(1);
    expect(invoked("engine_start_vc")).toEqual([]);
  });

  it("用户启动落定成纯 DSP：选音色要走 startVc 挂上模型", async () => {
    const e = eng({
      running: false,
      status: { state: "starting" },
      userStartPending: () => true,
      awaitUserStart: () =>
        Promise.resolve({ state: "running", dsp_only: true }),
    });
    await expect(applyVoiceToEngine(e)).resolves.toBe("applied");
    expect(invoked("engine_start_vc")).toHaveLength(1);
  });

  it("用户启动失败：选音色同样失败，不许去补 swap", async () => {
    const e = eng({
      running: false,
      status: { state: "starting" },
      userStartPending: () => true,
      awaitUserStart: () =>
        Promise.resolve({ state: "error", error: "引擎起不来" }),
    });
    await expect(applyVoiceToEngine(e)).rejects.toThrow("引擎起不来");
    expect(invoked("engine_swap_model")).toEqual([]);
    expect(invoked("engine_start_vc")).toEqual([]);
  });

  it("心跳已报 running 但用户启动还没落定：仍要等启动结果，不许直接 swap", async () => {
    // 运行中的心跳和未落定的启动是两回事 —— 启动没回来之前那份 running
    // 可能是旧 worker 的，按它放行 swap 会顶到错的目标上。
    let finish!: (st: EngineStatus) => void;
    const gate = new Promise<EngineStatus>((r) => {
      finish = r;
    });
    let waits = 0;
    const e = eng({
      running: true,
      status: { state: "running" },
      userStartPending: () => true,
      awaitUserStart: () => {
        waits += 1;
        return gate;
      },
    });
    const applied = applyVoiceToEngine(e);
    await Promise.resolve();
    expect(waits).toBe(1);
    expect(invoked("engine_swap_model")).toEqual([]);
    finish({ state: "running" });
    await expect(applied).resolves.toBe("applied");
    expect(invoked("engine_swap_model")).toHaveLength(1);
  });

  it("启动落定成 idle（落定前被取消/停掉）：退化成「只是记选择」", async () => {
    const e = eng({
      running: false,
      status: { state: "starting" },
      userStartPending: () => true,
      awaitUserStart: () => Promise.resolve({ state: "idle" }),
    });
    await expect(applyVoiceToEngine(e)).resolves.toBe("idle");
    // 引擎没在跑：不许碰音频流，也不是失败。
    expect(invoked("engine_swap_model")).toEqual([]);
    expect(invoked("engine_start_vc")).toEqual([]);
  });
});

describe("vcApplyError", () => {
  it("state:error 透出 error 文案", () => {
    const st: EngineStatus = { state: "error", error: "boom" };
    expect(vcApplyError(st)).toBe("boom");
  });

  it("非 running 非 error 也算失败（idle/stopping/starting）", () => {
    expect(vcApplyError({ state: "idle" })).toBeTruthy();
    expect(vcApplyError({})).toBeTruthy();
  });

  it("running 才算成功；status 里的旧字段不改变判定", () => {
    expect(
      vcApplyError({
        state: "running",
        model_apply: { phase: "failed", error: "old" },
      }),
    ).toBeNull();
  });
});
