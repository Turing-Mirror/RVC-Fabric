import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

export type MobileStatus = {
  enabled: boolean; connected: boolean; selected: boolean; running: boolean;
  device?: { id: string; name: string; phone: { microphone_ready?: boolean; monitor?: boolean; route?: string } };
  devices: { id: string; name: string; paired_at: number }[];
  output_devices?: { id: string; name: string }[];
  pc_monitor?: { enabled: boolean; device: string };
  voice_output?: { enabled: boolean; device: string };
  settings?: { I_noise_reduce?: boolean; in_gain_db?: number; out_gain_db?: number };
  proc_ms?: number | null; drops?: number;
};
export function useMobile() {
  const [status, setStatus] = useState<MobileStatus>({ enabled: false, connected: false, selected: false, running: false, devices: [] });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    const next = await invoke<MobileStatus>("mobile_status");
    setStatus(next);
  }, []);
  useEffect(() => {
    let alive = true;
    const unlisten = listen<MobileStatus>("mobile-changed", ({ payload }) => {
      if (alive) setStatus(previous => ({ ...previous, ...payload }));
    });
    void refresh().catch(() => {});
    return () => { alive = false; void unlisten.then(fn => fn()); };
  }, [refresh]);
  const action = useCallback(async (value: Record<string, unknown>) => {
    setBusy(true); setError("");
    try {
      const next = await invoke<MobileStatus>("mobile_action", { action: value });
      setStatus(previous => ({ ...previous, ...next }));
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }, []);
  return { status, action, refresh, error, busy };
}
export type MobileController = ReturnType<typeof useMobile>;
