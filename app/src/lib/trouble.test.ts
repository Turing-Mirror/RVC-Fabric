import { describe, expect, it } from "vitest";
import { classifyTrouble } from "./trouble";

describe("classifyTrouble", () => {
  it("recognises the common start failures", () => {
    expect(classifyTrouble("msg.vc.need_model")).toBe("voice");
    expect(classifyTrouble("runtime.not_ready")).toBe("runtime");
    expect(classifyTrouble("CUDA out of memory. Tried to allocate 20 MiB")).toBe("vram");
    expect(classifyTrouble("PortAudioError: Invalid device [PaErrorCode -9996]")).toBe("devices");
  });
  it("leaves anything else to the self-check", () => {
    expect(classifyTrouble("")).toBe("unknown");
    expect(classifyTrouble("Traceback: KeyError 'foo'")).toBe("unknown");
  });
});
