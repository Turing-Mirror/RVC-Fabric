import { describe, expect, it } from "vitest";
import { parseDevices, pickAutoDevices } from "./deviceSetup";

const STATUS = {
  hostapis: ["MME", "Windows WASAPI", "Windows DirectSound"],
  input_devices: [
    { name: "麦克风 (Realtek(R) Audio)", hostapi: "MME" },
    { name: "CABLE Output (VB-Audio Virtual Cable) (MME)", hostapi: "MME" },
    { name: "Microphone (NVIDIA Broadcast)", hostapi: "Windows WASAPI" },
  ],
  output_devices: [
    { name: "扬声器 (Realtek(R) Audio)", hostapi: "MME" },
    { name: "CABLE Input (VB-Audio Virtual Cable) (MME)", hostapi: "MME" },
  ],
};

describe("pickAutoDevices", () => {
  it("fills MME + mic + CABLE Input when everything is empty", () => {
    const pick = pickAutoDevices(
      { sg_hostapi: "", sg_input_device: "", sg_output_device: "" },
      STATUS,
    );
    expect(pick).not.toBeNull();
    expect(pick!.hostapi).toBe("MME");
    // 真麦克风优先，虚拟声卡的输出端（CABLE Output）不算麦克风。
    expect(pick!.input_device).toBe("麦克风 (Realtek(R) Audio)");
    expect(pick!.output_device).toBe("CABLE Input (VB-Audio Virtual Cable) (MME)");
  });

  it("keeps valid user choices untouched", () => {
    const pick = pickAutoDevices(
      {
        sg_hostapi: "Windows WASAPI",
        sg_input_device: "Microphone (NVIDIA Broadcast)",
        sg_output_device: "扬声器 (Realtek(R) Audio)",
      },
      STATUS,
    );
    expect(pick).toBeNull();
  });

  it("replaces only the field that went stale", () => {
    const pick = pickAutoDevices(
      {
        sg_hostapi: "MME",
        sg_input_device: "已经不存在的设备",
        sg_output_device: "CABLE Input (VB-Audio Virtual Cable) (MME)",
      },
      STATUS,
    );
    expect(pick).toEqual({ input_device: "麦克风 (Realtek(R) Audio)" });
  });

  it("does nothing without device lists", () => {
    expect(pickAutoDevices({}, undefined)).toBeNull();
    expect(pickAutoDevices({}, { input_devices: [], output_devices: [] })).toBeNull();
  });

  it("parses string and object entries alike", () => {
    expect(parseDevices(["a", { name: " b ", hostapi: "MME" }, null])).toEqual([
      { name: "a", hostapi: undefined },
      { name: "b", hostapi: "MME" },
    ]);
  });
});
