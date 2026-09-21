import { Nudge } from "./Nudge";
import { Btn } from "./ui";
import { t } from "../i18n/t";
import type { UpdateInfo } from "../lib/updateFlow";

export type UpdateResult = { version: string; restart: boolean };

/**
 * 更新提示条：待确认 / 在装 / 已完成 三态。
 *
 * 完成后只剩「已更新 + 重启生效 + 知道了」—— 把「下载并安装」摆回去
 * 就是让人对同一版本再装一遍。不自动重启，重启用户自己决定。
 */
export function UpdateNudge({
  offer,
  working,
  busy,
  error,
  result,
  line,
  onAccept,
  onDismiss,
}: {
  offer: UpdateInfo;
  working: boolean;
  busy: boolean;
  error: string;
  result: UpdateResult | null;
  line: string;
  onAccept: () => void;
  onDismiss: () => void;
}) {
  if (result) {
    return (
      <Nudge
        title={t("s.995e0f4c81", { v0: result.version })}
        actions={
          <Btn onClick={onDismiss}>{t("s.cb63c62e50")}</Btn>
        }
      >
        {t("s.3956a2d8bb", {
          v0: offer.local,
          v1: offer.notes || t("s.58941d30b7"),
        })}
      </Nudge>
    );
  }
  return (
    <Nudge
      title={
        working
          ? t("s.87c1bc6fe6")
          : t("s.a462205ca5", { v0: offer.remote })
      }
      actions={
        working ? (
          <Btn onClick={onDismiss} disabled={busy}>
            {busy ? t("s.65188d08a2") : t("s.cb63c62e50")}
          </Btn>
        ) : (
          <>
            <Btn onClick={onDismiss}>
              {error ? t("s.cb63c62e50") : t("s.479fcc1cc0")}
            </Btn>
            <Btn primary onClick={onAccept}>{t("s.f4df9977ea")}</Btn>
          </>
        )
      }
    >
      {working
        ? line
        : error ||
          t("s.3956a2d8bb", {
            v0: offer.local,
            v1: offer.notes || t("s.58941d30b7"),
          })}
    </Nudge>
  );
}
