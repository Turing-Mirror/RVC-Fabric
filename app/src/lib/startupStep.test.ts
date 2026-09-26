import { describe, expect, it } from "vitest";
import { STARTUP_STEPS, startupStep } from "./engine";

describe("开启变声按步显示", () => {
  it("按引擎报的阶段码落到对应的一步", () => {
    expect(startupStep({ state: "starting", message_code: "engine.launching" })?.index).toBe(0);
    expect(startupStep({ state: "starting", message_code: "engine.importing" })?.index).toBe(1);
    expect(startupStep({ state: "starting", message_code: "vc.loading_index" })?.index).toBe(2);
    expect(startupStep({ state: "starting", message_code: "vc.warmup" })?.index).toBe(3);
    expect(startupStep({ state: "starting", message_code: "vc.opening_stream" })).toEqual({
      index: 4,
      count: STARTUP_STEPS.length,
      labelKey: "dock.stepStream",
    });
  });

  it("切换音色、已在变声、空闲时不按步显示", () => {
    expect(startupStep({ state: "running", message_code: "vc.swapping" })).toBeNull();
    expect(startupStep({ state: "running", message_code: "vc.loading_model" })).toBeNull();
    expect(startupStep({ state: "idle", message_code: "engine.importing" })).toBeNull();
  });

  it("刚开始启动、还没有阶段码时停在第一步", () => {
    expect(startupStep({ state: "starting" })?.index).toBe(0);
  });
});
