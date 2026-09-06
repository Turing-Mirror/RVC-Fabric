import { useRef, useState } from "react";
import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { Btn } from "./ui";
import { useI18n } from "../i18n";
import { RangeBar } from "./controls";

export function AudioTrim({ input, disabled, onApply }: {
  input: string; disabled: boolean; onApply: (path: string) => void;
}) {
  const { t } = useI18n();
  const audio = useRef<HTMLAudioElement>(null);
  const [duration, setDuration] = useState(0);
  const [start, setStart] = useState(0);
  const [end, setEnd] = useState(0);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!/\.(wav|mp3|flac|m4a|ogg|aac|opus)$/i.test(input)) return null;
  let src = "";
  try { src = convertFileSrc(input); } catch { /* Desktop-only local audio. */ }
  const valid = duration > 0 && start >= 0 && end > start && end <= duration;
  const apply = async () => {
    if (!valid || busy) return;
    setBusy(true); setError("");
    audio.current?.pause();
    try { onApply(await invoke<string>("audio_trim", { input, start, end })); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };
  return <div className="py-2">
    <Btn disabled={disabled || busy} onClick={() => setOpen(!open)}>{t("neptune.trim")}</Btn>
    {open && <div className="mt-3 flex flex-col gap-3">
      <audio ref={audio} src={src} preload="metadata" className="w-full" controls
        onLoadedMetadata={(e) => {
          const d = e.currentTarget.duration;
          if (Number.isFinite(d)) { setDuration(d); setEnd(d); }
        }}
        onError={() => setError(t("neptune.previewFailed"))}
        onTimeUpdate={(e) => { if (e.currentTarget.currentTime >= end) e.currentTarget.pause(); }} />
      <div className="flex flex-wrap items-center gap-3">
        <label>{t("neptune.trimStart")} <input type="number" min={0} max={end} step="0.01"
          className="w-24 rounded-md border border-[var(--hairline)] bg-[var(--surface)] px-2 py-1" disabled={busy || disabled} value={start} onChange={(e) => setStart(Number(e.target.value))} /></label>
        <label>{t("neptune.trimEnd")} <input type="number" min={start} max={duration} step="0.01"
          className="w-24 rounded-md border border-[var(--hairline)] bg-[var(--surface)] px-2 py-1" disabled={busy || disabled} value={end} onChange={(e) => setEnd(Number(e.target.value))} /></label>
      </div>
      <RangeBar ariaLabel={t("neptune.trimStart")} min={0} max={duration} step={0.01} value={start}
        disabled={busy || disabled} onChange={(v) => setStart(Math.min(v, end))} />
      <RangeBar ariaLabel={t("neptune.trimEnd")} min={0} max={duration} step={0.01} value={end}
        disabled={busy || disabled} onChange={(v) => setEnd(Math.max(v, start))} />
      <div className="flex gap-2">
        <Btn disabled={!valid || busy || disabled} onClick={() => {
          if (audio.current) { audio.current.currentTime = start; void audio.current.play().catch(() => setError(t("neptune.previewFailed"))); }
        }}>{t("neptune.previewSelection")}</Btn>
        <Btn disabled={!valid || busy || disabled} onClick={() => void apply()}>{t(busy ? "neptune.trimming" : "neptune.applyTrim")}</Btn>
      </div>
      <p className="m-0 text-[12px] text-[var(--help)]">{error || t(duration > 0 && !valid ? "neptune.trimInvalid" : "neptune.trimHint")}</p>
    </div>}
  </div>;
}
