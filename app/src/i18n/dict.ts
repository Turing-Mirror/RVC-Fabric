import type { Dict, LocaleCode } from "./types";
import zh from "../../i18n/locales/zh-CN.json";

/**
 * 语言包按需加载（D-02）：zh-CN 是默认语言兼回退，随主包走；其余七种各
 * 拆成独立 chunk，第一次切到该语言时才加载——八种语言合计约 1.4MB，
 * 全量打进主包纯粹是启动时白解析。
 */
const LOADERS: Record<LocaleCode, () => Promise<Dict>> = {
  "zh-CN": () => Promise.resolve(zh as Dict),
  "en-US": () => import("../../i18n/locales/en-US.json").then((m) => m.default as Dict),
  "es-ES": () => import("../../i18n/locales/es-ES.json").then((m) => m.default as Dict),
  "fr-FR": () => import("../../i18n/locales/fr-FR.json").then((m) => m.default as Dict),
  "ja-JP": () => import("../../i18n/locales/ja-JP.json").then((m) => m.default as Dict),
  "ko-KR": () => import("../../i18n/locales/ko-KR.json").then((m) => m.default as Dict),
  "ru-RU": () => import("../../i18n/locales/ru-RU.json").then((m) => m.default as Dict),
  "zh-TW": () => import("../../i18n/locales/zh-TW.json").then((m) => m.default as Dict),
};

const PACKS: Partial<Record<LocaleCode, Dict>> = { "zh-CN": zh as Dict };
const PENDING: Partial<Record<LocaleCode, Promise<Dict>>> = {};

/** 加载并缓存语言包；重复调用共享同一条 promise，失败不缓存可重试。 */
export function ensurePack(locale: LocaleCode): Promise<Dict> {
  const got = PACKS[locale];
  if (got) return Promise.resolve(got);
  const inflight = PENDING[locale];
  if (inflight) return inflight;
  const p = LOADERS[locale]()
    .then((d) => {
      PACKS[locale] = d;
      delete PENDING[locale];
      return d;
    })
    .catch((e) => {
      delete PENDING[locale];
      throw e;
    });
  PENDING[locale] = p;
  return p;
}

export function packOf(locale: LocaleCode): Dict {
  return PACKS[locale] ?? PACKS["zh-CN"]!;
}

export function fallbackPack(): Dict {
  return PACKS["zh-CN"]!;
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
