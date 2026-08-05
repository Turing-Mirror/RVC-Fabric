/**
 * Localized display for community / official voice packs.
 *
 * Catalog fields (any may be missing):
 *   name           zh-Hans primary (legacy; always present)
 *   name_ja        Japanese
 *   name_en        English / romanization
 *   name_zh_Hant   Traditional Chinese
 *   series         primary series label (often zh)
 *   series_ja / series_en / series_zh_Hant
 *
 * English (and other non-CJK UI locales): show "原名 English" when both exist
 * e.g. 若葉睦 Wakaba Mutsumi — user request.
 */
import type { LocaleCode } from "../i18n/types";
import { getTLocale } from "../i18n/t";

export type NamedVoice = {
  id?: string;
  name?: string;
  name_ja?: string;
  name_en?: string;
  name_zh_Hant?: string;
  series?: string;
  series_ja?: string;
  series_en?: string;
  series_zh_Hant?: string;
  [key: string]: unknown;
};

/** Built-in fallbacks when catalog cache is old / missing i18n fields. */
const BY_ID: Record<
  string,
  {
    zh: string;
    ja?: string;
    en?: string;
    hant?: string;
    series?: string;
    series_ja?: string;
    series_en?: string;
    series_hant?: string;
  }
> = {
  Anon: {
    zh: "千早爱音",
    ja: "千早愛音",
    en: "Chihaya Anon",
    hant: "千早愛音",
    series: "MyGO!!!!!",
  },
  Tomori: {
    zh: "高松灯",
    ja: "高松燈",
    en: "Takamatsu Tomori",
    hant: "高松燈",
    series: "MyGO!!!!!",
  },
  Rana: {
    zh: "要乐奈",
    ja: "要楽奈",
    en: "Kaname Raana",
    hant: "要樂奈",
    series: "MyGO!!!!!",
  },
  Soyo: {
    zh: "长崎爽世",
    ja: "長崎そよ",
    en: "Nagasaki Soyo",
    hant: "長崎爽世",
    series: "MyGO!!!!!",
  },
  Taki: {
    zh: "椎名立希",
    ja: "椎名立希",
    en: "Shiina Taki",
    hant: "椎名立希",
    series: "MyGO!!!!!",
  },
  "tp-nahida": {
    zh: "纳西妲",
    ja: "ナヒーダ",
    en: "Nahida",
    hant: "納西妲",
    series: "原神",
    series_en: "Genshin Impact",
    series_ja: "原神",
    series_hant: "原神",
  },
  "tp-furina": {
    zh: "芙宁娜",
    ja: "フリーナ",
    en: "Furina",
    hant: "芙寧娜",
    series: "原神",
    series_en: "Genshin Impact",
    series_ja: "原神",
    series_hant: "原神",
  },
  "tp-raiden": {
    zh: "雷电将军",
    ja: "雷電将軍",
    en: "Raiden Shogun",
    hant: "雷電將軍",
    series: "原神",
    series_en: "Genshin Impact",
    series_ja: "原神",
    series_hant: "原神",
  },
  "tp-zhongli": {
    zh: "钟离",
    ja: "鍾離",
    en: "Zhongli",
    hant: "鍾離",
    series: "原神",
    series_en: "Genshin Impact",
    series_ja: "原神",
    series_hant: "原神",
  },
  "tp-miku": {
    zh: "初音未来",
    ja: "初音ミク",
    en: "Hatsune Miku",
    hant: "初音未來",
    series: "VOCALOID",
  },
  "tp-miku-power": {
    zh: "初音未来（Power）",
    ja: "初音ミク（Power）",
    en: "Hatsune Miku (Power)",
    hant: "初音未來（Power）",
    series: "VOCALOID",
  },
  "tp-trump": {
    zh: "唐纳德·特朗普",
    ja: "ドナルド・トランプ",
    en: "Donald Trump",
    hant: "唐納·川普",
  },
  guanguan: { zh: "guanguanV1", en: "guanguanV1", series: "RVC原版", series_en: "RVC Original", series_ja: "RVCオリジナル", series_hant: "RVC原版" },
  keruan: { zh: "keruanV1", en: "keruanV1", series: "RVC原版", series_en: "RVC Original", series_ja: "RVCオリジナル", series_hant: "RVC原版" },
  kiki: { zh: "kikiV1", en: "kikiV1", series: "RVC原版", series_en: "RVC Original", series_ja: "RVCオリジナル", series_hant: "RVC原版" },
  "youzhanv2-xi": {
    zh: "youzhanv2-xi",
    en: "youzhanv2-xi",
    series: "RVC原版",
    series_en: "RVC Original",
    series_ja: "RVCオリジナル",
    series_hant: "RVC原版",
  },
};

const SERIES_FALLBACK: Record<
  string,
  { en?: string; ja?: string; hant?: string; ko?: string }
