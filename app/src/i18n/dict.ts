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

export { lookup, interpolate } from "trm-ui";
