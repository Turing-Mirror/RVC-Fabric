import { expect, it } from "vitest";
import { placePopup } from "./popupPos";

const btn = (x: number, y: number, w = 32, h = 28) => ({
  left: x,
  right: x + w,
  top: y,
  bottom: y + h,
});

it("aligns to the trigger right edge and opens below when there is room", () => {
  const box = placePopup(btn(800, 40), { width: 200, height: 240 }, { width: 1100, height: 700 });
  expect(box.left).toBe(800 + 32 - 200);
  expect(box.top).toBe(40 + 28 + 6);
});

it("keeps the menu inside a small window instead of clipping", () => {
  const box = placePopup(btn(20, 500), { width: 220, height: 320 }, { width: 360, height: 560 });
  expect(box.left).toBeGreaterThanOrEqual(8);
  expect(box.left + 220).toBeLessThanOrEqual(360 - 8);
  expect(box.top).toBeGreaterThanOrEqual(8);
  expect(box.top + Math.min(320, box.maxHeight)).toBeLessThanOrEqual(560 - 8);
});

it("opens above the trigger when the window is too short below", () => {
  const box = placePopup(btn(100, 520), { width: 180, height: 200 }, { width: 800, height: 580 });
  expect(box.top + 200).toBeLessThanOrEqual(520);
  expect(box.top).toBeGreaterThanOrEqual(8);
});

it("caps height when the menu is taller than the window", () => {
  const box = placePopup(btn(40, 40), { width: 180, height: 2000 }, { width: 400, height: 300 });
  expect(box.maxHeight).toBe(300 - 16);
  expect(box.top).toBe(8);
});
