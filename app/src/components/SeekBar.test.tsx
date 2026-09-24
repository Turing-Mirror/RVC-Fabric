// @vitest-environment happy-dom
import { act } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { mount, type Mounted } from "../test/dom";
import { SeekBar } from "./SeekBar";

let mounted: Mounted | null = null;

afterEach(() => {
  mounted?.unmount();
  mounted = null;
});

function slider(): HTMLElement {
  const el = mounted!.container.querySelector<HTMLElement>("[role=slider]")!;
  el.getBoundingClientRect = () => ({ left: 100, width: 200, top: 0, height: 12, right: 300, bottom: 12, x: 100, y: 0, toJSON: () => ({}) });
  el.setPointerCapture = () => {};
  return el;
}

function pointer(el: HTMLElement, type: string, clientX: number) {
  act(() => {
    el.dispatchEvent(new PointerEvent(type, { bubbles: true, clientX, pointerId: 1 }));
  });
}

it("commits one seek on release at the dragged position", () => {
  const onSeek = vi.fn();
  mounted = mount(<SeekBar label="clip" position={1} length={10} onSeek={onSeek} />);
  const el = slider();
  pointer(el, "pointerdown", 120);
  pointer(el, "pointermove", 200);
  expect(onSeek).not.toHaveBeenCalled();
  expect(el.getAttribute("aria-valuenow")).toBe("5");
  pointer(el, "pointerup", 250);
  expect(onSeek).toHaveBeenCalledTimes(1);
  expect(onSeek).toHaveBeenCalledWith(7.5);
});

it("steps with arrow keys and ignores input while disabled", () => {
  const onSeek = vi.fn();
  mounted = mount(<SeekBar label="clip" position={4} length={10} onSeek={onSeek} />);
  act(() => {
    slider().dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));
  });
  expect(onSeek).toHaveBeenCalledWith(3);
  mounted.unmount();
  const blocked = vi.fn();
  mounted = mount(<SeekBar label="clip" position={4} length={10} disabled onSeek={blocked} />);
  pointer(slider(), "pointerdown", 150);
  pointer(slider(), "pointerup", 150);
  expect(blocked).not.toHaveBeenCalled();
});
