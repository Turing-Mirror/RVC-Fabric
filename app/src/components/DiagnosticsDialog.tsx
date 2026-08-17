import { useEffect, useRef, useState } from "react";
import { Btn } from "./ui";
import { t } from "../i18n/t";

export type DiagReport = {
  nickname: string;
  qq: string;
  description: string;
  withPerf: boolean;
};

/**
 * 生成诊断包前先问一句：你是谁、遇到了什么。
 *
 * 以前这里是一个 `askConfirm`，只问「要不要顺便跑性能测试」。结果支援收到的
 * 是一个 `diag_20260817_143012.zip`，既不知道该回复谁，也得从三十个日志文件
 * 里反推用户到底想说什么 —— 那件事只有用户自己知道，日志里没有。
 *
 * 三个字段全是可选的：填不填是用户的自由，不填也照样能出包。
 */
export function DiagnosticsDialog({
  open,
  onCancel,
  onSubmit,
}: {
  open: boolean;
  onCancel: () => void;
  onSubmit: (r: DiagReport) => void;
}) {
  const [nickname, setNickname] = useState("");
  const [qq, setQq] = useState("");
  const [description, setDescription] = useState("");
  const [withPerf, setWithPerf] = useState(false);
  const firstRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!open) return;
    setNickname("");
    setQq("");
    setDescription("");
    setWithPerf(false);
    const id = window.setTimeout(() => firstRef.current?.focus(), 30);
    return () => window.clearTimeout(id);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;

  const field =
    "w-full px-[13px] py-[7px] rounded-[var(--rs)] text-[13px] bg-transparent " +
    "text-[var(--ink)] shadow-[inset_0_0_0_1px_var(--line)] outline-none " +
    "focus:shadow-[inset_0_0_0_1px_var(--accent)]";

  return (
    <div
      className="fixed inset-0 z-[100] grid place-items-center p-6 bg-[color-mix(in_srgb,var(--ink)_28%,transparent)]"
      onClick={onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="w-full max-w-[460px] max-h-[88vh] overflow-y-auto rounded-[var(--r)] bg-[var(--surface)] p-6 shadow-[0_22px_56px_-18px_rgba(20,26,33,.34)]"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="m-0 mb-1 text-[15px] font-semibold">{t("s.diagTitle")}</h3>
        <p className="m-0 mb-4 text-[12.5px] text-[var(--meta)] leading-relaxed">
          {t("s.diagLead")}
        </p>

        <label className="block mb-3">
          <span className="block mb-1.5 text-[12.5px] text-[var(--ink-muted)]">
            {t("s.diagNickname")}
          </span>
          <input
            ref={firstRef}
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            maxLength={64}
            placeholder={t("s.diagNicknameHint")}
            className={field}
          />
        </label>

        <label className="block mb-3">
          <span className="block mb-1.5 text-[12.5px] text-[var(--ink-muted)]">
            {t("s.diagQq")}
          </span>
          <input
            value={qq}
            onChange={(e) => setQq(e.target.value)}
            maxLength={32}
            inputMode="numeric"
            placeholder={t("s.diagQqHint")}
            className={field}
          />
        </label>

        <label className="block mb-3">
          <span className="block mb-1.5 text-[12.5px] text-[var(--ink-muted)]">
            {t("s.diagDesc")}
          </span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={4000}
            rows={4}
            placeholder={t("s.diagDescHint")}
            className={field + " resize-y leading-relaxed"}
          />
        </label>

        <label className="flex items-start gap-2.5 mb-4 cursor-pointer">
          <input
            type="checkbox"
            checked={withPerf}
            onChange={(e) => setWithPerf(e.target.checked)}
            className="mt-0.5 accent-[var(--accent)]"
          />
          <span className="text-[12.5px] text-[var(--ink-muted)] leading-relaxed">
            {t("s.diagPerf")}
          </span>
        </label>

        {/* 用户要把这个包发到群里，所以得先说清楚里面有什么、没有什么。 */}
        <p className="m-0 mb-4 rounded-[var(--rs)] bg-[color-mix(in_srgb,var(--ink)_4%,transparent)] px-3 py-2 text-[12px] text-[var(--meta)] leading-relaxed">
          {t("s.diagPrivacy")}
        </p>

        <div className="flex justify-end gap-2.5">
          <Btn onClick={onCancel}>{t("dialog.cancel")}</Btn>
          <Btn
            primary
            onClick={() =>
              onSubmit({ nickname, qq, description, withPerf })
            }
          >
            {t("s.4aa2306395")}
          </Btn>
        </div>
      </div>
    </div>
  );
}
