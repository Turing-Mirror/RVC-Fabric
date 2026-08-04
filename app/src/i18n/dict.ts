import type { Dict, LocaleCode } from "./types";
import zh from "../../i18n/locales/zh-CN.json";
import en from "../../i18n/locales/en-US.json";

/** Bundled packs (Vite imports JSON at build time). */
const PACKS: Record<LocaleCode, Dict> = {
  "zh-CN": zh as Dict,
  "en-US": en as Dict,
};

export function packOf(locale: LocaleCode): Dict {
  return PACKS[locale] ?? PACKS["zh-CN"];
}

export function fallbackPack(): Dict {
  return PACKS["zh-CN"];
}

/** Dot-path lookup: "dock.start" → packs.dock.start */
export function lookup(dict: Dict, key: string): unknown {
  const parts = key.split(".").filter(Boolean);
  let cur: unknown = dict;
  for (const p of parts) {
    if (cur == null || typeof cur !== "object") return undefined;
    cur = (cur as Dict)[p];
  }
  return cur;
}

/**
 * Interpolate `{name}` placeholders.
 * Also accepts legacy `${name}` from older catalogs.
 */
export function interpolate(
  template: string,
  vars?: Record<string, string | number | undefined | null>,
): string {
  if (!vars) return template;
  return template
    .replace(/\$\{(\w+)\}/g, (_, k: string) => {
      const v = vars[k];
      return v == null ? "" : String(v);
    })
    .replace(/\{(\w+)\}/g, (_, k: string) => {
      const v = vars[k];
      return v == null ? "" : String(v);
    });
}
