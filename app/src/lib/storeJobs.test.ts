// @vitest-environment happy-dom
import { expect, it, vi } from "vitest";

const tauri = vi.hoisted(() => ({
  invoke: vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>(),
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: tauri.invoke }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(() => Promise.resolve(() => {})),
}));

import { enqueueJobIds, enqueueStoreDownload, getStoreJobs, MAX_STORE_JOBS } from "./storeJobs";
import { diagnosticOf } from "./diagnostics";

it("starts immediately when a slot is free", () => {
  const next = enqueueJobIds("a", [], []);
  expect(next.launch).toBe(true);
  expect(next.running).toEqual(["a"]);
  expect(next.queued).toEqual([]);
});

it("queues past the concurrent cap instead of dropping the click", () => {
  const running = Array.from({ length: MAX_STORE_JOBS }, (_, i) => `r${i}`);
  const next = enqueueJobIds("wait", running, []);
  expect(next.launch).toBe(false);
  expect(next.running).toEqual(running);
  expect(next.queued).toEqual(["wait"]);
});

it("does not start the same voice twice", () => {
  expect(enqueueJobIds("a", ["a"], []).launch).toBe(false);
  expect(enqueueJobIds("a", [], ["a"]).launch).toBe(false);
});

it("uses store.downloadFailedNamed with voice name on download failure", async () => {
  (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
  tauri.invoke.mockRejectedValueOnce(new Error("timeout"));
  enqueueStoreDownload({ id: "voice-1", name: "测试音色", pack_url: "https://example.com/a.zip" });
  await new Promise((r) => setTimeout(r, 10));
  const diag = diagnosticOf(getStoreJobs().error);
  expect(diag?.title).toEqual({ key: "store.downloadFailedNamed", params: { name: "测试音色" } });
  expect(diag?.detail.text).toContain("timeout");
  delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
});
