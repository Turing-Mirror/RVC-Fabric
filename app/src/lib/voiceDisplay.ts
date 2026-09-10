/**
 * Localized display for community / official voice packs.
 *
 * Catalog fields (any may be missing):
 *   name / name_i18n       primary name and locale map
 *   series / series_i18n   parent series and locale map
 *   group / group_i18n     optional child group and locale map
 *
 * English (and other non-CJK UI locales): show "原名 English" when both exist
 * e.g. 若葉睦 Wakaba Mutsumi — user request.
 */
import type { LocaleCode } from "../i18n/types";
import { getTLocale, t } from "../i18n/t";

export type LocalizedText = Record<string, string>;

export type NamedVoice = {
  id?: string;
  name?: string;
  name_i18n?: LocalizedText;
  name_ja?: string;
  name_en?: string;
  name_zh_Hant?: string;
  tag_i18n?: LocalizedText;
  description_i18n?: LocalizedText;
  author_i18n?: LocalizedText;
  series?: string;
  series_i18n?: LocalizedText;
  series_ja?: string;
  series_en?: string;
  series_zh_Hant?: string;
  /** Club / department inside a series, e.g. 研讨会. */
  group?: string;
  group_i18n?: LocalizedText;
  official?: boolean;
  origin?: string;
  origin_label?: string;
  [key: string]: unknown;
};

function str(v: unknown): string {
  if (typeof v === "string") return v.trim();
  // 清单 YAML 里未加引号的 YYMMDD 会进 JSON 数字，版本角标不能因此消失。
  if (typeof v === "number" && Number.isFinite(v)) return String(Math.trunc(v));
  return "";
}

/**
 * 发布日期 → 版本号样式的角标（260731 → v26.07.31）。
 *
 * 认三种写法：YYMMDD（清单现行格式）、YYYYMMDD、ISO 前缀。认不出返回空串，
 * 卡片上就不画这个角标 —— 没有日期不该显示成「v」加一串问号。
 */
export function voiceVersionLabel(date?: unknown): string {
  const d = str(date).replace(/[/.]/g, "-");
  let y = "";
  let m = "";
  let day = "";
  if (/^\d{6}$/.test(d)) {
    y = d.slice(0, 2);
    m = d.slice(2, 4);
    day = d.slice(4, 6);
  } else if (/^\d{8}$/.test(d)) {
    y = d.slice(0, 4);
    m = d.slice(4, 6);
    day = d.slice(6, 8);
  } else {
    const mt = d.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
    if (mt) {
      y = mt[1];
      m = mt[2].padStart(2, "0");
      day = mt[3].padStart(2, "0");
    }
  }
  if (!y || !m || !day) return "";
  const yy = y.length === 4 ? y.slice(2) : y;
  if (Number(m) < 1 || Number(m) > 12 || Number(day) < 1 || Number(day) > 31) {
    return "";
  }
  return `v${yy}.${m}.${day}`;
}

export type VoiceAuthor = { name: string; url?: string };

type AuthorSource = {
  author?: unknown;
  author_url?: unknown;
  authors?: unknown;
  // 索引签名不是摆设：NamedVoice 自己带一条，没有它 TS 会把这三个全可选的
  // 类型当「弱类型」，判定两者「没有共同属性」而拒收 —— voiceDisplay.ts:565
  // 那次 tsc 失败就是这样，而 build 脚本里 tsc 排在 vite build 前面。
  [key: string]: unknown;
};

/**
 * 一个音色的作者列表。新写法 `authors` 数组优先（元素是
 * `{name, url}` 或纯字符串），兼容单个 `author` + `author_url` 字段；
 * 名字去重，顺序保持原样。
 */
export function voiceAuthorList(v: AuthorSource): VoiceAuthor[] {
  const out: VoiceAuthor[] = [];
  const push = (name: string, url?: string) => {
    const n = name.trim();
    if (!n || /^(未知|unknown|—|-|n\/a|作者未知|未填写)$/i.test(n)) return;
    const hit = out.find((a) => a.name === n);
    if (hit) {
      if (!hit.url && url) hit.url = url;
      return;
    }
    out.push({ name: n, url: url || undefined });
  };
  if (Array.isArray(v.authors)) {
    for (const a of v.authors) {
      if (typeof a === "string") push(a);
      else if (a && typeof a === "object") {
        const m = a as Record<string, unknown>;
        push(str(m.name), str(m.url) || undefined);
      }
    }
  }
  const single = str(v.author);
  const singleUrl = str(v.author_url);
  if (out.length === 0 && single) push(single, singleUrl);
  else if (single) {
    // authors 里没带主页而单字段带了的话，补给同名那位。
    const hit = out.find((a) => a.name === single);
    if (hit && !hit.url && singleUrl) hit.url = singleUrl;
  }
  return out;
}

