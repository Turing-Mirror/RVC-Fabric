// @vitest-environment happy-dom
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
const bridge = vi.hoisted(() => ({ start: vi.fn(), invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: bridge.invoke }));
vi.mock("../lib/downloadModels", () => ({ getAssetsStatus: async () => ({ engine_core_ready: false, engine_core_size_bytes: 2097152 }) }));
vi.mock("../lib/extraJobs", () => ({ useExtraJobs: () => ({ busyKeys: {}, coreBusy: false, progByKey: {}, coreProg: null, msg: "", generation: 0 }), startExtraDownload: bridge.start, startEngineCoreDownload: vi.fn() }));
vi.mock("../i18n", () => ({ useI18n: () => ({ locale: "zh-CN" }) }));
vi.mock("./ui", () => ({ Btn: ({ children, onClick, disabled }: { children: import("react").ReactNode; onClick?: () => void; disabled?: boolean }) => createElement("button", { onClick, disabled }, children), Warn: ({ children }: { children: import("react").ReactNode }) => createElement("div", null, children) }));
import { ExtrasPanel } from "./ExtrasDialog";
it("shows optional models and allows downloading before the core is installed", async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  bridge.invoke.mockResolvedValue({ available: true, items: [{ key: "test-separation", label: "Separation model", group: "separate", size_bytes: 1048576, files: ["model.pth"], installed: false }] });
  const host = document.createElement("div");
  const root = createRoot(host);
  try {
    await act(async () => root.render(createElement(ExtrasPanel, { filter: "separate" })));
    expect(host.textContent).toContain("Separation model");
    expect(host.textContent).toContain("下载大小：2 MB");
    expect(host.textContent).not.toContain("720 MB");
    const download = [...host.querySelectorAll("button")].find(button => button.textContent === "下载");
    expect(download).toBeTruthy();
    expect(download!.disabled).toBe(false);
    await act(async () => download!.click());
    expect(bridge.start).toHaveBeenCalledWith("test-separation");
  } finally { await act(async () => root.unmount()); }
});
