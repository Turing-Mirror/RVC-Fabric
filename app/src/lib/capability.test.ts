/**
 * C-05 安装前能力说明：只写有依据的结论，检测不到的标「未知」，
 * 实时性能一律标待实测。
 */
import { describe, expect, it } from "vitest";
import { capabilityLines } from "./engine";

const base = {
  cpu_name: "Intel Core i5-9400",
  memory_gb: 16,
  gpus: ["NVIDIA GeForce RTX 3060"],
  nvidia_gpus: ["NVIDIA GeForce RTX 3060"],
};

describe("capabilityLines", () => {
  it("reports detected cpu, memory and gpu plus the untested note", () => {
    const lines = capabilityLines(base, "nvidia");
    expect(lines[0]).toContain("i5-9400");
    expect(lines[0]).toContain("16");
    expect(lines[0]).toContain("RTX 3060");
    expect(lines[lines.length - 1]).toContain("实测");
    expect(lines.length).toBe(2); // 检测行 + 待实测行，无额外警告
  });

  it("nvidia variant without an nvidia gpu warns but stays installable", () => {
    const lines = capabilityLines(
      { ...base, gpus: ["Intel UHD 630"], nvidia_gpus: [] },
      "nvidia",
    );
    expect(lines.some((l) => l.includes("NVIDIA") && l.includes("CPU"))).toBe(
      true,
    );
    expect(lines[lines.length - 1]).toContain("实测");
  });

  it("no gpu at all falls back to the cpu wording", () => {
    const lines = capabilityLines({ ...base, gpus: [], nvidia_gpus: [] }, "amd");
    expect(lines.some((l) => l.includes("CPU"))).toBe(true);
    // 选 amd 包但没显卡：先「需要显卡」警告，不跳过。
    expect(lines.some((l) => l.includes("显卡"))).toBe(true);
  });

  it("unknown hardware is reported as unknown, never invented", () => {
    const lines = capabilityLines(
      { cpu_name: "", memory_gb: 0, gpus: [], nvidia_gpus: [] },
      "nvidia",
    );
    expect(lines[0]).toContain("未知");
    expect(lines[0]).not.toMatch(/\d+(\.\d+)?\s*GB/);
  });
});
