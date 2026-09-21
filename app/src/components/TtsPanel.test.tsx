// @vitest-environment happy-dom
/**
 * STS 面板任务归属与生命周期回归（验收 F5/F6/G4/G6 + 第三轮）：
 *
 * - 打开面板时后端已在跑（静默 TTS/顾问任务或别窗任务）→ 只读观察，
 *   不给取消；轮询发现收尾后恢复可交互。
 * - 本窗发起的任务也要等后端回显凭证（status.run_owner / 事件 owner）
 *   才给取消；自封归属不作数，snapshot 在途期间 BUSY 可被别窗抢走。
 * - 旧轮询响应不得盖掉新忙态（代次守卫）；卸载后响应不落 state。
 * - 运行期晚到的扫描结果丢弃，不盖冻结清单视图；收尾后自动补扫。
 * - 失败∪未执行进重试（启动即败=整单；中途崩=成功条目排除），
 *   按冻结清单的精确身份，不重打 snapshot。
 */
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, tick, type Mounted } from "../test/dom";
import { t } from "../i18n/t";

const tauri = vi.hoisted(() => ({
  invoke: vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>(),
  handlers: new Map<string, (ev: { payload: unknown }) => void>(),
}));

const dialogs = vi.hoisted(() => ({
  askConfirm: vi.fn(async () => true),
  askPrompt: vi.fn(async () => null as string | null),
  pickPath: vi.fn(async () => null as string | null),
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: tauri.invoke,
  convertFileSrc: (p: string) => p,
}));
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn((name: string, cb: (ev: { payload: unknown }) => void) => {
    tauri.handlers.set(name, cb);
    return Promise.resolve(() => {
      tauri.handlers.delete(name);
    });
  }),
}));
vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => ({
    onFocusChanged: () => Promise.resolve(() => {}),
  }),
}));
vi.mock("../lib/voices", () => ({
  listVoices: vi.fn(async () => ({ models: [], selected_idx: -1 })),
}));
vi.mock("../lib/nativeDialog", () => ({ pickPath: dialogs.pickPath }));
vi.mock("../lib/webDialog", () => ({
  askConfirm: dialogs.askConfirm,
  askPrompt: dialogs.askPrompt,
}));
vi.mock("../lib/helpNav", () => ({ openHelpSection: vi.fn() }));
vi.mock("../lib/downloadModels", () => ({ openDownloadModels: vi.fn() }));

import { TtsPanel } from "./TtsPanel";

type IpcArgs = Record<string, unknown> | undefined;

function deferred<T = unknown>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function btn(m: Mounted, label: string): HTMLButtonElement | null {
  const all = [...m.container.querySelectorAll("button")];
  return (
    (all.find((b) => b.textContent?.trim() === label) as HTMLButtonElement) ??
    null
  );
}

