/** Supported UI locales. JSON packs live under app/i18n/locales/. */
export type LocaleCode =
  | "zh-CN"
  | "en-US"
  | "es-ES"
  | "fr-FR"
  | "ja-JP"
  | "ko-KR"
  | "ru-RU"
  | "zh-TW";

export const LOCALES: { id: LocaleCode; labelKey: string }[] = [
  { id: "zh-CN", labelKey: "locale.zh-CN" },
  { id: "zh-TW", labelKey: "locale.zh-TW" },
  { id: "en-US", labelKey: "locale.en-US" },
  { id: "ja-JP", labelKey: "locale.ja-JP" },
  { id: "ko-KR", labelKey: "locale.ko-KR" },
  { id: "es-ES", labelKey: "locale.es-ES" },
  { id: "fr-FR", labelKey: "locale.fr-FR" },
  { id: "ru-RU", labelKey: "locale.ru-RU" },
];

export const DEFAULT_LOCALE: LocaleCode = "zh-CN";

export function isLocaleCode(v: unknown): v is LocaleCode {
  return (
    typeof v === "string" &&
    (LOCALES as { id: string }[]).some((l) => l.id === v)
  );
}

export type GlossaryTerm = {
  id: string;
  term: string;
  brief: string;
  detail: string;
};

export type Dict = Record<string, unknown>;
