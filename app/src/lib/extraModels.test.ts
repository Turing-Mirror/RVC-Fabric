/**
 * C-06/C-07：文件名 → 用途展示名的集中适配。
 *
 * - 截图五项：HP3/HP4、去回声标准/强力、去回声与混响；
 * - 旧拼写别名（DeEcho / De-Echo）映射到同一名字；
 * - 同包多文件给出不重名选项；
 * - 未知本地模型原样返回文件名，不伪造用途、不显示翻译键。
 */
import { describe, expect, it } from "vitest";
import { extraModelLabel } from "./extraModels";

describe("extraModelLabel", () => {
  it("C8 验收五项：用途名 + 变体标识", () => {
    expect(extraModelLabel("3_HP-Vocal-UVR.pth")).toBe("人声提取（HP3）");
    expect(extraModelLabel("4_HP-Vocal-UVR.pth")).toBe("人声提取（HP4）");
    expect(extraModelLabel("UVR-De-Echo-Normal.pth")).toBe("去回声（标准）");
    expect(extraModelLabel("UVR-De-Echo-Aggressive.pth")).toBe("去回声（强力）");
    expect(extraModelLabel("UVR-DeEcho-DeReverb.pth")).toBe("去回声与混响");
  });

  it("旧拼写别名归一到同一名字", () => {
    expect(extraModelLabel("UVR-DeEcho-Normal.pth")).toBe(
      extraModelLabel("UVR-De-Echo-Normal.pth"),
    );
    expect(extraModelLabel("UVR-DeEcho-Aggressive.pth")).toBe(
      extraModelLabel("UVR-De-Echo-Aggressive.pth"),
    );
  });

  it("同包多文件的选项互不重名", () => {
    const names = [
      "7_HP2-UVR.pth",
      "8_HP2-UVR.pth",
      "9_HP2-UVR.pth",
    ].map(extraModelLabel);
    expect(new Set(names).size).toBe(3);
    names.forEach((n) => expect(n).toContain("HP2"));
  });

  it("单文件包直接用用途名", () => {
    expect(extraModelLabel("UVR-DeNoise.pth")).toBe("降噪");
    expect(extraModelLabel("UVR-DeNoise-Lite.pth")).toBe("降噪（轻量）");
  });

  it("未知本地模型保留原名，不出现翻译键", () => {
    expect(extraModelLabel("my-custom-model.pth")).toBe("my-custom-model.pth");
    expect(extraModelLabel("随便什么名字.pth")).toBe("随便什么名字.pth");
  });
});
