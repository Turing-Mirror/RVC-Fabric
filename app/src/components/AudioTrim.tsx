import { useEffect, useRef, useState } from "react";
import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { Btn } from "./ui";
import { useI18n } from "../i18n";
import { RangeBar } from "./controls";
import { SegmentControl } from "./SegmentControl";
import { useAudioWaveform } from "../lib/useAudioWaveform";
import { WaveformRange } from "./WaveformRange";

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

export function AudioTrimEditor({ input, disabled, onApply, onBusyChange }: AudioTrimEditorProps) {
  const { t } = useI18n();
  const audio = useRef<HTMLAudioElement>(null);
  const previewing = useRef(false);
  const waveform = useAudioWaveform(input);
  const [metadata, setMetadata] = useState({ input: "", duration: 0 });
  const duration = waveform.duration || (metadata.input === input ? metadata.duration : 0);
  const [start, setStart] = useState(0);
  const [end, setEnd] = useState(0);
  const [mode, setMode] = useState<EditMode>("keep");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    audio.current?.pause();
    previewing.current = false;
    setMetadata({ input, duration: 0 });
    setStart(0);
    setEnd(0);
    setCurrentTime(0);
    setMode("keep");
  }, [input]);

  useEffect(() => {
    if (duration > 0) setEnd((value) => value || duration);
  }, [duration]);

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

  const seek = (time: number) => {
    previewing.current = false;
    const t0 = Math.max(0, Math.min(duration, time));
    setCurrentTime(t0);
    if (audio.current) audio.current.currentTime = t0;
  };

  if (!canTrimAudio(input)) return null;
  return <div className="mt-3 flex flex-col gap-3">
    <audio ref={audio} src={(() => { try { return convertFileSrc(input); } catch { return ""; } })()} preload="metadata" className="hidden"
      onLoadedMetadata={(e) => {
        const d = e.currentTarget.duration;
        if (Number.isFinite(d) && d > 0) {
          setMetadata({ input, duration: d });
          setEnd((v) => v || d);
        }
      }}
      onError={() => setError(t("neptune.previewFailed"))}
      onPlay={() => setPlaying(true)}
      onPause={() => setPlaying(false)}
      onTimeUpdate={(e) => {
        const now = e.currentTarget.currentTime;
        setCurrentTime(now);
        if (previewing.current && end > 0 && now >= end) {
          e.currentTarget.pause();
          previewing.current = false;
        }
      }} />
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
    <WaveformRange duration={duration} peaks={waveform.peaks} start={start} end={end}
      currentTime={currentTime} playing={playing} disabled={disabled || busy}
      label={t("neptune.waveform")} onRangeChange={(nextStart, nextEnd) => { setStart(nextStart); setEnd(nextEnd); }} />
    {waveform.loading ? <p className="m-0 text-[12px] text-[var(--help)]">{t("neptune.waveformLoading")}</p> : null}
    {waveform.error ? <p className="m-0 text-[12px] text-[var(--help)]">{t("neptune.waveformFailed")}</p> : null}
    <p className="m-0 text-[12px] text-[var(--help)]">{t("neptune.waveformHint")}</p>
    <RangeBar ariaLabel={t("neptune.position")} min={0} max={duration || 1} step={0.01} value={currentTime}
      disabled={busy || disabled || !duration} onChange={seek} />
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
          previewing.current = true;
          audio.current.currentTime = start;
          setCurrentTime(start);
          void audio.current.play().catch(() => setError(t("neptune.previewFailed")));
        }
      }}>{t("neptune.previewSelection")}</Btn>
      <Btn disabled={!canApply || busy || disabled} onClick={() => void apply()}>{t(busy ? "neptune.trimming" : "neptune.applyTrim")}</Btn>
    </div>
    <p className="m-0 text-[12px] text-[var(--help)]">{error || (removingEverything && mode === "remove" ? t("neptune.selectionInvalid") : duration > 0 && !valid ? t("neptune.trimInvalid") : t("neptune.trimHint"))}</p>
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
