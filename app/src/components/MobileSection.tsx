import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Block, Btn, Group, ListItem } from "./ui";
import { Select, Toggle, Slider } from "./controls";
import { useI18n } from "../i18n";
import type { MobileController } from "../hooks/useMobile";

type Invitation = { payload: string; svg: string; expires_at: number; endpoint: string; addresses: string[]; host: string };
function GainControl({ label, value, min, max, onChange }: {
  label: string; value: number; min: number; max: number; onChange: (value: number) => Promise<void>;
}) {
  const [draft, setDraft] = useState<number | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const revision = useRef(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const change = (next: number) => {
    setDraft(next); window.clearTimeout(timer.current);
    const request = ++revision.current;
    timer.current = window.setTimeout(() => {
      void onChange(next).finally(() => { if (request === revision.current) setDraft(null); });
    }, 250);
  };
  return <ListItem title={label} right={<Slider value={draft ?? value} min={min} max={max} step={0.5}
    onChange={change} ariaLabel={label} format={v => `${v} dB`} />} />;
}
export function MobileSection({ mobile }: { mobile: MobileController }) {
  const { t } = useI18n();
  const { status, action, busy } = mobile;
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  const [pairing, setPairing] = useState(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());
  const [copied, setCopied] = useState(false);
  const [page, setPage] = useState(0);
  const [routeDevice, setRouteDevice] = useState({ monitor: "", output: "" });
  useEffect(() => {
    if (!invitation) return;
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(tick);
  }, [invitation]);
  const pair = async (host?: string) => {
    setPairing(true); setError(""); setCopied(false);
    try { setInvitation(await invoke<Invitation>("mobile_pairing", { host })); await mobile.refresh(); }
    catch (e) { setError(String(e)); }
    finally { setPairing(false); }
  };
  const left = invitation ? Math.max(0, Math.ceil((invitation.expires_at - now) / 1000)) : 0;
  const devices = status.devices || [];
  const pages = Math.max(1, Math.ceil(devices.length / 5));
  const currentPage = Math.min(page, pages - 1);
  const route = (kind: "monitor" | "output") => {
    const current = kind === "monitor" ? status.pc_monitor : status.voice_output;
    const device = routeDevice[kind] || current?.device || "";
    return <ListItem title={t(kind === "monitor" ? "mobile.monitor" : "mobile.output")}
      right={<div className="flex flex-wrap items-center justify-end gap-3">
        <Select value={device} options={[{ id: "", label: t("s.53e2db7016") }, ...(status.output_devices || []).map(d => ({ id: d.id, label: d.name }))]}
          onChange={id => { setRouteDevice(p => ({ ...p, [kind]: id })); if (current?.enabled) void action({ type: kind, enabled: !!id, device: id }); }} />
        <Toggle label={t(kind === "monitor" ? "mobile.monitor" : "mobile.output")} checked={!!current?.enabled}
          disabled={busy || (!device && !current?.enabled)} onChange={enabled => void action({ type: kind, enabled, device })} />
      </div>} />;
  };
  return <Block title={t("mobile.pairing")}>
    <Group>
      <ListItem title={status.connected ? status.device?.name || t("mobile.paired") : t("mobile.connectPhone")}
        desc={status.connected ? (status.device?.phone?.microphone_ready ? t("mobile.microphoneReady") : t("mobile.waitMicrophone")) : t("mobile.pairHint")}
        right={<div className="flex flex-wrap gap-2">
          <Btn disabled={pairing} onClick={() => void pair(invitation?.host)}>{t(invitation ? "mobile.refreshQr" : "mobile.showQr")}</Btn>
          {status.enabled && <Btn disabled={busy} onClick={() => { void action({ type: "disable" }); setInvitation(null); }}>{t("mobile.disable")}</Btn>}
        </div>} />
      {invitation && !status.connected && <div className="px-5 py-4 flex flex-wrap gap-5 items-center">
        {left > 0 ? <img src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(invitation.svg)}`} alt={t("mobile.pairing")}
          className="w-64 h-64 max-w-full bg-white rounded-[var(--rs)]" /> : <p role="status">{t("mobile.expired")}</p>}
        <div className="flex flex-col gap-3 min-w-0 flex-1">
          <Select value={invitation.host} options={invitation.addresses.map(id => ({ id, label: id }))}
            onChange={host => void pair(host)} disabled={pairing} />
          <span className="text-[13px] break-all">{invitation.endpoint}</span>
          <span className="text-xs text-[var(--meta)]">{t("mobile.expires", { seconds: left })}</span>
          <Btn disabled={!left} onClick={() => { void navigator.clipboard.writeText(invitation.payload).then(() => setCopied(true)).catch(() => setError("clipboard_failed")); }}>{t(copied ? "mobile.copied" : "mobile.copy")}</Btn>
        </div>
      </div>}
      {status.connected && <>
        <ListItem title={t("mobile.source")} desc={t(status.selected ? "mobile.phoneSource" : "mobile.computerSource")}
          right={<div className="flex flex-wrap gap-2">
            <Btn disabled={busy || status.selected || !status.device?.phone?.microphone_ready} onClick={() => void action({ type: "use" })}>{t("mobile.usePhone")}</Btn>
            <Btn disabled={busy || !status.selected} onClick={() => void action({ type: "computer" })}>{t("mobile.useComputer")}</Btn>
            <Btn disabled={busy} onClick={() => void action({ type: "disconnect" })}>{t("mobile.disconnect")}</Btn>
          </div>} />
        <ListItem title={t("mobile.soundDestination")} desc={t("mobile.soundHint")}
          right={<Btn onClick={() => void mobile.refresh().catch(e => setError(String(e)))}>{t("mobile.refreshDevices")}</Btn>} />
        {route("monitor")}{route("output")}
        <ListItem title={t("mobile.phoneOutput")} desc={status.device?.phone?.route || t("mobile.phoneOutputHint")} />
        <ListItem title={t("mobile.denoise")} right={<Toggle label={t("mobile.denoise")} checked={!!status.settings?.I_noise_reduce} disabled={busy}
          onChange={enabled => void action({ type: "settings", patch: { I_noise_reduce: enabled } })} />} />
        <GainControl label={t("s.02942ba343")} value={status.settings?.in_gain_db ?? 0} min={-12} max={24}
          onChange={value => action({ type: "settings", patch: { in_gain_db: value } })} />
        <GainControl label={t("mobile.gain")} value={status.settings?.out_gain_db ?? 0} min={-30} max={12}
          onChange={value => action({ type: "settings", patch: { out_gain_db: value } })} />
      </>}
      {devices.slice(currentPage * 5, (currentPage + 1) * 5).map(device => <ListItem key={device.id} title={device.name}
        desc={t(device.id === status.device?.id ? "mobile.paired" : "mobile.remembered")}
        right={<Btn disabled={busy} onClick={() => void action({ type: "revoke", id: device.id })}>{t("mobile.forget")}</Btn>} />)}
      {pages > 1 && <div className="flex justify-end gap-2 p-3" aria-label={t("mobile.devices")}>
        {Array.from({ length: pages }, (_, i) => <Btn key={i} disabled={i === currentPage} onClick={() => setPage(i)}>{i + 1}</Btn>)}
      </div>}
      {(error || mobile.error) && <p role="alert" className="px-5 py-3 text-[var(--notify)]">{t("mobile.failed")}</p>}
    </Group>
  </Block>;
}
