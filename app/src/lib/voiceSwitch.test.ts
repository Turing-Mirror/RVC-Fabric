// @vitest-environment happy-dom
/**
 * N03/B-05 回归：音色切换派发器。
 *
 * - 点下即 pending（不等后端回话）；
 * - 同一目标重复点击只提交一次；
 * - 快速点不同目标只保留最新意图，被顶掉的按 superseded 结算；
 * - 旧任务的完成不得覆盖更新选择（不 apply）；
 * - 失败如实报错，pending 清空，可重试。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const tauri = vi.hoisted(() => ({
  invoke: vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>(),
  calls: [] as { cmd: string; args?: unknown }[],
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: tauri.invoke }));

type SwitchMod = typeof import("./voiceSwitch");

function deferred<T = unknown>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const mockInvoke = (fn: (cmd: string, args?: unknown) => Promise<unknown>) =>
  tauri.invoke.mockImplementation(async (cmd: string, args?: unknown) => {
    tauri.calls.push({ cmd, args });
    return fn(cmd, args);
  });

const voice = (path: string, name: string) =>
  ({ path, dir: "", name, file: `${name}.pth` }) as Parameters<
    SwitchMod["requestVoiceSwitch"]
  >[0];

async function freshModule(): Promise<SwitchMod> {
  vi.resetModules();
  return import("./voiceSwitch");
}

describe("voiceSwitch 派发器", () => {
  beforeEach(() => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    tauri.calls.length = 0;
    tauri.invoke.mockReset();
  });

  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
  });

  it("点下即 pending，不等后端回话", async () => {
    const vs = await freshModule();
    const gate = deferred();
    mockInvoke((cmd) =>
      cmd === "voices_select" ? gate.promise : Promise.resolve(0),
    );
    const apply = vi.fn();
    const p = vs.requestVoiceSwitch(voice("p/a.pth", "A"), apply);
    // 同步可见：反馈先于一切异步完成。
    expect(vs.voiceSwitchPendingKey()).toBe("p/a.pth");
    gate.resolve({ ok: true, model: voice("p/a.pth", "A") });
    await p;
    expect(vs.voiceSwitchPendingKey()).toBe("");
  });

  it("同一目标在切换中再点：只提交一次，两处调用都结算", async () => {
    const vs = await freshModule();
    const gate = deferred();
    mockInvoke((cmd) =>
      cmd === "voices_select" ? gate.promise : Promise.resolve(0),
    );
    const apply = vi.fn();
    const p1 = vs.requestVoiceSwitch(voice("p/a.pth", "A"), apply);
    const p2 = vs.requestVoiceSwitch(voice("p/a.pth", "A"), apply);
    gate.resolve({ ok: true });
    const [o1, o2] = await Promise.all([p1, p2]);
    expect(tauri.calls.filter((c) => c.cmd === "voices_select")).toHaveLength(1);
    expect(o1.kind).toBe("done");
    expect(o2.kind).toBe("done");
    expect(apply).toHaveBeenCalledTimes(1);
  });

  it("快速点不同目标：最新意图胜出，旧结果不回写", async () => {
    const vs = await freshModule();
    const gateA = deferred();
    mockInvoke((cmd, args) => {
      if (cmd !== "voices_select") return Promise.resolve(0);
      const path = String((args as { path?: string }).path || "");
      return path.endsWith("a.pth") ? gateA.promise : Promise.resolve({ ok: true });
    });
    const applyA = vi.fn();
    const applyB = vi.fn();
    const pA = vs.requestVoiceSwitch(voice("p/a.pth", "A"), applyA);
    // A 还在途，B 到达：B 是有效目标。
    const pB = vs.requestVoiceSwitch(voice("p/b.pth", "B"), applyB);
    expect(vs.voiceSwitchPendingKey()).toBe("p/b.pth");
    gateA.resolve({ ok: true });
    const [oA, oB] = await Promise.all([pA, pB]);
    expect(oA.kind).toBe("superseded");
    expect(oB.kind).toBe("done");
    expect(applyA).not.toHaveBeenCalled();
    expect(applyB).toHaveBeenCalledTimes(1);
  });

  it("排队中的旧意图被更新的点击直接顶掉，不再执行", async () => {
    const vs = await freshModule();
    const gateA = deferred();
    mockInvoke((cmd, args) => {
      if (cmd !== "voices_select") return Promise.resolve(0);
      const path = String((args as { path?: string }).path || "");
      return path.endsWith("a.pth") ? gateA.promise : Promise.resolve({ ok: true });
    });
    const pA = vs.requestVoiceSwitch(voice("p/a.pth", "A"), vi.fn());
    const pB = vs.requestVoiceSwitch(voice("p/b.pth", "B"), vi.fn());
    // B 还没轮到就被 C 顶掉：B 永不执行。
    const pC = vs.requestVoiceSwitch(voice("p/c.pth", "C"), vi.fn());
    gateA.resolve({ ok: true });
    const [oA, oB, oC] = await Promise.all([pA, pB, pC]);
    const selects = tauri.calls
      .filter((c) => c.cmd === "voices_select")
      .map((c) => String((c.args as { path?: string }).path));
    expect(selects).toEqual(["p/a.pth", "p/c.pth"]);
    expect(oA.kind).toBe("superseded");
    expect(oB.kind).toBe("superseded");
    expect(oC.kind).toBe("done");
  });

  it("后端失败：如实报错，pending 清空，可重试", async () => {
    const vs = await freshModule();
    mockInvoke((cmd) =>
      cmd === "voices_select"
        ? Promise.reject(new Error("音色文件缺失"))
        : Promise.resolve(0),
    );
    const apply = vi.fn();
    const out = await vs.requestVoiceSwitch(voice("p/a.pth", "A"), apply);
    expect(out.kind).toBe("error");
    expect(apply).not.toHaveBeenCalled();
    expect(vs.voiceSwitchPendingKey()).toBe("");
    // 失败后能再点 —— 不卡在 pending。
    mockInvoke((cmd) =>
      cmd === "voices_select" ? Promise.resolve({ ok: true }) : Promise.resolve(0),
    );
    const retry = await vs.requestVoiceSwitch(voice("p/a.pth", "A"), apply);
    expect(retry.kind).toBe("done");
    expect(apply).toHaveBeenCalledTimes(1);
  });
});
