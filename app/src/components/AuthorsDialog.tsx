import { useEffect } from "react";
import { Btn } from "./ui";
import { t } from "../i18n/t";
import { openExternal } from "../lib/plaza";
import type { VoiceAuthor } from "../lib/voices";

/**
 * 多作者时问一声「打开哪一位的主页」。居中卡片，跟关闭询问同一套样式；
 * 点遮罩或 Esc 关闭。模型页和广场的音色卡共用。
 */
export function AuthorsDialog({
  authors,
  onClose,
}: {
  authors: VoiceAuthor[];
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div
      className="fixed inset-0 z-[92] grid place-items-center p-6 bg-[color-mix(in_srgb,var(--ink)_28%,transparent)]"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[360px] rounded-[var(--r)] bg-[var(--surface)] p-5 shadow-[0_20px_60px_rgba(0,0,0,0.22)]"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="m-0 mb-1 text-[15px] font-semibold">{t("s.authorsPickTitle")}</h3>
        <p className="m-0 mb-3.5 text-[12.5px] text-[var(--ink-muted)]">
          {t("s.authorsPickHint")}
        </p>
        <div className="flex flex-col gap-2 items-stretch">
          {authors.map((a) => (
            <Btn
              key={`${a.name}|${a.url}`}
              onClick={() => {
                void openExternal(a.url || "");
                onClose();
              }}
            >
              <span className="block truncate w-full">{a.name}</span>
            </Btn>
          ))}
        </div>
      </div>
    </div>
  );
}
