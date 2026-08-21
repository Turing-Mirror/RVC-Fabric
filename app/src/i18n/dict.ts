import type { Dict, LocaleCode } from "./types";
import zh from "../../i18n/locales/zh-CN.json";
import en from "../../i18n/locales/en-US.json";
import es from "../../i18n/locales/es-ES.json";
import fr from "../../i18n/locales/fr-FR.json";
import ja from "../../i18n/locales/ja-JP.json";
import ko from "../../i18n/locales/ko-KR.json";
import ru from "../../i18n/locales/ru-RU.json";
import tw from "../../i18n/locales/zh-TW.json";

/** Bundled packs (Vite imports JSON at build time). */
const PACKS: Record<LocaleCode, Dict> = {
  "zh-CN": zh as Dict,
  "en-US": en as Dict,
  "es-ES": es as Dict,
  "fr-FR": fr as Dict,
  "ja-JP": ja as Dict,
  "ko-KR": ko as Dict,
  "ru-RU": ru as Dict,
  "zh-TW": tw as Dict,
};

export function packOf(locale: LocaleCode): Dict {
  return PACKS[locale] ?? PACKS["zh-CN"];
}

export function fallbackPack(): Dict {
  return PACKS["zh-CN"];
}

/** Dot-path lookup: "dock.start" → packs.dock.start ; "s.ab12" → packs.s.ab12 */
export function lookup(dict: Dict, key: string): unknown {
  const parts = key.split(".").filter(Boolean);
  if (!parts.length) return undefined;
  let cur: unknown = dict;
  for (let i = 0; i < parts.length; i++) {
    if (cur == null || typeof cur !== "object") return undefined;
    const part = parts[i];
    const obj = cur as Dict;
    if (part in obj) {
      cur = obj[part];
      continue;
    }
    const rest = parts.slice(i).join(".");
    return obj[rest];
  }
  return cur;
}

/**
 * Interpolate `{name}` placeholders.
 * Also accepts legacy `${name}` from older catalogs, and bare `{}` slots filled
 * left-to-right from `v0`, `v1`, … — the same convention the Rust side's
 * `te`/`t2`/`tn` already handles, so one pack can serve both sides.
 */
export function interpolate(
  template: string,
  vars?: Record<string, string | number | undefined | null>,
): string {
  if (!vars) return template;
  let slot = 0;
  return template
    .replace(/\$\{(\w+)\}/g, (_, k: string) => {
      const v = vars[k];
      return v == null ? "" : String(v);
    })
    .replace(/\{(\w+)\}/g, (_, k: string) => {
      const v = vars[k];
      return v == null ? "" : String(v);
    })
    .replace(/\{\}/g, () => {
      const v = vars[`v${slot++}`];
      return v == null ? "{}" : String(v);
    });
}
