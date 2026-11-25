import { describe, expect, it } from "vitest";
import { classifyTrouble } from "./trouble";
import { legacyDiagnostic } from "./diagnostics";

describe("classifyTrouble", () => {
  it("does not re-diagnose legacy exception keywords", () => {
    for (const text of ["CUDA out of memory", "PortAudio Invalid device", "runtime.not_ready"]) {
      expect(classifyTrouble(text)).toBe("unknown");
    }
  });
  it("uses the diagnostic action and identity", () => {
    const diagnostic = legacyDiagnostic("raw");
    diagnostic.actions = [{ id: "open_device_settings", params: {} }];
    expect(classifyTrouble(diagnostic)).toBe("devices");
    diagnostic.actions = [];
    diagnostic.code = "diag.oom_gpu";
    expect(classifyTrouble(diagnostic)).toBe("vram");
  });
});
