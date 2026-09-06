import { useEffect, useRef, useState } from "react";
import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { Btn } from "./ui";
import { useI18n } from "../i18n";
import { RangeBar } from "./controls";
import { SegmentControl } from "./SegmentControl";

type AudioTrimProps = {
  input: string;
  disabled: boolean;
  onApply: (path: string) => void;
};

export function canTrimAudio(input: string): boolean {
  return /\.(wav|mp3|flac|m4a|ogg|aac|opus)$/i.test(input);
}

export function AudioTrimButton({
  disabled,
  open,
  onClick,
}: {
  disabled: boolean;
  open: boolean;
  onClick: () => void;
}) {
  const { t } = useI18n();
  return <Btn disabled={disabled} on={open} onClick={onClick}>{t("neptune.trim")}</Btn>;
}

type EditMode = "keep" | "remove";

type AudioTrimEditorProps = AudioTrimProps & {
  onBusyChange?: (busy: boolean) => void;
};

const WAVE_HEIGHT = 160;

export function AudioTrimEditor({ input, disabled, onApply, onBusyChange }: AudioTrimEditorProps) {
  const { t } = useI18n();
  const audio = useRef<HTMLAudioElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const dragStart = useRef<number | null>(null);
  const [duration, setDuration] = useState(0);
  const [start, setStart] = useState(0);
  const [end, setEnd] = useState(0);
  const [peaks, setPeaks] = useState<number[]>([]);
  const [waveformLoading, setWaveformLoading] = useState(false);
  const [waveformError, setWaveformError] = useState("");
  const [mode, setMode] = useState<EditMode>("keep");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    let context: AudioContext | null = null;
    setDuration(0);
    setStart(0);
    setEnd(0);
    setPeaks([]);
    setWaveformError("");
    setWaveformLoading(true);

    const load = async () => {
      try {
        const src = convertFileSrc(input);
        const response = await fetch(src);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        context = new AudioContext();
        const buffer = await context.decodeAudioData(await response.arrayBuffer());
        const bins = Math.min(24_000, Math.max(1_200, Math.ceil(buffer.duration * 24)));
        const channels = Array.from({ length: buffer.numberOfChannels }, (_, i) => buffer.getChannelData(i));
        const result = new Array<number>(bins).fill(0);
        const step = buffer.length / bins;
        for (let i = 0; i < bins; i += 1) {
          const from = Math.floor(i * step);
          const to = Math.max(from + 1, Math.min(buffer.length, Math.ceil((i + 1) * step)));
          let peak = 0;
          for (let sample = from; sample < to; sample += 1) {
            for (const channel of channels) peak = Math.max(peak, Math.abs(channel[sample] || 0));
          }
          result[i] = peak;
        }
        if (alive) {
          setDuration(buffer.duration);
          setStart(0);
          setEnd(buffer.duration);
          setPeaks(result);
        }
      } catch (e) {
        if (alive) setWaveformError(String(e));
      } finally {
        if (alive) setWaveformLoading(false);
        if (context && context.state !== "closed") void context.close().catch(() => undefined);
      }
    };
    void load();
    return () => {
      alive = false;
      if (context && context.state !== "closed") void context.close().catch(() => undefined);
    };
  }, [input]);

  const waveformWidth = Math.max(720, Math.min(14_000, Math.ceil(Math.max(duration, 1) * 24)));

  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    el.width = Math.max(1, Math.ceil(waveformWidth * dpr));
    el.height = Math.ceil(WAVE_HEIGHT * dpr);
    el.style.width = `${waveformWidth}px`;
    el.style.height = `${WAVE_HEIGHT}px`;
    const ctx = el.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const css = getComputedStyle(document.documentElement);
    const surface = css.getPropertyValue("--surface").trim() || "#ffffff";
    const meta = css.getPropertyValue("--meta").trim() || "#9aa7b2";
    const accent = css.getPropertyValue("--accent").trim() || "#53b9dc";
    ctx.fillStyle = surface;
    ctx.fillRect(0, 0, waveformWidth, WAVE_HEIGHT);
    ctx.strokeStyle = meta;
    ctx.beginPath();
    ctx.moveTo(0, WAVE_HEIGHT / 2 + 0.5);
    ctx.lineTo(waveformWidth, WAVE_HEIGHT / 2 + 0.5);
    ctx.stroke();
    if (!peaks.length || !duration) return;

    const left = Math.max(0, Math.min(waveformWidth, (start / duration) * waveformWidth));
    const right = Math.max(left, Math.min(waveformWidth, (end / duration) * waveformWidth));
    ctx.fillStyle = "rgba(20, 26, 33, 0.12)";
    ctx.fillRect(0, 0, left, WAVE_HEIGHT);
    ctx.fillRect(right, 0, waveformWidth - right, WAVE_HEIGHT);
    const middle = WAVE_HEIGHT / 2;
    const unit = waveformWidth / peaks.length;
    ctx.lineWidth = 1;
    peaks.forEach((peak, i) => {
      const x = (i + 0.5) * unit;
      const h = Math.max(1, peak * (WAVE_HEIGHT * 0.44));
      const selected = x >= left && x <= right;
      ctx.strokeStyle = selected ? accent : meta;
      ctx.beginPath();
      ctx.moveTo(x, middle - h);
      ctx.lineTo(x, middle + h);
      ctx.stroke();
    });
    ctx.fillStyle = accent;
    ctx.fillRect(Math.max(0, left - 1), 0, 2, WAVE_HEIGHT);
    ctx.fillRect(Math.min(waveformWidth - 2, right - 1), 0, 2, WAVE_HEIGHT);
  }, [duration, end, peaks, start, waveformWidth]);

  const timeAt = (clientX: number) => {
    const el = canvas.current;
    if (!el || !duration) return 0;
    const rect = el.getBoundingClientRect();
    const x = Math.max(0, Math.min(waveformWidth, (clientX - rect.left) * (waveformWidth / rect.width)));
    return (x / waveformWidth) * duration;
  };

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (disabled || busy || !duration) return;
    const value = timeAt(e.clientX);
    dragStart.current = value;
    setStart(value);
    setEnd(value);
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (dragStart.current == null) return;
    const value = timeAt(e.clientX);
    setStart(Math.min(dragStart.current, value));
    setEnd(Math.max(dragStart.current, value));
  };
  const onPointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    dragStart.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
  };

  const valid =
    duration > 0 &&
    Number.isFinite(start) &&
    Number.isFinite(end) &&
    start >= 0 &&
    end > start &&
    end <= duration;
  const removingEverything = valid && start <= 0.01 && end >= duration - 0.01;
  const canApply = valid && (mode === "keep" || !removingEverything);

  const apply = async () => {
    if (!canApply || busy) return;
    setBusy(true);
    onBusyChange?.(true);
    setError("");
    audio.current?.pause();
    try {
      const output = await invoke<string>(mode === "keep" ? "audio_trim" : "audio_cut", mode === "keep"
        ? { input, start, end }
        : { input, start, end, duration });
      onApply(output);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
      onBusyChange?.(false);
    }
  };

  if (!canTrimAudio(input)) return null;
  return <div className="mt-3 flex flex-col gap-3">
    <audio ref={audio} src={(() => { try { return convertFileSrc(input); } catch { return ""; } })()} preload="metadata" className="w-full" controls
      onLoadedMetadata={(e) => {
        const d = e.currentTarget.duration;
        if (Number.isFinite(d) && d > 0) {
          setDuration((v) => v || d);
          setEnd((v) => v || d);
        }
      }}
      onError={() => setError(t("neptune.previewFailed"))}
      onTimeUpdate={(e) => { if (end > 0 && e.currentTarget.currentTime >= end) e.currentTarget.pause(); }} />
    <div className="flex flex-wrap items-center gap-3">
      <span className="text-[12.5px]">{t("neptune.editMode")}</span>
      <SegmentControl<EditMode>
        value={mode}
        onChange={setMode}
        options={[
          { id: "keep", label: t("neptune.keepSelection") },
          { id: "remove", label: t("neptune.removeSelection") },
        ]}
      />
    </div>
    <div
      ref={scroll}
      className="max-w-full overflow-x-auto rounded-[var(--rs)] border border-[var(--hairline)] bg-[var(--surface)]"
      onWheel={(e) => {
        if (!e.shiftKey || !scroll.current) return;
        e.preventDefault();
        scroll.current.scrollLeft += e.deltaY || e.deltaX;
      }}
    >
      <canvas
        ref={canvas}
        role="img"
        aria-label={t("neptune.waveform")}
        className="block max-w-none cursor-crosshair touch-none"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      />
    </div>
    {waveformLoading ? <p className="m-0 text-[12px] text-[var(--help)]">{t("neptune.waveformLoading")}</p> : null}
    {waveformError ? <p className="m-0 text-[12px] text-[var(--help)]">{t("neptune.waveformFailed")}</p> : null}
    <p className="m-0 text-[12px] text-[var(--help)]">{t("neptune.waveformHint")}</p>
    <div className="flex flex-wrap items-center gap-3">
      <label>{t("neptune.trimStart")} <input type="number" min={0} max={end} step="0.01"
        className="w-24 rounded-md border border-[var(--hairline)] bg-[var(--surface)] px-2 py-1" disabled={busy || disabled} value={Number.isFinite(start) ? start.toFixed(2) : ""} onChange={(e) => setStart(Number(e.target.value))} /></label>
      <label>{t("neptune.trimEnd")} <input type="number" min={start} max={duration} step="0.01"
        className="w-24 rounded-md border border-[var(--hairline)] bg-[var(--surface)] px-2 py-1" disabled={busy || disabled} value={Number.isFinite(end) ? end.toFixed(2) : ""} onChange={(e) => setEnd(Number(e.target.value))} /></label>
    </div>
    <RangeBar ariaLabel={t("neptune.trimStart")} min={0} max={duration} step={0.01} value={start}
      disabled={busy || disabled} onChange={(v) => setStart(Math.min(v, end))} />
    <RangeBar ariaLabel={t("neptune.trimEnd")} min={0} max={duration} step={0.01} value={end}
      disabled={busy || disabled} onChange={(v) => setEnd(Math.max(v, start))} />
    <div className="flex gap-2">
      <Btn disabled={!valid || busy || disabled} onClick={() => {
        if (audio.current) {
          audio.current.currentTime = start;
          void audio.current.play().catch(() => setError(t("neptune.previewFailed")));
        }
      }}>{t("neptune.previewSelection")}</Btn>
      <Btn disabled={!canApply || busy || disabled} onClick={() => void apply()}>{t(busy ? "neptune.trimming" : mode === "keep" ? "neptune.applyTrim" : "neptune.applyRemove")}</Btn>
    </div>
    <p className="m-0 text-[12px] text-[var(--help)]">{error || (removingEverything ? t("neptune.selectionInvalid") : duration > 0 && !valid ? t("neptune.trimInvalid") : t("neptune.trimHint"))}</p>
  </div>;
}

/** 保留旧的块状用法；STS 面板把按钮和编辑器拆开放置。 */
export function AudioTrim({ input, disabled, onApply }: AudioTrimProps) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!canTrimAudio(input)) return null;
  return <div className="py-2">
    <AudioTrimButton disabled={disabled || busy} open={open} onClick={() => setOpen(!open)} />
    {open ? <AudioTrimEditor input={input} disabled={disabled} onApply={onApply} onBusyChange={setBusy} /> : null}
  </div>;
}
