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

import { useUpdateFlow, type UpdateChannelStatus, type UpdateInfo } from "./updateFlow";

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
    // 装完是终态：提示条回到可点状态，不能停在「正在更新」。
    expect(flow().working).toBe(false);
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
    expect(tauri.invoke).toHaveBeenCalledWith("update_app", { version: "1.7.0" });
    unmount();
  });

  it("同一拍里重复 check()：忙碌判定要在重渲染前生效，只查一次", async () => {
    mockInvoke(() => offer());
    const { flow, unmount } = mountFlow();
    await act(async () => {
      // 两次调用读的是同一份渲染闭包 —— busy state 还没更新。
      void flow().check();
      void flow().check();
    });
    expect(
      tauri.calls.filter((c) => c === "update_check"),
    ).toHaveLength(1);
    unmount();
  });

  it("安装进行中重复 accept：只派发一次安装", async () => {
    let resolveApply!: (v: unknown) => void;
    mockInvoke((cmd) =>
      cmd === "update_check"
        ? offer()
        : new Promise((res) => { resolveApply = res; }),
    );
    const { flow, unmount } = mountFlow();
    await act(async () => {
      await flow().check();
    });
    await act(async () => {
      void flow().accept();
      void flow().accept();
      for (let i = 0; i < 5; i++) await Promise.resolve();
    });
    expect(
      tauri.calls.filter((c) => c === "update_apply"),
    ).toHaveLength(1);
    await act(async () => {
      resolveApply({ ok: true });
      await Promise.resolve();
    });
    unmount();
  });

  it("安装进行中 present()：不得把 working 撤掉、不得换掉在装的提示", async () => {
    let resolveApply!: (v: unknown) => void;
    mockInvoke((cmd) =>
      cmd === "update_check"
        ? offer()
        : new Promise((res) => { resolveApply = res; }),
    );
    const { flow, unmount } = mountFlow();
    await act(async () => {
      await flow().check();
    });
    act(() => {
      void flow().accept();
    });
    await act(async () => {
      for (let i = 0; i < 5; i++) await Promise.resolve();
    });
    expect(flow().working).toBe(true);
    // 自动检查此刻又查到一次新版：它只该被忽略，不能打断在装的流程。
    act(() => {
      flow().present(offer({ remote: "9.9.9" }));
    });
    expect(flow().working).toBe(true);
    await act(async () => {
      resolveApply({ ok: true });
      await Promise.resolve();
    });
    unmount();
  });

  it("整包更新器返回 installed:false：终态复位，不能永远停在「正在更新」", async () => {
    mockInvoke((cmd) =>
      cmd === "update_check"
        ? offer({ action: "external", package_type: "full_package" })
        : { installed: false },
    );
    const { flow, unmount } = mountFlow();
    await act(async () => {
      await flow().check();
    });
    await act(async () => {
      await flow().accept();
    });
    expect(flow().working).toBe(false);
    expect(flow().busy).toBe(false);
    expect(flow().error).not.toBe("");
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
    // 重试成功同样是终态。
    expect(flow().working).toBe(false);
    expect(flow().error).toBe("");
    expect(
      tauri.calls.filter((c) => c === "update_apply"),
    ).toHaveLength(2);
    unmount();
  });

  it("安装成功：进入 completed 结果态，不是回到可点的旧提示", async () => {
    mockInvoke((cmd) =>
      cmd === "update_check"
        ? offer()
        : { ok: true, restart_required: true },
    );
    const { flow, unmount } = mountFlow();
    await act(async () => {
      await flow().check();
    });
    await act(async () => {
      await flow().accept();
    });
    // 终态：working/busy 都松了，result 记着「装好了、要重启」。
    expect(flow().working).toBe(false);
    expect(flow().busy).toBe(false);
    expect(flow().result).toEqual({ version: "1.7.0", restart: true });
    // 已完成的 offer 不能再装一遍：accept / installOffer 都不许再发。
    await act(async () => {
      await flow().accept();
      await flow().installOffer(offer());
    });
    expect(
      tauri.calls.filter((c) => c === "update_apply"),
    ).toHaveLength(1);
    unmount();
  });

  it("installOffer 在忙碌时不许换掉在装的提示", async () => {
    let resolveApply!: (v: unknown) => void;
    mockInvoke((cmd) =>
      cmd === "update_check"
        ? offer()
        : new Promise((res) => {
            resolveApply = res;
          }),
    );
    const { flow, unmount } = mountFlow();
    await act(async () => {
      await flow().check();
    });
    act(() => {
      void flow().accept();
    });
    await act(async () => {
      for (let i = 0; i < 5; i++) await Promise.resolve();
    });
    expect(flow().working).toBe(true);
    // 安装还没落定，installOffer 不许把 offer 换成别的东西。
    act(() => {
      void flow().installOffer(offer({ remote: "9.9.9" }));
    });
    expect(flow().offer?.remote).toBe("1.7.0");
    await act(async () => {
      resolveApply({ ok: true, restart_required: true });
      await Promise.resolve();
    });
    unmount();
  });

  it("关掉完成提示：offer 与 result 一起清", async () => {
    mockInvoke((cmd) =>
      cmd === "update_check"
        ? offer()
        : { ok: true, restart_required: true },
    );
    const { flow, unmount } = mountFlow();
    await act(async () => {
      await flow().check();
    });
    await act(async () => {
      await flow().accept();
    });
    expect(flow().result).not.toBeNull();
    act(() => flow().dismiss());
    expect(flow().offer).toBeNull();
    expect(flow().result).toBeNull();
    unmount();
  });

  it("选择 Beta 只检查目标，明确确认后才安装该通道和版本", async () => {
    mockInvoke((cmd) => cmd === "update_channel_status"
      ? { channel: "stable", version: "1.8.1", beta_available: true }
      : cmd === "update_check"
        ? offer({ local: "1.8.1", remote: "1.8.2-beta.4", action: "external", channel: "beta", installed_channel: "stable", switching_channel: true })
        : { installed: true, version: "1.8.2-beta.4" });
    const { flow, unmount } = mountFlow();
    await act(async () => { await flow().refreshChannelStatus(); });
    await act(async () => { await flow().selectChannel("beta"); });
    expect(tauri.calls).toEqual(["update_channel_status", "update_check"]);
    expect(tauri.invoke).toHaveBeenCalledWith("update_check", { channel: "beta" });
    expect(flow().channelStatus?.channel).toBe("stable");
    expect(flow().selectedChannel).toBe("beta");
    expect(flow().offer?.remote).toBe("1.8.2-beta.4");
    await act(async () => { await flow().accept(); });
    expect(tauri.invoke).toHaveBeenCalledWith("update_app", { channel: "beta", version: "1.8.2-beta.4" });
    expect(flow().channelStatus?.channel).toBe("stable");
    unmount();
  });

  it("Beta 返回较低正式版：检查与安装均绑定 Stable，失败保留实际 Beta 通道", async () => {
    mockInvoke((cmd) => {
      if (cmd === "update_channel_status") return { channel: "beta", version: "1.8.2-beta.4", beta_available: true };
      if (cmd === "update_check") return offer({ local: "1.8.2-beta.4", remote: "1.8.0", action: "external", channel: "stable", installed_channel: "beta", switching_channel: true, downgrade: true });
      throw new Error("signature verification failed");
    });
    const { flow, unmount } = mountFlow();
    await act(async () => { await flow().refreshChannelStatus(); });
    expect(flow().selectedChannel).toBe("beta");
    await act(async () => { await flow().selectChannel("stable"); });
    expect(flow().offer?.downgrade).toBe(true);
    expect(tauri.calls).not.toContain("update_app");
    await act(async () => { await flow().accept(); });
    expect(tauri.invoke).toHaveBeenCalledWith("update_app", { channel: "stable", version: "1.8.0" });
    expect(flow().channelStatus?.channel).toBe("beta");
    expect(flow().result).toBeNull();
    expect(flow().busy).toBe(false);
    expect(flow().error).toContain("signature verification failed");
    unmount();
  });

  it("未配置 Beta 时不发送检查，也不把选择当成已切换", async () => {
    mockInvoke(() => ({ channel: "stable", version: "1.8.1", beta_available: false }));
    const { flow, unmount } = mountFlow();
    await act(async () => { await flow().refreshChannelStatus(); });
    await act(async () => { await flow().selectChannel("beta"); });
    expect(tauri.calls).toEqual(["update_channel_status"]);
    expect(flow().selectedChannel).toBe("stable");
    expect(flow().channelStatus?.channel).toBe("stable");
    expect(flow().line).toContain("Beta");
    unmount();
  });

  it("旧启动检查晚返回时不能覆盖新选 Beta 的目标与提示", async () => {
    let resolveOld!: (value: UpdateInfo) => void;
    mockInvoke((cmd, args) => {
      if (cmd === "update_channel_status") return { channel: "stable", version: "1.8.1", beta_available: true };
      if (!args) return new Promise<UpdateInfo>((resolve) => { resolveOld = resolve; });
      return offer({ remote: "1.8.2-beta.4", channel: "beta", installed_channel: "stable", switching_channel: true });
    });
    const { flow, unmount } = mountFlow();
    await act(async () => { await flow().refreshChannelStatus(); });
    let oldCheck!: Promise<UpdateInfo | null>;
    act(() => { oldCheck = flow().probe(); });
    await act(async () => { await flow().selectChannel("beta"); });
    await act(async () => { resolveOld(offer({ remote: "1.8.1", channel: "stable" })); });
    expect(await oldCheck).toBeNull();
    expect(flow().offer?.channel).toBe("beta");
    expect(flow().checkedTarget?.remote).toBe("1.8.2-beta.4");
    expect(flow().line).toContain("1.8.2-beta.4");
    unmount();
  });

  it("已返回的旧启动结果也不能在选择通道后重新弹出", async () => {
    mockInvoke((cmd, args) => cmd === "update_channel_status"
      ? { channel: "stable", version: "1.8.1", beta_available: true }
      : offer(args ? { channel: "beta", remote: "1.8.2-beta.4", switching_channel: true } : { channel: "stable" }));
    const { flow, unmount } = mountFlow();
    await act(async () => { await flow().refreshChannelStatus(); });
    let old!: UpdateInfo | null;
    await act(async () => { old = await flow().probe(); });
    await act(async () => { await flow().selectChannel("beta"); });
    act(() => { flow().present(old!); });
    expect(flow().offer?.channel).toBe("beta");
    unmount();
  });

  it("Stable→Beta→Stable 后再次进入同一 Beta 不继承上个通道完成标记", async () => {
    let installed: UpdateChannelStatus = { channel: "stable", version: "1.8.1", beta_available: true };
    mockInvoke((cmd, args) => {
      if (cmd === "update_channel_status") return installed;
      const channel = (args as { channel?: string })?.channel ?? installed.channel;
      const version = channel === "beta" ? "1.8.2-beta.4" : "1.8.1";
      if (cmd === "update_check") return offer({ channel: channel as "stable" | "beta", remote: version, local: installed.version, installed_channel: installed.channel, switching_channel: channel !== installed.channel, action: "external" });
      return { installed: true, version };
    });
    const { flow, unmount } = mountFlow();
    await act(async () => { await flow().refreshChannelStatus(); });
    await act(async () => { await flow().selectChannel("beta"); });
    await act(async () => { await flow().accept(); });
    installed = { ...installed, channel: "beta", version: "1.8.2-beta.4" };
    await act(async () => { await flow().refreshChannelStatus(); });
    await act(async () => { await flow().selectChannel("stable"); });
    await act(async () => { await flow().accept(); });
    installed = { ...installed, channel: "stable", version: "1.8.1" };
    await act(async () => { await flow().refreshChannelStatus(); });
    await act(async () => { await flow().selectChannel("beta"); });
    expect(flow().offer?.remote).toBe("1.8.2-beta.4");
    await act(async () => { await flow().accept(); });
    expect(tauri.calls.filter((cmd) => cmd === "update_app")).toHaveLength(3);
    unmount();
  });

  it("切换检查失败不会保留先前可安装的旧提示", async () => {
    mockInvoke((cmd, args) => {
      if (cmd === "update_channel_status") return { channel: "stable", version: "1.8.1", beta_available: true };
      if (args) throw new Error("Beta unavailable");
      return offer({ channel: "stable" });
    });
    const { flow, unmount } = mountFlow();
    await act(async () => { await flow().refreshChannelStatus(); await flow().check(); });
    expect(flow().offer).not.toBeNull();
    await act(async () => { await flow().selectChannel("beta"); });
    expect(flow().offer).toBeNull();
    expect(flow().channelStatus?.channel).toBe("stable");
    expect(flow().line).toContain("Beta unavailable");
    unmount();
  });
});
