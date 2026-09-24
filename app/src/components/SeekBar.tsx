import { useState, type KeyboardEvent, type PointerEvent } from "react";

type Props = {
  label: string;
  /** Position and length in seconds. */
  position: number;
  length: number;
  disabled?: boolean;
  /** Arrow keys move by this many seconds. */
  step?: number;
  onSeek: (seconds: number) => void;
};

/** Thin progress bar that can be dragged; only the release commits a seek. */
export function SeekBar({ label, position, length, disabled, step = 1, onSeek }: Props) {
  const [drag, setDrag] = useState<number | null>(null);
  const shown = drag ?? position;
  const ratio = length > 0 ? Math.min(1, Math.max(0, shown / length)) : 0;
  const at = (event: PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return rect.width > 0 ? Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)) * length : 0;
  };
  const inactive = disabled || !(length > 0);

  return <div role="slider" aria-label={label} tabIndex={inactive ? -1 : 0}
    aria-valuemin={0} aria-valuemax={length} aria-valuenow={Math.min(shown, length)} aria-disabled={inactive}
    className={`group relative h-3 flex items-center touch-none ${inactive ? "" : "cursor-pointer"}`}
    onPointerDown={(event) => {
      if (inactive) return;
      event.currentTarget.setPointerCapture(event.pointerId);
      setDrag(at(event));
    }}
    onPointerMove={(event) => { if (drag != null) setDrag(at(event)); }}
    onPointerUp={(event) => {
      if (drag == null) return;
      const target = at(event);
      setDrag(null);
      onSeek(target);
    }}
    onPointerCancel={() => setDrag(null)}
    onKeyDown={(event: KeyboardEvent<HTMLDivElement>) => {
      if (inactive) return;
      const delta = event.key === "ArrowRight" ? step : event.key === "ArrowLeft" ? -step : 0;
      if (!delta) return;
      event.preventDefault();
      onSeek(Math.min(length, Math.max(0, position + delta)));
    }}>
    <div className="h-1.5 w-full rounded-full bg-[var(--line)] overflow-hidden">
      <div className="h-full bg-[var(--accent)]" style={{ width: `${ratio * 100}%` }} />
    </div>
    {inactive ? null : <div className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--accent)] opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
      style={{ left: `${ratio * 100}%`, opacity: drag != null ? 1 : undefined }} />}
  </div>;
}
