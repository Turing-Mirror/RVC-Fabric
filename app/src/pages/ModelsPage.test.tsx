// @vitest-environment happy-dom
/**
 * B5 回归：模型页的「使用中」徽标只认总控已提交的身份（currentId），
 * 不认持久化的 selected_idx。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, tick, type Mounted } from "../test/dom";

const tauri = vi.hoisted(() => ({
  invoke: vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>(),
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: tauri.invoke }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(() => Promise.resolve(() => {})),
}));

import { ModelsPage } from "./ModelsPage";
import { invalidateVoicesCache } from "../lib/voices";
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
    ).filter((s) => s.textContent === badge);
    expect(badges).toHaveLength(1);
    // 徽章所在的卡片容器里得有乙的名字。
    const card = badges[0].closest("div");
    expect(card?.parentElement?.textContent).toContain("乙");
  });
});
