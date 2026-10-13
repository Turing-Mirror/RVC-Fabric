// @vitest-environment happy-dom
/**
 * C-04 FLIP 位置过渡：delta 计算与残余位移读取。
 */
import { act, createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, type Mounted } from "../test/dom";
import { flipDelta, flipTransform, parseTransform, useFlipRow, type FlipBox } from "./flip";

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
    expect(parseTransform("none")).toEqual({ x: 0, y: 0, scaleX: 1, scaleY: 1 });
    expect(parseTransform("")).toEqual({ x: 0, y: 0, scaleX: 1, scaleY: 1 });
    expect(parseTransform("matrix(1, 0, 0, 1, -320, 0)")).toEqual({
      x: -320,
      y: 0,
      scaleX: 1,
      scaleY: 1,
    });
    expect(parseTransform("translate(-320px, 0px)")).toEqual({
      x: -320,
      y: 0,
      scaleX: 1,
      scaleY: 1,
    });
    expect(
      parseTransform("matrix3d(1,0,0,0,0,1,0,0,0,0,1,0,-40,60,0,1)"),
    ).toEqual({ x: -40, y: 60, scaleX: 1, scaleY: 1 });
  });

  it("keeps scale when a size animation is interrupted", () => {
    expect(parseTransform("matrix(0.8, 0, 0, 0.9, -80, 4)")).toEqual({
      x: -80, y: 4, scaleX: 0.8, scaleY: 0.9,
    });
    expect(flipTransform(
      { x: 300, y: 0, width: 280, height: 330 },
      { x: 0, y: 20, width: 240, height: 290 },
      { x: -60, y: 5, scaleX: 0.9, scaleY: 0.95 },
    )).toEqual({ x: 240, y: -15, scaleX: 1.05, scaleY: 313.5 / 290 });
  });
});

