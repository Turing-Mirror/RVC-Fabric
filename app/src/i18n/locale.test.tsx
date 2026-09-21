// @vitest-environment happy-dom
/**
 * 语言切换回归：按需加载的语言包要以「最后一次点击」为准，
 * 加载失败时保持当前语言、且不得把没装上的语言写进配置。
 */
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, tick, type Mounted } from "../test/dom";
import type { Dict, LocaleCode } from "./types";

const tauri = vi.hoisted(() => ({
  invoke: vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>(),
  configSetCalls: [] as Record<string, unknown>[],
}));

const dictCtl = vi.hoisted(() => ({
  ensurePack: (code: LocaleCode): Promise<Dict> => {
    void code;
    return Promise.resolve({});
  },
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: tauri.invoke }));
vi.mock("./dict", async (importOriginal) => {
  const orig = await importOriginal<typeof import("./dict")>();
  return {
    ...orig,
    ensurePack: (code: LocaleCode) => dictCtl.ensurePack(code),
  };
});

import { I18nProvider, useI18n, type TranslateFn } from "./index";

type Ctx = {
  locale: LocaleCode;
  ready: boolean;
  setLocale: (c: LocaleCode) => void;
  t: TranslateFn;
};

function deferred<T = Dict>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("setLocale 语言包加载语义", () => {
  const mounts: Mounted[] = [];
  let ctx!: Ctx;

  beforeEach(() => {
    tauri.configSetCalls.length = 0;
    dictCtl.ensurePack = () => Promise.resolve({});
    tauri.invoke.mockImplementation(async (cmd: string, args?: unknown) => {
      if (cmd === "config_get") {
        return { ui_locale_picked: true, ui_locale: "zh-CN" };
      }
      if (cmd === "config_set") {
        tauri.configSetCalls.push(
          (args as { patch: Record<string, unknown> }).patch,
        );
        return { config: {}, needs_restart: [] };
      }
      return {};
    });
    function Probe() {
      const v = useI18n();
      ctx = { locale: v.locale, ready: v.ready, setLocale: v.setLocale, t: v.t };
      return null;
    }
    const m = mount(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );
    mounts.push(m);
  });

  afterEach(() => {
    while (mounts.length) mounts.pop()?.unmount();
  });

  it("加载成功才切换并落配置", async () => {
    await tick();
    expect(ctx.ready).toBe(true);
    act(() => ctx.setLocale("ja-JP"));
    await tick();
    expect(ctx.locale).toBe("ja-JP");
    expect(tauri.configSetCalls).toEqual([{ ui_locale: "ja-JP" }]);
  });

  it("快速连点以最后一次点击为准，不是先回来的那个", async () => {
    await tick();
    const gateEn = deferred<Dict>();
    dictCtl.ensurePack = (code: LocaleCode) =>
      code === "en-US" ? gateEn.promise : Promise.resolve({});
    act(() => ctx.setLocale("en-US"));
    act(() => ctx.setLocale("ja-JP"));
    await tick();
    expect(ctx.locale).toBe("ja-JP");
    // en-US 的包晚到：不得把界面拽回更早的意图。
    await act(async () => {
      gateEn.resolve({});
    });
    await tick();
    expect(ctx.locale).toBe("ja-JP");
    // 落配置的也只能是最终选中的语言。
    expect(tauri.configSetCalls).toEqual([{ ui_locale: "ja-JP" }]);
  });

  it("语言包加载失败：保持当前语言，不把没装上的写进配置", async () => {
    await tick();
    dictCtl.ensurePack = (code: LocaleCode) =>
      code === "fr-FR"
        ? Promise.reject(new Error("pack missing"))
        : Promise.resolve({});
    act(() => ctx.setLocale("fr-FR"));
    await tick();
    expect(ctx.locale).toBe("zh-CN");
    expect(
      tauri.configSetCalls.filter((p) => "ui_locale" in p),
    ).toHaveLength(0);
    // 失败后换到能加载的语言仍然正常。
    act(() => ctx.setLocale("ja-JP"));
    await tick();
    expect(ctx.locale).toBe("ja-JP");
  });
});
