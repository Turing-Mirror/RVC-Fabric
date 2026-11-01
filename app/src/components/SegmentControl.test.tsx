// @vitest-environment happy-dom
import { act, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, type Mounted } from "../test/dom";
import { SegmentControl } from "./SegmentControl";

describe("SegmentControl 的指针收尾", () => {
  let mounted: Mounted | undefined;
  let now: number;
  let nextFrame: number;
  let frames: Map<number, FrameRequestCallback>;

  beforeEach(() => {
    now = 0;
    nextFrame = 0;
    frames = new Map();
    vi.spyOn(performance, "now").mockImplementation(() => now);
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      const id = ++nextFrame;
      frames.set(id, callback);
      return id;
    });
    vi.stubGlobal("cancelAnimationFrame", (id: number) => frames.delete(id));
    vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(100);
    vi.spyOn(HTMLElement.prototype, "offsetLeft", "get").mockImplementation(function (this: HTMLElement) {
      return 3 + (this.tagName === "BUTTON" ? Array.from(this.parentElement!.children).indexOf(this) * 100 : 0);
    });
  });

  afterEach(() => {
    mounted?.unmount();
    mounted = undefined;
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  function setup() {
    const changed = vi.fn();
    function Example() {
      const [value, setValue] = useState("a");
      return <SegmentControl options={[{ id: "a", label: "甲" }, { id: "b", label: "乙" }]} value={value} onChange={(id) => { changed(id); setValue(id); }} />;
    }
    mounted = mount(<Example />);
    const root = mounted.container.querySelector<HTMLElement>(".seg")!;
    const thumb = root.querySelector<HTMLElement>(".seg-thumb")!;
    vi.spyOn(thumb, "getBoundingClientRect").mockReturnValue({ left: 3, right: 103 } as DOMRect);
    root.setPointerCapture = vi.fn();
    return { root, changed };
  }

  function pointer(target: EventTarget, type: string, x = 50, id = 17) {
    now += 50;
    const event = new PointerEvent(type, { bubbles: true, pointerId: id, pointerType: "mouse", isPrimary: true, button: 0, clientX: x });
    Object.defineProperty(event, "timeStamp", { value: now });
    act(() => target.dispatchEvent(event));
  }

  function finishFrames() {
    act(() => {
      for (let i = 0; i < 240 && frames.size; i++) {
        now += 16;
        const callbacks = [...frames.values()];
        frames.clear();
        callbacks.forEach((callback) => callback(now));
      }
    });
  }

  it.each(["pointerup", "pointercancel"])("按下后直接移出控件，在外部 %s 后结束动画循环", (ending) => {
    const { root, changed } = setup();
    pointer(root, "pointerdown");
    pointer(document.body, "pointermove", 250);
    pointer(document.body, ending, 250);
    finishFrames();
    expect(changed).not.toHaveBeenCalled();
    expect(frames.size).toBe(0);
  });

  it("拖动时失去 pointer capture 也会落定选择并结束动画循环", () => {
    const { root, changed } = setup();
    pointer(root, "pointerdown");
    pointer(root, "pointermove", 140);
    expect(root.setPointerCapture).toHaveBeenCalledWith(17);
    pointer(root, "lostpointercapture", 140);
    finishFrames();
    expect(changed).toHaveBeenCalledExactlyOnceWith("b");
    expect(frames.size).toBe(0);
  });

  it("普通点击仍等滑块到达目标后才切换", () => {
    const { root, changed } = setup();
    act(() => root.querySelectorAll("button")[1].click());
    expect(changed).not.toHaveBeenCalled();
    finishFrames();
    finishFrames();
    expect(changed).toHaveBeenCalledExactlyOnceWith("b");
    expect(frames.size).toBe(0);
  });

  it("正常拖动松手只切换一次，随后丢失 capture 不会重复切换", () => {
    const { root, changed } = setup();
    pointer(root, "pointerdown");
    pointer(root, "pointermove", 140);
    pointer(root, "pointerup", 140);
    pointer(root, "lostpointercapture", 140);
    finishFrames();
    expect(changed).toHaveBeenCalledExactlyOnceWith("b");
    expect(frames.size).toBe(0);
  });

  it("卸载时移除外部松手监听并取消在途动画", () => {
    const { root, changed } = setup();
    pointer(root, "pointerdown");
    mounted!.unmount();
    mounted = undefined;
    pointer(window, "pointerup", 250);
    expect(changed).not.toHaveBeenCalled();
    expect(frames.size).toBe(0);
  });
});
