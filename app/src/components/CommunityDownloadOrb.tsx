import { errorSummary } from "../lib/diagnostics";
import { useEffect, useState } from "react";
import { ProgressOrb } from "trm-ui";
import { useI18n } from "../i18n";
import { useExtraJobs } from "../lib/extraJobs";
import { useStoreJobs } from "../lib/storeJobs";
import { joinClauses } from "../lib/text";

type Props = {
  activePage: string;
  orbSlot?: number;
  onOpenPlaza: () => void;
  onOpenDownloads: () => void;
};

/**
 * 社区页（角色包、引擎资源、分离/训练模型）在后台继续下载时，
 * 切到其他页面后在左下角显示丝滑的进度小球；无报错完成自动收起，出错时亮红点提醒。
 */
export function CommunityDownloadOrb({
  activePage,
  orbSlot = 0,
  onOpenPlaza,
  onOpenDownloads,
}: Props) {
  const { t } = useI18n();
  const store = useStoreJobs();
  const extras = useExtraJobs();
  const [alertErr, setAlertErr] = useState<{ text: string; target: "plaza" | "downloads" } | null>(null);

  const offPlaza = activePage !== "plaza";
  const extraKeys = Object.keys(extras.busyKeys);
  const extraActive = (extras.coreBusy ? 1 : 0) + extraKeys.length;
  const storeActive = store.running.length + store.queued.length;
  const totalActive = extraActive + storeActive;

  useEffect(() => {
    if (!offPlaza) {
      setAlertErr(null);
      return;
    }
    if (extras.hasError && extras.msg) {
      setAlertErr({ text: extras.msg, target: "downloads" });
      return;
    }
    if (store.error) {
      setAlertErr({ text: store.error, target: "plaza" });
      return;
    }
    if (totalActive > 0) {
      setAlertErr(null);
    }
  }, [offPlaza, extras.hasError, extras.msg, store.error, totalActive]);

  const pcts: number[] = [];
  for (const id of store.running) {
    const p = store.prog[id]?.percent;
    if (typeof p === "number" && p > 0) pcts.push(p);
  }
  if (extras.coreBusy && extras.coreProg) {
    const p = extras.coreProg.percent ?? (extras.coreProg.total ? ((extras.coreProg.done ?? 0) / extras.coreProg.total) * 100 : undefined);
    if (typeof p === "number" && p > 0) pcts.push(p);
  }
  for (const k of extraKeys) {
    const p = extras.progByKey[k];
    if (p?.total) pcts.push(((p.done ?? 0) / p.total) * 100);
  }
  const percent = pcts.length > 0 ? Math.min(100, pcts.reduce((a, b) => a + b, 0) / pcts.length) : undefined;

  const showError = offPlaza && totalActive === 0 && alertErr !== null;
  const open = offPlaza && (totalActive > 0 || showError);
  const tooltip = showError
    ? joinClauses([t("s.communityDownloading"), errorSummary(alertErr.text, alertErr.target === "downloads" ? "download" : "store")])
    : joinClauses([
        store.activeLabel || t("s.communityDownloading"),
        totalActive > 1 ? t("s.communityDownloadCount", { v0: totalActive }) : "",
        percent !== undefined ? `${Math.round(percent)}%` : "",
      ]);

  return (
    <ProgressOrb
      open={open}
      contained
      z={50}
      slot={orbSlot}
      bottom={92}
      percent={showError ? undefined : percent}
      attention={showError ? "error" : "idle"}
      label={t("s.orbDownloadLabel")}
      tooltip={tooltip}
      onClick={() => {
        const goDownloads = showError ? alertErr.target === "downloads" : extraActive > 0;
        setAlertErr(null);
        if (goDownloads) onOpenDownloads();
        else onOpenPlaza();
      }}
    />
  );
}