function localeCandidates(locale: string): string[] {
  const normalized = locale.replace(/_/g, "-");
  const short = normalized.split("-")[0] || "";
  const out = [locale, normalized, short];
  if (normalized.startsWith("en")) out.push("en-US", "en");
  if (normalized.startsWith("ja")) out.push("ja-JP", "ja");
  if (normalized.startsWith("ko")) out.push("ko-KR", "ko");
  if (normalized.startsWith("es")) out.push("es-ES", "es");
  if (normalized.startsWith("fr")) out.push("fr-FR", "fr");
  if (normalized.startsWith("ru")) out.push("ru-RU", "ru");
  if (normalized === "zh-TW" || normalized === "zh-Hant") {
    out.push("zh-TW", "zh_Hant", "zh-Hant");
  } else if (normalized.startsWith("zh")) {
    out.push("zh-CN", "zh-Hans", "zh-Hans-CN");
  }
  return [...new Set(out.filter(Boolean))];
}

/** Read a locale map without coupling callers to a particular catalog shape. */
export function localizedTextValue(
  value: unknown,
  locale?: LocaleCode | string,
): string {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "";
  const map = value as Record<string, unknown>;
  const loc = String(locale || getTLocale() || "zh-CN");
  for (const candidate of localeCandidates(loc)) {
    const hit = str(map[candidate]);
    if (hit) return hit;
  }
  return "";
}

function localizedFieldValue(
  v: NamedVoice,
  field: string,
  locale: string,
): string {
  const map = v[`${field}_i18n`];
  const localized = localizedTextValue(map, locale);
  if (localized) return localized;
  const normalized = locale.replace(/_/g, "-");
  const short = normalized.split("-")[0] || "";
  for (const key of [
    `${field}_${locale}`,
    `${field}_${normalized}`,
    `${field}_${short}`,
    `${field}_${locale.replace(/-/g, "_")}`,
    normalized === "zh-TW" ? `${field}_zh_Hant` : "",
  ]) {
    if (!key) continue;
    const hit = str(v[key]);
    if (hit) return hit;
  }
  return "";
}

function localizedFieldValues(v: NamedVoice, field: string): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  const add = (value: unknown) => {
    if (typeof value === "object" && value && !Array.isArray(value)) {
      for (const nested of Object.values(value)) add(nested);
      return;
    }
    const item = str(value);
    if (item && !seen.has(item)) {
      seen.add(item);
      out.push(item);
    }
  };
  add(v[field]);
  const map = v[`${field}_i18n`];
  if (map && typeof map === "object" && !Array.isArray(map)) {
    for (const value of Object.values(map)) add(value);
  }
  for (const key of [
    `${field}_en`,
    `${field}_ja`,
    `${field}_zh_Hant`,
    `${field}_ko`,
    `${field}_es`,
    `${field}_fr`,
    `${field}_ru`,
  ]) {
    add(v[key]);
  }
  return out;
}

/** Locale-aware separator for visible lists. */
type ListFormatConstructor = new (
  locales?: string | string[],
  options?: {
    type?: "conjunction" | "disjunction" | "unit";
    style?: "long" | "short" | "narrow";
  },
) => { format(values: string[]): string };

export function formatLocalizedList(
  values: readonly string[],
  locale?: LocaleCode | string,
): string {
  const items = [...new Set(values.map((value) => value.trim()).filter(Boolean))];
  if (items.length < 2) return items[0] || "";
  const loc = locale || getTLocale() || "zh-CN";
  try {
    const ListFormat = (Intl as typeof Intl & {
      ListFormat?: ListFormatConstructor;
    }).ListFormat;
    if (!ListFormat) return items.join(", ");
    return new ListFormat(loc, {
      type: "conjunction",
      style: "short",
    }).format(items);
  } catch {
    return items.join(", ");
  }
}

