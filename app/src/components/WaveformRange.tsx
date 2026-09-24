import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  columnAmplitudes,
  fitPxPerSec,
  MAX_PX_PER_SEC,
  scrollAfterZoom,
  timeAtX,
  waveformWidth,
  xAtTime,
  zoomPxPerSec,
} from "../lib/waveformView";

const HEIGHT = 160;
const MAX_WIDTH = 5_000_000;

type Props = {
  duration: number;
  peaks: number[];
  start: number;
  end: number;
  currentTime?: number;
  playing?: boolean;
  disabled?: boolean;
  label: string;
  onRangeChange: (start: number, end: number) => void;
};

/** One viewport-sized canvas over a scrollable timeline; never allocates a whole-song bitmap. */
export function WaveformRange({ duration, peaks, start, end, currentTime, playing, disabled, label, onRangeChange }: Props) {
  const scroll = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const dragStart = useRef<number | null>(null);
  const pendingScroll = useRef<number | null>(null);
  const scaleRef = useRef(0);
  const [viewWidth, setViewWidth] = useState(720);
  const [scrollLeft, setScrollLeft] = useState(0);
  const [pxPerSec, setPxPerSec] = useState(0);

  useEffect(() => {
    const el = scroll.current;
    if (!el) return;
    const update = () => setViewWidth(Math.max(1, el.clientWidth));
    update();
    if (typeof ResizeObserver !== "undefined") {
      const observer = new ResizeObserver(update);
      observer.observe(el);
      return () => observer.disconnect();
    }
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  const fit = fitPxPerSec(duration, viewWidth);
  const maxScale = Math.min(MAX_PX_PER_SEC, MAX_WIDTH / Math.max(duration, 0.001));
  const scale = Math.min(pxPerSec || fit, maxScale);
  const width = waveformWidth(duration, scale);
  scaleRef.current = scale;

  useEffect(() => {
    const el = scroll.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      if (!duration) return;
      // Shift+wheel, or a sideways trackpad swipe, pans instead of zooming.
      if (event.shiftKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
        event.preventDefault();
        el.scrollLeft += event.shiftKey ? event.deltaY || event.deltaX : event.deltaX;
        return;
      }
      event.preventDefault();
      const oldScale = scaleRef.current || fit;
      // Line-based wheels (deltaMode 1) report rows, not pixels.
      const delta = event.deltaMode === 1 ? event.deltaY * 40 : event.deltaY;
      const next = Math.min(maxScale, zoomPxPerSec(oldScale, delta, fit));
      const cursor = event.clientX - el.getBoundingClientRect().left;
      pendingScroll.current = scrollAfterZoom(el.scrollLeft, cursor, waveformWidth(duration, oldScale), waveformWidth(duration, next));
      setPxPerSec(next);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [duration, fit, maxScale]);

  useLayoutEffect(() => {
    if (pendingScroll.current == null || !scroll.current) return;
    scroll.current.scrollLeft = pendingScroll.current;
    setScrollLeft(scroll.current.scrollLeft);
    pendingScroll.current = null;
  }, [width]);

  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    el.width = Math.ceil(viewWidth * dpr);
    el.height = Math.ceil(HEIGHT * dpr);
    const ctx = el.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const css = getComputedStyle(document.documentElement);
    const surface = css.getPropertyValue("--surface").trim() || "#ffffff";
    const meta = css.getPropertyValue("--meta").trim() || "#9aa7b2";
    const accent = css.getPropertyValue("--accent").trim() || "#53b9dc";
    ctx.fillStyle = surface;
    ctx.fillRect(0, 0, viewWidth, HEIGHT);
    ctx.strokeStyle = meta;
    ctx.beginPath();
    ctx.moveTo(0, HEIGHT / 2 + 0.5);
    ctx.lineTo(viewWidth, HEIGHT / 2 + 0.5);
    ctx.stroke();
    if (!duration || !peaks.length) return;

    const left = xAtTime(start, duration, width) - scrollLeft;
    const right = xAtTime(end, duration, width) - scrollLeft;
    ctx.fillStyle = "rgba(20, 26, 33, 0.12)";
    ctx.fillRect(0, 0, Math.max(0, left), HEIGHT);
    ctx.fillRect(Math.max(0, right), 0, Math.max(0, viewWidth - right), HEIGHT);
    const amps = columnAmplitudes(peaks, width, scrollLeft, viewWidth);
    const scaleY = HEIGHT * 0.44 / 255;
    const fillEnvelope = (color: string) => {
      ctx.beginPath();
      ctx.moveTo(0, HEIGHT / 2);
      for (let x = 0; x < amps.length; x += 1) ctx.lineTo(x + 0.5, HEIGHT / 2 - Math.max(0.5, amps[x] * scaleY));
      for (let x = amps.length - 1; x >= 0; x -= 1) ctx.lineTo(x + 0.5, HEIGHT / 2 + Math.max(0.5, amps[x] * scaleY));
      ctx.closePath();
      ctx.fillStyle = color;
      ctx.fill();
    };
    fillEnvelope(meta);
    if (right > left) {
      ctx.save();
      ctx.beginPath();
      ctx.rect(left, 0, right - left, HEIGHT);
      ctx.clip();
      fillEnvelope(accent);
      ctx.restore();
    }
    ctx.fillStyle = accent;
    if (left >= 0 && left < viewWidth) ctx.fillRect(left - 1, 0, 2, HEIGHT);
    if (right >= 0 && right < viewWidth) ctx.fillRect(right - 1, 0, 2, HEIGHT);
    if (currentTime != null && Number.isFinite(currentTime)) {
      const head = xAtTime(currentTime, duration, width) - scrollLeft;
      if (head >= 0 && head < viewWidth) {
        ctx.fillStyle = css.getPropertyValue("--ink").trim() || "#222";
        ctx.fillRect(head, 0, 1, HEIGHT);
      }
    }
  }, [currentTime, duration, end, peaks, scrollLeft, start, viewWidth, width]);

  useEffect(() => {
    const el = scroll.current;
    if (!el || !playing || !duration || currentTime == null) return;
    const x = xAtTime(currentTime, duration, width);
    if (x < el.scrollLeft + 32 || x > el.scrollLeft + el.clientWidth - 32) {
      el.scrollLeft = Math.max(0, x - el.clientWidth / 3);
    }
  }, [currentTime, duration, playing, width]);

  const timeAt = (clientX: number) => {
    const rect = canvas.current?.getBoundingClientRect();
    if (!rect || !duration) return 0;
    return timeAtX(scrollLeft + clientX - rect.left, duration, width);
  };

  return <div ref={scroll} onScroll={(event) => setScrollLeft(event.currentTarget.scrollLeft)}
    className="max-w-full overflow-x-auto rounded-[var(--rs)] border border-[var(--hairline)] bg-[var(--surface)]">
    <div className="relative" style={{ width, height: HEIGHT }}>
      <canvas ref={canvas} role="img" aria-label={label} width={viewWidth} height={HEIGHT}
        className="block cursor-crosshair touch-none" style={{ position: "absolute", left: scrollLeft, width: viewWidth, height: HEIGHT }}
        onPointerDown={(event) => {
          if (disabled || !duration) return;
          const time = timeAt(event.clientX);
          dragStart.current = time;
          onRangeChange(time, time);
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          if (dragStart.current == null) return;
          const time = timeAt(event.clientX);
          onRangeChange(Math.min(dragStart.current, time), Math.max(dragStart.current, time));
        }}
        onPointerUp={(event) => {
          dragStart.current = null;
          if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
        }}
        onPointerCancel={(event) => {
          dragStart.current = null;
          if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
        }} />
    </div>
  </div>;
}
