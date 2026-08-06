import { useEffect, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Btn } from "./ui";
import {
  LOCALES,
  detectSystemLocale,
  useI18n,
  type LocaleCode,
} from "../i18n";

type Props = {
  open: boolean;
  onDone: () => void;
};

/**
 * 首次启动：选界面语言。
 *
 * 默认预选系统语言；确认后写入 ui_locale + ui_locale_picked，之后不再出现。
 * 排在 Runtime 补全之前，这样补全窗本身也是用户选的语言。
 */
export function LanguageGate({ open, onDone }: Props) {
  const { t, locale, setLocale } = useI18n();
  const system = useMemo(() => detectSystemLocale(), []);
  const [choice, setChoice] = useState<LocaleCode>(locale || system);

  useEffect(() => {
    if (open) setChoice(locale || system);
  }, [open, locale, system]);

  if (!open) return null;

  const confirm = () => {
    const code = choice;
    setLocale(code);
    void invoke("config_set", {
      patch: { ui_locale: code, ui_locale_picked: true },
    }).catch(() => {});
    onDone();
  };

  return (
    <div className="absolute inset-0 z-[55] flex items-center justify-center bg-[color-mix(in_srgb,var(--ink)_28%,transparent)] p-6">
      <div className="w-full max-w-[440px] rounded-[var(--r)] bg-[var(--surface)] shadow-[0_22px_56px_-18px_rgba(20,26,33,.34)] p-7">
        <h2 className="text-[22px] font-semibold m-0 mb-2">
          {t("onboarding.languageTitle")}
        </h2>
        <p className="text-[13px] text-[var(--help)] m-0 mb-1 leading-relaxed">
          {t("onboarding.languageDesc")}
        </p>
        <p className="text-[12px] text-[var(--meta)] m-0 mb-5 leading-relaxed">
          {t("onboarding.languageSystemHint", {
            lang: t(
              LOCALES.find((l) => l.id === system)?.labelKey || "locale.zh-CN",
            ),
          })}
        </p>

        <div className="flex flex-col gap-2 mb-6 max-h-[min(48vh,360px)] overflow-y-auto">
          {LOCALES.map((l) => {
            const on = l.id === choice;
            const isSys = l.id === system;
            return (
              <button
                key={l.id}
                type="button"
                onClick={() => {
                  setChoice(l.id);
                  // 实时预览文案，确认前不写盘
                  setLocale(l.id);
                }}
                className={[
                  "text-left border-0 rounded-[var(--rs)] px-3.5 py-2.5 cursor-pointer",
                  "text-[13.5px] transition-colors",
                  on
                    ? "bg-[var(--accent-soft)] text-[var(--ink)] shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--accent)_40%,transparent)]"
                    : "bg-[color-mix(in_srgb,var(--ink)_4%,transparent)] text-[var(--ink-muted)]",
                ].join(" ")}
              >
                <span className="inline-flex items-center flex-wrap gap-x-2">
                  <span>{t(l.labelKey)}</span>
                  {isSys ? (
                    <span className="text-[11.5px] text-[var(--accent)]">
                      {t("onboarding.languageSystemBadge")}
                    </span>
                  ) : null}
                </span>
              </button>
            );
          })}
        </div>

        <div className="flex justify-end">
          <Btn primary onClick={confirm}>
            {t("onboarding.languageContinue")}
          </Btn>
        </div>
      </div>
    </div>
  );
}
