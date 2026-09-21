// @vitest-environment happy-dom
/**
 * 「使用中」徽标对账（B5）回归。
 *
 * - model_active 变化触发查目录；迟到的旧结果不得覆盖更新的状态
 *   （A/B 交替、慢的 A 先回也不行）；
 * - 同名文件在不同目录只能靠精确 path/modelKey 匹配，不能撞名；
 * - 字段缺席（旧 worker）不动显示；明确 null 才清空。
 */
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, tick, type Mounted } from "../test/dom";
import type { EngineStatus } from "../lib/engine";
import { invalidateVoicesCache } from "../lib/voices";
import {
  useActiveVoiceReconcile,
  type ActiveVoiceLabel,
} from "./useActiveVoice";

const tauri = vi.hoisted(() => ({
  invoke: vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>(),
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: tauri.invoke }));

function deferred<T = unknown>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const mounts: Mounted[] = [];
beforeEach(() => {
  // voices_list 有模块级缓存与在途共享：每个用例从零开始，不然上一个
  // 用例的目录会漏进这一个。
  tauri.invoke.mockReset();
  invalidateVoicesCache();
});
afterEach(() => {
  while (mounts.length) mounts.pop()?.unmount();
  invalidateVoicesCache();
  delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
});

function makeProbe(calls: ActiveVoiceLabel[]) {
  // 同一个组件类型：换 status 是 props 变化不是重挂载 —— hook 实例延续，
  // generation 守卫才有得守。
  return function Probe({
    status,
    running = true,
  }: {
    status: EngineStatus;
    running?: boolean;
  }) {
    useActiveVoiceReconcile(running, status, (v) => calls.push(v));
    return null;
  };
}

const st = (pth: string | null | undefined): EngineStatus => ({
  state: "running",
  model_active:
    pth === undefined ? undefined : pth === null ? null : { pth_path: pth },
});

