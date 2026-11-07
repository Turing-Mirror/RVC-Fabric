// @vitest-environment happy-dom
import { act, type ReactNode } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { mount, tick, type Mounted } from "../test/dom";
import { t } from "../i18n/t";
const bridge = vi.hoisted(() => ({ invoke: vi.fn(), pick: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: bridge.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn(async () => () => {}) }));
vi.mock("../lib/nativeDialog", () => ({ pickPath: bridge.pick }));
vi.mock("./ToolWindow", () => {
  const Slot = ({ children }: { children: ReactNode }) => <div>{children}</div>;
  return { ToolBody: Slot, ToolActions: Slot, ToolTitleActions: Slot };
});
import { TrainPanel } from "./TrainPanel";
let mounted: Mounted;
beforeEach(() => {
  Object.assign(window, { __TAURI_INTERNALS__: {} });
  bridge.pick.mockResolvedValue("dataset/next");
  bridge.invoke.mockReset().mockImplementation(async (command: string) => {
    if (command === "train_queue_list") return { jobs: [{ id: "1", state: "running", req: {
      exp: "first", sample_rate: "48k", dataset: "dataset/first", total_epoch: 200, batch_size: 4,
    }, progress: { stage: "train", done: 100, total: 200 }, error: "" }] };
    if (command === "train_status") return {
      runtime_ready: true, worker_present: true, mute_present: true, hubert_present: true,
      nvidia: true, rmvpe_present: true, pretrained: [{ sample_rate: "48k", ready: true }],
      suggested_batch: 4, experiments: [], busy: true, disk_free_bytes: 1e11,
    };
    if (command === "train_scan_dataset") return {
      files: 20, other_files: 0, total_bytes: 1000, by_ext: { wav: 20 }, truncated: false, supported: ["wav"],
    };
    if (command === "train_output_dir") return "";
    return {};
  });
});
afterEach(() => {
  mounted?.unmount();
  delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
});
function button(label: string): HTMLButtonElement {
  const el = [...mounted.container.querySelectorAll("button")].find(b => b.textContent === label);
  if (!el) throw new Error(`Missing button ${label}`);
  return el;
}
function edit(input: HTMLInputElement, value: string) {
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
it("keeps adding independent parameter snapshots while a previous job is running", async () => {
  mounted = mount(<TrainPanel />);
  await tick(); await tick();
  act(() => button(t("s.70b208202c")).click());
  await tick(); await tick();
  const name = mounted.container.querySelector<HTMLInputElement>(`input[placeholder="${t("s.b27dd877b1")}"]`)!;
  edit(name, "second");
  const add = button(t("trainingQueue.Add"));
  expect(add.disabled).toBe(false);
  act(() => add.click());
  await tick(); await tick();
  const firstRequest = bridge.invoke.mock.calls.find(([command]) => command === "train_queue_add")![1];
  expect(firstRequest.req).toMatchObject({ exp: "second", dataset: "dataset/next", total_epoch: 200, batch_size: 4 });
  edit(name, "third");
  expect(add.disabled).toBe(false);
  act(() => add.click());
  await tick(); await tick();
  const additions = bridge.invoke.mock.calls.filter(([command]) => command === "train_queue_add");
  expect(additions).toHaveLength(2);
  expect(additions[1][1].req.exp).toBe("third");
  expect(firstRequest.req.exp).toBe("second");
  expect(bridge.invoke.mock.calls.some(([command]) => command === "train_start" || command === "train_cancel")).toBe(false);
});
