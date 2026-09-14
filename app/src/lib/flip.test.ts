// @vitest-environment happy-dom
/**
 * C-04 FLIP 位置过渡：delta 计算与残余位移读取。
 */
import { describe, expect, it } from "vitest";
import { flipDelta, parseTransform } from "./flip";

describe("flipDelta", () => {
  it("moves a card from its old spot to the new one", () => {
    // 侧边卡(左 0)升到中央(左 320)：先按 +320 反向平移，再播回 0。
    expect(flipDelta({ x: 0, y: 0 }, { x: 320, y: 0 }, { x: 0, y: 0 })).toEqual({
      x: -320,
      y: 0,
    });
  });

  it("wraps rows on the vertical axis too", () => {
    expect(flipDelta({ x: 100, y: 0 }, { x: 10, y: 220 }, { x: 0, y: 0 })).toEqual(
      { x: 90, y: -220 },
    );
  });

  it("continues mid-flight: residual transform folds into the next delta", () => {
    // 卡片还在从 0→320 的途中（残余 -120），又重排到 500：
    // 从当前视觉位置出发，不再跳回布局起点。
    expect(
      flipDelta({ x: 0, y: 0 }, { x: 500, y: 0 }, { x: -120, y: 0 }),
    ).toEqual({ x: -620, y: 0 });
  });
});

describe("parseTransform", () => {
  it("parses matrix(), translate() and none", () => {
    expect(parseTransform("none")).toEqual({ x: 0, y: 0 });
    expect(parseTransform("")).toEqual({ x: 0, y: 0 });
    expect(parseTransform("matrix(1, 0, 0, 1, -320, 0)")).toEqual({
      x: -320,
      y: 0,
    });
    expect(parseTransform("translate(-320px, 0px)")).toEqual({
      x: -320,
      y: 0,
    });
    expect(
      parseTransform("matrix3d(1,0,0,0,0,1,0,0,0,0,1,0,-40,60,0,1)"),
    ).toEqual({ x: -40, y: 60 });
  });
});
