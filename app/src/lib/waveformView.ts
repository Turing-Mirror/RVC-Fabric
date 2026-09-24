export const MIN_PX_PER_SEC = 8;
export const MAX_PX_PER_SEC = 4000;

/** Pixels per second that fit the whole clip in the container. */
export function fitPxPerSec(duration: number, containerWidth: number): number {
  const d = Math.max(duration, 0.001);
  const w = Math.max(containerWidth, 1);
  return Math.min(MAX_PX_PER_SEC, Math.max(MIN_PX_PER_SEC, w / d));
}

export function clampPxPerSec(value: number, minFit: number): number {
  return Math.min(MAX_PX_PER_SEC, Math.max(minFit, value));
}

/** Wheel distance (pixels) that doubles or halves the zoom; one mouse notch is about 100. */
export const ZOOM_DOUBLING_DELTA = 250;

/** `deltaY < 0` zooms in, proportionally to how far the wheel moved. */
export function zoomPxPerSec(current: number, deltaY: number, minFit: number): number {
  const factor = Math.min(2, Math.max(0.5, 2 ** (-deltaY / ZOOM_DOUBLING_DELTA)));
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

/**
 * Amplitude (0-255) for each pixel column of the visible window. Zoomed out, a
 * column takes the loudest bin it covers; zoomed in past the bin density, it
 * interpolates between neighbours so the envelope stays continuous.
 */
export function columnAmplitudes(
  peaks: ArrayLike<number>,
  width: number,
  scrollLeft: number,
  viewWidth: number,
): Float32Array {
  const columns = Math.max(0, Math.ceil(viewWidth));
  const out = new Float32Array(columns);
  const n = peaks.length;
  if (!n || width <= 0) return out;
  const binsPerPx = n / width;
  for (let x = 0; x < columns; x += 1) {
    const from = (scrollLeft + x) * binsPerPx;
    const to = from + binsPerPx;
    if (from >= n || to <= 0) continue;
    if (binsPerPx >= 1) {
      let peak = 0;
      const last = Math.min(n, Math.ceil(to));
      for (let i = Math.max(0, Math.floor(from)); i < last; i += 1) peak = Math.max(peak, peaks[i]);
      out[x] = peak;
    } else {
      const at = Math.max(0, Math.min(n - 1, (from + to) / 2 - 0.5));
      const i = Math.floor(at);
      const j = Math.min(n - 1, i + 1);
      out[x] = peaks[i] + (peaks[j] - peaks[i]) * (at - i);
    }
  }
  return out;
}
