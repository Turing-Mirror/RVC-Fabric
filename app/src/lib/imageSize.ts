/** Bound decoded output, including extremely narrow free-form selections. */
export function coverSize(width: number, height: number): [number, number] {
  const w = Math.max(1, width);
  const h = Math.max(1, height);
  const scale = Math.min(512 / Math.min(w, h), 2048 / Math.max(w, h));
  return [Math.max(1, Math.round(w * scale)), Math.max(1, Math.round(h * scale))];
}