> = {
  "原神": { en: "Genshin Impact", ja: "原神", hant: "原神", ko: "원신" },
  "RVC原版": { en: "RVC Original", ja: "RVCオリジナル", hant: "RVC原版", ko: "RVC 오리지널" },
  "MyGO!!!!!": { en: "MyGO!!!!!", ja: "MyGO!!!!!", hant: "MyGO!!!!!" },
  VOCALOID: { en: "VOCALOID", ja: "VOCALOID", hant: "VOCALOID" },
};

function str(v: unknown): string {
  return typeof v === "string" ? v.trim() : "";
}

function resolveParts(v: NamedVoice) {
  const id = str(v.id);
  const fb = id ? BY_ID[id] : undefined;
  const zh = str(v.name) || fb?.zh || id || "?";
  const ja = str(v.name_ja) || fb?.ja || "";
  const en = str(v.name_en) || fb?.en || "";
  const hant = str(v.name_zh_Hant) || fb?.hant || zh;
  return { zh, ja, en, hant, id };
}

/**
 * Card / list title for the store (and install display_name).
 */
export function displayVoiceName(
  v: NamedVoice,
  locale?: LocaleCode | string,
): string {
  const loc = (locale || getTLocale() || "zh-CN") as string;
  const { zh, ja, en, hant } = resolveParts(v);

  if (loc === "ja-JP") {
    return ja || zh;
  }
  if (loc === "zh-CN") {
    return zh;
  }
  if (loc === "zh-TW") {
    return hant || zh;
  }
  // en-US / es-ES / fr-FR / ko-KR / ru-RU / …
  // Prefer "原名(日) English" so Latin UI still shows the original script.
  const native = ja || zh;
  if (en) {
    if (native && native !== en) {
      return `${native} ${en}`;
    }
    return en;
  }
  return native;
}

/** Pick from `field_i18n` map / flat aliases, then primary field. */
function pickFieldI18n(
  v: NamedVoice,
  field: string,
  locale: string,
): string {
  const map = v[`${field}_i18n`];
  if (map && typeof map === "object" && !Array.isArray(map)) {
    const m = map as Record<string, unknown>;
    const cands = [locale, locale.split("-")[0] || ""];
    if (locale.startsWith("en")) cands.push("en-US", "en");
    if (locale.startsWith("ja")) cands.push("ja-JP", "ja");
    if (locale.startsWith("ko")) cands.push("ko-KR", "ko");
    if (locale === "zh-TW") cands.push("zh_Hant", "zh-Hant");
    for (const c of cands) {
      if (!c) continue;
      const hit = str(m[c]);
      if (hit) return hit;
    }
  }
  const short = locale.split("-")[0] || "";
  for (const k of [
    `${field}_${locale}`,
    `${field}_${short}`,
    `${field}_${locale.replace(/-/g, "_")}`,
    locale === "zh-TW" ? `${field}_zh_Hant` : "",
  ]) {
    if (!k) continue;
    const hit = str(v[k]);
    if (hit) return hit;
  }
  return str(v[field]);
}

/** Store card tag line (少女音 / Girl voice / …). */
export function displayVoiceTag(
  v: NamedVoice,
  locale?: LocaleCode | string,
): string {
  const loc = (locale || getTLocale() || "zh-CN") as string;
  return pickFieldI18n(v, "tag", loc);
}

/** Longer description under the card / detail. */
export function displayVoiceDescription(
  v: NamedVoice,
  locale?: LocaleCode | string,
): string {
  const loc = (locale || getTLocale() || "zh-CN") as string;
  return pickFieldI18n(v, "description", loc);
}

export function displayVoiceSeries(
  v: NamedVoice,
  locale?: LocaleCode | string,
): string {
  const loc = (locale || getTLocale() || "zh-CN") as string;
  const id = str(v.id);
  const fb = id ? BY_ID[id] : undefined;
  const primary = str(v.series) || fb?.series || "";
  if (!primary) return "";

  const seriesEn = str(v.series_en) || fb?.series_en || SERIES_FALLBACK[primary]?.en || "";
  const seriesJa = str(v.series_ja) || fb?.series_ja || SERIES_FALLBACK[primary]?.ja || "";
  const seriesHant =
    str(v.series_zh_Hant) || fb?.series_hant || SERIES_FALLBACK[primary]?.hant || primary;

  if (loc === "ja-JP") return seriesJa || primary;
  if (loc === "zh-CN") return primary;
  if (loc === "zh-TW") return seriesHant;
  if (loc === "ko-KR") {
    return SERIES_FALLBACK[primary]?.ko || seriesEn || primary;
  }
  // Latin locales
  return seriesEn || primary;
}

/** Search haystack: all name variants so filtering works in any language. */
export function voiceSearchText(v: NamedVoice): string {
  const { zh, ja, en, hant, id } = resolveParts(v);
  return [zh, ja, en, hant, id, str(v.series), str(v.author), str(v.tag)]
    .filter(Boolean)
    .join(" ");
}
