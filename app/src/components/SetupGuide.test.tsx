// @vitest-environment happy-dom
/**
 * 新手引导开头的反馈须知：第一次打开引导先看它，停够几秒才能继续，看过就不再出现。
 */
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, tick, type Mounted } from "../test/dom";

const tauri = vi.hoisted(() => ({
  invoke: vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>(),
}));
vi.mock("@tauri-apps/api/core", () => ({ invoke: tauri.invoke }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(() => Promise.resolve(() => {})),
}));

import { SetupGuide } from "./SetupGuide";
import { t } from "../i18n/t";

const mounts: Mounted[] = [];

function guide() {
  return (
    <SetupGuide
      open
      step="cable"
      onStep={() => {}}
      onMinimize={() => {}}
      onFinish={() => {}}
      workerAlive={false}
      devicesBusy={false}
      onReloadDevices={() => {}}
      running={false}
      starting={false}
      onToggleRun={() => {}}
      onNavigate={() => {}}
    />
  );
}

function okButton(m: Mounted) {
  return Array.from(m.container.ownerDocument.querySelectorAll("button")).find((b) =>
    b.textContent?.startsWith(t("s.guide.notice.ok")),
  );
}

describe("引导开头的反馈须知", () => {
  let cfg: Record<string, unknown>;
  beforeEach(() => {
    vi.useFakeTimers();
    cfg = {};
    tauri.invoke.mockReset();
    tauri.invoke.mockImplementation(async (cmd: string) => {
      if (cmd === "config_get") return cfg;
      return {};
    });
  });

  afterEach(() => {
    while (mounts.length) mounts.pop()?.unmount();
    vi.useRealTimers();
  });

  it("没看过：先显示须知，五秒后才能点「我知道了」，点完记下并进入第一步", async () => {
    const m = mount(guide());
    mounts.push(m);
    await tick();
    await tick();
    const doc = m.container.ownerDocument;
    expect(doc.body.textContent).toContain(t("s.guide.notice.title"));
    expect(doc.body.textContent).not.toContain(t("s.guide.cable.title"));
    expect(okButton(m)?.disabled).toBe(true);
    for (let i = 0; i < 5; i++) {
      await act(async () => {
        vi.advanceTimersByTime(1000);
      });
    }
    const ok = okButton(m);
    expect(ok?.disabled).toBe(false);
    act(() => ok!.click());
    await tick();
    expect(tauri.invoke).toHaveBeenCalledWith("config_set", { patch: { feedback_notice_done: true } });
    expect(doc.body.textContent).toContain(t("s.guide.cable.title"));
  });

  it("看过了：直接进入步骤", async () => {
    cfg = { feedback_notice_done: true };
    const m = mount(guide());
    mounts.push(m);
    await tick();
    await tick();
    const doc = m.container.ownerDocument;
    expect(doc.body.textContent).not.toContain(t("s.guide.notice.title"));
    expect(doc.body.textContent).toContain(t("s.guide.cable.title"));
  });
});
