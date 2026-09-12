export const MIN_PX_PER_SEC = 8;
export const MAX_PX_PER_SEC = 400;

/** Pixels per second that fit the whole clip in the container. */
export function fitPxPerSec(duration: number, containerWidth: number): number {
  const d = Math.max(duration, 0.001);
  const w = Math.max(containerWidth, 1);
  return Math.min(MAX_PX_PER_SEC, Math.max(MIN_PX_PER_SEC, w / d));
}

export function clampPxPerSec(value: number, minFit: number): number {
  return Math.min(MAX_PX_PER_SEC, Math.max(minFit, value));
}

/** `deltaY < 0` zooms in. */
export function zoomPxPerSec(current: number, deltaY: number, minFit: number): number {
  const factor = deltaY < 0 ? 1.15 : 1 / 1.15;
  return clampPxPerSec(current * factor, minFit);
}

export function waveformWidth(duration: number, pxPerSec: number): number {
  return Math.max(1, Math.ceil(Math.max(duration, 0) * pxPerSec));
}

/** Keep the point under the cursor still after a width change. */
export function scrollAfterZoom(
  scrollLeft: number,
  cursorInView: number,
  oldWidth: number,
  newWidth: number,
): number {
  const cursorInContent = scrollLeft + cursorInView;
  const ratio = oldWidth <= 0 ? 0 : cursorInContent / oldWidth;
  return Math.max(0, ratio * newWidth - cursorInView);
}

export function timeAtX(x: number, duration: number, width: number): number {
  if (width <= 0 || duration <= 0) return 0;
  const clamped = Math.max(0, Math.min(width, x));
  return (clamped / width) * duration;
}

export function xAtTime(time: number, duration: number, width: number): number {
  if (duration <= 0) return 0;
  return Math.max(0, Math.min(width, (time / duration) * width));
}
