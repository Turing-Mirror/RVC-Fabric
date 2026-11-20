// @vitest-environment happy-dom
import { act } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import { mount, tick } from "../test/dom";
import { t } from "../i18n/t";

const storeState = vi.hoisted(() => ({
  running: [] as string[],
  queued: [] as string[],
  prog: {} as Record<string, { percent?: number }>,
  error: null as string | null,
  activeLabel: undefined as string | undefined,
}));

const extraState = vi.hoisted(() => ({
  coreBusy: false,
  coreProg: null as { done?: number; total?: number; percent?: number } | null,
  busyKeys: {} as Record<string, boolean>,
  progByKey: {} as Record<string, { done?: number; total?: number }>,
  msg: "",
  hasError: false,
}));

vi.mock("../lib/storeJobs", () => ({ useStoreJobs: () => storeState }));
vi.mock("../lib/extraJobs", () => ({ useExtraJobs: () => extraState }));

import { CommunityDownloadOrb } from "./CommunityDownloadOrb";

beforeEach(() => {
  storeState.running = [];
  storeState.queued = [];
  storeState.prog = {};
  storeState.error = null;
  storeState.activeLabel = undefined;
  extraState.coreBusy = false;
  extraState.coreProg = null;
  extraState.busyKeys = {};
  extraState.progByKey = {};
  extraState.msg = "";
  extraState.hasError = false;
});

it("shows orb only off-plaza during community downloads, auto-hides cleanly, and alerts on error", async () => {
  const onOpenPlaza = vi.fn();
  const onOpenDownloads = vi.fn();
  const modal = mount(
    <CommunityDownloadOrb
      activePage="plaza"
      onOpenPlaza={onOpenPlaza}
      onOpenDownloads={onOpenDownloads}
    />,
  );
  const body = modal.container.ownerDocument.body;

  const renderAt = async (page: string) => {
    await act(async () => {
      modal.root.render(
        <CommunityDownloadOrb activePage={page} onOpenPlaza={onOpenPlaza} onOpenDownloads={onOpenDownloads} />,
      );
      await tick();
    });
  };

  try {
    storeState.running = ["voice-1"];
    storeState.prog = { "voice-1": { percent: 55 } };
    storeState.activeLabel = "Demo Voice";

    await renderAt("plaza");
    expect(body.querySelector(`button[aria-label="${t("s.orbDownloadLabel")}"]`)).toBeNull();

    await renderAt("home");
    const orb = body.querySelector(`button[aria-label="${t("s.orbDownloadLabel")}"]`) as HTMLButtonElement | null;
    expect(orb).not.toBeNull();
    expect(orb!.textContent).toContain("55");

    storeState.running = [];
    storeState.prog = {};
    await renderAt("home");
    const exitingOrb = body.querySelector(`button[aria-label="${t("s.orbDownloadLabel")}"]`);
    expect(exitingOrb === null || exitingOrb.classList.contains("trm-orb-out")).toBe(true);

    extraState.coreBusy = true;
    await renderAt("home");
    extraState.coreBusy = false;
    extraState.hasError = true;
    extraState.msg = "download failed";
    await renderAt("home");
    const errOrb = body.querySelector(`button[aria-label="${t("s.orbDownloadLabel")}"]`) as HTMLButtonElement | null;
    expect(errOrb).not.toBeNull();
    expect(errOrb!.classList.contains("trm-orb-out")).toBe(false);
    await act(async () => errOrb!.click());
    expect(onOpenDownloads).toHaveBeenCalledOnce();
    expect(onOpenPlaza).not.toHaveBeenCalled();
  } finally {
    modal.unmount();
  }
});
