// @vitest-environment happy-dom
/**
 * C2 验收：检查归检查，确认更新归更新。
 *
 * - 手动检查与自动检查都只发 update_check，不碰 update_apply / update_app；
 * - 发现新版只挂待确认提示，用户点确认才进入下载安装；
 * - 取消 / 关闭提示不更新；
 * - 安装失败回到原位置可重试，不永久停在「正在更新」；
 * - 无更新与检查失败只写状态行。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { mount } from "../test/dom";

const tauri = vi.hoisted(() => ({
  invoke: vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>(),
  calls: [] as string[],
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: tauri.invoke }));

import { useUpdateFlow, type UpdateInfo } from "./updateFlow";

const offer = (over: Partial<UpdateInfo> = {}): UpdateInfo => ({
  local: "1.6.0",
  remote: "1.7.0",
  available: true,
  blocked_by_min_version: false,
  min_app_version: "",
  package_type: "gui_patch",
  action: "apply_patch",
  url: "https://example/patch.zip",
  sha256: "ab".repeat(32),
  notes: "修复若干问题",
  ...over,
});

function mockInvoke(fn: (cmd: string, args?: unknown) => unknown) {
  tauri.invoke.mockImplementation(async (cmd: string, args?: unknown) => {
    tauri.calls.push(cmd);
    return fn(cmd, args);
  });
}

function mountFlow() {
  let flow!: ReturnType<typeof useUpdateFlow>;
  const Probe = () => {
    flow = useUpdateFlow();
    return null;
  };
  const m = mount(<Probe />);
  return { flow: () => flow, unmount: m.unmount };
}

describe("useUpdateFlow", () => {
  beforeEach(() => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    tauri.calls.length = 0;
    tauri.invoke.mockReset();
  });
  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
  });

  it("手动检查发现新版：只查不装，挂出待确认提示", async () => {
    mockInvoke(() => offer());
    const { flow, unmount } = mountFlow();
    await act(async () => {
      await flow().check();
    });
    expect(tauri.calls).toEqual(["update_check"]);
    expect(flow().offer?.remote).toBe("1.7.0");
    unmount();
  });

  it("无更新：状态行写已是最新，不弹提示", async () => {
    mockInvoke(() => offer({ available: false, remote: "—" }));
    const { flow, unmount } = mountFlow();
    await act(async () => {
      await flow().check();
    });
    expect(flow().offer).toBeNull();
    expect(flow().line).toContain("1.6.0");
    unmount();
  });

  it("检查失败：如实写状态行，不弹提示、不卡忙碌", async () => {
    mockInvoke(() => {
      throw new Error("network down");
    });
    const { flow, unmount } = mountFlow();
    await act(async () => {
      await flow().check();
    });
    expect(flow().offer).toBeNull();
    expect(flow().busy).toBe(false);
    expect(flow().line).toContain("network down");
    unmount();
  });

  it("关闭提示不触发任何下载或安装", async () => {
    mockInvoke(() => offer());
    const { flow, unmount } = mountFlow();
    await act(async () => {
      await flow().check();
    });
    act(() => flow().dismiss());
    expect(flow().offer).toBeNull();
    expect(tauri.calls).toEqual(["update_check"]);
    unmount();
  });

  it("确认后才下载安装：补丁走 update_apply", async () => {
    mockInvoke((cmd) =>
      cmd === "update_check" ? offer() : { ok: true },
    );
    const { flow, unmount } = mountFlow();
    await act(async () => {
      await flow().check();
    });
    await act(async () => {
      await flow().accept();
    });
    expect(tauri.calls).toEqual(["update_check", "update_apply"]);
    expect(flow().working).toBe(true);
    expect(flow().line).toContain("1.7.0");
    unmount();
  });

  it("整包更新走签名更新器 update_app", async () => {
    mockInvoke((cmd) =>
      cmd === "update_check"
        ? offer({ action: "external", package_type: "full_package" })
        : { installed: true, version: "1.7.0" },
    );
    const { flow, unmount } = mountFlow();
    await act(async () => {
      await flow().check();
    });
    await act(async () => {
      await flow().accept();
    });
    expect(tauri.calls).toEqual(["update_check", "update_app"]);
    unmount();
  });

  it("安装失败：错误留在原位置，可原地重试", async () => {
    let fail = true;
    mockInvoke((cmd) => {
      if (cmd === "update_check") return offer();
      if (fail) throw new Error("下载中断");
      return { ok: true };
    });
    const { flow, unmount } = mountFlow();
    await act(async () => {
      await flow().check();
    });
    await act(async () => {
      await flow().accept();
    });
    // 失败：回到可点状态，错误可见，按钮不再是「正在更新」。
    expect(flow().working).toBe(false);
    expect(flow().busy).toBe(false);
    expect(flow().error).toContain("下载中断");
    expect(flow().offer).not.toBeNull();
    // 原地重试：再发一次 update_apply，成功。
    fail = false;
    await act(async () => {
      await flow().accept();
    });
    expect(flow().working).toBe(true);
    expect(flow().error).toBe("");
    expect(
      tauri.calls.filter((c) => c === "update_apply"),
    ).toHaveLength(2);
    unmount();
  });
});
