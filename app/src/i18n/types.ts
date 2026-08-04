/** Supported UI locales. Add a JSON under app/i18n/locales/ when extending. */
export type LocaleCode = "zh-CN" | "en-US";

export const LOCALES: { id: LocaleCode; labelKey: string }[] = [
  { id: "zh-CN", labelKey: "locale.zh-CN" },
  { id: "en-US", labelKey: "locale.en-US" },
];

export const DEFAULT_LOCALE: LocaleCode = "zh-CN";

export type GlossaryTerm = {
  id: string;
  term: string;
  brief: string;
  detail: string;
};

export type Dict = Record<string, unknown>;
