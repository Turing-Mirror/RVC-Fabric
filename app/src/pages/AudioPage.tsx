import { useCallback, useEffect, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Block, Btn, PageHead, PagePad } from "../components/ui";
import { Select } from "../components/controls";
import { askConfirm } from "../lib/webDialog";
import { useI18n } from "../i18n";
import { useAudioWaveform } from "../lib/useAudioWaveform";
import { WaveformRange } from "../components/WaveformRange";

type Source = {
  id: string;
  path: string;
  kind: "file" | "directory";
  mode: "reference" | "copy";
  excludes: string[];
};
type Asset = {
  id: string;
  path: string;
  origin: string;
  source_ids: string[];
  available: boolean;
  excluded_source_ids?: string[];
};
type Entry = {
  id: string;
  asset_id: string;
  name: string;
  number: number | null;
  start: number;
  end: number | null;
};
type Library = {
  revision: number;
  sources: Source[];
  assets: Asset[];
  entries: Entry[];
};
type Device = { id: string; name: string };
type PreviewStatus = {
  state: "idle" | "playing" | "paused" | "ended" | "error";
  name: string;
  played_frames: number;
  length_frames: number;
  sample_rate: number;
};

const EMPTY: Library = { revision: 0, sources: [], assets: [], entries: [] };

