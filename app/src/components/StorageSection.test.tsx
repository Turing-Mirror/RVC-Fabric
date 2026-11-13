// @vitest-environment happy-dom
import { act } from "react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { mount, tick, type Mounted } from "../test/dom";
const mocks = vi.hoisted(() => ({ invoke: vi.fn(), confirm: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: mocks.invoke }));
vi.mock("trm-ui/fabric", async (orig) => ({ ...(await orig<typeof import("trm-ui/fabric")>()), ...({ askConfirm: mocks.confirm }) }));
import { StorageSection } from "./StorageSection";
import { t } from "../i18n/t";

const usage = { items: [{ name: "temp", bytes: 1024 }, { name: "update_cache", bytes: 2048 }], total_bytes: 3072, free_bytes: 10000 };
let m: Mounted;
beforeEach(() => {
  mocks.confirm.mockResolvedValue(true);
  mocks.invoke.mockReset();
  mocks.invoke.mockImplementation(async (cmd: string) => cmd === "storage_usage" ? usage : cmd === "storage_clean" ? { freed_bytes: 3072 } : []);
});
afterEach(() => m?.unmount());
describe("storage feedback", () => {
  it("keeps usable statistics if the training scan fails", async () => {
    mocks.invoke.mockImplementation(async (cmd: string) => {
      if (cmd === "storage_usage") return usage;
      throw new Error("scan unavailable");
    });
    m = mount(<StorageSection />); await tick();
    expect(m.container.textContent).toContain("3.0 KB");
    expect(m.container.querySelector('[role="alert"]')?.textContent).toBe(t("s.storageScanFailed"));
  });
  it("counts update cache in temporary cleanup and retains success when refresh fails", async () => {
    m = mount(<StorageSection />); await tick();
    const check = m.container.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(check.closest("label")?.textContent).toContain("3.0 KB");
    act(() => check.click());
    const apply = [...m.container.querySelectorAll("button")].find((b) => b.textContent === t("s.cleanupApply"))!;
    mocks.invoke.mockImplementation(async (cmd: string) => {
      if (cmd === "storage_clean") return { freed_bytes: 3072 };
      throw new Error("refresh unavailable");
    });
    await act(async () => apply.click()); await tick();
    expect(mocks.invoke).toHaveBeenCalledWith("storage_clean", { kinds: ["temp"] });
    expect(m.container.textContent).toContain(t("s.cleanDone", { size: "3.0 KB" }));
    expect(m.container.querySelector('[role="alert"]')?.textContent).toBe(t("s.storageScanFailed"));
    expect(check.checked).toBe(false);
    expect(apply.disabled).toBe(true);
  });
});
