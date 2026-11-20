// @vitest-environment happy-dom
import { act } from "react";
import { expect, it, vi } from "vitest";
import { mount, tick } from "../test/dom";
import { t } from "../i18n/t";

const { invoke } = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));
vi.mock("../lib/engine", () => ({
  startProvision: (variant: string, force: boolean) => invoke("provision_start", { variant, force }),
  cancelProvision: () => invoke("provision_cancel"),
}));

import { ProvisionGate } from "./ProvisionGate";

it("offers one dependency at a time and keeps remaining steps when one is skipped", async () => {
  invoke.mockImplementation(async (command: string) => {
    switch (command) {
      case "provision_start": return { ok: true };
      case "assets_status": return { engine_core_ready: false, vbcable_installed: false };
      case "vcredist_installed": return false;
      default: return {};
    }
  });
  const finish = vi.fn();
  const modal = mount(
    <ProvisionGate open initial={{ recommended_variant: "nvidia" }} onDone={finish} />,
  );
  const body = modal.container.ownerDocument.body;
  const click = async (label: string) => {
    const button = Array.from(body.querySelectorAll("button")).find(b => b.textContent?.trim() === label);
    expect(button, label).toBeDefined();
    await act(async () => button!.click());
    await tick();
  };

  try {
    expect(body.textContent).toContain(t("s.405125fb37"));
    await click(t("runtimeActions.download"));
    expect(body.textContent).toContain(t("extras.engineTitle"));
    expect(body.textContent).not.toContain(t("s.vcrTitle"));
    await click(t("s.479fcc1cc0"));
    expect(body.textContent).toContain(t("s.vcrTitle"));
    expect(finish).not.toHaveBeenCalled();
    await click(t("s.vcrInstall"));
    expect(invoke.mock.calls.map(([name]) => name)).toEqual(expect.arrayContaining([
      "assets_ensure_vcredist", "vcredist_install",
    ]));
    expect(body.textContent).toContain(t("s.3d4e683008"));
    await click(t("s.087db63ab1"));
    expect(body.textContent).toContain(t("s.vbcableDone"));
    expect(body.textContent).toContain(t("s.f2e88c071e"));
    await click(t("s.33246f6a5e"));
    expect(finish).toHaveBeenCalledOnce();
  } finally {
    modal.unmount();
  }
});

it("minimizes active downloads to a bottom-left orb and auto-completes or prompts on click", async () => {
  let resolveProvision!: (value: { ok: boolean; message?: string }) => void;
  invoke.mockImplementation((command: string) => {
    switch (command) {
      case "provision_start":
        return new Promise((resolve) => {
          resolveProvision = resolve;
        });
      case "assets_status":
        return Promise.resolve({ engine_core_ready: true, vbcable_installed: true });
      case "vcredist_installed":
        return Promise.resolve(true);
      default:
        return Promise.resolve({});
    }
  });

  const finish = vi.fn();
  const modal = mount(
    <ProvisionGate open initial={{ recommended_variant: "nvidia" }} onDone={finish} />,
  );
  const body = modal.container.ownerDocument.body;
  const clickButton = async (label: string) => {
    const button = Array.from(body.querySelectorAll("button")).find((b) => b.textContent?.trim() === label);
    expect(button, label).toBeDefined();
    await act(async () => button!.click());
    await tick();
  };

  try {
    await clickButton(t("runtimeActions.download"));
    await clickButton(t("s.setupBackground"));
    const orb = body.querySelector(`button[aria-label="${t("s.orbDownloadLabel")}"]`) as HTMLButtonElement | null;
    expect(orb).not.toBeNull();
    expect(finish).not.toHaveBeenCalled();

    await act(async () => {
      resolveProvision({ ok: true });
      await tick();
    });
    expect(finish).toHaveBeenCalledOnce();
  } finally {
    modal.unmount();
  }
});

it("keeps orb highlighted when next dependency happens while minimized and expands on click", async () => {
  let resolveProvision!: (value: { ok: boolean; message?: string }) => void;
  invoke.mockImplementation((command: string) => {
    switch (command) {
      case "provision_start":
        return new Promise((resolve) => {
          resolveProvision = resolve;
        });
      case "assets_status":
        return Promise.resolve({ engine_core_ready: false, vbcable_installed: true });
      case "vcredist_installed":
        return Promise.resolve(true);
      default:
        return Promise.resolve({});
    }
  });

  const finish = vi.fn();
  const modal = mount(
    <ProvisionGate open initial={{ recommended_variant: "nvidia" }} onDone={finish} />,
  );
  const body = modal.container.ownerDocument.body;
  const clickButton = async (label: string) => {
    const button = Array.from(body.querySelectorAll("button")).find((b) => b.textContent?.trim() === label);
    expect(button, label).toBeDefined();
    await act(async () => button!.click());
    await tick();
  };

  try {
    await clickButton(t("runtimeActions.download"));
    await clickButton(t("s.setupBackground"));
    await act(async () => {
      resolveProvision({ ok: true });
      await tick();
    });
    expect(finish).not.toHaveBeenCalled();
    const orb = body.querySelector(`button[aria-label="${t("s.orbDownloadLabel")}"]`) as HTMLButtonElement | null;
    expect(orb).not.toBeNull();
    await act(async () => orb!.click());
    await tick();
    expect(body.textContent).toContain(t("extras.engineTitle"));
  } finally {
    modal.unmount();
  }
});
