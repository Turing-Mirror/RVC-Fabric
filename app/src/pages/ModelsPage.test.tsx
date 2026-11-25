// @vitest-environment happy-dom
/**
 * B5 回归：模型页的「使用中」徽标只认总控已提交的身份（currentId），
 * 不认持久化的 selected_idx。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, useState } from "react";
import { mount, tick, type Mounted } from "../test/dom";

const tauri = vi.hoisted(() => ({
  invoke: vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>(),
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: tauri.invoke }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(() => Promise.resolve(() => {})),
}));

import { ModelsPage } from "./ModelsPage";
import { invalidateVoicesCache, listVoices } from "../lib/voices";
import { t } from "../i18n/t";

const CATALOG = {
  models: [
    { name: "甲", path: "m/a.pth", file: "a.pth", dir: "m/a" },
    { name: "乙", path: "m/b.pth", file: "b.pth", dir: "m/b" },
  ],
  // 持久化意图指向乙 —— 但它不是「在用」。
  selected_idx: 1,
};

const mounts: Mounted[] = [];

/** 与 App 一样，导航保留在父层，模型页离开后会卸载。 */
function ModelsNavigation({ initialKind = "dsp" }: { initialKind?: "rvc" | "dsp" }) {
  const [visible, setVisible] = useState(true);
  const [kind, setKind] = useState<"rvc" | "dsp">(initialKind);
  const [nonce, setNonce] = useState(0);
  return (
    <>
      <button data-testid="leave" onClick={() => setVisible(false)}>离开</button>
      <button data-testid="return" onClick={() => setVisible(true)}>返回</button>
      <button data-testid="open-dsp" onClick={() => {
        setKind("dsp");
        setNonce((n) => n + 1);
        setVisible(true);
      }}>首页 DSP 入口</button>
      {visible ? <ModelsPage focusKind={kind} focusNonce={nonce} onKindChange={setKind} /> : null}
    </>
  );
}

function kindButton(m: Mounted, kind: "rvc" | "dsp"): HTMLButtonElement {
  const label = t(kind === "rvc" ? "s.dspKindRvc" : "s.dspKindDsp");
  const button = Array.from(m.container.querySelectorAll("button"))
    .find((b) => b.textContent === label);
  if (!button) throw new Error(`Missing models kind button: ${label}`);
  return button;
}

function navigate(m: Mounted, action: string) {
  act(() => (m.container.querySelector(`[data-testid="${action}"]`) as HTMLButtonElement).click());
}

