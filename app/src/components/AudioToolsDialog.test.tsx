// @vitest-environment happy-dom
import { act } from "react";
import { expect, it, vi } from "vitest";
import { mount, tick } from "../test/dom";
import { t } from "../i18n/t";

const { ensureAudioTools } = vi.hoisted(() => ({ ensureAudioTools: vi.fn() }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));
vi.mock("../lib/downloadModels", () => ({
  audioToolsDownloading: () => false,
  ensureAudioTools,
}));

import { AudioToolsDialog } from "./AudioToolsDialog";

it("minimizes audio tools download to an orb and auto-closes upon completion", async () => {
  let resolveTools!: () => void;
  ensureAudioTools.mockImplementation(
    () => new Promise<void>((resolve) => { resolveTools = resolve; }),
  );
  const onClose = vi.fn();
  const modal = mount(<AudioToolsDialog open onClose={onClose} />);
  const body = modal.container.ownerDocument.body;
  const clickButton = async (label: string) => {
    const button = Array.from(body.querySelectorAll("button")).find((b) => b.textContent?.trim() === label);
    expect(button, label).toBeDefined();
    await act(async () => button!.click());
    await tick();
  };

  try {
    await clickButton(t("audioTools.download"));
    await clickButton(t("audioTools.background"));
    const orb = body.querySelector(`button[aria-label="${t("s.orbDownloadLabel")}"]`) as HTMLButtonElement | null;
    expect(orb).not.toBeNull();
    expect(onClose).not.toHaveBeenCalled();

    await act(async () => {
      resolveTools();
      await tick();
    });
    expect(onClose).toHaveBeenCalledOnce();
  } finally {
    modal.unmount();
  }
});
