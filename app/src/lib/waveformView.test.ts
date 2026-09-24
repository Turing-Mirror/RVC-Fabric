import { expect, it } from "vitest";
import {
  clampPxPerSec,
  columnAmplitudes,
  fitPxPerSec,
  scrollAfterZoom,
  timeAtX,
  waveformWidth,
  xAtTime,
  zoomPxPerSec,
  MAX_PX_PER_SEC,
  MIN_PX_PER_SEC,
} from "./waveformView";

it("fits the whole clip in the container instead of a fixed pixel-per-second scale", () => {
  expect(fitPxPerSec(10, 800)).toBe(80);
  expect(fitPxPerSec(10, 20)).toBe(MIN_PX_PER_SEC);
  expect(fitPxPerSec(0.01, 8000)).toBe(MAX_PX_PER_SEC);
});

it("zooms in and out around the current scale and stays in range", () => {
  const minFit = 40;
  expect(zoomPxPerSec(80, -1, minFit)).toBeGreaterThan(80);
  expect(zoomPxPerSec(80, 1, minFit)).toBeLessThan(80);
  // One mouse notch zooms noticeably; a fine trackpad step only slightly.
  expect(zoomPxPerSec(80, -100, minFit)).toBeGreaterThan(100);
  expect(zoomPxPerSec(80, -4, minFit)).toBeLessThan(82);
  expect(zoomPxPerSec(80, -10000, minFit)).toBe(160);
  expect(clampPxPerSec(1, minFit)).toBe(minFit);
  expect(clampPxPerSec(9999, minFit)).toBe(MAX_PX_PER_SEC);
});

it("keeps the cursor's time still when the waveform grows", () => {
  expect(scrollAfterZoom(100, 50, 400, 800)).toBe(250);
  expect(waveformWidth(10, 80)).toBe(800);
  expect(timeAtX(400, 10, 800)).toBe(5);
  expect(xAtTime(5, 10, 800)).toBe(400);
});

it("keeps the envelope continuous when zoomed past the peak density", () => {
  const zoomedIn = columnAmplitudes([0, 200], 20, 0, 20);
  expect(Array.from(zoomedIn).every((v, i, all) => i === 0 || v >= all[i - 1])).toBe(true);
  expect(zoomedIn[10]).toBeGreaterThan(0);
  expect(zoomedIn[19]).toBe(200);
  expect(Array.from(columnAmplitudes([10, 90, 30, 5], 2, 0, 2))).toEqual([90, 30]);
  expect(Array.from(columnAmplitudes([10, 90, 30, 5], 2, 1, 2))).toEqual([30, 0]);
});