function resolveParts(v: NamedVoice) {
  const id = str(v.id);
  const zh = localizedFieldValue(v, "name", "zh-CN") || str(v.name) || id || "?";
  const ja = localizedFieldValue(v, "name", "ja-JP") || str(v.name_ja);
  const en = localizedFieldValue(v, "name", "en-US") || str(v.name_en);
  const hant =
    localizedFieldValue(v, "name", "zh-TW") || str(v.name_zh_Hant) || zh;
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
    return ja || en || zh;
  }
  if (loc === "zh-CN") {
    return zh;
  }
  if (loc === "zh-TW") {
    return hant || zh;
  }
  const localized = localizedFieldValue(v, "name", loc);
  if (localized && !loc.startsWith("en")) {
    return localized;
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
  return localizedFieldValue(v, field, locale) || str(v[field]);
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

function catalogSeriesRaw(v: NamedVoice): string {
  return str(v.series);
}

export function displayVoiceSeries(
  v: NamedVoice,
  locale?: LocaleCode | string,
): string {
  const loc = (locale || getTLocale() || "zh-CN") as string;
  return pickFieldI18n(v, "series", loc) || catalogSeriesRaw(v);
}

function namesEqual(a: string, b: string): boolean {
  return a.trim().toLowerCase() === b.trim().toLowerCase();
}

/**
 * True when a series key is just the only voice's own name.
 *
 * Catalog rows sometimes put the character in `series` (ATRI / ATRI).
 * Treating that as a franchise makes one character look like a category.
 */
export function isCharacterAsSeries(
  seriesKey: string,
  voices: NamedVoice[],
  locale?: LocaleCode | string,
): boolean {
  const s = seriesKey.trim();
  if (!s || voices.length !== 1) return false;
  const loc = locale || getTLocale();
  const v = voices[0];
  return (
    namesEqual(s, displayVoiceName(v, loc)) ||
    namesEqual(s, str(v.name)) ||
    namesEqual(s, str(v.id))
  );
}

/** True when a child-group label is just that one voice's name. */
export function isCharacterAsGroup(
  groupLabel: string,
  voices: NamedVoice[],
  locale?: LocaleCode | string,
): boolean {
  const g = groupLabel.trim();
  if (!g || voices.length !== 1) return false;
  const loc = locale || getTLocale();
  const v = voices[0];
  return namesEqual(g, displayVoiceName(v, loc)) || namesEqual(g, str(v.name));
}

/** Franchise / IP the voice belongs to (蔚蓝档案, BanG Dream, …). */
export function voiceParentSeries(
  v: NamedVoice,
  locale?: LocaleCode | string,
): string {
  const loc = (locale || getTLocale() || "zh-CN") as string;
  return displayVoiceSeries(v, loc);
}

/** Raw child-group key used for sorting and stable focus ids. */
export function voiceGroupRaw(v: NamedVoice): string {
  return str(v.group);
}

/** Localized child-group label. Empty when the catalog row has no group. */
export function voiceChildGroup(
  v: NamedVoice,
  locale?: LocaleCode | string,
): string {
  const loc = (locale || getTLocale() || "zh-CN") as string;
  return displayVoiceGroup(v, loc);
}

export function compareVoiceGroups(
  aRaw: string,
  bRaw: string,
  other = "",
  locale?: LocaleCode | string,
): number {
  const aEmpty = !aRaw || aRaw === other;
  const bEmpty = !bRaw || bRaw === other;
  if (aEmpty !== bEmpty) return aEmpty ? 1 : -1;
  return aRaw.localeCompare(bRaw, locale || getTLocale() || "zh-CN");
}

/** Author line for store / library cards. Picks locale from author_i18n when present. */
export function displayVoiceAuthor(
  v: NamedVoice,
  locale?: LocaleCode | string,
): string {
  const loc = (locale || getTLocale() || "zh-CN") as string;
  const fromI18n = pickFieldI18n(v, "author", loc);
  if (fromI18n) return fromI18n;
  const a = v.author;
  if (a && typeof a === "object" && !Array.isArray(a)) {
    const m = a as Record<string, unknown>;
    const hit = str(m[loc]) || str(m["zh-CN"]) || str(m.zh) || "";
    if (hit) return hit;
  }
  const single = str(a);
  if (single) return single;
  // 只有 authors 数组、没有单个 author 字段时，广场/首页也会走到这里。
  return formatLocalizedList(
    voiceAuthorList(v).map((x) => x.name),
    loc,
  );
}

/** Club / department label inside a series (研讨会, Veritas, …). */
export function displayVoiceGroup(
  v: NamedVoice,
  locale?: LocaleCode | string,
): string {
  const loc = (locale || getTLocale() || "zh-CN") as string;
  const primary = pickFieldI18n(v, "group", loc) || str(v.group);
  return primary;
}

/** 清单 `origin` 是站点代号；卡片上要写成「第三方 · Hugging Face」。 */
function originDisplayName(origin: string): string {
  const trimmed = origin.trim();
  switch (trimmed.toLowerCase()) {
    case "huggingface":
    case "hf":
    case "hugging-face":
      return "Hugging Face";
    case "cnb":
      return "CNB";
    default:
      return trimmed;
  }
}

/**
 * 社区音色来源一行。后端会填 `origin_label`，但旧缓存 / 插值失败时会留下
 * 「第三方 · {origin}」——前端再算一次，占位符不能露给用户。
 */
export function displayVoiceOrigin(v: NamedVoice): string {
  const official = v.official !== false;
  const origin = str(v.origin);
  const label = str(v.origin_label);
  if (label && !label.includes("{origin}") && !label.includes("${origin}")) {
    return label;
  }
  if (official) {
    return origin ? originDisplayName(origin) : t("s.7c134b6e64");
  }
  const shown = originDisplayName(origin);
  if (!shown) return t("s.4500b5dfc7");
  return t("s.d03c6cb553", { origin: shown });
}

/** Search haystack: all name variants so filtering works in any language. */
export function voiceSearchText(v: NamedVoice): string {
  return [
    ...localizedFieldValues(v, "name"),
    ...localizedFieldValues(v, "series"),
    ...localizedFieldValues(v, "group"),
    ...localizedFieldValues(v, "author"),
    ...localizedFieldValues(v, "tag"),
    ...localizedFieldValues(v, "description"),
    str(v.id),
    ...voiceAuthorList(v).map((author) => author.name),
  ]
    .filter(Boolean)
    .join(" ");
}
