// @vitest-environment happy-dom
import { act } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { I18nProvider, tStatic } from "../i18n";
import { mount, tick, type Mounted } from "../test/dom";
import { MobileSection } from "./MobileSection";
import type { MobileController } from "../hooks/useMobile";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
let view: Mounted | undefined;
afterEach(() => { view?.unmount(); shell.invoke.mockReset(); });
const controller = (): MobileController => ({ status: { enabled: false, connected: false, running: false, selected: false, devices: [] },
  action: vi.fn(async () => {}), refresh: vi.fn(async () => {}), busy: false, error: "" });
it("opens the network only after a pairing action", async () => {
  const mobile = controller();
  shell.invoke.mockResolvedValue({ svg: "<svg/>", payload: "invite", expires_at: Date.now() + 120000, endpoint: "http://192.168.1.2:8787", addresses: ["192.168.1.2"], host: "192.168.1.2" });
  view = mount(<I18nProvider><MobileSection mobile={mobile} /></I18nProvider>); await tick();
  expect(shell.invoke.mock.calls.some(call => call[0] === "mobile_pairing")).toBe(false);
  const button = [...view.container.querySelectorAll("button")].find(b => b.textContent === tStatic("mobile.showQr"));
  expect(button).toBeDefined(); act(() => button!.click()); await tick();
  expect(shell.invoke).toHaveBeenCalledWith("mobile_pairing", { host: undefined });
  expect(view.container.querySelector("img")?.getAttribute("src")).toContain("data:image/svg+xml");
});
it("requires a ready microphone before switching to phone input", async () => {
  const mobile = controller(); mobile.status.connected = true;
  mobile.status.device = { id: "one", name: "Phone", phone: { microphone_ready: false } };
  mobile.status.output_devices = [{ id: "headphones", name: "Headphones" }];
  view = mount(<I18nProvider><MobileSection mobile={mobile} /></I18nProvider>); await tick();
  expect([...view.container.querySelectorAll("button")].find(b => b.textContent === tStatic("mobile.usePhone"))?.disabled).toBe(true);
  expect(mobile.action).not.toHaveBeenCalled();
  expect(view.container.textContent).toContain(tStatic("mobile.waitMicrophone"));
  expect(view.container.textContent).toContain(tStatic("s.53e2db7016"));
  expect(view.container.textContent).not.toContain(tStatic("s.e6b7c3d266"));
});
