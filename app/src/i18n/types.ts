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

/**
 * Map OS / browser language tags to a supported UI locale.
 * e.g. zh, zh-Hans-CN → zh-CN; en-GB → en-US; zh-TW / zh-HK → zh-TW.
 */
export function detectSystemLocale(
  tag?: string | null,
): LocaleCode {
  const raw = (tag ||
    (typeof navigator !== "undefined"
      ? navigator.language || navigator.languages?.[0]
      : "") ||
    DEFAULT_LOCALE)
    .toString()
    .trim()
    .replace(/_/g, "-");
  if (!raw) return DEFAULT_LOCALE;
  if (isLocaleCode(raw)) return raw;
  // zh-Hans-CN, zh-CN-xxx
  const lower = raw.toLowerCase();
  if (lower.startsWith("zh")) {
    if (
      lower.includes("tw") ||
      lower.includes("hk") ||
      lower.includes("mo") ||
      lower.includes("hant")
    ) {
      return "zh-TW";
    }
    return "zh-CN";
  }
  const base = lower.split("-")[0];
  const map: Record<string, LocaleCode> = {
    en: "en-US",
    ja: "ja-JP",
    ko: "ko-KR",
    es: "es-ES",
    fr: "fr-FR",
    ru: "ru-RU",
  };
  return map[base] ?? DEFAULT_LOCALE;
}

export type GlossaryTerm = {
  id: string;
  term: string;
  brief: string;
  detail: string;
};

export type Dict = Record<string, unknown>;