function click(el: HTMLElement) {
  act(() => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

function emit(name: string, payload: unknown) {
  act(() => {
    tauri.handlers.get(name)?.({ payload });
  });
}

const SCAN_IDLE = { sources: [], items: [], pending: 0, excluded: 0 };

describe("TtsPanel STS 任务生命周期", () => {
  const mounts: Mounted[] = [];
  let status: Record<string, unknown>;
  let calls: { cmd: string; args?: unknown }[];
  let ipc: Record<string, (args?: IpcArgs) => unknown>;
  let scanGates: ReturnType<typeof deferred>[];

  beforeEach(() => {
    calls = [];
    scanGates = [];
    tauri.handlers.clear();
    tauri.invoke.mockReset();
    status = { busy: false };
    ipc = {
      sts_status: () => status,
      sts_sources_scan: () => SCAN_IDLE,
      sts_snapshot: () => ({ manifest: [], total: 0 }),
    };
    tauri.invoke.mockImplementation(async (cmd: string, args?: unknown) => {
      calls.push({ cmd, args });
      const h = ipc[cmd];
      return h ? h(args as IpcArgs) : {};
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    while (mounts.length) mounts.pop()?.unmount();
  });

  /** 让 sts_sources_scan 排队，由测试逐个放行。 */
  function queueScans() {
    ipc.sts_sources_scan = () => {
      const d = deferred();
      scanGates.push(d);
      return d.promise;
    };
  }

  it("打开时后端在跑静默任务：只读观察，无取消；轮询到收尾后恢复", async () => {
    vi.useFakeTimers();
    status = {
      busy: true,
      run_quiet: true,
      progress: { phase: "run", done: 1, total: 3, pct: 33 },
    };
    const m = mount(<TtsPanel />);
    mounts.push(m);
    await tick();
    // 观察态：来源操作禁用、外来提示在、取消键不出现。
    expect(btn(m, t("s.stsAddDir"))?.disabled).toBe(true);
    expect(btn(m, t("s.4d0b4688c7"))).toBeNull();
    expect(m.container.textContent).toContain(t("s.stsForeignBusy"));
    // 静默任务没有终态事件：轮询发现 busy 落下后收尾。
    status = { busy: false };
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await tick();
    await tick();
    expect(btn(m, t("s.stsAddDir"))?.disabled).toBe(false);
    expect(m.container.textContent).not.toContain(t("s.stsForeignBusy"));
  });

  it("外来非静默任务（事件先到）：同样只读无取消，轮询收尾", async () => {
    vi.useFakeTimers();
    const m = mount(<TtsPanel />);
    mounts.push(m);
    await tick();
    emit("sts-progress", { phase: "run", done: 0, total: 2, pct: 10 });
    await tick();
    expect(btn(m, t("s.4d0b4688c7"))).toBeNull();
    expect(m.container.textContent).toContain(t("s.stsForeignBusy"));
    status = {
      busy: true,
      run_quiet: false,
      progress: { phase: "run", done: 1, total: 2, pct: 50 },
    };
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(btn(m, t("s.4d0b4688c7"))).toBeNull();
    status = { busy: false };
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await tick();
    await tick();
    expect(m.container.textContent).not.toContain(t("s.stsForeignBusy"));
  });

  const READY = {
    busy: false,
    runtime_ready: true,
    engine_core_ready: true,
    worker_present: true,
    model_path: "D:/models/a.pth",
    model_name: "a",
  };

  function sentOwner(): string | undefined {
    const c = calls.find((x) => x.cmd === "sts_start");
    return (c?.args as { owner?: string } | undefined)?.owner;
  }

  it("本窗发起：后端回显凭证后才给取消；取消带凭证", async () => {
    vi.useFakeTimers();
    status = { ...READY };
    queueScans();
    const runGate = deferred();
    ipc.sts_snapshot = () => ({
      manifest: [{ src: "D:/in/a.wav", rel: "a.wav" }],
      total: 1,
      excluded: 0,
    });
    ipc.sts_start = () => runGate.promise;
    const m = mount(<TtsPanel />);
    mounts.push(m);
    await tick();
    scanGates[0].resolve({ ...SCAN_IDLE, pending: 1 });
    await tick();
    click(btn(m, t("s.stsWillProcess", { v0: 1 }))!);
    await tick();
    // 任务已发出但后端还没回显凭证：自封归属不算数，取消键仍不出现。
    const token = sentOwner();
    expect(token).toBeTruthy();
    expect(btn(m, t("s.4d0b4688c7"))).toBeNull();
    // 事件回显本窗凭证 → 取消键放行。
    emit("sts-progress", {
      phase: "run",
      done: 0,
      total: 1,
      pct: 5,
      owner: token,
    });
    await tick();
    const cancelBtn = btn(m, t("s.4d0b4688c7"));
    expect(cancelBtn).not.toBeNull();
    // 轮询在任务期间看到 busy 且无 run_owner：不得夺走已证明的归属。
    status = { busy: true, run_quiet: false };
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(btn(m, t("s.4d0b4688c7"))).not.toBeNull();
    click(cancelBtn!);
    await tick();
    const cancelCall = calls.find((c) => c.cmd === "sts_cancel");
    expect((cancelCall?.args as { owner?: string })?.owner).toBe(token);
    runGate.resolve({ files: [], skipped: [], output: "D:/out" });
    await tick();
    await tick();
  });

  it("snapshot 在途时别窗抢走任务：降级观察，取消键始终不出现", async () => {
    status = { ...READY };
    queueScans();
    const snapGate = deferred<unknown>();
    ipc.sts_snapshot = () => snapGate.promise;
    ipc.sts_start = () => Promise.reject(new Error("already running"));
    const m = mount(<TtsPanel />);
    mounts.push(m);
    await tick();
    scanGates[0].resolve({ ...SCAN_IDLE, pending: 1 });
    await tick();
    click(btn(m, t("s.stsWillProcess", { v0: 1 }))!);
    await tick();
    // 快照还在等：别窗任务的事件带着它的凭证先到 → 本窗自封归属被清。
    emit("sts-progress", {
      phase: "run",
      done: 0,
      total: 2,
      pct: 5,
      owner: "other-window-token",
    });
    await tick();
    expect(btn(m, t("s.4d0b4688c7"))).toBeNull();
    // 后端按权威拒绝重复启动，且此刻后端仍被别窗占着（权威状态是
    // sts_status：busy + 别人的凭证）。finally 不得把控件放可编辑——
    // 保持外来观察态直到别窗任务收尾。
    status = {
      busy: true,
      run_quiet: false,
      run_owner: "other-window-token",
      progress: { phase: "run", done: 1, total: 2, pct: 50 },
    };
    snapGate.resolve({
      manifest: [{ src: "D:/in/a.wav", rel: "a.wav" }],
      total: 1,
    });
    await tick();
    await tick();
    expect(btn(m, t("s.4d0b4688c7"))).toBeNull();
    expect(calls.some((c) => c.cmd === "sts_cancel")).toBe(false);
    // 外来任务仍在跑：来源/输出控件一律保持锁定。
    expect(btn(m, t("s.stsAddDir"))?.disabled).toBe(true);
    expect(m.container.textContent).toContain(t("s.stsForeignBusy"));
  });

  it("旧轮询响应不得盖掉新忙态（代次守卫）", async () => {
    vi.useFakeTimers();
    const m = mount(<TtsPanel />);
    mounts.push(m);
    await tick();
    // 让下一轮轮询挂在半空。
    const statusGate = deferred<unknown>();
    ipc.sts_status = () => statusGate.promise;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    // 事件先到：外来任务开跑，代次+1，进入观察态。
    emit("sts-progress", { phase: "run", done: 0, total: 2, pct: 5 });
    await tick();
    expect(m.container.textContent).toContain(t("s.stsForeignBusy"));
    // 旧 idle 响应落地：代次已变，必须作废，不许把忙态清回 idle。
    statusGate.resolve({ busy: false });
    await tick();
    await tick();
    expect(m.container.textContent).toContain(t("s.stsForeignBusy"));
    expect(btn(m, t("s.stsAddDir"))?.disabled).toBe(true);
  });

  it("运行期晚到的扫描结果丢弃；收尾后自动补扫", async () => {
    status = { ...READY };
    queueScans();
    const runGate = deferred();
    ipc.sts_snapshot = () => ({
      manifest: [{ src: "D:/in/a.wav", rel: "a.wav" }],
      total: 1,
    });
    ipc.sts_start = () => runGate.promise;
    const m = mount(<TtsPanel />);
    mounts.push(m);
    await tick();
    scanGates[0].resolve({ ...SCAN_IDLE, pending: 1 });
    await tick();
    // 手动刷新 → 第二代扫描在途。
    click(btn(m, t("s.stsRefresh"))!);
    await tick();
    expect(scanGates.length).toBe(2);
    click(btn(m, t("s.stsWillProcess", { v0: 1 }))!);
    await tick();
    // 输出目录选择在运行期锁定（G4）。
    const outBtn = btn(m, t("s.70b208202c"));
    expect(outBtn?.disabled).toBe(true);
    // 在途扫描运行期返回：结果丢弃，不改写运行态视图。
    scanGates[1].resolve({
      sources: [
        { id: "s1", kind: "dir", path: "D:/in", recursive: true, short: "in" },
      ],
      items: [],
      pending: 0,
      excluded: 0,
    });
    await tick();
    expect(m.container.querySelectorAll("ul li").length).toBe(0);
    expect(outBtn?.disabled).toBe(true);
    // 收尾：finally 自动补扫，新的清单落地。
    runGate.resolve({ files: ["D:/out/a.wav"], skipped: [], output: "D:/out" });
    await tick();
    await tick();
    expect(scanGates.length).toBe(3);
    scanGates[2].resolve({
      sources: [
        { id: "s1", kind: "dir", path: "D:/in", recursive: true, short: "in" },
      ],
      items: [],
      pending: 0,
      excluded: 0,
    });
    await tick();
    expect(m.container.querySelectorAll("ul li").length).toBeGreaterThan(0);
  });

  it("整批失败：重试带失败∪未执行的冻结身份，不重打 snapshot", async () => {
    status = { ...READY };
    const runGate = deferred();
    let startN = 0;
    ipc.sts_sources_scan = () => ({
      ...SCAN_IDLE,
      pending: 2,
      items: [
        { name: "a.wav", rel: "a.wav", path: "D:/in/a.wav", size: 1, mtime: 1 },
        { name: "b.wav", rel: "b.wav", path: "D:/in/b.wav", size: 1, mtime: 1 },
      ],
    });
    ipc.sts_snapshot = () => ({
      manifest: [
        { src: "D:/in/a.wav", rel: "a.wav" },
        { src: "D:/in/b.wav", rel: "b.wav" },
      ],
      total: 2,
    });
    ipc.sts_start = () =>
      ++startN === 1
        ? runGate.promise
        : Promise.resolve({
            files: ["D:/out/a.wav"],
            skipped: [],
            output: "D:/out",
          });
    const m = mount(<TtsPanel />);
    mounts.push(m);
    await tick();
    click(btn(m, t("s.stsWillProcess", { v0: 2 }))!);
    await tick();
    // 运行中来一条带全路径的 skip 事件（a.wav 快照后消失）。
    // 真实后端事件必带 owner 回显；不带凭证的事件不进本窗账本。
    emit("sts-progress", {
      phase: "skip",
      file: "a.wav",
      path: "D:/in/a.wav",
      reason: "source missing",
      owner: sentOwner(),
    });
    await tick();
    runGate.reject(new Error("all failed"));
    await tick();
    await tick();
    // 没有一条 done 事件：a 是失败、b 是未执行 → 重试集合是两条。
    const retryBtn = btn(m, t("s.stsRetryFailed", { v0: 2 }));
    expect(retryBtn).not.toBeNull();
    click(retryBtn!);
    await tick();
    await tick();
    const starts = calls.filter((c) => c.cmd === "sts_start");
    expect(starts).toHaveLength(2);
    expect(
      (starts[1].args as { manifest?: { src: string }[] }).manifest,
    ).toEqual([
      { src: "D:/in/a.wav", rel: "a.wav" },
      { src: "D:/in/b.wav", rel: "b.wav" },
    ]);
    expect(calls.filter((c) => c.cmd === "sts_snapshot")).toHaveLength(1);
  });

  it("启动即败（一条事件都没来）：整单进重试集合", async () => {
    status = { ...READY };
    ipc.sts_sources_scan = () => ({ ...SCAN_IDLE, pending: 3 });
    ipc.sts_snapshot = () => ({
      manifest: ["a", "b", "c"].map((n) => ({
        src: `D:/in/${n}.wav`,
        rel: `${n}.wav`,
      })),
      total: 3,
      excluded: 1,
    });
    ipc.sts_start = () => Promise.reject(new Error("worker spawn failed"));
    const m = mount(<TtsPanel />);
    mounts.push(m);
    await tick();
    click(btn(m, t("s.stsWillProcess", { v0: 3 }))!);
    await tick();
    await tick();
    // 0 条已处理、0 条失败记录 → 三条全算未执行。
    const retryBtn = btn(m, t("s.stsRetryFailed", { v0: 3 }));
    expect(retryBtn).not.toBeNull();
    click(retryBtn!);
    await tick();
    const starts = calls.filter((c) => c.cmd === "sts_start");
    expect(starts).toHaveLength(2);
    expect(
      (starts[1].args as { manifest?: { src: string }[] }).manifest?.length,
    ).toBe(3);
    expect(calls.filter((c) => c.cmd === "sts_snapshot")).toHaveLength(1);
  });

  it("中途崩溃：已成功的排除，失败∪未执行进重试", async () => {
    status = { ...READY };
    ipc.sts_sources_scan = () => ({ ...SCAN_IDLE, pending: 3 });
    ipc.sts_snapshot = () => ({
      manifest: ["a", "b", "c"].map((n) => ({
        src: `D:/in/${n}.wav`,
        rel: `${n}.wav`,
      })),
      total: 3,
    });
    const runGate = deferred();
    ipc.sts_start = () => runGate.promise;
    const m = mount(<TtsPanel />);
    mounts.push(m);
    await tick();
    click(btn(m, t("s.stsWillProcess", { v0: 3 }))!);
    await tick();
    const token = sentOwner();
    // a.wav 已处理完（done=1），b.wav 被跳过，然后任务整体挂掉——
    // c.wav 从未被处理。重试 = {b} ∪ {c}，a 不重跑。
    emit("sts-progress", { phase: "run", done: 1, total: 3, pct: 33, owner: token });
    emit("sts-progress", {
      phase: "skip",
      file: "b.wav",
      path: "D:/in/b.wav",
      reason: "corrupt",
      owner: token,
    });
    await tick();
    runGate.reject(new Error("crash mid-batch"));
    await tick();
    await tick();
    const retryBtn = btn(m, t("s.stsRetryFailed", { v0: 2 }));
    expect(retryBtn).not.toBeNull();
    click(retryBtn!);
    await tick();
    const starts = calls.filter((c) => c.cmd === "sts_start");
    expect(starts).toHaveLength(2);
    expect(
      (starts[1].args as { manifest?: { src: string }[] }).manifest,
    ).toEqual([
      { src: "D:/in/b.wav", rel: "b.wav" },
      { src: "D:/in/c.wav", rel: "c.wav" },
    ]);
  });

  it("外来任务的进度/跳过事件不进本窗账本：跳过清单与重试集合隔离", async () => {
    vi.useFakeTimers();
    status = { ...READY };
    ipc.sts_sources_scan = () => ({ ...SCAN_IDLE, pending: 2 });
    ipc.sts_snapshot = () => ({
      manifest: ["a", "b"].map((n) => ({
        src: `D:/in/${n}.wav`,
        rel: `${n}.wav`,
      })),
      total: 2,
    });
    const runGate = deferred();
    ipc.sts_start = () => runGate.promise;
    const m = mount(<TtsPanel />);
    mounts.push(m);
    await tick();
    // 先出现一条外来任务的事件（别窗在跑）：skip/done 都不许进账本。
    emit("sts-progress", {
      phase: "skip",
      file: "x.wav",
      path: "D:/foreign/x.wav",
      reason: "corrupt",
      owner: "foreign-token",
    });
    emit("sts-progress", {
      phase: "run",
      done: 7,
      total: 9,
      pct: 77,
      owner: "foreign-token",
    });
    await tick();
    // 跳过清单不含外来条目。
    expect(m.container.textContent).not.toContain("x.wav");
    // 别窗任务收尾，轮询解除观察态。
    status = { busy: false };
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await tick();
    await tick();
    // 本窗发起自己的单：a 完成、后端报 b 失败终态。
    click(btn(m, t("s.stsWillProcess", { v0: 2 }))!);
    await tick();
    const token = sentOwner();
    emit("sts-progress", { phase: "run", done: 1, total: 2, pct: 50, owner: token });
    await tick();
    runGate.resolve({
      files: ["D:/out/a.wav"],
      skipped: [{ file: "D:/in/b.wav", name: "b.wav", reason: "bad" }],
      output: "D:/out",
    });
    await tick();
    await tick();
    // 重试集合只含本单的 b：外来 done=7 / x.wav 一律不算数。
    const retryBtn = btn(m, t("s.stsRetryFailed", { v0: 1 }));
    expect(retryBtn).not.toBeNull();
    expect(m.container.textContent).not.toContain("x.wav");
    click(retryBtn!);
    await tick();
    const starts = calls.filter((c) => c.cmd === "sts_start");
    expect(
      (starts[1].args as { manifest?: { src: string }[] }).manifest,
    ).toEqual([{ src: "D:/in/b.wav", rel: "b.wav" }]);
  });

  it("本单收尾后迟到的旧凭证事件：不进账本、不被误认归属", async () => {
    vi.useFakeTimers();
    status = { ...READY };
    ipc.sts_sources_scan = () => ({ ...SCAN_IDLE, pending: 1 });
    ipc.sts_snapshot = () => ({
      manifest: [{ src: "D:/in/a.wav", rel: "a.wav" }],
      total: 1,
    });
    const runGate = deferred();
    ipc.sts_start = () => runGate.promise;
    const m = mount(<TtsPanel />);
    mounts.push(m);
    await tick();
    click(btn(m, t("s.stsWillProcess", { v0: 1 }))!);
    await tick();
    const token = sentOwner();
    runGate.resolve({
      files: [],
      skipped: [{ file: "D:/in/a.wav", name: "a.wav", reason: "bad" }],
      output: "D:/out",
    });
    await tick();
    await tick();
    // 终态已落定：重试集合 = {a}。
    expect(btn(m, t("s.stsRetryFailed", { v0: 1 }))).not.toBeNull();
    // 迟到的本单旧事件（done/skip）：凭证已作废 → 一律按外来处理，
    // 不改已落定的账本。
    emit("sts-progress", {
      phase: "skip",
      file: "ghost.wav",
      path: "D:/in/ghost.wav",
      reason: "late",
      owner: token,
    });
    await tick();
    expect(m.container.textContent).not.toContain("ghost.wav");
    // 迟到事件把界面短暂带进了观察态——轮询发现空闲后恢复可编辑。
    status = { busy: false };
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await tick();
    await tick();
    expect(btn(m, t("s.stsAddDir"))?.disabled).toBe(false);
    expect(btn(m, t("s.stsRetryFailed", { v0: 1 }))).not.toBeNull();
  });

  it("卸载后轮询停止，不再调 sts_status", async () => {
    vi.useFakeTimers();
    const m = mount(<TtsPanel />);
    mounts.push(m);
    await tick();
    const before = calls.filter((c) => c.cmd === "sts_status").length;
    m.unmount();
    mounts.pop();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(calls.filter((c) => c.cmd === "sts_status")).toHaveLength(before);
  });
});
