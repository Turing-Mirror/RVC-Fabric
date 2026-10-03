import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type MouseEvent } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn, PageHead, PagePad } from "../components/ui";
import { MoreMenuPopup, type PopupAnchor } from "../components/MoreMenu";
import { Swap } from "../components/Motion";
import { HelpMark } from "../components/Tooltip";
import { Select, Slider } from "../components/controls";
import { askConfirm } from "../lib/webDialog";
import { useI18n } from "../i18n";
import { useAudioWaveform } from "../lib/useAudioWaveform";
import { WaveformRange } from "../components/WaveformRange";
import { AudioHotkeyEditor } from "../components/AudioHotkeyEditor";
import { SeekBar } from "../components/SeekBar";
import type { PlaybackStatus, VoicePlaybackStatus } from "../lib/audioPlayback";

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
  looped: boolean;
};
type Library = {
  revision: number;
  sources: Source[];
  assets: Asset[];
  entries: Entry[];
};
type Device = { id: string; name: string };
type PreviewStatus = PlaybackStatus;
type AudioVolumeStatus = { volume: number; muted: boolean };

const EMPTY: Library = { revision: 0, sources: [], assets: [], entries: [] };

type Props = {
  /** 「语音输出设备」旁的「更改」：去设置页的设备分页改输出设备。 */
  onOpenDeviceSettings?: () => void;
};

