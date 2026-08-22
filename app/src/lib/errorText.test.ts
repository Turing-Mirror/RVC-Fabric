import { describe, expect, it } from "vitest";
import { splitErrorText } from "./errorText";

const GRAD_MULTIPLY = `Traceback (most recent call last):
  File "D:\\\\RVC Fabric\\\\infer\\\\modules\\\\vc\\\\modules.py", line 206, in vc_single
    audio_opt = self.pipeline.pipeline(
  File "D:\\\\RVC Fabric\\\\Runtime\\\\lib\\\\site-packages\\\\fairseq\\\\modules\\\\grad_multiply.py", line 13, in forward
    res = x.new(x)
RuntimeError: new(): expected key in DispatchKeySet(CPU, CUDA, HIP, XLA, MPS, IPU, XPU, HPU, Lazy, Meta) but got: PrivateUse1`;

describe("splitErrorText", () => {
  it("uses the last real error line as the headline for a traceback", () => {
    const { head, detail, hasMore } = splitErrorText(GRAD_MULTIPLY);
    expect(head).toContain("PrivateUse1");
    expect(head).not.toMatch(/^Traceback/);
    expect(hasMore).toBe(true);
    expect(detail).toContain("Traceback");
    expect(detail).toContain("PrivateUse1");
  });

  it("keeps a friendly multi-line message as first-line + rest", () => {
    const { head, detail, hasMore } = splitErrorText(
      "显存不够（CUDA OOM）。\n请先停止变声再试。",
    );
    expect(head).toBe("显存不够（CUDA OOM）。");
    expect(detail).toBe("请先停止变声再试。");
    expect(hasMore).toBe(true);
  });

  it("leaves a single line alone", () => {
    const { head, detail, hasMore } = splitErrorText("找不到音色模型");
    expect(head).toBe("找不到音色模型");
    expect(detail).toBe("");
    expect(hasMore).toBe(false);
  });
});