describe("模型页使用中徽标", () => {
  beforeEach(() => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    invalidateVoicesCache();
    tauri.invoke.mockReset();
    tauri.invoke.mockImplementation((cmd: string) => {
      if (cmd === "voices_list") return Promise.resolve(CATALOG);
      if (cmd === "config_get") return Promise.resolve({});
      return Promise.resolve({ items: [] });
    });
  });

  afterEach(() => {
    while (mounts.length) mounts.pop()?.unmount();
    invalidateVoicesCache();
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
  });

  it("does not claim an empty library before the first read completes", () => {
    tauri.invoke.mockImplementation(cmd => cmd === "voices_list" ? new Promise(() => {}) : Promise.resolve({}));
    const m = mount(<ModelsPage />); mounts.push(m);
    expect(m.container.textContent).not.toContain(t("s.c9efc20514"));
    expect(m.container.textContent).not.toContain(t("s.b4ac696046"));
  });

  it("renders cached models before a delayed refresh and retains them on failure", async () => {
    await listVoices();
    invalidateVoicesCache();
    let reject!: (reason: Error) => void;
    tauri.invoke.mockImplementation(cmd => cmd === "voices_list"
      ? new Promise((_resolve, fail) => { reject = fail; }) : Promise.resolve({}));
    const m = mount(<ModelsPage currentId="m/b.pth" />);
    mounts.push(m);
    expect(m.container.textContent).toContain("甲");
    expect(m.container.textContent).toContain("乙");
    expect(m.container.textContent).not.toContain(t("s.c9efc20514"));
    await act(async () => reject(new Error("offline")));
    expect(m.container.textContent).toContain("甲");
  });

  it("late index/profile responses cannot overwrite a newer selection", async () => {
    const pending = new Map<string, (value: unknown) => void>();
    tauri.invoke.mockImplementation((cmd, args) => {
      if (cmd === "voices_list") return Promise.resolve({ models: CATALOG.models.map((m) => ({ ...m, source: "user_data" })) });
      if (cmd === "voices_index_list" || cmd === "voices_profiles_list") {
        const dir = (args as { modelDir: string }).modelDir;
        return new Promise((resolve) => pending.set(`${cmd}:${dir}`, resolve));
      }
      return Promise.resolve({});
    });
    const m = mount(<ModelsPage currentId="m/a.pth" />);
    mounts.push(m);
    await tick(); await tick();
    act(() => m.root.render(<ModelsPage currentId="m/b.pth" />));
    await tick();
    const resolve = (dir: string, label: string) => {
      pending.get(`voices_index_list:${dir}`)!({ items: [{ path: label, label, active: true, badge: "" }] });
      pending.get(`voices_profiles_list:${dir}`)!({ items: [{ id: label, name: label, source: "user", source_label: "", active: true }] });
    };
    await act(async () => resolve("m/b", "NEW_PANEL"));
    expect(m.container.textContent).toContain("NEW_PANEL");
    await act(async () => resolve("m/a", "OLD_PANEL"));
    expect(m.container.textContent).toContain("NEW_PANEL");
    expect(m.container.textContent).not.toContain("OLD_PANEL");
  });

  it("currentId 为空：selected_idx 不许假造「使用中」徽标", async () => {
    const badge = t("s.e6aa2cbd7b");
    const m = mount(<ModelsPage currentId="" />);
    mounts.push(m);
    await tick();
    await tick();
    expect(m.container.textContent).toContain("甲");
    expect(m.container.textContent).not.toContain(badge);
  });

  it("currentId 指向乙：徽标只落在乙的卡上", async () => {
    const badge = t("s.e6aa2cbd7b");
    const m = mount(<ModelsPage currentId="m/b.pth" />);
    mounts.push(m);
    await tick();
    await tick();
    const badges = Array.from(
      m.container.querySelectorAll("span"),
    ).filter((s) => s.textContent === badge && !s.closest("button"));
    expect(badges).toHaveLength(1);
    // 徽章所在的卡片容器里得有乙的名字。
    const card = badges[0].closest("div");
    expect(card?.parentElement?.textContent).toContain("乙");
  });

  it("首页 DSP 入口首帧即选中 DSP，不先闪 RVC", () => {
    const m = mount(<ModelsPage focusKind="dsp" />);
    mounts.push(m);
    expect(kindButton(m, "dsp").classList.contains("text-[var(--ink)]")).toBe(true);
  });

  it("首页进入 DSP 后手动切回 RVC，离开再返回保留 RVC（issue #8）", async () => {
    const m = mount(<ModelsNavigation />);
    mounts.push(m);
    await tick();
    act(() => kindButton(m, "rvc").click());
    expect(kindButton(m, "rvc").classList.contains("text-[var(--ink)]")).toBe(true);
    navigate(m, "leave");
    navigate(m, "return");
    await tick();
    expect(kindButton(m, "rvc").classList.contains("text-[var(--ink)]")).toBe(true);
  });

  it("手动切换 DSP 也能跨页面保留，首页明确跳转仍然有效", async () => {
    const m = mount(<ModelsNavigation initialKind="rvc" />);
    mounts.push(m);
    await tick();
    act(() => kindButton(m, "rvc").click());
    act(() => kindButton(m, "dsp").click());
    navigate(m, "leave");
    navigate(m, "return");
    await tick();
    expect(kindButton(m, "dsp").classList.contains("text-[var(--ink)]")).toBe(true);
    act(() => kindButton(m, "rvc").click());
    navigate(m, "open-dsp");
    expect(kindButton(m, "dsp").classList.contains("text-[var(--ink)]")).toBe(true);
  });
});