describe("useFlipRow animation lifecycle", () => {
  const mounts: Mounted[] = [];
  const geometry = new Map<string, FlipBox>();
  const transforms = new Map<string, string>();
  const animateDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "animate");
  type StubAnimation = { cancel: ReturnType<typeof vi.fn>; onfinish: (() => void) | null; oncancel: (() => void) | null };
  let animations: StubAnimation[];
  let animate: ReturnType<typeof vi.fn>;
  let reduce: boolean;

  function Probe({ keys, stamp }: { keys: string[]; stamp: number }) {
    const ref = useFlipRow<HTMLDivElement>();
    return createElement("div", { ref }, keys.map((key) =>
      createElement("button", { key, "data-flip": key }, `${key}:${stamp}`)));
  }
  function render(m: Mounted, stamp: number, keys = ["a", "b"]) {
    act(() => m.root.render(createElement(Probe, { keys, stamp })));
  }
  function start() {
    const m = mount(createElement(Probe, { keys: ["a", "b"], stamp: 0 }));
    mounts.push(m);
    return m;
  }
  function move() {
    geometry.set("a", { x: 300, y: 0, width: 280, height: 330 });
    geometry.set("b", { x: 0, y: 20, width: 240, height: 290 });
  }

  beforeEach(() => {
    reduce = false;
    animations = [];
    geometry.clear();
    transforms.clear();
    geometry.set("a", { x: 0, y: 20, width: 240, height: 290 });
    geometry.set("b", { x: 280, y: 0, width: 280, height: 330 });
    for (const [property, field] of [
      ["offsetLeft", "x"], ["offsetTop", "y"], ["offsetWidth", "width"], ["offsetHeight", "height"],
    ] as const) {
      vi.spyOn(HTMLElement.prototype, property, "get").mockImplementation(function (this: HTMLElement) {
        return geometry.get(this.dataset.flip || "")?.[field] ?? 0;
      });
    }
    vi.spyOn(window, "matchMedia").mockImplementation(() => ({ matches: reduce }) as MediaQueryList);
    vi.stubGlobal("getComputedStyle", (node: HTMLElement) => ({
      transform: transforms.get(node.dataset.flip || "") || "none",
    }));
    animate = vi.fn(() => {
      const animation: StubAnimation = {
        cancel: vi.fn(() => animation.oncancel?.()), onfinish: null, oncancel: null,
      };
      animations.push(animation);
      return animation;
    });
    Object.defineProperty(HTMLElement.prototype, "animate", { configurable: true, writable: true, value: animate });
  });

  afterEach(() => {
    while (mounts.length) mounts.pop()?.unmount();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    if (animateDescriptor) Object.defineProperty(HTMLElement.prototype, "animate", animateDescriptor);
    else Reflect.deleteProperty(HTMLElement.prototype, "animate");
  });

  it("combines movement and size change into a single animation", () => {
    const m = start();
    expect(animate).not.toHaveBeenCalled();
    move();
    render(m, 1);
    expect(animate).toHaveBeenCalledTimes(2);
    expect(animate.mock.calls[0][0]).toEqual([
      { transform: `translate(-300px, 20px) scale(${240 / 280}, ${290 / 330})`, transformOrigin: "0 0" },
      { transform: "none", transformOrigin: "0 0" },
    ]);
  });

  it("does not restart an in-flight animation on an ordinary state refresh", () => {
    const m = start();
    move();
    render(m, 1);
    transforms.set("a", "matrix(0.9, 0, 0, 0.95, -80, 4)");
    transforms.set("b", "matrix(1.1, 0, 0, 1.05, 80, -4)");
    render(m, 2);
    render(m, 3);
    expect(animate).toHaveBeenCalledTimes(2);
    expect(animations[0].cancel).not.toHaveBeenCalled();
  });

  it("does not add a settling animation after completion", () => {
    const m = start();
    move();
    render(m, 1);
    animations.forEach((animation) => animation.onfinish?.());
    render(m, 2);
    expect(animate).toHaveBeenCalledTimes(2);
  });

  it("continues from the current visual size and position on rapid switching", () => {
    const m = start();
    move();
    render(m, 1);
    const old = animations[0];
    transforms.set("a", "matrix(0.9, 0, 0, 0.95, -60, 5)");
    geometry.set("a", { x: 0, y: 20, width: 240, height: 290 });
    render(m, 2);
    expect(old.cancel).toHaveBeenCalledOnce();
    expect(animate.mock.calls[2][0][0]).toEqual({
      transform: `translate(240px, -15px) scale(1.05, ${313.5 / 290})`, transformOrigin: "0 0",
    });
    // A late callback from the old animation must not erase its replacement.
    old.onfinish?.();
    m.unmount();
    mounts.pop();
    expect(animations[2].cancel).toHaveBeenCalledOnce();
  });

  it("animates size changes even when the card does not move", () => {
    const m = start();
    geometry.set("a", { x: 0, y: 20, width: 280, height: 330 });
    render(m, 1);
    expect(animate).toHaveBeenCalledOnce();
    expect(animate.mock.calls[0][0][0].transform).toContain(`scale(${240 / 280}, ${290 / 330})`);
  });

  it("cancels animations for removed cards and on unmount", () => {
    const m = start();
    move();
    render(m, 1);
    render(m, 2, ["a"]);
    expect(animations[1].cancel).toHaveBeenCalledOnce();
    expect(animations[0].cancel).not.toHaveBeenCalled();
    m.unmount();
    mounts.pop();
    expect(animations[0].cancel).toHaveBeenCalledOnce();
  });

  it("ends active animations when reduced motion is enabled", () => {
    const m = start();
    move();
    render(m, 1);
    reduce = true;
    render(m, 2);
    expect(animate).toHaveBeenCalledTimes(2);
    expect(animations[0].cancel).toHaveBeenCalledOnce();
    expect(animations[1].cancel).toHaveBeenCalledOnce();
  });

  it("does not animate from or to an unmeasurable hidden card", () => {
    geometry.set("a", { x: 0, y: 0, width: 0, height: 0 });
    const m = start();
    geometry.set("a", { x: 0, y: 20, width: 240, height: 290 });
    render(m, 1);
    expect(animate).not.toHaveBeenCalled();
  });
});
