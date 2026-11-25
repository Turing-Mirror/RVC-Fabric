import { beforeEach, expect, it, vi } from "vitest";
import { applyModelVersion, listModelVersions, type ModelVersions } from "./modelVersions";

const bridge = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: bridge.invoke }));
beforeEach(() => { bridge.invoke.mockReset(); });

it("lists an installed voice without changing the returned current state", async () => {
  const response: ModelVersions = { experiment: "voice", weights_dir: "weights", weights: [{
    kind: "rvc", current: { state: "source_removed", file: "voice_e2_s40.pth", epoch: 2, step: 40 }, versions: [],
  }] };
  bridge.invoke.mockResolvedValue(response);
  expect(await listModelVersions("models/voice")).toBe(response);
  expect(bridge.invoke).toHaveBeenCalledWith("model_versions_list", { target: "models/voice" });
});

it("passes the candidate filename and kind and surfaces native errors", async () => {
  bridge.invoke.mockRejectedValue("missing candidate");
  await expect(applyModelVersion("models/voice", "rvc", "voice_e2_s40.pth")).rejects.toMatchObject({ diagnostic: { scope: { feature: "importexport" }, detail: { text: "missing candidate" } } });
  expect(bridge.invoke).toHaveBeenCalledWith("model_version_apply", {
    target: "models/voice", kind: "rvc", file: "voice_e2_s40.pth",
  });
});