describe("模型页训练轮次", () => {
  const USER_CATALOG = {
    models: [
      { name: "甲", path: "m/a/a.pth", file: "a.pth", dir: "m/a", source: "user_data" },
      { name: "外部", path: "legacy/x.pth", file: "x.pth", dir: "", source: "legacy_weights" },
    ],
  };

  function makeModelVersions(count = 2, opts?: {
    experiment?: string | null;
    state?: "matched" | "source_removed" | "external" | "missing";
    currentEpoch?: number | null;
    activeFile?: string;
  }) {
    const activeFile = opts?.activeFile ?? "a_e100.pth";
    const versions = Array.from({ length: count }, (_, idx) => {
      const epoch = (idx + 1) * 50;
      const file = `a_e${epoch}.pth`;
      return {
        file,
        epoch,
        step: null,
        is_final: idx === count - 1,
        current: file === activeFile,
      };
    });
    return {
      experiment: opts && "experiment" in opts ? opts.experiment : "a",
      weights_dir: "C:/weights",
      weights: [
        {
          kind: "rvc",
          current: {
            state: opts?.state ?? "matched",
            file: activeFile,
            epoch: opts && "currentEpoch" in opts ? opts.currentEpoch : 100,
            step: null,
          },
          versions,
        },
      ],
    };
  }

  beforeEach(() => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    invalidateVoicesCache();
    tauri.invoke.mockReset();
  });

  afterEach(() => {
    while (mounts.length) mounts.pop()?.unmount();
    invalidateVoicesCache();
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
  });

  it("hides training epochs block when experiment is null or versions are empty or voice is not user_data", async () => {
    tauri.invoke.mockImplementation((cmd) => {
      if (cmd === "voices_list") return Promise.resolve(USER_CATALOG);
      if (cmd === "config_get") return Promise.resolve({});
      if (cmd === "model_versions_list") return Promise.resolve(makeModelVersions(0, { experiment: null }));
      return Promise.resolve({ items: [] });
    });

    const m = mount(<ModelsPage currentId="m/a/a.pth" />);
    mounts.push(m);
    await tick();
    await tick();
    expect(m.container.textContent).not.toContain(t("s.modelVersionsTitle"));

    act(() => m.root.render(<ModelsPage currentId="legacy/x.pth" />));
    await tick();
    expect(m.container.textContent).not.toContain(t("s.modelVersionsTitle"));
  });

  it("renders versions with final badge and switches version on click", async () => {
    let versionsState = makeModelVersions(2, { activeFile: "a_e100.pth" });
    tauri.invoke.mockImplementation((cmd, args) => {
      if (cmd === "voices_list") return Promise.resolve(USER_CATALOG);
      if (cmd === "config_get") return Promise.resolve({});
      if (cmd === "model_versions_list") return Promise.resolve(versionsState);
      if (cmd === "model_version_apply") {
        const { file } = args as { file: string };
        versionsState = makeModelVersions(2, { activeFile: file });
        return Promise.resolve(versionsState);
      }
      return Promise.resolve({ items: [] });
    });

    const m = mount(<ModelsPage currentId="m/a/a.pth" />);
    mounts.push(m);
    await tick();
    await tick();

    expect(m.container.textContent).toContain(t("s.modelVersionsTitle"));
    expect(m.container.textContent).toContain(t("s.modelVersionEpoch", { v0: 50 }));
    expect(m.container.textContent).toContain(t("s.modelVersionEpoch", { v0: 100 }));
    expect(m.container.textContent).toContain(t("s.modelVersionFinal"));

    // Click "使用" inside the training epochs block (for epoch 50)
    const section = [...m.container.querySelectorAll("section, div")]
      .find((el) => el.querySelector("h2, h3")?.textContent === t("s.modelVersionsTitle"));
    const useBtn = [...(section ?? m.container).querySelectorAll("button")]
      .find((b) => b.textContent === t("s.0e2d3a3c09") && !b.disabled);
    expect(useBtn).toBeDefined();
    await act(async () => useBtn!.click());
    await tick();
    await tick();

    expect(tauri.invoke).toHaveBeenCalledWith("model_version_apply", {
      target: "m/a",
      kind: "rvc",
      file: "a_e50.pth",
    });
  });

  it("renders source_removed and external notes", async () => {
    let state: "source_removed" | "external" = "source_removed";
    let currentEpoch: number | null = 75;
    tauri.invoke.mockImplementation((cmd) => {
      if (cmd === "voices_list") return Promise.resolve(USER_CATALOG);
      if (cmd === "config_get") return Promise.resolve({});
      if (cmd === "model_versions_list") return Promise.resolve(makeModelVersions(2, { state, currentEpoch }));
      return Promise.resolve({ items: [] });
    });

    const m = mount(<ModelsPage currentId="m/a/a.pth" />);
    mounts.push(m);
    await tick();
    await tick();
    expect(m.container.textContent).toContain(t("s.modelVersionsSourceRemoved", { v0: 75 }));

    currentEpoch = null;
    act(() => m.root.render(<ModelsPage key="unknown" currentId="m/a/a.pth" />));
    await tick();
    await tick();
    expect(m.container.textContent).toContain(t("s.modelVersionsSourceRemovedUnknown"));

    state = "external";
    act(() => m.root.render(<ModelsPage key="ext" currentId="m/a/a.pth" />));
    await tick();
    await tick();
    expect(m.container.textContent).toContain(t("s.modelVersionsExternal"));
  });

  it("paginates training epochs at 8 items per page", async () => {
    tauri.invoke.mockImplementation((cmd) => {
      if (cmd === "voices_list") return Promise.resolve(USER_CATALOG);
      if (cmd === "config_get") return Promise.resolve({});
      if (cmd === "model_versions_list") return Promise.resolve(makeModelVersions(10, { activeFile: "a_e500.pth" }));
      return Promise.resolve({ items: [] });
    });

    const m = mount(<ModelsPage currentId="m/a/a.pth" />);
    mounts.push(m);
    await tick();
    await tick();

    expect(m.container.textContent).toContain(t("s.modelVersionEpoch", { v0: 50 }));
    expect(m.container.textContent).toContain(t("s.modelVersionEpoch", { v0: 400 }));
    expect(m.container.textContent).not.toContain(t("s.modelVersionEpoch", { v0: 450 }));

    const page2Btn = [...m.container.querySelectorAll("button")]
      .find((b) => b.dataset.k === "p2" || b.textContent?.trim() === "2");
    expect(page2Btn).toBeDefined();
    await act(async () => page2Btn!.click());
    await tick();

    expect(m.container.textContent).toContain(t("s.modelVersionEpoch", { v0: 450 }));
    expect(m.container.textContent).toContain(t("s.modelVersionEpoch", { v0: 500 }));
  });
});

