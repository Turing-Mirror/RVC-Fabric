/**
 * Glossary terms — data lives in locale JSON (`glossary.terms`).
 */
import { packOf, fallbackPack, lookup } from "./dict";
import { DEFAULT_LOCALE, type LocaleCode } from "./types";

export type GlossaryTerm = {
  id: string;
  term: string;
  brief: string;
  detail: string;
};

let _staticLocale: LocaleCode = DEFAULT_LOCALE;

/** Called when UI locale changes. */
export function setGlossaryLocale(code: LocaleCode) {
  _staticLocale = code;
}

export function termsFrom(locale: LocaleCode): GlossaryTerm[] {
  const primary = packOf(locale);
  const fb = fallbackPack();
  const raw = lookup(primary, "glossary.terms") ?? lookup(fb, "glossary.terms");
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const o = item as Record<string, unknown>;
      const id = String(o.id ?? "");
      const term = String(o.term ?? "");
      if (!id || !term) return null;
      return {
        id,
        term,
        brief: String(o.brief ?? ""),
        detail: String(o.detail ?? ""),
      };
    })
    .filter((x): x is GlossaryTerm => x != null);
}

/**
 * Detail for a term id or localized label (static locale).
 * Prefer matching by id in new code.
 */
export function tip(termOrId: string): string {
  const list = termsFrom(_staticLocale);
  const hit = list.find((t) => t.term === termOrId || t.id === termOrId);
  return hit?.detail ?? "";
}

export function getGlossary(): GlossaryTerm[] {
  return termsFrom(_staticLocale);
}
