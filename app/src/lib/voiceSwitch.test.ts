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

  it("A→B→A：最后一次点击回到在途目标，排队的 B 被顶掉", async () => {
    const vs = await freshModule();
    const gateA = deferred();
    mockInvoke((cmd, args) => {
      if (cmd !== "voices_select") return Promise.resolve(0);
      const path = String((args as { path?: string }).path || "");
      return path.endsWith("a.pth")
        ? gateA.promise
        : Promise.resolve({ ok: true });
    });
    const applyA = vi.fn();
    const applyB = vi.fn();
    const applyA2 = vi.fn();
    const pA = vs.requestVoiceSwitch(voice("p/a.pth", "A"), applyA);
    // A 在途时 B 成为排队目标。
    const pB = vs.requestVoiceSwitch(voice("p/b.pth", "B"), applyB);
    // 用户最后一次点击回到 A —— 最新意图是 A，不是 B。
    const pA2 = vs.requestVoiceSwitch(voice("p/a.pth", "A"), applyA2);
    // pending 必须反映最新意图：A。
    expect(vs.voiceSwitchPendingKey()).toBe("p/a.pth");
    gateA.resolve({ ok: true, model: voice("p/a.pth", "A") });
    const [oA, oB, oA2] = await Promise.all([pA, pB, pA2]);
    expect(oA.kind).toBe("done");
    expect(oB.kind).toBe("superseded");
    expect(oA2.kind).toBe("done");
    // B 从未提交，也从未应用。
    const selects = tauri.calls
      .filter((c) => c.cmd === "voices_select")
      .map((c) => String((c.args as { path?: string }).path));
    expect(selects).toEqual(["p/a.pth"]);
    expect(applyB).not.toHaveBeenCalled();
    expect(applyA).toHaveBeenCalledTimes(1);
  });

  it("排队中的目标被再点：共享同一排队任务，不重复提交", async () => {
    const vs = await freshModule();
    const gateA = deferred();
    mockInvoke((cmd, args) => {
      if (cmd !== "voices_select") return Promise.resolve(0);
      const path = String((args as { path?: string }).path || "");
      return path.endsWith("a.pth")
        ? gateA.promise
        : Promise.resolve({ ok: true });
    });
    const applyB = vi.fn();
    const pA = vs.requestVoiceSwitch(voice("p/a.pth", "A"), vi.fn());
    const pB1 = vs.requestVoiceSwitch(voice("p/b.pth", "B"), applyB);
    const pB2 = vs.requestVoiceSwitch(voice("p/b.pth", "B"), vi.fn());
    gateA.resolve({ ok: true });
    const [oA, oB1, oB2] = await Promise.all([pA, pB1, pB2]);
    expect(oA.kind).toBe("superseded");
    expect(oB1.kind).toBe("done");
    expect(oB2.kind).toBe("done");
    const selects = tauri.calls
      .filter((c) => c.cmd === "voices_select")
      .map((c) => String((c.args as { path?: string }).path));
    expect(selects).toEqual(["p/a.pth", "p/b.pth"]);
    expect(applyB).toHaveBeenCalledTimes(1);
  });

  it("apply 在途（引擎换模型未落定）时新意图到达：按 superseded 结算，最新目标继续执行", async () => {
    const vs = await freshModule();
    mockInvoke((cmd) => {
      if (cmd !== "voices_select") return Promise.resolve(0);
      return Promise.resolve({ ok: true });
    });
    const gateApply = deferred<void>();
    const applyA = vi.fn(() => gateApply.promise);
    const applyB = vi.fn();
    const pA = vs.requestVoiceSwitch(voice("p/a.pth", "A"), applyA);
    // select/setHot 都已放行：apply 已被调用但还没返回 —— 换模型正在后台加载。
    for (let i = 0; i < 20 && !applyA.mock.calls.length; i++) {
      await Promise.resolve();
    }
    expect(applyA).toHaveBeenCalledTimes(1);
    // 用户此刻改选 B：A 的应用结果已经不是最新意图。
    const pB = vs.requestVoiceSwitch(voice("p/b.pth", "B"), applyB);
    expect(vs.voiceSwitchPendingKey()).toBe("p/b.pth");
    gateApply.resolve(undefined);
    const [oA, oB] = await Promise.all([pA, pB]);
    expect(oA.kind).toBe("superseded");
    expect(oB.kind).toBe("done");
    expect(applyB).toHaveBeenCalledTimes(1);
  });

  it("apply 在途中的 A→B→A：回到在途目标顶掉排队的 B，B 永不执行", async () => {
    const vs = await freshModule();
    mockInvoke((cmd) =>
      cmd === "voices_select"
        ? Promise.resolve({ ok: true })
        : Promise.resolve(0),
    );
    const gateApply = deferred<void>();
    const applyA = vi.fn(() => gateApply.promise);
    const applyB = vi.fn();
    const pA = vs.requestVoiceSwitch(voice("p/a.pth", "A"), applyA);
    // A 的 select/setHot 已放行，引擎换模型还在路上。
    for (let i = 0; i < 20 && !applyA.mock.calls.length; i++) {
      await Promise.resolve();
    }
    expect(applyA).toHaveBeenCalledTimes(1);
    // 用户先点了 B（排队），又点回 A —— 最新意图就是 A 本身。
    const pB = vs.requestVoiceSwitch(voice("p/b.pth", "B"), applyB);
    const pA2 = vs.requestVoiceSwitch(voice("p/a.pth", "A"), vi.fn());
    expect(vs.voiceSwitchPendingKey()).toBe("p/a.pth");
    gateApply.resolve(undefined);
    const [oA, oB, oA2] = await Promise.all([pA, pB, pA2]);
    expect(oA.kind).toBe("done");
    expect(oB.kind).toBe("superseded");
    expect(oA2.kind).toBe("done");
    // B 从未提交 select，也从未应用；A 只切了一次。
    const selects = tauri.calls
      .filter((c) => c.cmd === "voices_select")
      .map((c) => String((c.args as { path?: string }).path));
    expect(selects).toEqual(["p/a.pth"]);
    expect(applyB).not.toHaveBeenCalled();
    expect(applyA).toHaveBeenCalledTimes(1);
  });

  it("apply（引擎换模型）拒绝：按 error 结算，真实错误透传给调用方", async () => {
    const vs = await freshModule();
    mockInvoke((cmd) =>
      cmd === "voices_select"
        ? Promise.resolve({ ok: true })
        : Promise.resolve(0),
    );
    const out = await vs.requestVoiceSwitch(voice("p/a.pth", "A"), () =>
      Promise.reject(new Error("换模型超时")),
    );
    expect(out.kind).toBe("error");
    if (out.kind === "error") expect(out.error).toContain("换模型超时");
    expect(vs.voiceSwitchPendingKey()).toBe("");
  });

  it("热参数下发失败：不得吞成成功，按 error 结算且不 apply", async () => {
    const vs = await freshModule();
    mockInvoke((cmd) => {
      if (cmd === "voices_select") return Promise.resolve({ ok: true });
      if (cmd === "engine_set_hot") {
        return Promise.reject(new Error("worker lost"));
      }
      return Promise.resolve(0);
    });
    const apply = vi.fn();
    const out = await vs.requestVoiceSwitch(voice("p/a.pth", "A"), apply);
    expect(out.kind).toBe("error");
    expect(apply).not.toHaveBeenCalled();
  });

  it("apply 在途期间同目标再点：共享这次在途应用，不重复 select", async () => {
    const vs = await freshModule();
    mockInvoke((cmd) =>
      cmd === "voices_select"
        ? Promise.resolve({ ok: true })
        : Promise.resolve(0),
    );
    const gateApply = deferred<void>();
    const applyA = vi.fn(() => gateApply.promise);
    const applyA2 = vi.fn();
    const pA = vs.requestVoiceSwitch(voice("p/a.pth", "A"), applyA);
    for (let i = 0; i < 20 && !applyA.mock.calls.length; i++) {
      await Promise.resolve();
    }
    expect(applyA).toHaveBeenCalledTimes(1);
    const pA2 = vs.requestVoiceSwitch(voice("p/a.pth", "A"), applyA2);
    gateApply.resolve(undefined);
    const [oA, oA2] = await Promise.all([pA, pA2]);
    expect(oA.kind).toBe("done");
    expect(oA2.kind).toBe("done");
    const selects = tauri.calls.filter((c) => c.cmd === "voices_select");
    expect(selects).toHaveLength(1);
    expect(applyA).toHaveBeenCalledTimes(1);
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