export function AudioPage({ onOpenDeviceSettings }: Props = {}) {
  const { t } = useI18n();
  const [library, setLibrary] = useState<Library>(EMPTY);
  const [devices, setDevices] = useState<Device[]>([]);
  const [deviceId, setDeviceId] = useState("");
  // 插播和变声从同一个设备出去：设置页的「输出设备」。这里只显示，不另外选。
  const [outputName, setOutputName] = useState("");
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
  const [voice, setVoice] = useState<VoicePlaybackStatus | null>(null);
  const [voiceInstances, setVoiceInstances] = useState<VoicePlaybackStatus[]>([]);
  const [volume, setVolume] = useState<AudioVolumeStatus>({ volume: 1, muted: false });
  const [monitor, setMonitor] = useState(true);
  const [busy, setBusy] = useState(false);
  const [voicePreparing, setVoicePreparing] = useState(false);
  const [exportBusy, setExportBusy] = useState(false);
  const [scanActive, setScanActive] = useState(false);
  const [scanned, setScanned] = useState(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  // 来源行的「⋯」/右键菜单：绑定的是被点开的那条来源，跟左侧当前筛选无关。
  const [srcMenu, setSrcMenu] = useState<{ anchor: PopupAnchor; align: "left" | "right"; source: Source } | null>(null);
  // 关菜单时把焦点还给打开它的那枚按钮（右键打开的还给同一行的 ⋯）。
  const menuReturnFocus = useRef<HTMLElement | null>(null);
  // 只有 Esc / 点菜单项 / 再点同一枚 ⋯ 这类「用户主动收菜单」才还焦点；
  // 外点、Tab 离开把焦点留在用户新指的地方（比如刚点进去的搜索框）。
  const menuRestore = useRef(false);

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
    void invoke<Record<string, unknown>>("config_get")
      .then((cfg) => {
        if (alive && typeof cfg.audio_preview_device_id === "string") {
          setDeviceId(cfg.audio_preview_device_id);
        }
        if (alive && typeof cfg.sg_output_device === "string") {
          setOutputName(cfg.sg_output_device);
        }
        if (alive) setMonitor(cfg.audio_music_monitor !== false);
      })
      .catch(() => {});
    void invoke<AudioVolumeStatus>("audio_voice_volume_get")
      .then((value) => { if (alive && value) setVolume(value); })
      .catch(() => {});
    const listener = listen("audio-library://changed", () => {
      void invoke<Library>("audio_library_get").then(acceptLibrary).catch(() => {});
    });
    const volumeListener = listen<AudioVolumeStatus>("audio-volume://changed", (event) => {
      if (alive && event.payload) setVolume(event.payload);
    });
    const scanListener = listen<number>("audio-library://scan", (event) => setScanned(event.payload));
    return () => {
      alive = false;
      void listener.then((off) => off());
      void volumeListener.then((off) => off());
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
        const [status, instances] = await Promise.all([
          invoke<VoicePlaybackStatus>("audio_voice_status"),
          invoke<VoicePlaybackStatus[]>("audio_voice_instances"),
        ]);
        if (active) {
          setVoice(status);
          setVoiceInstances(instances);
        }
      } catch {
        if (active) {
          setVoice(null);
          setVoiceInstances([]);
        }
      }
    };
    void poll();
    const timer = window.setInterval(poll, 200);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  // 点别处、Esc、换页滚动都关菜单。打开时按钮自己 stopPropagation，不会刚开就关。
  // 菜单自己内部滚动（项太多超出窗口时）不算换页滚动：data-more-menu 豁免。
  useEffect(() => {
    if (!srcMenu) return;
    const close = () => setSrcMenu(null);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") menuRestore.current = true;
      if (e.key === "Escape" || e.key === "Tab") setSrcMenu(null);
    };
    const onScroll = (e: Event) => {
      if ((e.target as Element | null)?.closest?.("[data-more-menu]")) return;
      close();
    };
    window.addEventListener("click", close);
    window.addEventListener("contextmenu", close);
    window.addEventListener("keydown", onKey);
    window.addEventListener("resize", close);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("contextmenu", close);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", close);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [srcMenu]);

  // 菜单关上后按关闭原因决定焦点去向；那一行（来源被移除）不在了就放过。
  // preventScroll：还焦点别把刚滚过的来源栏拽回按钮所在处。
  useEffect(() => {
    if (srcMenu) return;
    if (!menuRestore.current) return;
    menuRestore.current = false;
    const el = menuReturnFocus.current;
    if (el && document.contains(el)) el.focus({ preventScroll: true });
  }, [srcMenu]);

  /** 行尾「⋯」：右缘对齐按钮；同一条再点一下是关上。 */
  const openSourceMenu = (e: MouseEvent<HTMLButtonElement>, source: Source) => {
    e.stopPropagation();
    menuReturnFocus.current = e.currentTarget;
    const r = e.currentTarget.getBoundingClientRect();
    // 再点同一枚 ⋯ 是「主动收菜单」：还焦点；开新菜单默认不还。
    const closing = srcMenu?.source.id === source.id;
    menuRestore.current = Boolean(closing);
    setSrcMenu(closing
      ? null
      : { anchor: { left: r.left, right: r.right, top: r.top, bottom: r.bottom }, align: "right", source });
  };

  /** 行上右键：菜单贴着指针开，左缘对齐。焦点还给本行的 ⋯ 按钮。 */
  const openSourceMenuAt = (x: number, y: number, source: Source, row: HTMLElement) => {
    menuReturnFocus.current = row.querySelector<HTMLElement>("[data-source-menu]");
    setSrcMenu({ anchor: { left: x, right: x, top: y, bottom: y }, align: "left", source });
  };

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
        : code.includes("audio_voice_device_missing") ? t("audio.chooseVoiceDevice")
        : code.includes("audio_voice_device_locked") ? t("audio.voiceDeviceLocked")
        : code.includes("audio_voice_output_failed") ? t("audio.microphoneBridgeFailed")
        : code.includes("audio_music_capacity_reached") ? t("audio.playbackCapacity")
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

  const changeVolume = (command: string, args?: Record<string, unknown>) => {
    void invoke<AudioVolumeStatus>(command, args).then(setVolume)
      .catch(() => setError(t("audio.operationFailed")));
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

  const startVoice = (mode: "replace" | "overlay") => {
    if (!selected || !outputName) {
      setError(t("audio.chooseVoiceDevice"));
      return;
    }
    setVoicePreparing(true);
    void run(async () => {
      setVoice(await invoke<VoicePlaybackStatus>("audio_voice_start", {
        entryId: selected.id,
        mode,
      }));
    }).finally(() => setVoicePreparing(false));
  };

  const progress = preview && preview.length_frames > 0
    ? Math.min(100, preview.played_frames / preview.length_frames * 100)
    : 0;
  const unplayable = (asset?: Asset) => !asset || asset.available === false || selectedExcluded ||
    (asset.excluded_source_ids?.length ?? 0) === asset.source_ids.length;
  const sourceCount = (id: string) => library.entries.filter((entry) => assetById.get(entry.asset_id)?.source_ids.includes(id)).length;
  const field = "block mt-1 px-3 py-2 rounded-[var(--rs)] text-[var(--ink)] bg-transparent shadow-[inset_0_0_0_1px_var(--line)] outline-none focus:shadow-[inset_0_0_0_1px_var(--accent)]";
  // 双击条目：直接替换播放到语音，与常见音效板的用法一致
  const playNow = (entry: Entry) => {
    chooseEntry(entry);
    if (!outputName || unplayable(assetById.get(entry.asset_id))) return;
    setVoicePreparing(true);
    void run(async () => {
      setVoice(await invoke<VoicePlaybackStatus>("audio_voice_start", { entryId: entry.id, mode: "replace" }));
    }).finally(() => setVoicePreparing(false));
  };

  return (
    <PagePad fill>
      <PageHead title={t("audio.title")} sub={t("audio.subtitle")} actions={
        <>
          <label className="flex items-center gap-1.5 text-[12px] text-[var(--meta)] mr-1"><input type="checkbox" checked={copy} onChange={(e) => setCopy(e.target.checked)} />{t("audio.copyFiles")}</label>
          <label className="flex items-center gap-1.5 text-[12px] text-[var(--meta)] mr-2"><input type="checkbox" checked={recursive} onChange={(e) => setRecursive(e.target.checked)} />{t("audio.recursive")}</label>
          <Btn onClick={() => pick("file")} disabled={busy}>{t("audio.importFiles")}</Btn>
          <Btn onClick={() => pick("directory")} disabled={busy}>{t("audio.importFolders")}</Btn>
        </>
      } />
      {error ? <p role="alert" className="flex-none text-[13px] text-[var(--danger)] mt-4 mb-0">{error}</p> : null}
      {notice ? <p role="status" className="flex-none text-[13px] text-[var(--meta)] mt-4 mb-0">{notice}</p> : null}
      {scanActive ? <div className="flex-none flex items-center gap-3 mt-4 text-[12px] text-[var(--meta)]" role="status">
        <span>{t("audio.scanProgress", { count: scanned })}</span>
        <Btn onClick={() => void invoke("audio_library_scan_cancel")}>{t("audio.cancelScan")}</Btn>
      </div> : null}

      {/* 浏览区（三栏）占页头以下的剩余高度；语音输出栏贴在底部，紧挨着 Dock。
          正在播放的段多了只在栏内滚动，栏高有上限。 */}
      <div className="mt-4 flex-1 min-h-0 flex flex-col"
        style={{ "--audio-source-w": "clamp(140px, 16cqw, 184px)" } as CSSProperties}>
      {/* 三栏常驻：任何窗口宽都保留来源栏。来源栏宽吃 --audio-source-w 这一个基准，
          随页宽收缩、不瓜分富余宽度；各栏在自己内部滚动 */}
      <div className="flex-1 min-h-0 grid gap-6 max-[1020px]:gap-4 items-stretch grid-rows-[minmax(0,1fr)] grid-cols-[var(--audio-source-w)_minmax(0,1fr)_minmax(260px,380px)]">
        <aside aria-label={t("audio.sources")} className="min-h-0 overflow-y-auto overscroll-contain">
          <div className="text-[12px] text-[var(--meta)] mb-2 px-2.5">{t("audio.sources")}</div>
          <div className="flex flex-col gap-0.5">
            <SourceBtn on={sourceId === ""} label={t("audio.all")} count={library.entries.length} onClick={() => { setSourceId(""); setSelectedId(""); }} />
            {library.sources.map((source) => (
              <SourceBtn key={source.id} on={sourceId === source.id} label={sourceNames.get(source.id) ?? source.path} title={source.path} count={sourceCount(source.id)}
                menuLabel={t("audio.sourceMenu")}
                menuOpen={srcMenu?.source.id === source.id}
                onMenu={(e) => openSourceMenu(e, source)}
                onContextMenu={(e, row) => openSourceMenuAt(e.clientX, e.clientY, source, row)}
                onClick={() => { setSourceId(source.id); setSelectedId(""); }} />
            ))}
          </div>
        </aside>

        <section aria-label={t("audio.entries")} className="min-w-0 min-h-0 flex flex-col">
          <div className="flex-none flex items-stretch gap-3 flex-nowrap">
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("audio.search")}
              className="flex-1 min-w-[72px] text-[13px] text-[var(--ink)] bg-transparent px-3.5 py-2 rounded-[var(--rs)] shadow-[inset_0_0_0_1px_var(--line)] outline-none focus:shadow-[inset_0_0_0_1px_var(--accent)]" />
            <label title={t("audio.showExcluded")} className="min-w-0 flex items-center gap-1.5 px-3 rounded-[var(--rs)] shadow-[inset_0_0_0_1px_var(--line)] text-[12px] text-[var(--meta)] cursor-pointer">
              <input type="checkbox" checked={showExcluded} onChange={(e) => setShowExcluded(e.target.checked)} />
              <span className="truncate">{t("audio.showExcluded")}</span>
            </label>
          </div>
          <div className="flex-none mt-2 flex items-center text-[11.5px] text-[var(--meta)] px-3">
            <span>{t("audio.entryCount", { count: shown.length })}</span>
            <span className="ml-auto">{t("audio.dblHint")}</span>
          </div>
          <Swap k={`${sourceId}|${showExcluded}`} className="mt-1.5 flex-1 min-h-0 overflow-y-auto overscroll-contain [&>*]:h-full">
            <div className="bg-[var(--group)] rounded-[var(--r)] p-1.5">
              {shown.length === 0 ? <p className="text-[13px] text-[var(--meta)] py-4 px-2.5 m-0">{t("audio.empty")}</p> : shown.map((entry) => {
                const asset = assetById.get(entry.asset_id);
                const on = entry.id === selectedId;
                const playing = voiceInstances.some((instance) => instance.name === entry.name);
                return (
                  <button type="button" key={entry.id} onClick={() => chooseEntry(entry)} onDoubleClick={() => playNow(entry)} aria-pressed={on}
                    className={`w-full text-left flex items-center gap-3 px-2.5 py-2 rounded-[var(--rs)] border-0 cursor-pointer transition-colors ${on ? "bg-[var(--accent-soft)]" : "bg-transparent hover:bg-[color-mix(in_srgb,var(--ink)_5%,transparent)]"}`}>
                    <span className={`w-9 flex-none text-right tabular-nums text-[12px] ${entry.number != null ? "text-[var(--ink-muted)]" : "text-[var(--meta)]"}`}>{entry.number ?? "—"}</span>
                    <span className={`min-w-0 truncate text-[13px] ${on ? "text-[var(--accent)] font-medium" : "text-[var(--ink)]"}`}>{entry.name}</span>
                    {playing ? <span aria-hidden className="flex-none flex items-end gap-[2px] h-3">{[0, 1, 2].map((i) => <span key={i} className="eq-bar w-[2px] rounded-full bg-[var(--accent)]" style={{ animationDelay: `${i * 0.18}s` }} />)}</span> : null}
                    <span className="ml-auto flex-none text-[11px] text-[var(--meta)]">{asset?.available === false ? t("audio.missing") : entry.start > 0 || entry.end != null ? t("audio.clip") : entry.looped ? t("audio.loop") : ""}</span>
                  </button>
                );
              })}
            </div>
          </Swap>
        </section>

        <aside aria-label={selected?.name ?? t("audio.entries")} className="min-w-0 min-h-0 overflow-y-auto overscroll-contain rounded-[var(--r)]">
          <Swap k={selected?.id ?? ""} className="h-full [&>*]:h-full">
            {selected && selectedAsset ? <div className="bg-[var(--group)] rounded-[var(--r)] p-4 space-y-4">
              <div>
                <div className="text-[15px] font-semibold truncate">{selected.name}</div>
                <div className="mt-1 text-[11.5px] text-[var(--meta)] break-all">{selectedAsset.path}</div>
              </div>
              {selectedAsset.available === false ? <div className="flex items-center gap-2 text-[12px] text-[var(--meta)]">
                <span>{t("audio.missing")}</span>
                {selectedAsset.path === selectedAsset.origin ?
                  <Btn disabled={busy} onClick={() => relink("file", "asset", selectedAsset.id)}>{t("audio.relinkFile")}</Btn> : null}
              </div> : null}
              <div className="flex flex-wrap gap-2">
                <Btn primary disabled={busy || !outputName || unplayable(selectedAsset)} onClick={() => startVoice("replace")}>{t("audio.playToVoice")}</Btn>
                <Btn disabled={busy || !outputName || unplayable(selectedAsset)} onClick={() => startVoice("overlay")}>{t("audio.overlayToVoice")}</Btn>
              </div>
              <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-2 gap-y-3 items-end">
                <label className="text-[12px] text-[var(--meta)] min-w-0">{t("audio.entryName")}
                  <input value={entryName} onChange={(e) => setEntryName(e.target.value)} className={`${field} w-full`} />
                </label>
                <Btn disabled={busy} onClick={() => void run(async () => { acceptLibrary(await invoke<Library>("audio_library_rename_entry", { entryId: selected.id, name: entryName })); })}>{t("audio.saveName")}</Btn>
                <label className="text-[12px] text-[var(--meta)] min-w-0">{t("audio.fixedNumber")}
                  <input type="number" min="1" step="1" value={number} onChange={(e) => setNumber(e.target.value)} className={`${field} w-full`} />
                </label>
                <Btn disabled={busy} onClick={saveNumber}>{t("audio.saveNumber")}</Btn>
              </div>
              <label className="flex items-center gap-1.5 text-[12px] text-[var(--meta)]">
                <input type="checkbox" checked={selected.looped} disabled={busy}
                  onChange={(event) => { const looped = event.target.checked; void run(async () => { acceptLibrary(await invoke<Library>("audio_library_set_loop", { entryId: selected.id, looped })); }); }} />
                {t("audio.loopByDefault")}
              </label>
              {waveform.duration > 0 ? <WaveformRange duration={waveform.duration} peaks={waveform.peaks}
                start={Number.isFinite(Number(clipStart)) ? Number(clipStart) : 0}
                end={clipEnd.trim() && Number.isFinite(Number(clipEnd)) ? Number(clipEnd) : waveform.duration}
                disabled={busy} label={t("neptune.waveform")}
                onRangeChange={(start, end) => {
                  setClipStart(String(Math.min(start, waveform.duration, Number(start.toFixed(4)))));
                  setClipEnd(String(Math.min(end, waveform.duration, Number(end.toFixed(4)))));
                }} /> : null}
              {waveform.duration > 0 ? <p className="text-[12px] text-[var(--meta)] m-0">{t("neptune.waveformHint")}</p> : null}
              {waveform.loading ? <p className="text-[12px] text-[var(--meta)] m-0">{t("neptune.waveformLoading")}</p> : null}
              {waveform.error ? <p className="text-[12px] text-[var(--meta)] m-0">{t("neptune.waveformFailed")}</p> : null}
              <div className="grid grid-cols-2 gap-2">
                <label className="text-[12px] text-[var(--meta)]">{t("audio.startSeconds")}
                  <input type="number" min="0" step="0.001" value={clipStart} onChange={(e) => setClipStart(e.target.value)} className={`${field} w-full`} />
                </label>
                <label className="text-[12px] text-[var(--meta)]">{t("audio.endSeconds")}
                  <input type="number" min="0" step="0.001" value={clipEnd} onChange={(e) => setClipEnd(e.target.value)} className={`${field} w-full`} />
                </label>
              </div>
              <div className="flex items-end gap-2 flex-wrap">
                <label className="text-[12px] text-[var(--meta)]">{t("audio.localOutput")}
                  <Select value={deviceId} options={[{ id: "", label: t("audio.chooseDevice") }, ...devices.map((device) => ({ id: device.id, label: device.name }))]}
                    onChange={(id) => { setDeviceId(id); void invoke("config_set", { patch: { audio_preview_device_id: id } }).catch(() => setError(t("audio.operationFailed"))); }} width={200} />
                </label>
                <Btn disabled={busy || !deviceId || unplayable(selectedAsset)} onClick={startPreview}>{t("audio.preview")}</Btn>
                <Btn disabled={!preview || (preview.state !== "playing" && preview.state !== "paused")} onClick={() => void invoke<PreviewStatus>("audio_preview_pause", { paused: preview?.state !== "paused" }).then(setPreview).catch(() => setError(t("audio.operationFailed")))}>
                  {preview?.state === "paused" ? t("audio.resume") : t("audio.pause")}
                </Btn>
                <Btn disabled={!preview || (preview.state !== "playing" && preview.state !== "paused")} onClick={() => void invoke<PreviewStatus>("audio_preview_stop").then(setPreview).catch(() => setError(t("audio.operationFailed")))}>{t("audio.stop")}</Btn>
              </div>
              {preview && preview.state !== "idle" ? <div className="text-[12px] text-[var(--meta)]">
                {preview.state === "error" ? <p role="alert" className="m-0">{t("neptune.previewFailed")}</p> : null}
                {preview.name} · {(preview.played_frames / Math.max(1, preview.sample_rate)).toFixed(1)} / {(preview.length_frames / Math.max(1, preview.sample_rate)).toFixed(1)} s
                <div className="h-1.5 mt-2 rounded-full bg-[var(--line)] overflow-hidden"><div className="h-full bg-[var(--accent)]" style={{ width: `${progress}%` }} /></div>
              </div> : null}
              <div className="flex items-end gap-2 flex-wrap">
                <label className="text-[12px] text-[var(--meta)] flex-1 min-w-[140px]">{t("audio.clipName")}
                  <input value={clipName} onChange={(e) => setClipName(e.target.value)} className={`${field} w-full`} />
                </label>
                <Btn disabled={busy} onClick={addClip}>{t("audio.addClip")}</Btn>
              </div>
              <div className="flex gap-2 flex-wrap">
                <Btn disabled={busy} onClick={applyRange}>{t("audio.applyRange")}</Btn>
                <Btn disabled={busy || selectedAsset.available === false} onClick={exportClip}>{t("audio.exportWav")}</Btn>
                {exportBusy ? <Btn onClick={() => void invoke("audio_library_export_cancel")}>{t("audio.cancelExport")}</Btn> : null}
                {sourceId ? (selectedExcluded
                  ? <Btn disabled={busy} onClick={() => void run(async () => { acceptLibrary(await invoke<Library>("audio_library_restore", { sourceId, path: selectedAsset.origin })); })}>{t("audio.restore")}</Btn>
                  : <Btn disabled={busy} onClick={() => void run(async () => { acceptLibrary(await invoke<Library>("audio_library_exclude", { sourceId, assetId: selectedAsset.id })); })}>{t("audio.exclude")}</Btn>) : null}
              </div>
              <AudioHotkeyEditor key={selected.id} entryId={selected.id} entries={library.entries} />
            </div> : <div className="h-full min-h-[220px] grid place-items-center rounded-[var(--r)] border border-dashed border-[var(--line)] bg-[color-mix(in_srgb,var(--group)_55%,transparent)] px-6">
              <p className="m-0 max-w-[300px] text-center text-[12.5px] text-[var(--meta)] leading-relaxed">{t("audio.editEmpty")}</p>
            </div>}
          </Swap>
        </aside>
      </div>

      {/* 底部的语音输出栏：输出设备、总音量，以及正在输出到语音的每一段，每段一行。
          贴着 Dock 放，像是 Dock 往上多出的一层；只在这一页有。 */}
      <section aria-label={t("audio.voiceOutput")} className="mt-4 flex-none flex flex-col px-2 pt-2.5 pb-3 shadow-[0_-1px_0_var(--line)]">
        {voiceInstances.length > 0 ? <div className="max-h-[112px] mb-2 overflow-y-auto overscroll-contain flex flex-col gap-1" aria-label={t("audio.activePlayback")}>
          {voiceInstances.map((instance) => <div key={instance.instance_id}
            className="rise flex items-center gap-2.5 text-[12px] text-[var(--meta)]">
            <span aria-hidden className="flex-none flex items-end gap-[2px] h-3 w-3">{[0, 1, 2].map((i) => <span key={i} className={`${instance.state === "paused" ? "" : "eq-bar"} w-[2px] h-[3px] rounded-full bg-[var(--accent)]`} style={{ animationDelay: `${i * 0.18}s` }} />)}</span>
            <span className="w-[160px] flex-none truncate text-[12.5px] text-[var(--ink)]" title={instance.name}>{instance.name}</span>
            <div className="flex-1 min-w-[120px]">
              <SeekBar label={instance.name}
                position={instance.played_frames / Math.max(1, instance.sample_rate)}
                length={instance.length_frames / Math.max(1, instance.sample_rate)}
                onSeek={(seconds) => void invoke<VoicePlaybackStatus>("audio_voice_seek", {
                  instanceId: instance.instance_id, seconds,
                }).then(setVoice).catch((cause) => setError(String(cause).includes("audio_playback_cancelled")
                  ? t("audio.playbackCancelled") : t("audio.operationFailed")))} />
            </div>
            <span className="flex-none tabular-nums w-[84px] text-right">{(instance.played_frames / Math.max(1, instance.sample_rate)).toFixed(1)} / {(instance.length_frames / Math.max(1, instance.sample_rate)).toFixed(1)} s</span>
            <Btn onClick={() => void invoke<VoicePlaybackStatus>("audio_voice_pause", {
              paused: instance.state !== "paused", instanceId: instance.instance_id,
            }).catch(() => setError(t("audio.operationFailed")))}>{t(instance.state === "paused" ? "audio.resume" : "audio.pause")}</Btn>
            <Btn onClick={() => void invoke<VoicePlaybackStatus>("audio_voice_replay", {
              instanceId: instance.instance_id,
            }).then(setVoice).catch((cause) => setError(String(cause).includes("audio_playback_cancelled")
              ? t("audio.playbackCancelled") : t("audio.operationFailed")))}>{t("audio.replay")}</Btn>
            <Btn on={instance.looping} onClick={() => void invoke<VoicePlaybackStatus>("audio_voice_loop", {
              instanceId: instance.instance_id, looping: !instance.looping,
            }).then(setVoice).catch(() => setError(t("audio.operationFailed")))}>{t("audio.loop")}</Btn>
            <Btn onClick={() => void invoke<VoicePlaybackStatus>("audio_voice_stop_instance", {
              instanceId: instance.instance_id,
            }).then(setVoice).catch(() => setError(t("audio.operationFailed")))}>{t("audio.stop")}</Btn>
          </div>)}
        </div> : null}
        <div className="flex-none flex items-center gap-x-4 gap-y-2 flex-wrap">
          <div className="flex items-center gap-1.5 text-[12px] text-[var(--meta)] min-w-0">
            <span className="flex-none inline-flex items-center gap-1">{t("audio.voiceDevice")}<HelpMark title={t("audio.voiceOutputNote")} /></span>
            <span className="min-w-0 max-w-[240px] truncate text-[12.5px] text-[var(--ink)]" title={outputName || undefined}>{outputName || t("audio.noVoiceDevice")}</span>
            {onOpenDeviceSettings ? <Btn onClick={onOpenDeviceSettings}>{t("audio.changeVoiceDevice")}</Btn> : null}
          </div>
          <div className="flex items-center gap-2 text-[12px] text-[var(--meta)] min-w-[240px] flex-1 max-w-[360px]">
            <span className="flex-none whitespace-nowrap">{t("audio.masterVolume")}</span>
            <div className="flex-1">
              <Slider
                value={volume.muted ? 0 : Math.round(volume.volume * 100)}
                min={0} max={100} step={1}
                onChange={(v) => changeVolume("audio_voice_volume_set", { volume: v / 100 })}
              />
            </div>
            <Btn onClick={() => changeVolume("audio_voice_volume_toggle")}>{t(volume.muted ? "audio.unmute" : "audio.mute")}</Btn>
          </div>
          <label className="flex items-center gap-1.5 text-[12px] text-[var(--meta)]">
            <input type="checkbox" checked={monitor}
              onChange={(event) => { const enabled = event.target.checked; void invoke<boolean>("audio_voice_monitor_set", { enabled })
                .then(setMonitor).catch(() => setError(t("audio.operationFailed"))); }} />
            {t("audio.monitorMusic")}
          </label>
          <span className="ml-auto">
            <Btn disabled={voiceInstances.length === 0 && !voicePreparing} onClick={() => void invoke<VoicePlaybackStatus>("audio_voice_stop").then((status) => {
              setVoice(status);
              setVoiceInstances([]);
            }).catch(() => setError(t("audio.operationFailed")))}>{t("audio.stopAll")}</Btn>
          </span>
        </div>
        {voice?.state === "error" ? <p role="alert" className="flex-none text-[12px] text-[var(--danger)] mt-2 mb-0">{t("audio.voicePlaybackFailed")}</p> : null}
      </section>
      </div>

      {/* 来源行的「⋯」/右键菜单。菜单项绑定 srcMenu.source —— 被点开的那一条，
          刷新/重新定位/移除都发它的稳定 ID，与左侧当前筛选无关。
          执行与 Esc 收菜单才把焦点还给行尾 ⋯；Tab 离开保持焦点走向。 */}
      {srcMenu ? <MoreMenuPopup id="audio-source-menu" anchor={srcMenu.anchor} align={srcMenu.align} onClose={(reason) => {
        menuRestore.current = reason !== "tab";
        setSrcMenu(null);
      }} items={[
        { label: t("audio.refresh"), disabled: busy, action: () => void run(async () => {
          setScanned(0);
          setScanActive(true);
          try { acceptLibrary(await invoke<Library>("audio_library_refresh", { sourceId: srcMenu.source.id })); }
          finally { setScanActive(false); }
        }) },
        ...(srcMenu.source.mode === "reference" ? [{
          label: t("audio.relinkSource"), disabled: busy,
          action: () => relink(srcMenu.source.kind, "source", srcMenu.source.id),
        }] : []),
        { label: t("audio.removeSource"), danger: true, disabled: busy, action: () => void run(async () => {
          if (!(await askConfirm(t("audio.removeConfirm")))) return;
          acceptLibrary(await invoke<Library>("audio_library_remove_source", { sourceId: srcMenu.source.id }));
          if (sourceId === srcMenu.source.id) { setSourceId(""); setSelectedId(""); }
        }) },
      ]} /> : null}
    </PagePad>
  );
}

/** 左栏的一个来源：名称与条目数；行尾「⋯」/行上右键开来源菜单。选中的底色略深。 */
function SourceBtn({ on, label, title, count, onClick, menuLabel, menuOpen, onMenu, onContextMenu }: {
  on: boolean;
  label: string;
  title?: string;
  count: number;
  onClick: () => void;
  /** 传了才挂行尾 ⋯ 与右键（「全部音频」没有来源可管）。 */
  menuLabel?: string;
  /** 这一行的菜单正开着：aria-expanded 用，也让 ⋯ 常显不被 hover 收回。 */
  menuOpen?: boolean;
  onMenu?: (e: MouseEvent<HTMLButtonElement>) => void;
  onContextMenu?: (e: MouseEvent<HTMLElement>, row: HTMLElement) => void;
}) {
  const row = useRef<HTMLDivElement>(null);
  return (
    <div ref={row} className="group relative"
      onContextMenu={onContextMenu ? (e) => {
        e.preventDefault();
        e.stopPropagation();
        onContextMenu(e, row.current ?? e.currentTarget);
      } : undefined}>
      <button type="button" onClick={onClick} aria-pressed={on} aria-label={title}
        className={`w-full flex items-center gap-2 px-2.5 py-1.5 ${onMenu ? "pr-7" : ""} rounded-[var(--rs)] border-0 cursor-pointer text-left text-[13px] transition-colors ${on ? "bg-[color-mix(in_srgb,var(--ink)_7%,transparent)] text-[var(--ink)] font-medium" : "bg-transparent text-[var(--ink-muted)] hover:text-[var(--ink)] hover:bg-[color-mix(in_srgb,var(--ink)_4%,transparent)]"}`}>
        <span className="min-w-0 truncate" title={title}>{label}</span>
        <span className={`flex-none text-[11px] text-[var(--meta)] tabular-nums font-normal ${onMenu ? "" : "ml-auto"}`}>{count}</span>
      </button>
      {onMenu ? <button type="button" data-source-menu aria-label={menuLabel} aria-haspopup="menu"
        aria-expanded={menuOpen ?? false} aria-controls={menuOpen ? "audio-source-menu" : undefined}
        onClick={onMenu}
        className={`absolute right-0.5 top-1/2 -translate-y-1/2 w-6 h-6 grid place-items-center rounded-[6px] border-0 cursor-pointer text-[13px] leading-none text-[var(--meta)] bg-transparent hover:bg-[color-mix(in_srgb,var(--ink)_7%,transparent)] hover:text-[var(--ink)] focus-visible:bg-[color-mix(in_srgb,var(--ink)_7%,transparent)] focus-visible:outline-2 focus-visible:outline-[var(--accent)] focus-visible:outline-offset-[-1px] ${menuOpen ? "opacity-100" : "opacity-0"} group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity`}>
        ⋯
      </button> : null}
    </div>
  );
}