describe("模型页顶部提示条", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    invalidateVoicesCache();
    tauri.invoke.mockReset();
    tauri.invoke.mockImplementation((cmd: string) => {
      if (cmd === "voices_list") return Promise.resolve(CATALOG);
      if (cmd === "config_get") return Promise.resolve({});
      return Promise.resolve({ items: [] });
    });
  });

  afterEach(() => {
    while (mounts.length) mounts.pop()?.unmount();
    invalidateVoicesCache();
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
    vi.useRealTimers();
  });

  it("报错提示不自动消失，可手动关闭；非报错提示 4 秒后自动消失", async () => {
    tauri.invoke.mockImplementation((cmd: string) => {
      if (cmd === "voices_list") return Promise.resolve(CATALOG);
      if (cmd === "config_get") return Promise.resolve({});
      if (cmd === "voices_open_dir") return Promise.reject(new Error("open failed"));
      return Promise.resolve({ items: [] });
    });
    const m = mount(<ModelsPage />);
    mounts.push(m);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });

    const openDirBtn = [...m.container.querySelectorAll("button")]
      .find((b) => b.textContent === t("s.031c105578"));
    expect(openDirBtn).toBeDefined();
    await act(async () => {
      openDirBtn!.click();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(m.container.querySelector('[role="alert"]')).not.toBeNull();

    // 超过 4 秒后报错条仍然保留
    await act(async () => { vi.advanceTimersByTime(5000); });
    expect(m.container.querySelector('[role="alert"]')).not.toBeNull();

    // 点击关闭按钮后收起
    const closeBtn = [...m.container.querySelectorAll("button")]
      .find((b) => b.textContent === t("s.6c14bd7f6f"));
    expect(closeBtn).toBeDefined();
    act(() => closeBtn!.click());
    expect(m.container.querySelector('[role="alert"]')).toBeNull();

    // 非报错提示（刷新完成）4 秒后照旧自动消失
    const refreshBtn = [...m.container.querySelectorAll("button")]
      .find((b) => b.textContent === t("s.38108eaa1d"));
    expect(refreshBtn).toBeDefined();
    await act(async () => {
      refreshBtn!.click();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(m.container.querySelector('[role="status"]')?.textContent).toContain(t("s.58b4af2771"));
    await act(async () => { vi.advanceTimersByTime(4100); });
    expect(m.container.querySelector('[role="status"]')).toBeNull();
  });
});
