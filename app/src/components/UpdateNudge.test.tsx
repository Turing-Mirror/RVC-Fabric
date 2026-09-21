// @vitest-environment happy-dom
/**
 * 更新提示的渲染回归（round3 驳回项）：
 *
 * - 装完之后必须显示「已完成 + 需要重启 + 只有关闭」，不能再把
 *   「有新版本，是否立即更新」和「下载并安装」按钮摆回去 —— 点下去就是
 *   对已完成的 offer 再装一遍；
 * - 安装中仍是「正在更新」+ 一个关闭钮；
 * - 待确认时照旧是「稍后 / 下载并安装」。
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { mount, type Mounted } from "../test/dom";
import { UpdateNudge } from "./UpdateNudge";
import { t } from "../i18n/t";
import type { UpdateInfo } from "../lib/updateFlow";

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

const mounts: Mounted[] = [];
afterEach(() => {
  while (mounts.length) mounts.pop()?.unmount();
});

const buttons = (m: Mounted) =>
  Array.from(m.container.querySelectorAll("button")).map(
    (b) => b.textContent || "",
  );

describe("UpdateNudge", () => {
  it("完成态：标题是已更新+重启生效，只剩一个「知道了」", () => {
    const onAccept = vi.fn();
    const onDismiss = vi.fn();
    const m = mount(
      <UpdateNudge
        offer={offer()}
        working={false}
        busy={false}
        error=""
        result={{ version: "1.7.0", restart: true }}
        line={t("s.995e0f4c81", { v0: "1.7.0" })}
        onAccept={onAccept}
        onDismiss={onDismiss}
      />,
    );
    mounts.push(m);
    const text = m.container.textContent || "";
    expect(text).toContain(t("s.995e0f4c81", { v0: "1.7.0" }));
    // 只有关闭钮：不再有「下载并安装」/「稍后」。
    expect(buttons(m)).toEqual([t("s.cb63c62e50")]);
    act(() => {
      (m.container.querySelector("button") as HTMLElement).click();
    });
    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(onAccept).not.toHaveBeenCalled();
  });

  it("安装中：「正在更新」+ 关闭钮，没有安装入口", () => {
    const m = mount(
      <UpdateNudge
        offer={offer()}
        working={true}
        busy={true}
        error=""
        result={null}
        line="下载中…"
        onAccept={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );
    mounts.push(m);
    expect(m.container.textContent).toContain(t("s.87c1bc6fe6"));
    expect(m.container.textContent).not.toContain(t("s.f4df9977ea"));
  });

  it("待确认：「稍后 / 下载并安装」都在，点安装回调 onAccept", () => {
    const onAccept = vi.fn();
    const m = mount(
      <UpdateNudge
        offer={offer()}
        working={false}
        busy={false}
        error=""
        result={null}
        line=""
        onAccept={onAccept}
        onDismiss={vi.fn()}
      />,
    );
    mounts.push(m);
    expect(m.container.textContent).toContain(
      t("s.a462205ca5", { v0: "1.7.0" }),
    );
    const btns = buttons(m);
    expect(btns).toContain(t("s.479fcc1cc0"));
    expect(btns).toContain(t("s.f4df9977ea"));
    const install = Array.from(
      m.container.querySelectorAll("button"),
    ).find((b) => b.textContent === t("s.f4df9977ea")) as HTMLElement;
    act(() => install.click());
    expect(onAccept).toHaveBeenCalledTimes(1);
  });
});
