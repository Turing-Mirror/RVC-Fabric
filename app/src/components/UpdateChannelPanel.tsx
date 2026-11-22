import { Field, Select } from "./controls";
import { Btn } from "./ui";
import { useI18n } from "../i18n";
import {
  updateChannelLabel,
  type UpdateChannel,
  type UpdateChannelStatus,
  type UpdateInfo,
} from "../lib/updateFlow";
import type { UpdateResult } from "./UpdateNudge";

export type UpdateChannelPanelProps = {
  status: UpdateChannelStatus | null;
  selected: UpdateChannel;
  target: UpdateInfo | null;
  offer: UpdateInfo | null;
  busy: boolean;
  working: boolean;
  error: string;
  result: UpdateResult | null;
  onSelect: (channel: UpdateChannel) => void;
  onAccept: () => void;
  onDismiss: () => void;
};

/** The installed channel stays unchanged until a different program is running. */
export function UpdateChannelPanel({
  status, selected, target, offer, busy, working, error, result,
  onSelect, onAccept, onDismiss,
}: UpdateChannelPanelProps) {
  const { t } = useI18n();
  const switching = offer?.switching_channel === true;
  return <>
    <Field label={t("update.currentChannel")} inline control={
      <span className="text-[13px] text-[var(--ink-muted)]">
        {status ? updateChannelLabel(status.channel) : t("s.valueLoading")}
      </span>
    } />
    <Field label={t("update.targetChannel")} desc={t("update.selectOnly")} inline control={
      <Select width={160} value={selected} disabled={!status || busy}
        ariaLabel={t("update.targetChannel")}
        options={[
          { id: "stable", label: t("update.stable") },
          { id: "beta", label: "Beta" },
        ]}
        onChange={(value) => onSelect(value as UpdateChannel)} />
    } />
    {selected === "beta" ? <p className="text-xs text-[var(--help)] m-0 leading-[1.75]">
      {t("update.betaHint")}
    </p> : null}
    {status && !status.beta_available ? <p className="text-xs text-[var(--help)] m-0 leading-[1.75]">
      {t("update.channelUnavailable")}
    </p> : null}
    {target ? <Field label={t("update.targetVersion")} inline control={
      <span className="text-[13px] text-[var(--ink-muted)] tabular-nums">{target.remote}</span>
    } /> : null}
    {switching && offer ? <div className="flex flex-col gap-3">
      {result ? <>
        <p role="status" className="text-[13px] text-[var(--ink-muted)] m-0">
          {t("s.995e0f4c81", { v0: result.version })}
        </p>
        <div><Btn onClick={onDismiss}>{t("s.cb63c62e50")}</Btn></div>
      </> : <>
        <p className="text-[13px] text-[var(--ink-muted)] m-0">
          {t("update.switchTitle", {
            channel: updateChannelLabel(offer.channel ?? selected), version: offer.remote,
          })}
        </p>
        <p className="text-xs text-[var(--help)] m-0 leading-[1.75]">{t("update.switchBody")}</p>
        {offer.downgrade ? <p className="text-xs text-[var(--help)] m-0 leading-[1.75]">
          {t("update.downgradeBody")}
        </p> : null}
        {offer.legacy_target ? <p className="text-xs text-[var(--help)] m-0 leading-[1.75]">
          {t("update.legacyStableHint")}
        </p> : null}
        {offer.notes ? <p className="text-xs text-[var(--help)] m-0 leading-[1.75] whitespace-pre-wrap">{offer.notes}</p> : null}
        {error ? <p role="alert" className="text-xs text-[var(--danger-text)] m-0">{error}</p> : null}
        <div className="flex flex-wrap gap-2.5">
          <Btn onClick={onDismiss} disabled={busy}>{t("s.479fcc1cc0")}</Btn>
          <Btn primary onClick={onAccept} busy={working} disabled={busy}>
            {working ? t("s.87c1bc6fe6") : t("update.switchInstall")}
          </Btn>
        </div>
      </>}
    </div> : null}
  </>;
}