export function AudioPage() {
  const { t } = useI18n();
  const [library, setLibrary] = useState<Library>(EMPTY);
  const [devices, setDevices] = useState<Device[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [voiceDevices, setVoiceDevices] = useState<Device[]>([]);
  const [voiceDeviceId, setVoiceDeviceId] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [search, setSearch] = useState("");
  const [showExcluded, setShowExcluded] = useState(false);
  const [copy, setCopy] = useState(false);
  const [recursive, setRecursive] = useState(true);
  const [number, setNumber] = useState("");
  const [entryName, setEntryName] = useState("");
  const [clipName, setClipName] = useState("");
  const [clipStart, setClipStart] = useState("0");
  const [clipEnd, setClipEnd] = useState("");
  const [preview, setPreview] = useState<PreviewStatus | null>(null);
  const [voice, setVoice] = useState<PreviewStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [exportBusy, setExportBusy] = useState(false);
  const [scanActive, setScanActive] = useState(false);
  const [scanned, setScanned] = useState(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const acceptLibrary = useCallback((next: Library) => {
    setLibrary((previous) => next.revision >= previous.revision ? next : previous);
  }, []);

  useEffect(() => {
    let alive = true;
    void invoke<Library>("audio_library_get")
      .then((value) => { if (alive) acceptLibrary(value); })
      .catch(() => { if (alive) setError(t("audio.readFailed")); });
    void invoke<Device[]>("audio_preview_devices")
      .then((value) => { if (alive) setDevices(value); })
      .catch(() => { if (alive) setDevices([]); });
    void invoke<Device[]>("audio_voice_devices")
      .then((value) => { if (alive) setVoiceDevices(value); })
      .catch(() => { if (alive) setVoiceDevices([]); });
    void invoke<Record<string, unknown>>("config_get")
      .then((cfg) => {
        if (alive && typeof cfg.audio_preview_device_id === "string") {
          setDeviceId(cfg.audio_preview_device_id);
        }
        if (alive && typeof cfg.audio_voice_device_id === "string") {
          setVoiceDeviceId(cfg.audio_voice_device_id);
        }
      })
      .catch(() => {});
    const listener = listen("audio-library://changed", () => {
      void invoke<Library>("audio_library_get").then(acceptLibrary).catch(() => {});
    });
    const scanListener = listen<number>("audio-library://scan", (event) => setScanned(event.payload));
    return () => {
      alive = false;
      void listener.then((off) => off());
      void scanListener.then((off) => off());
    };
  }, [t, acceptLibrary]);

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const status = await invoke<PreviewStatus>("audio_preview_status");
        if (active) setPreview(status);
      } catch {
        if (active) setPreview(null);
      }
      try {
        const status = await invoke<PreviewStatus>("audio_voice_status");
        if (active) setVoice(status);
      } catch {
        if (active) setVoice(null);
      }
    };
    void poll();
    const timer = window.setInterval(poll, 200);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  const assetById = useMemo(() => new Map(library.assets.map((asset) => [asset.id, asset])), [library.assets]);
  const sourceNames = useMemo(() => {
    const leaves = library.sources.map((source) => source.path.split(/[\\/]/).filter(Boolean));
    const counts = new Map<string, number>();
    for (const parts of leaves) {
      const name = parts[parts.length - 1] ?? "";
      counts.set(name, (counts.get(name) ?? 0) + 1);
    }
    return new Map(library.sources.map((source, index) => {
      const parts = leaves[index];
      const name = parts[parts.length - 1] ?? source.path;
      return [source.id, (counts.get(name) ?? 0) > 1 ? parts.join(" / ") : name];
    }));
  }, [library.sources]);
  const selected = library.entries.find((entry) => entry.id === selectedId);
  const selectedAsset = selected && assetById.get(selected.asset_id);
  const waveform = useAudioWaveform(selectedAsset?.available ? selectedAsset.path : null);
  const selectedExcluded = selectedAsset && sourceId
    ? selectedAsset.excluded_source_ids?.includes(sourceId) === true
    : false;
  const shown = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return library.entries
      .filter((entry) => {
        const asset = assetById.get(entry.asset_id);
        const excluded = sourceId
          ? asset?.excluded_source_ids?.includes(sourceId) === true
          : (asset?.excluded_source_ids?.length ?? 0) === asset?.source_ids.length;
        return asset && excluded === showExcluded && (!sourceId || asset.source_ids.includes(sourceId)) &&
          (!query || entry.name.toLocaleLowerCase().includes(query));
      })
      .sort((a, b) => (a.number ?? Number.MAX_SAFE_INTEGER) - (b.number ?? Number.MAX_SAFE_INTEGER) ||
        a.name.localeCompare(b.name));
  }, [library.entries, assetById, sourceId, search, showExcluded]);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (cause) {
      const code = String(cause);
      if (code.includes("audio_scan_cancelled")) {
        setNotice(t("audio.scanCancelled"));
      } else if (code.includes("audio_export_cancelled")) {
        setNotice(t("audio.exportCancelled"));
      } else setError(code.includes("audio_number_taken") ? t("audio.numberTaken")
        : code.includes("audio_clip_invalid") ? t("audio.clipInvalid")
        : code.includes("audio_preview_device_is_") ? t("audio.previewDeviceInvalid")
        : code.includes("audio_voice_engine_active") ? t("audio.voiceEngineActive")
        : code.includes("audio_voice_device_is_preview") ? t("audio.voiceDeviceInvalid")
        : code.includes("audio_voice_device_locked") ? t("audio.voiceDeviceLocked")
        : code.includes("audio_voice_output_failed") ? t("audio.microphoneBridgeFailed")
        : code.includes("audio_playback_cancelled") ? t("audio.playbackCancelled")
        : code.includes("audio_relink_conflict") || code.includes("audio_relink_shared_asset") ? t("audio.relinkConflict")
        : code.includes("audio_relink_outside_source") ? t("audio.relinkOutsideSource")
        : code.includes("audio_relink_kind_mismatch") ? t("audio.relinkKindMismatch")
        : code.includes("audio_export_exists") ? t("audio.exportExists")
        : code.includes("audio_tools_missing") ? t("audio.toolsMissing")
        : t("audio.operationFailed"));
    } finally {
      setBusy(false);
    }
  };

  const pick = (kind: "file" | "directory") => {
    void run(async () => {
      const paths = await invoke<string[]>("audio_library_pick", { kind });
      if (paths.length === 0) return;
      setScanned(0);
      setScanActive(true);
      try {
        acceptLibrary(await invoke<Library>("audio_library_import", { paths, copy, recursive }));
      } finally {
        setScanActive(false);
      }
    });
  };

  const relink = (kind: "file" | "directory", scope: "source" | "asset", id: string) => {
    void run(async () => {
      const replacement = await invoke<string | null>("audio_library_pick_replacement", { kind });
      if (!replacement) return;
      const command = scope === "source" ? "audio_library_relink_source" : "audio_library_relink_asset";
      const args = scope === "source" ? { sourceId: id, replacement } : { assetId: id, replacement, replaceScannedDuplicate: false };
      if (scope === "source") {
        setScanned(0);
        setScanActive(true);
      }
      try {
        try {
          acceptLibrary(await invoke<Library>(command, args));
        } catch (cause) {
          if (scope !== "asset" || !String(cause).includes("audio_relink_duplicate_target")) throw cause;
          if (await askConfirm(t("audio.relinkDuplicateConfirm"))) {
            acceptLibrary(await invoke<Library>(command, { ...args, replaceScannedDuplicate: true }));
          }
        }
      } finally {
        setScanActive(false);
      }
    });
  };

  const chooseEntry = (entry: Entry) => {
    setSelectedId(entry.id);
    setEntryName(entry.name);
    setNumber(entry.number?.toString() ?? "");
    setClipName("");
    setClipStart(entry.start.toString());
    setClipEnd(entry.end?.toString() ?? "");
  };

  const saveNumber = () => {
    if (!selected) return;
    const parsed = number.trim() === "" ? null : Number(number);
    if (parsed != null && (!Number.isSafeInteger(parsed) || parsed <= 0)) {
      setError(t("audio.numberInvalid"));
      return;
    }
    void run(async () => {
      acceptLibrary(await invoke<Library>("audio_library_set_number", { entryId: selected.id, number: parsed }));
    });
  };

  const addClip = () => {
    if (!selectedAsset) return;
    const start = Number(clipStart);
    const end = clipEnd.trim() ? Number(clipEnd) : null;
    if (!clipName.trim() || !Number.isFinite(start) || start < 0 ||
      (end != null && (!Number.isFinite(end) || end <= start))) {
      setError(t("audio.clipInvalid"));
      return;
    }
    void run(async () => {
      const updated = await invoke<Library>("audio_library_add_clip", {
        assetId: selectedAsset.id, name: clipName, start, end,
      });
      acceptLibrary(updated);
      setSelectedId(updated.entries[updated.entries.length - 1].id);
      setEntryName(clipName.trim());
      setNumber("");
      setClipName("");
    });
  };

  const applyRange = () => {
    if (!selected) return;
    const start = Number(clipStart);
    const end = clipEnd.trim() ? Number(clipEnd) : null;
    if (!Number.isFinite(start) || start < 0 || (end != null && (!Number.isFinite(end) || end <= start))) {
      setError(t("audio.clipInvalid"));
      return;
    }
    void run(async () => {
      acceptLibrary(await invoke<Library>("audio_library_set_range", { entryId: selected.id, start, end }));
    });
  };

  const exportClip = () => {
    if (!selected) return;
    const start = Number(clipStart);
    const end = clipEnd.trim() ? Number(clipEnd) : null;
    if (!Number.isFinite(start) || start < 0 || (end != null && (!Number.isFinite(end) || end <= start))) {
      setError(t("audio.clipInvalid"));
      return;
    }
    setExportBusy(true);
    void run(async () => {
      const path = await invoke<string | null>("audio_library_export", { entryId: selected.id, start, end });
      if (path) setNotice(t("audio.exported"));
    }).finally(() => setExportBusy(false));
  };

  const startPreview = () => {
    if (!selected || !deviceId) {
      setError(t("audio.chooseDevice"));
      return;
    }
    const start = Number(clipStart);
    const end = clipEnd.trim() ? Number(clipEnd) : null;
    if (!Number.isFinite(start) || start < 0 || (end != null && (!Number.isFinite(end) || end <= start))) {
      setError(t("audio.clipInvalid"));
      return;
    }
    void run(async () => {
      setPreview(await invoke<PreviewStatus>("audio_preview_start", {
        entryId: selected.id,
        deviceId,
        start,
        end,
      }));
    });
  };

  const startVoice = () => {
    if (!selected || !voiceDeviceId) {
      setError(t("audio.chooseVoiceDevice"));
      return;
    }
    void run(async () => {
      await invoke("config_set", { patch: { audio_voice_device_id: voiceDeviceId } });
      setVoice(await invoke<PreviewStatus>("audio_voice_start", {
        entryId: selected.id,
        deviceId: voiceDeviceId,
      }));
    });
  };

  const progress = preview && preview.length_frames > 0
    ? Math.min(100, preview.played_frames / preview.length_frames * 100)
    : 0;
  const voiceProgress = voice && voice.length_frames > 0
    ? Math.min(100, voice.played_frames / voice.length_frames * 100)
    : 0;

  return (
    <PagePad>
      <PageHead title={t("audio.title")} sub={t("audio.subtitle")} actions={
        <>
          <Btn onClick={() => pick("file")} disabled={busy}>{t("audio.importFiles")}</Btn>
          <Btn onClick={() => pick("directory")} disabled={busy}>{t("audio.importFolders")}</Btn>
        </>
      } />
      <div className="flex flex-wrap gap-5 mt-5 text-[12.5px] text-[var(--ink-muted)]">
        <label className="flex items-center gap-2"><input type="checkbox" checked={copy} onChange={(e) => setCopy(e.target.checked)} />{t("audio.copyFiles")}</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={recursive} onChange={(e) => setRecursive(e.target.checked)} />{t("audio.recursive")}</label>
      </div>
      {error ? <p role="alert" className="text-[13px] text-[var(--danger)] mt-4">{error}</p> : null}
      {notice ? <p role="status" className="text-[13px] text-[var(--meta)] mt-4">{notice}</p> : null}
      {scanActive ? <div className="flex items-center gap-3 mt-4 text-[12px] text-[var(--meta)]" role="status">
        <span>{t("audio.scanProgress", { count: scanned })}</span>
        <Btn onClick={() => void invoke("audio_library_scan_cancel")}>{t("audio.cancelScan")}</Btn>
      </div> : null}

      <Block title={t("audio.sources")}>
        <div className="flex flex-wrap gap-2">
          <Btn on={sourceId === ""} onClick={() => { setSourceId(""); setSelectedId(""); }}>{t("audio.all")}</Btn>
          {library.sources.map((source) => (
            <Btn key={source.id} on={sourceId === source.id} ariaLabel={source.path} className="max-w-full truncate" onClick={() => { setSourceId(source.id); setSelectedId(""); }}>
              <span title={source.path}>{sourceNames.get(source.id)}</span>
            </Btn>
          ))}
        </div>
        {sourceId ? <div className="flex gap-2 mt-3">
          <Btn disabled={busy} onClick={() => void run(async () => {
            setScanned(0);
            setScanActive(true);
            try { acceptLibrary(await invoke<Library>("audio_library_refresh", { sourceId })); }
            finally { setScanActive(false); }
          })}>{t("audio.refresh")}</Btn>
          {library.sources.find((source) => source.id === sourceId)?.mode === "reference" ?
            <Btn disabled={busy} onClick={() => {
              const source = library.sources.find((source) => source.id === sourceId);
              if (source) relink(source.kind, "source", source.id);
            }}>{t("audio.relinkSource")}</Btn> : null}
          <Btn disabled={busy} onClick={() => void run(async () => {
            if (!(await askConfirm(t("audio.removeConfirm")))) return;
            acceptLibrary(await invoke<Library>("audio_library_remove_source", { sourceId }));
            setSourceId("");
            setSelectedId("");
          })}>{t("audio.removeSource")}</Btn>
        </div> : null}
      </Block>

      <Block title={t("audio.entries")} note={t("audio.entryCount", { count: shown.length })}>
        <label className="flex items-center gap-2 text-[12px] text-[var(--meta)] mb-3">
          <input type="checkbox" checked={showExcluded} onChange={(e) => setShowExcluded(e.target.checked)} />
          {t("audio.showExcluded")}
        </label>
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("audio.search")}
          className="w-full max-w-[400px] text-[13px] text-[var(--ink)] bg-transparent px-3.5 py-2 rounded-[var(--rs)] shadow-[inset_0_0_0_1px_var(--line)] outline-none focus:shadow-[inset_0_0_0_1px_var(--accent)]" />
        <div className="mt-3 bg-[var(--group)] rounded-[var(--r)] px-4">
          {shown.length === 0 ? <p className="text-[13px] text-[var(--meta)] py-4 m-0">{t("audio.empty")}</p> : shown.map((entry) => (
            <button type="button" key={entry.id} onClick={() => chooseEntry(entry)}
              className="w-full text-left flex items-center gap-3 py-3 border-0 border-b border-[var(--line)] last:border-b-0 bg-transparent cursor-pointer hover:text-[var(--accent)]">
              <span className="w-12 text-[var(--meta)] text-[12px]">{entry.number ?? "—"}</span>
              <span className="min-w-0 truncate text-[13px] text-[var(--ink)]">{entry.name}</span>
              <span className="ml-auto text-[11px] text-[var(--meta)]">{assetById.get(entry.asset_id)?.available === false ? t("audio.missing") : entry.start > 0 || entry.end != null ? t("audio.clip") : ""}</span>
            </button>
          ))}
        </div>
      </Block>

      <Block title={t("audio.voiceOutput")} note={t("audio.voiceOutputNote")}>
        <div className="flex items-end gap-3 flex-wrap">
          <label className="text-[12px] text-[var(--meta)]">{t("audio.voiceDevice")}
            <Select value={voiceDeviceId} options={[{ id: "", label: t("audio.chooseVoiceDevice") }, ...voiceDevices.map((device) => ({ id: device.id, label: device.name }))]}
              onChange={(id) => { setVoiceDeviceId(id); void invoke("config_set", { patch: { audio_voice_device_id: id } }).catch(() => setError(t("audio.operationFailed"))); }} width={240} />
          </label>
          <Btn disabled={!voice || (voice.state !== "playing" && voice.state !== "paused")} onClick={() => void invoke<PreviewStatus>("audio_voice_pause", { paused: voice?.state !== "paused" }).then(setVoice).catch(() => setError(t("audio.operationFailed")))}>
            {voice?.state === "paused" ? t("audio.resume") : t("audio.pause")}
          </Btn>
          <Btn disabled={!voice || (voice.state !== "playing" && voice.state !== "paused")} onClick={() => void invoke<PreviewStatus>("audio_voice_stop").then(setVoice).catch(() => setError(t("audio.operationFailed")))}>{t("audio.stop")}</Btn>
        </div>
        {voice && voice.state !== "idle" ? <div className="text-[12px] text-[var(--meta)] mt-3">
          {voice.state === "error" ? <p role="alert">{t("audio.voicePlaybackFailed")}</p> : null}
          {voice.name} · {(voice.played_frames / Math.max(1, voice.sample_rate)).toFixed(1)} / {(voice.length_frames / Math.max(1, voice.sample_rate)).toFixed(1)} s
          <div className="h-1.5 mt-2 rounded-full bg-[var(--line)] overflow-hidden"><div className="h-full bg-[var(--accent)]" style={{ width: `${voiceProgress}%` }} /></div>
        </div> : null}
      </Block>

      {selected && selectedAsset ? <Block title={selected.name}>
        <div className="bg-[var(--group)] rounded-[var(--r)] p-4 space-y-4">
          <div className="text-[12px] text-[var(--meta)] break-all">{selectedAsset.path}</div>
          {selectedAsset.available === false ? <div className="flex items-center gap-2 text-[12px] text-[var(--meta)]">
            <span>{t("audio.missing")}</span>
            {selectedAsset.path === selectedAsset.origin ?
              <Btn disabled={busy} onClick={() => relink("file", "asset", selectedAsset.id)}>{t("audio.relinkFile")}</Btn> : null}
          </div> : null}
          <div className="flex items-end gap-3 flex-wrap">
            <label className="text-[12px] text-[var(--meta)]">{t("audio.entryName")}
              <input value={entryName} onChange={(e) => setEntryName(e.target.value)} className="block mt-1 px-3 py-2 rounded-[var(--rs)] text-[var(--ink)] bg-transparent shadow-[inset_0_0_0_1px_var(--line)]" />
            </label>
            <Btn disabled={busy} onClick={() => void run(async () => { acceptLibrary(await invoke<Library>("audio_library_rename_entry", { entryId: selected.id, name: entryName })); })}>{t("audio.saveName")}</Btn>
          </div>
          <div className="flex items-end gap-3 flex-wrap">
            <label className="text-[12px] text-[var(--meta)]">{t("audio.fixedNumber")}
              <input type="number" min="1" step="1" value={number} onChange={(e) => setNumber(e.target.value)}
                className="block mt-1 w-36 px-3 py-2 rounded-[var(--rs)] text-[var(--ink)] bg-transparent shadow-[inset_0_0_0_1px_var(--line)]" />
            </label>
            <Btn disabled={busy} onClick={saveNumber}>{t("audio.saveNumber")}</Btn>
          </div>
          {waveform.duration > 0 ? <WaveformRange duration={waveform.duration} peaks={waveform.peaks}
            start={Number.isFinite(Number(clipStart)) ? Number(clipStart) : 0}
            end={clipEnd.trim() && Number.isFinite(Number(clipEnd)) ? Number(clipEnd) : waveform.duration}
            disabled={busy} label={t("neptune.waveform")}
            onRangeChange={(start, end) => {
              setClipStart(String(Math.min(start, waveform.duration, Number(start.toFixed(4)))));
              setClipEnd(String(Math.min(end, waveform.duration, Number(end.toFixed(4)))));
            }} /> : null}
          {waveform.loading ? <p className="text-[12px] text-[var(--meta)]">{t("neptune.waveformLoading")}</p> : null}
          {waveform.error ? <p className="text-[12px] text-[var(--meta)]">{t("neptune.waveformFailed")}</p> : null}
          <div className="flex items-end gap-3 flex-wrap">
            <label className="text-[12px] text-[var(--meta)]">{t("audio.localOutput")}
              <Select value={deviceId} options={[{ id: "", label: t("audio.chooseDevice") }, ...devices.map((device) => ({ id: device.id, label: device.name }))]}
                onChange={(id) => { setDeviceId(id); void invoke("config_set", { patch: { audio_preview_device_id: id } }).catch(() => setError(t("audio.operationFailed"))); }} width={240} />
            </label>
            <Btn disabled={busy || !deviceId || selectedAsset.available === false || selectedExcluded || (selectedAsset.excluded_source_ids?.length ?? 0) === selectedAsset.source_ids.length} onClick={startPreview}>{t("audio.preview")}</Btn>
            <Btn disabled={busy || !voiceDeviceId || selectedAsset.available === false || selectedExcluded || (selectedAsset.excluded_source_ids?.length ?? 0) === selectedAsset.source_ids.length} onClick={startVoice}>{t("audio.playToVoice")}</Btn>
            <Btn disabled={!preview || (preview.state !== "playing" && preview.state !== "paused")} onClick={() => void invoke<PreviewStatus>("audio_preview_pause", { paused: preview?.state !== "paused" }).then(setPreview).catch(() => setError(t("audio.operationFailed")))}>
              {preview?.state === "paused" ? t("audio.resume") : t("audio.pause")}
            </Btn>
            <Btn disabled={!preview || (preview.state !== "playing" && preview.state !== "paused")} onClick={() => void invoke<PreviewStatus>("audio_preview_stop").then(setPreview).catch(() => setError(t("audio.operationFailed")))}>{t("audio.stop")}</Btn>
          </div>
          {preview && preview.state !== "idle" ? <div className="text-[12px] text-[var(--meta)]">
            {preview.state === "error" ? <p role="alert">{t("neptune.previewFailed")}</p> : null}
            {preview.name} · {(preview.played_frames / Math.max(1, preview.sample_rate)).toFixed(1)} / {(preview.length_frames / Math.max(1, preview.sample_rate)).toFixed(1)} s
            <div className="h-1.5 mt-2 rounded-full bg-[var(--line)] overflow-hidden"><div className="h-full bg-[var(--accent)]" style={{ width: `${progress}%` }} /></div>
          </div> : null}
          <div className="flex items-end gap-3 flex-wrap">
            <label className="text-[12px] text-[var(--meta)]">{t("audio.clipName")}
              <input value={clipName} onChange={(e) => setClipName(e.target.value)} className="block mt-1 px-3 py-2 rounded-[var(--rs)] text-[var(--ink)] bg-transparent shadow-[inset_0_0_0_1px_var(--line)]" />
            </label>
            <label className="text-[12px] text-[var(--meta)]">{t("audio.startSeconds")}
              <input type="number" min="0" step="0.001" value={clipStart} onChange={(e) => setClipStart(e.target.value)} className="block mt-1 w-28 px-3 py-2 rounded-[var(--rs)] text-[var(--ink)] bg-transparent shadow-[inset_0_0_0_1px_var(--line)]" />
            </label>
            <label className="text-[12px] text-[var(--meta)]">{t("audio.endSeconds")}
              <input type="number" min="0" step="0.001" value={clipEnd} onChange={(e) => setClipEnd(e.target.value)} className="block mt-1 w-28 px-3 py-2 rounded-[var(--rs)] text-[var(--ink)] bg-transparent shadow-[inset_0_0_0_1px_var(--line)]" />
            </label>
            <Btn disabled={busy} onClick={addClip}>{t("audio.addClip")}</Btn>
            <Btn disabled={busy} onClick={applyRange}>{t("audio.applyRange")}</Btn>
            <Btn disabled={busy || selectedAsset.available === false} onClick={exportClip}>{t("audio.exportWav")}</Btn>
            {exportBusy ? <Btn onClick={() => void invoke("audio_library_export_cancel")}>{t("audio.cancelExport")}</Btn> : null}
          </div>
          {sourceId ? <div className="flex gap-2">
            {selectedExcluded
              ? <Btn disabled={busy} onClick={() => void run(async () => { acceptLibrary(await invoke<Library>("audio_library_restore", { sourceId, path: selectedAsset.origin })); })}>{t("audio.restore")}</Btn>
              : <Btn disabled={busy} onClick={() => void run(async () => { acceptLibrary(await invoke<Library>("audio_library_exclude", { sourceId, assetId: selectedAsset.id })); })}>{t("audio.exclude")}</Btn>}
          </div> : null}
        </div>
      </Block> : null}
    </PagePad>
  );
}
