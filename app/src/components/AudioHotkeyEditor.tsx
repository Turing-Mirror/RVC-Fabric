import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn } from "./ui";
import { Select } from "./controls";
import { useI18n } from "../i18n";
import { AUDIO_ACTIONS, comboFromEvent, type AudioHotkeyBinding } from "../lib/hotkeys";

type Entry = { id: string; name: string };

export function AudioHotkeyEditor({ entries, entryId }: { entries?: Entry[]; entryId?: string }) {
  const { t } = useI18n();
  const [available, setAvailable] = useState<Entry[]>(entries ?? []);
  const [bindings, setBindings] = useState<AudioHotkeyBinding[]>([]);
  const [statuses, setStatuses] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [arming, setArming] = useState(false);
  const [error, setError] = useState("");
  const [recording, setRecording] = useState<string | null>(null);
  const recordingRef = useRef<string | null>(null);
  const armingRef = useRef<string | null>(null);
  const hotkeysEnabledRef = useRef(false);

  useEffect(() => { if (entries) setAvailable(entries); }, [entries]);

  const refresh = useCallback(async () => {
    const [next, config, states] = await Promise.all([
      invoke<AudioHotkeyBinding[]>("audio_hotkeys_get"),
      invoke<Record<string, unknown>>("config_get"),
      invoke<{ binding_id: string; state: string }[]>("audio_hotkeys_status"),
    ]);
    setBindings(next);
    setStatuses(Object.fromEntries(states.map((item) => [item.binding_id, item.state])));
    hotkeysEnabledRef.current = config.hotkeys_enabled === true;
    if (!entries) {
      const library = await invoke<{ entries: Entry[] }>("audio_library_get");
      setAvailable(library.entries);
    }
  }, [entries]);

  useEffect(() => {
    let alive = true;
    void refresh().catch(() => { if (alive) setError(t("audio.operationFailed")); });
    const listener = listen("hotkeys://changed", () => {
      if (alive) void refresh().catch(() => {});
    });
    return () => { alive = false; void listener.then((off) => off()); };
  }, [refresh, t]);

  useEffect(() => () => {
    if (recordingRef.current || armingRef.current) {
      armingRef.current = null;
      void invoke("hotkeys_apply", { enabled: hotkeysEnabledRef.current }).catch(() => {});
    }
  }, []);

  const save = async (next: AudioHotkeyBinding[]) => {
    setBusy(true);
    setError("");
    try {
      await invoke("audio_hotkeys_set", { bindings: next });
      await refresh();
    } catch (cause) {
      setError(String(cause).includes("audio_hotkey_conflict")
        ? t("audio.hotkeyConflict") : t("audio.hotkeySaveFailed"));
      await refresh().catch(() => {});
    } finally {
      setBusy(false);
    }
  };

  const update = (id: string, patch: Partial<AudioHotkeyBinding>) => {
    void save(bindings.map((binding) => binding.binding_id === id ? { ...binding, ...patch } : binding));
  };

  const add = () => {
    const target = entryId ?? available[0]?.id ?? null;
    const next: AudioHotkeyBinding = {
      binding_id: crypto.randomUUID(),
      action: target ? "play-entry" : "pause-current",
      target_entry_id: target,
      combo: "",
      scope: "window",
      enabled: true,
      mode: "replace",
    };
    void save([...bindings, next]);
  };

  const beginRecording = async (id: string) => {
    if (busy || armingRef.current || recordingRef.current) return;
    armingRef.current = id;
    setArming(true);
    setError("");
    try {
      const result = await invoke<{ registered: string[] }>("hotkeys_apply", { enabled: false });
      if (!Array.isArray(result.registered) || result.registered.length) {
        throw new Error("audio_hotkey_suspend_failed");
      }
      if (armingRef.current !== id) {
        await invoke("hotkeys_apply", { enabled: hotkeysEnabledRef.current }).catch(() => {});
        return;
      }
      armingRef.current = null;
      recordingRef.current = id;
      setRecording(id);
    } catch {
      armingRef.current = null;
      setError(t("audio.hotkeySuspendFailed"));
    } finally {
      setArming(false);
    }
  };

  const endRecording = (id: string, combo?: string) => {
    if (armingRef.current === id) {
      armingRef.current = null;
      return;
    }
    if (recordingRef.current !== id) return;
    recordingRef.current = null;
    setRecording(null);
    void (async () => {
      if (combo !== undefined) {
        await save(bindings.map((binding) => binding.binding_id === id ? { ...binding, combo } : binding));
      }
      await invoke("hotkeys_apply", { enabled: hotkeysEnabledRef.current }).catch(() => {});
    })();
  };

  const onRecordKey = (id: string, event: KeyboardEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (event.repeat) return;
    if (event.key === "Escape") { endRecording(id); return; }
    const combo = comboFromEvent(event.nativeEvent);
    if (combo) endRecording(id, combo);
  };

  const shown = entryId
    ? bindings.filter((binding) => binding.action === "play-entry" && binding.target_entry_id === entryId)
    : bindings;
  const actionLabels: Record<string, string> = {
    "play-entry": t("audio.playToVoice"),
    "pause-current": t("audio.hotkeyPauseCurrent"),
    "stop-current": t("audio.hotkeyStopCurrent"),
    "stop-all": t("audio.stopAll"),
    "stop-preview": t("audio.hotkeyStopPreview"),
    "volume-up": t("audio.volumeUp"),
    "volume-down": t("audio.volumeDown"),
    "mute-audio": t("audio.hotkeyToggleMute"),
    "show-audio": t("audio.hotkeyShowAudio"),
  };
  const statusLabels: Record<string, string> = {
    registered: t("audio.hotkeyRegistered"),
    window: t("audio.hotkeyWindow"),
    unbound: t("audio.hotkeyUnbound"),
    disabled: t("audio.hotkeyDisabled"),
    conflict: t("audio.hotkeyConflictStatus"),
  };

  return <div className="space-y-3 text-[12px] text-[var(--meta)]">
    <div className="flex items-center gap-3">
      <span className="text-[13px] text-[var(--ink)]">{t("audio.hotkeySection")}</span>
      <Btn disabled={busy || arming} onClick={add}>{t("audio.hotkeyAdd")}</Btn>
    </div>
    {error ? <p role="alert" className="text-[var(--danger)]">{error}</p> : null}
    {shown.length === 0 ? <p>{t("audio.hotkeyEmpty")}</p> : shown.map((binding) => <div key={binding.binding_id}
      className="flex flex-wrap items-end gap-2 rounded-[var(--rs)] bg-[var(--group)] px-3 py-2">
      {!entryId ? <label>{t("audio.hotkeyAction")}
        <Select value={binding.action} disabled={busy || arming} options={AUDIO_ACTIONS
          .filter((action) => !action.requires_entry || available.length > 0)
          .map((action) => ({ id: action.action, label: actionLabels[action.action] ?? action.action }))}
          onChange={(action) => update(binding.binding_id, {
            action,
            target_entry_id: action === "play-entry" ? available[0]?.id ?? null : null,
          })} />
      </label> : null}
      {binding.action === "play-entry" && !entryId ? <label>{t("audio.hotkeyEntry")}
        <Select value={binding.target_entry_id ?? ""} disabled={busy || arming}
          options={available.map((entry) => ({ id: entry.id, label: entry.name }))}
          onChange={(target_entry_id) => update(binding.binding_id, { target_entry_id })} />
      </label> : null}
      {binding.action === "play-entry" ? <label>{t("audio.hotkeyMode")}
        <Select value={binding.mode ?? "replace"} disabled={busy || arming}
          options={[{ id: "replace", label: t("audio.hotkeyReplace") }, { id: "overlay", label: t("audio.hotkeyOverlay") }]}
          onChange={(mode) => update(binding.binding_id, { mode: mode as "replace" | "overlay" })} />
      </label> : null}
      <label>{t("audio.hotkeyScope")}
        <Select value={binding.scope} disabled={busy || arming}
          options={[{ id: "window", label: t("audio.hotkeyWindow") }, { id: "global", label: t("audio.hotkeyGlobal") }]}
          onChange={(scope) => update(binding.binding_id, { scope: scope as "window" | "global" })} />
      </label>
      <label className="flex items-center gap-1.5 pb-1">
        <input type="checkbox" checked={binding.enabled} disabled={busy || arming}
          onChange={(event) => update(binding.binding_id, { enabled: event.target.checked })} />
        {t("audio.hotkeyEnabled")}
      </label>
      <button type="button" disabled={busy} data-hotkey-recorder
        className="rounded-[var(--rs)] px-3 py-[7px] text-[13px] text-[var(--ink)] bg-transparent shadow-[inset_0_0_0_1px_var(--line)] disabled:opacity-50"
        onClick={() => void beginRecording(binding.binding_id)}
        onBlur={() => endRecording(binding.binding_id)}
        onKeyDown={recording === binding.binding_id ? (event) => onRecordKey(binding.binding_id, event) : undefined}>
        {recording === binding.binding_id ? t("audio.hotkeyRecording") : binding.combo || t("audio.hotkeyRecord")}
      </button>
      <span className="pb-1">{statusLabels[statuses[binding.binding_id] ?? ""] ?? ""}</span>
      <Btn disabled={busy || arming || !binding.combo} onClick={() => update(binding.binding_id, { combo: "" })}>{t("audio.hotkeyClear")}</Btn>
      <Btn disabled={busy || arming} onClick={() => void save(bindings.filter((item) => item.binding_id !== binding.binding_id))}>{t("audio.hotkeyRemove")}</Btn>
    </div>)}
  </div>;
}