describe("useActiveVoiceReconcile", () => {
  it("迟到的 A 目录结果不能覆盖更新的 B 状态", async () => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    const a = deferred<unknown>();
    const b = deferred<unknown>();
    let n = 0;
    tauri.invoke.mockImplementation((cmd: string) => {
      if (cmd !== "voices_list") return Promise.resolve({});
      n += 1;
      return n === 1 ? a.promise : b.promise;
    });
    const calls: ActiveVoiceLabel[] = [];
    const Probe = makeProbe(calls);
    const m = mount(<Probe status={st("m/a.pth")} />);
    mounts.push(m);
    await tick();
    expect(tauri.invoke).toHaveBeenCalledTimes(1);
    // B 的 active 进来：作废目录缓存让 B 发起独立的一次查询 ——
    // 这样 A、B 两次请求能真正倒序落定。
    invalidateVoicesCache();
    act(() => {
      m.root.render(<Probe status={st("m/b.pth")} />);
    });
    await tick();
    expect(tauri.invoke).toHaveBeenCalledTimes(2);
    // B 的目录先回，A 的更慢：慢的那次不许赢。
    await act(async () => {
      b.resolve({
        models: [{ name: "乙", path: "m/b.pth", file: "b.pth", dir: "m" }],
      });
    });
    await tick();
    await act(async () => {
      a.resolve({
        models: [{ name: "甲", path: "m/a.pth", file: "a.pth", dir: "m" }],
      });
    });
    await tick();
    expect(calls).toHaveLength(1);
    expect(calls[0].name).toBe("乙");
    expect(calls[0].id).toBe("m/b.pth");
  });

  it("同名 .pth 在不同目录：只按精确 path 命中，目录没有就退文件名", async () => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    tauri.invoke.mockImplementation((cmd: string) => {
      if (cmd === "voices_list") {
        return Promise.resolve({
          models: [
            { name: "一号", path: "d1/voice.pth", file: "voice.pth", dir: "d1" },
            { name: "二号", path: "d2/voice.pth", file: "voice.pth", dir: "d2" },
          ],
        });
      }
      return Promise.resolve({});
    });
    const calls: ActiveVoiceLabel[] = [];
    const Probe = makeProbe(calls);
    const m = mount(<Probe status={st("d2/voice.pth")} />);
    mounts.push(m);
    await tick();
    await tick();
    expect(calls).toHaveLength(1);
    expect(calls[0].name).toBe("二号");
    expect(calls[0].id).toBe("d2/voice.pth");
  });

  it("active 是目录外的文件：不许拿同名文件冒充", async () => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    tauri.invoke.mockImplementation((cmd: string) => {
      if (cmd === "voices_list") {
        return Promise.resolve({
          models: [
            { name: "库里同名", path: "lib/voice.pth", file: "voice.pth", dir: "lib" },
          ],
        });
      }
      return Promise.resolve({});
    });
    const calls: ActiveVoiceLabel[] = [];
    const Probe = makeProbe(calls);
    const m = mount(<Probe status={st("other/voice.pth")} />);
    mounts.push(m);
    await tick();
    await tick();
    expect(calls).toHaveLength(1);
    expect(calls[0].id).toBe("other/voice.pth");
    expect(calls[0].name).toBe("voice");
  });

  it("字段缺席（旧 worker）：不发查询也不动显示", async () => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    const calls: ActiveVoiceLabel[] = [];
    function Probe() {
      useActiveVoiceReconcile(true, { state: "running" }, (v) =>
        calls.push(v),
      );
      return null;
    }
    const m = mount(<Probe />);
    mounts.push(m);
    await tick();
    expect(tauri.invoke).not.toHaveBeenCalled();
    expect(calls).toEqual([]);
  });

  it("同一语义身份的心跳不中止在途的目录查询", async () => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    const gate = deferred<unknown>();
    tauri.invoke.mockImplementation((cmd: string) =>
      cmd === "voices_list" ? gate.promise : Promise.resolve({}),
    );
    const calls: ActiveVoiceLabel[] = [];
    const Probe = makeProbe(calls);
    const m = mount(<Probe status={st("m/a.pth")} />);
    mounts.push(m);
    await tick();
    expect(tauri.invoke).toHaveBeenCalledTimes(1);
    // 每 400ms 一次的心跳只换了 status 对象，语义身份没变 ——
    // 不许 cleanup 掉在途的 listVoices，也不许再发一次。
    act(() => {
      m.root.render(<Probe status={{ ...st("m/a.pth"), input_db: -42 }} />);
      m.root.render(<Probe status={{ ...st("m/a.pth"), input_db: -40 }} />);
    });
    await tick();
    expect(tauri.invoke).toHaveBeenCalledTimes(1);
    await act(async () => {
      gate.resolve({
        models: [{ name: "甲", path: "m/a.pth", file: "a.pth", dir: "m" }],
      });
    });
    await tick();
    expect(calls).toEqual([{ id: "m/a.pth", name: "甲", tag: "" }]);
  });

  it("初始就是 model_active:null：也要把已显示的选中音色清掉", async () => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    const calls: ActiveVoiceLabel[] = [];
    const Probe = makeProbe(calls);
    const m = mount(<Probe status={st(null)} />);
    mounts.push(m);
    await tick();
    expect(calls).toEqual([{ id: "", name: "", tag: "" }]);
    expect(tauri.invoke).not.toHaveBeenCalled();
  });

  it("目录查询失败要重试，不能一错就永久 latch", async () => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    // 每次 voices_list 各拿一个 deferred，由测试逐个控制成败。
    const gates: ReturnType<typeof deferred>[] = [];
    tauri.invoke.mockImplementation((cmd: string) => {
      if (cmd !== "voices_list") return Promise.resolve({});
      const d = deferred();
      gates.push(d);
      return d.promise;
    });
    const calls: ActiveVoiceLabel[] = [];
    const Probe = makeProbe(calls);
    const m = mount(<Probe status={st("m/a.pth")} />);
    mounts.push(m);
    await tick();
    expect(gates).toHaveLength(1);
    // 第一次失败 → 同一身份原地重试，不是永久 latch。
    await act(async () => {
      gates[0].reject(new Error("catalog offline"));
    });
    await tick();
    await tick();
    expect(gates.length).toBeGreaterThanOrEqual(2);
    // 重试成功 → 同一身份照常出结果。
    await act(async () => {
      gates[1].resolve({
        models: [{ name: "甲", path: "m/a.pth", file: "a.pth", dir: "m" }],
      });
    });
    await tick();
    expect(calls).toEqual([{ id: "m/a.pth", name: "甲", tag: "" }]);
  });

  it("停了再起的同一路径要重新对账（worker 寿命变了）", async () => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    tauri.invoke.mockImplementation((cmd: string) =>
      cmd === "voices_list"
        ? Promise.resolve({
            models: [{ name: "甲", path: "m/a.pth", file: "a.pth", dir: "m" }],
          })
        : Promise.resolve({}),
    );
    const calls: ActiveVoiceLabel[] = [];
    const Probe = makeProbe(calls);
    const m = mount(<Probe status={st("m/a.pth")} />);
    mounts.push(m);
    await tick();
    await tick();
    expect(calls).toHaveLength(1);
    // 停流：running=false → 对账作废。
    act(() => {
      m.root.render(<Probe status={{ state: "idle" }} running={false} />);
    });
    await tick();
    // 再开：worker 是新 pid，同一路径也必须重新查目录。
    invalidateVoicesCache();
    act(() => {
      m.root.render(
        <Probe status={{ ...st("m/a.pth"), pid: 999 }} running={true} />,
      );
    });
    await tick();
    await tick();
    expect(tauri.invoke).toHaveBeenCalledTimes(2);
    expect(calls).toHaveLength(2);
    expect(calls[1].id).toBe("m/a.pth");
  });

  it("相对路径按 product_root 归到根再比目录里的绝对身份", async () => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    tauri.invoke.mockImplementation((cmd: string) =>
      cmd === "voices_list"
        ? Promise.resolve({
            models: [
              {
                name: "甲",
                path: "F:/Root/User_Data/models/a/model.pth",
                file: "model.pth",
                dir: "F:/Root/User_Data/models/a",
              },
              // 另一目录里的同名文件绝不能撞上。
              {
                name: "撞名",
                path: "F:/Else/models/b/model.pth",
                file: "model.pth",
                dir: "F:/Else/models/b",
              },
            ],
          })
        : Promise.resolve({}),
    );
    const calls: ActiveVoiceLabel[] = [];
    const Probe = makeProbe(calls);
    const m = mount(
      <Probe
        status={{
          state: "running",
          product_root: "F:/Root",
          model_active: { pth_path: "User_Data/models/a/model.pth" },
        }}
      />,
    );
    mounts.push(m);
    await tick();
    await tick();
    expect(calls).toEqual([
      { id: "F:/Root/User_Data/models/a/model.pth", name: "甲", tag: "" },
    ]);
  });

  it("组件卸载后在途目录结果不得回写", async () => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    const gate = deferred<unknown>();
    tauri.invoke.mockImplementation((cmd: string) =>
      cmd === "voices_list" ? gate.promise : Promise.resolve({}),
    );
    const calls: ActiveVoiceLabel[] = [];
    const Probe = makeProbe(calls);
    const m = mount(<Probe status={st("m/a.pth")} />);
    mounts.push(m);
    await tick();
    m.unmount();
    mounts.pop();
    await act(async () => {
      gate.resolve({
        models: [{ name: "甲", path: "m/a.pth", file: "a.pth", dir: "m" }],
      });
    });
    await tick();
    expect(calls).toEqual([]);
  });

  it("active 从有到 null：明确清空显示", async () => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    tauri.invoke.mockImplementation((cmd: string) => {
      if (cmd === "voices_list") {
        return Promise.resolve({
          models: [{ name: "甲", path: "m/a.pth", file: "a.pth", dir: "m" }],
        });
      }
      return Promise.resolve({});
    });
    const calls: ActiveVoiceLabel[] = [];
    const Probe = makeProbe(calls);
    const m = mount(<Probe status={st("m/a.pth")} />);
    mounts.push(m);
    await tick();
    await tick();
    expect(calls[0]?.name).toBe("甲");
    // worker 回报「没有在用的模型了」（纯 DSP / 解绑）→ 徽标清掉。
    act(() => {
      m.root.render(<Probe status={st(null)} />);
    });
    await tick();
    expect(calls[calls.length - 1]).toEqual({ id: "", name: "", tag: "" });
  });
});
