import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Btn } from "./ui";
import { Toggle } from "./controls";
import { Nudge } from "./Nudge";
import { Leave } from "./Presence";
import { useI18n } from "../i18n";
import { setConfig, type Config } from "../lib/config";
import { pickAutoDevices } from "../lib/deviceSetup";
import { startVc, type EngineStatus } from "../lib/engine";

type Device = { name: string; hostapi: string; direction: string };

async function recover(action: string, enabled?: boolean, device?: Device) {
  const result = await invoke<{ config: Config; status: EngineStatus }>("audio_recover", { action, enabled, device });
  if (action !== "restore") {
    const patch = pickAutoDevices(result.config, result.status);
    if (patch) await setConfig(patch);
  }
}

export function AudioRecoveryBanner({ status }: { status?: EngineStatus }) {
  const { t } = useI18n();
  const [dismissed, setDismissed] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const reason = String(status?.error || status?.message || "");
  const relevant = /audio|device|portaudio|asio|声卡|设备|音频|裝置|音訊|0xc000/i.test(reason);
  const show = status?.state === "error" && relevant && dismissed !== reason;
  const run = async (action: string) => {
    setBusy(true); setError("");
    try { await recover(action, true); await startVc(); setDismissed(reason); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };
  return <Leave>{show ? <Nudge title={t("neptune.deviceIgnore")} actions={<>
    <Btn disabled={busy} onClick={() => setDismissed(reason)}>{t("neptune.close")}</Btn>
    <Btn disabled={busy} onClick={() => void run("check")}>{t("neptune.deviceIgnore")}</Btn>
    <Btn disabled={busy} onClick={() => void run("compatibility")}>{t("neptune.deviceCompatibility")}</Btn>
  </>}>{error || t("neptune.deviceRecovery")}{" "}{t("neptune.compatibilityHint")}</Nudge> : null}</Leave>;
}

export function AudioRecoverySettings({ config }: { config: Config }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ignored = (Array.isArray(config.ignored_audio_devices) ? config.ignored_audio_devices : []) as Device[];
  const run = async (action: string, enabled?: boolean, device?: Device) => {
    setBusy(true); setError("");
    try { await recover(action, enabled, device); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };
  return <div className="my-4 rounded-[var(--r)] bg-[var(--group)] px-5 py-4 flex flex-col gap-3">
    <div className="flex items-center justify-between gap-3">
      <Toggle label={t("neptune.deviceCompatibility")} checked={config.audio_compatibility === true} disabled={busy} onChange={(v) => void run("compatibility", v)} />
    </div>
    <p className="m-0 text-[12.5px] text-[var(--help)]">{t("neptune.compatibilityHint")}</p>
    {ignored.length > 0 && <>
      <span>{t("neptune.ignoredDevices")}</span>
      <Toggle label={t("neptune.ignoreEnabled")} checked={config.audio_ignore_enabled === true} disabled={busy} onChange={(v) => void run("ignore", v)} />
      <p className="m-0 text-[12.5px] text-[var(--help)]">{t("neptune.ignoredHint")}</p>
      {ignored.map((device) => <div key={`${device.hostapi}:${device.name}:${device.direction}`} className="flex items-center justify-between gap-3">
        <span className="min-w-0 break-words">{device.name} · {device.hostapi} · {t(device.direction === "input" ? "neptune.input" : "neptune.output")}</span>
        <Btn disabled={busy} onClick={() => void run("restore", undefined, device)}>{t("neptune.deviceRestore")}</Btn>
      </div>)}
    </>}
    {error && <p role="alert" className="m-0 text-[12.5px]">{error}</p>}
  </div>;
}
