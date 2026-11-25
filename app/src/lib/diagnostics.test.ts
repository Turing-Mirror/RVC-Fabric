
import { beforeEach, expect, it, vi } from "vitest";
import { setTLocale } from "../i18n/t";
import { actionsFor, contentFor, diagnosticOf, diagnosticPayload, errorWithTitle, legacyDiagnostic } from "./diagnostics";
import { invoke, invokeFor } from "./invoke";
const bridge = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: bridge.invoke }));
beforeEach(() => { setTLocale("zh-CN"); bridge.invoke.mockReset(); });
it("keeps raw legacy evidence out of the primary copy", () => {
  const raw = "train.py exited 1\nValueError: unknown failure";
  const content = contentFor(raw, "training");
  expect(content.title).toBe("训练未能完成。");
  expect(content.cause).toBe("暂时无法判断原因。");
  expect(content.steps?.length).toBeGreaterThan(0);
  expect(content.detail).toBe(raw);
  expect(content.copy).toContain(raw);
  expect(content.title).not.toContain("train.py");
});
it("wraps a failed bridge locally and preserves a diagnostic from Rust", async () => {
  bridge.invoke.mockRejectedValueOnce("runtime failed");
  await expect(invoke("train_queue_add", { req: {} })).rejects.toMatchObject({
    diagnostic: { scope: { feature: "training" }, code: "diag.unknown", detail: { text: "runtime failed" } },
  });
  expect(bridge.invoke).toHaveBeenCalledTimes(1);
  const diagnostic = legacyDiagnostic("raw", "training");
  diagnostic.error_id = "run-1";
  bridge.invoke.mockRejectedValueOnce({ diagnostic, message: "legacy" });
  try { await invoke("train_queue_add"); } catch (error) {
    expect(diagnosticOf(error)?.error_id).toBe("run-1");
  }
});
it("only renders supported actions and propagates their rejection", async () => {
  const diagnostic = legacyDiagnostic("raw");
  diagnostic.actions = [{ id: "open_help", params: { section: "train" } }, { id: "unsupported", params: {} }];
  const failed = vi.fn().mockRejectedValue(new Error("window unavailable"));
  const actions = actionsFor(diagnostic, { open_help: failed });
  expect(actions).toHaveLength(1);
  await expect(actions[0].run()).rejects.toThrow("window unavailable");
  expect(failed).toHaveBeenCalledWith({ section: "train" });
});
it("preserves normal IPC objects and carries item diagnostics into legacy state", () => {
  const normal = { jobs: [{ id: "1", state: "done" }] };
  expect(diagnosticPayload(normal)).toBe(normal);
  const diagnostic = legacyDiagnostic("decoder error", "voicechange");
  const result = diagnosticPayload({ skipped: [{ reason: "legacy", diagnostic }] });
  expect(diagnosticOf(result.skipped[0].reason)?.error_id).toBe(diagnostic.error_id);
});
it("preserves diagnosed cause, steps and detail when overriding the title", () => {
  const diagnosed = {
    ...legacyDiagnostic("WinError 5: access denied", "training"),
    code: "diag.access_denied",
    confidence: "confirmed" as const,
    cause: { key: "diag.cause.accessDenied", params: {} },
    steps: [{ key: "diag.step.permission", params: {} }],
  };
  const wrapped = errorWithTitle(diagnosed, "s.storageScanFailed", "other");
  const content = contentFor(wrapped, "other");
  expect(content.title).toBe("存储信息刷新失败，请重新统计。");
  expect(content.cause).not.toBe("暂时无法判断原因。");
  expect(content.steps).toHaveLength(1);
  expect(content.detail).toContain("WinError 5");
  expect(content.copy).toContain("存储信息刷新失败，请重新统计。");
  expect(content.copy).toContain("WinError 5");
});
it("overrides misleading command-prefix features on invokeFor even for Rust diagnostics", async () => {
  const rustDiag = legacyDiagnostic("permission denied", "training");
  rustDiag.code = "diag.access_denied";
  rustDiag.cause = { key: "diag.cause.accessDenied", params: {} };
  bridge.invoke.mockRejectedValueOnce({ diagnostic: rustDiag });
  try {
    await invokeFor("other", "train_cleanup_scan");
    expect.unreachable();
  } catch (error) {
    const d = diagnosticOf(error);
    expect(d?.scope.feature).toBe("other");
    expect(d?.title.key).toBe("diag.title.other");
    expect(d?.cause?.key).toBe("diag.cause.accessDenied");
  }
});
