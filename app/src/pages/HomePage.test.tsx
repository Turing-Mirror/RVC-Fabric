// @vitest-environment happy-dom
/**
 * B5 回归：首页的「使用中」只认总控已提交的身份（currentId）。
 *
 * 目录的 selected_idx 是持久化的选择意图 —— 上次切换失败时它会撒谎，
 * 没确认在用的音色不许把库里第一条画成当前、也不许给任何卡贴徽标。
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

import { HomePage } from "./HomePage";
import { invalidateVoicesCache } from "../lib/voices";
import { t } from "../i18n/t";

const CATALOG = {
  models: [
    { name: "甲", path: "m/a.pth", file: "a.pth", dir: "m/a" },
    { name: "乙", path: "m/b.pth", file: "b.pth", dir: "m/b" },
    { name: "丙", path: "m/c.pth", file: "c.pth", dir: "m/c" },
  ],
  // 持久化意图指向乙 —— 但它不是「在用」。
  selected_idx: 1,
  recent_keys: ["m/a", "m/b", "m/c"],
};

const mounts: Mounted[] = [];

describe("首页使用中徽标", () => {
  beforeEach(() => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    invalidateVoicesCache();
    tauri.invoke.mockReset();
    tauri.invoke.mockImplementation((cmd: string) => {
      if (cmd === "voices_list") return Promise.resolve(CATALOG);
      if (cmd === "config_get") return Promise.resolve({});
      return Promise.resolve({});
    });
  });

  afterEach(() => {
    while (mounts.length) mounts.pop()?.unmount();
    invalidateVoicesCache();
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
  });

  it("currentId 为空：不贴任何卡的「使用中」，主角位显示占位文案", async () => {
    const badge = t("s.e6aa2cbd7b");
    const m = mount(<HomePage currentId="" />);
    mounts.push(m);
    await tick();
    await tick();
    // 三张卡都在，但没有一张贴「使用中」。
    expect(m.container.textContent).toContain("甲");
    expect(m.container.textContent).not.toContain(badge);
    // 主角位（横幅下的 accent 行）显示的是占位文案，不是目录第一条。
    const hero = m.container.querySelector(
      "p.text-\\[19px\\]",
    ) as HTMLElement | null;
    expect(hero).not.toBeNull();
    expect(hero!.textContent).toBe(t("s.262d11e2d6"));
    expect(hero!.textContent).not.toContain("乙");
  });

  it("currentId 指向乙：只有乙贴徽标，主角位是它的名字", async () => {
    const badge = t("s.e6aa2cbd7b");
    const m = mount(<HomePage currentId="m/b.pth" />);
    mounts.push(m);
    await tick();
    await tick();
    const hero = m.container.querySelector(
      "p.text-\\[19px\\]",
    ) as HTMLElement | null;
    expect(hero!.textContent).toContain("乙");
    // 徽章只出现一次 —— 在乙的卡上。
    const badges = Array.from(
      m.container.querySelectorAll("span"),
    ).filter((s) => s.textContent === badge);
    expect(badges).toHaveLength(1);
  });
});
