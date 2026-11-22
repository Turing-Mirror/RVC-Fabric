// @vitest-environment happy-dom
import { act } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, type Mounted } from "../test/dom";
import { t } from "../i18n/t";
import { UpdateChannelPanel, type UpdateChannelPanelProps } from "./UpdateChannelPanel";

const mounts: Mounted[] = [];
afterEach(() => { while (mounts.length) mounts.pop()?.unmount(); });

function render(overrides: Partial<UpdateChannelPanelProps> = {}) {
  const props: UpdateChannelPanelProps = {
    status: { channel: "stable", version: "1.8.1", beta_available: true },
    selected: "stable", target: null, offer: null, busy: false, working: false,
    error: "", result: null, onSelect: vi.fn(), onAccept: vi.fn(), onDismiss: vi.fn(), ...overrides,
  };
  const m = mount(<UpdateChannelPanel {...props} />);
  mounts.push(m);
  return { ...m, props };
}

const stableOffer = {
  local: "1.8.2-beta.4", remote: "1.8.0", available: true,
  blocked_by_min_version: false, min_app_version: "", package_type: "full_package",
  action: "external", url: "https://example.invalid/setup.exe", sha256: "a".repeat(64),
  notes: "", channel: "stable" as const, installed_channel: "beta" as const,
  switching_channel: true, downgrade: true, legacy_target: true,
};

describe("UpdateChannelPanel", () => {
  it("选择目标通道只发选择回调，不默认安装", () => {
    const m = render();
    const select = m.container.querySelector('[aria-label="' + t("update.targetChannel") + '"]') as HTMLElement;
    expect(select).not.toBeNull();
    act(() => select.click());
    const beta = Array.from(document.body.querySelectorAll('[role="option"]')).find((el) => el.textContent?.trim().startsWith("Beta")) as HTMLElement;
    expect(beta).toBeDefined();
    act(() => beta.click());
    expect(m.props.onSelect).toHaveBeenCalledWith("beta");
    expect(m.props.onAccept).not.toHaveBeenCalled();
    expect(m.container.textContent).toContain(t("update.selectOnly"));
  });

  it("显示实际 Beta 与目标正式版，降级和旧版返回边界明确确认", () => {
    const m = render({
      status: { channel: "beta", version: "1.8.2-beta.4", beta_available: true },
      selected: "stable", target: stableOffer, offer: stableOffer,
    });
    expect(m.container.textContent).toContain("Beta");
    expect(m.container.textContent).toContain("1.8.0");
    expect(m.container.textContent).toContain(t("update.downgradeBody"));
    expect(m.container.textContent).toContain(t("update.legacyStableHint"));
    expect(m.props.onAccept).not.toHaveBeenCalled();
    const install = Array.from(m.container.querySelectorAll("button")).find((button) => button.textContent?.trim() === t("update.switchInstall"))!;
    act(() => install.click());
    expect(m.props.onAccept).toHaveBeenCalledOnce();
  });

  it("下载失败保留错误和重试入口，取消不会触发安装", () => {
    const m = render({ offer: stableOffer, error: "signature failed" });
    expect(m.container.querySelector('[role="alert"]')?.textContent).toBe("signature failed");
    const later = Array.from(m.container.querySelectorAll("button")).find((button) => button.textContent?.trim() === t("s.479fcc1cc0"))!;
    act(() => later.click());
    expect(m.props.onDismiss).toHaveBeenCalledOnce();
    expect(m.props.onAccept).not.toHaveBeenCalled();
  });

  it("支持通道的新正式版不显示旧版缺少入口提示", () => {
    const m = render({ offer: { ...stableOffer, remote: "1.8.2", legacy_target: false } });
    expect(m.container.textContent).not.toContain(t("update.legacyStableHint"));
    expect(m.container.textContent).toContain(t("update.switchInstall"));
  });

  it("忙碌时通道和安装入口不可重复操作", () => {
    const m = render({ offer: stableOffer, busy: true, working: true });
    const select = m.container.querySelector('[aria-label="' + t("update.targetChannel") + '"]') as HTMLButtonElement;
    expect(select.disabled).toBe(true);
    for (const button of m.container.querySelectorAll("button")) {
      act(() => button.click());
    }
    expect(m.props.onAccept).not.toHaveBeenCalled();
    expect(m.props.onSelect).not.toHaveBeenCalled();
  });

  it("完成后只显示关闭按钮，不重复提供切换安装", () => {
    const m = render({ offer: stableOffer, result: { version: "1.8.0", restart: true } });
    expect(m.container.textContent).not.toContain(t("update.switchInstall"));
    expect(m.container.textContent).toContain(t("s.995e0f4c81", { v0: "1.8.0" }));
  });
});
