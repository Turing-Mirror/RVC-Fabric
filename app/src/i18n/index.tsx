/**
 * Lightweight i18n for the product shell (no react-i18next dependency).
 *
 * Locale packs live in `app/i18n/locales/{code}.json` and are shared with the
 * Rust host (same files, same keys under tray.* / msg.*).
 *
 * Usage:
 *   const { t, locale, setLocale } = useI18n();
 *   t("dock.start")
 *   t("dock.current", { name: "Foo" })
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { invoke } from "@tauri-apps/api/core";
import {
  fallbackPack,
  interpolate,
  lookup,
  packOf,
} from "./dict";
import {
  DEFAULT_LOCALE,
  LOCALES,
  isLocaleCode,
  type Dict,
  type LocaleCode,
} from "./types";
import {
  setGlossaryLocale,
  termsFrom,
  tip as glossaryTip,
  type GlossaryTerm,
} from "./glossary";
import { setTLocale, t as tStaticExport } from "./t";

export type { LocaleCode, GlossaryTerm };
export { LOCALES, DEFAULT_LOCALE };
export { tip } from "./glossary";
export { t } from "./t";

export type TranslateFn = (
  key: string,
  vars?: Record<string, string | number | undefined | null>,
) => string;

type I18nCtx = {
  locale: LocaleCode;
  setLocale: (code: LocaleCode) => void;
  t: TranslateFn;
  /** Resolve engine `message_code` (msg.*) with optional params object. */
  tMsg: (
    code: string | undefined | null,
    fallback?: string,
    vars?: Record<string, string | number | undefined | null>,
  ) => string;
  glossary: GlossaryTerm[];
  ready: boolean;
};

const Ctx = createContext<I18nCtx | null>(null);

function translate(
  primary: Dict,
  fallback: Dict,
  key: string,
  vars?: Record<string, string | number | undefined | null>,
): string {
  let v = lookup(primary, key);
  if (typeof v !== "string") {
    v = lookup(fallback, key);
  }
  if (typeof v !== "string") {
    // Last resort: show the key so missing translations are obvious in dev.
    return key;
  }
  return interpolate(v, vars);
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<LocaleCode>(DEFAULT_LOCALE);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const cfg = await invoke<Record<string, unknown>>("config_get");
        const raw = cfg.ui_locale;
        if (alive && isLocaleCode(raw)) {
          setLocaleState(raw);
          setStaticLocale(raw);
          setGlossaryLocale(raw);
          setTLocale(raw);
        }
      } catch {
        /* browser preview */
      } finally {
        if (alive) setReady(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const setLocale = useCallback((code: LocaleCode) => {
    setLocaleState(code);
    setStaticLocale(code);
    setGlossaryLocale(code);
    setTLocale(code);
    document.documentElement.lang = code;
    try {
      void invoke("config_set", { patch: { ui_locale: code } });
      void invoke("i18n_set_locale", { locale: code });
    } catch {
      /* no shell */
    }
  }, []);

  useEffect(() => {
    setStaticLocale(locale);
    setGlossaryLocale(locale);
    setTLocale(locale);
    document.documentElement.lang = locale;
  }, [locale]);

  const primary = useMemo(() => packOf(locale), [locale]);
  const fallback = useMemo(() => fallbackPack(), []);

  const t = useCallback<TranslateFn>(
    (key, vars) => translate(primary, fallback, key, vars),
    [primary, fallback],
  );

  const tMsg = useCallback(
    (
      code: string | undefined | null,
      fb?: string,
      vars?: Record<string, string | number | undefined | null>,
    ) => {
      if (code) {
        const key = code.includes(".") ? `msg.${code}` : `msg.${code}`;
        // codes are stored as msg.engine.starting — accept both "engine.starting"
        // and full "msg.engine.starting"
        const path = code.startsWith("msg.") ? code : `msg.${code}`;
        const hit = lookup(primary, path) ?? lookup(fallback, path);
        if (typeof hit === "string") return interpolate(hit, vars);
        // also try without double msg.
        const hit2 = translate(primary, fallback, key, vars);
        if (hit2 !== key) return hit2;
      }
      return fb ?? "";
    },
    [primary, fallback],
  );

  const glossary = useMemo(
    (): GlossaryTerm[] => termsFrom(locale),
    [locale],
  );

  const value = useMemo(
    () => ({ locale, setLocale, t, tMsg, glossary, ready }),
    [locale, setLocale, t, tMsg, glossary, ready],
  );

  // Remount the tree when language changes so modules that call `t()` /
  // `tStatic` without subscribing to context still refresh labels.
  return (
    <Ctx.Provider value={value}>
      <div key={locale} className="contents">
        {children}
      </div>
    </Ctx.Provider>
  );
}

export function useI18n(): I18nCtx {
  const v = useContext(Ctx);
  if (!v) {
    // Safe fallback for components rendered outside provider (tests / edge).
    const primary = packOf(DEFAULT_LOCALE);
    const fb = fallbackPack();
    const t: TranslateFn = (key, vars) => translate(primary, fb, key, vars);
    return {
      locale: DEFAULT_LOCALE,
      setLocale: () => {},
      t,
      tMsg: (code, fallback, vars) => {
        if (code) {
          const path = code.startsWith("msg.") ? code : `msg.${code}`;
          const hit = lookup(primary, path);
          if (typeof hit === "string") return interpolate(hit, vars);
        }
        return fallback ?? "";
      },
      glossary: [],
      ready: true,
    };
  }
  return v;
}

/** Non-hook translate for modules that cannot use hooks (engine.ts helpers). */
export function setStaticLocale(code: LocaleCode) {
  setTLocale(code);
}

export function tStatic(
  key: string,
  vars?: Record<string, string | number | undefined | null>,
): string {
  return tStaticExport(key, vars);
}

/** Hook: glossary for current locale. */
export function useGlossary(): GlossaryTerm[] {
  return useI18n().glossary;
}

export function useGlossarySectionTitle(): string {
  const { t } = useI18n();
  return useMemo(() => t("glossary.sectionTitle"), [t]);
}

// re-export tip for `import { tip } from "../i18n"`
void glossaryTip;
