/**
 * Non-React translate. Safe for lib modules and for components after
 * I18nProvider remounts on locale change (see index.tsx).
 *
 * Keys: semantic (`dock.start`) or auto (`s.<hash>`).
 */
import { fallbackPack, interpolate, lookup, packOf } from "./dict";
import { DEFAULT_LOCALE, type LocaleCode } from "./types";

let _locale: LocaleCode = DEFAULT_LOCALE;

export function setTLocale(code: LocaleCode) {
  _locale = code;
}

export function getTLocale(): LocaleCode {
  return _locale;
}

export type TVars = Record<string, string | number | undefined | null>;

export function t(key: string, vars?: TVars): string {
  const primary = packOf(_locale);
  const fb = fallbackPack();
  let v = lookup(primary, key);
  if (typeof v !== "string") {
    v = lookup(fb, key);
  }
  // en-US may leave s.* empty — already fell back to zh via lookup on fb
  if (typeof v !== "string") {
    return key;
  }
  return interpolate(v, vars);
}
