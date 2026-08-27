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
import { getTLocale, t } from "../i18n/t";

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
  /** Club / department inside a series, e.g. 研讨会. */
  group?: string;
  official?: boolean;
  origin?: string;
  origin_label?: string;
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
    series: "BanG Dream",
  },
  Tomori: {
    zh: "高松灯",
    ja: "高松燈",
    en: "Takamatsu Tomori",
    hant: "高松燈",
    series: "BanG Dream",
  },
  Rana: {
    zh: "要乐奈",
    ja: "要楽奈",
    en: "Kaname Raana",
    hant: "要樂奈",
    series: "BanG Dream",
  },
  Soyo: {
    zh: "长崎爽世",
    ja: "長崎そよ",
    en: "Nagasaki Soyo",
    hant: "長崎爽世",
    series: "BanG Dream",
  },
  Taki: {
    zh: "椎名立希",
    ja: "椎名立希",
    en: "Shiina Taki",
    hant: "椎名立希",
    series: "BanG Dream",
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
  "BanG Dream": { en: "BanG Dream", ja: "BanG Dream", hant: "BanG Dream", ko: "뱅드림" },
  VOCALOID: { en: "VOCALOID", ja: "VOCALOID", hant: "VOCALOID" },
  "蔚蓝档案": { en: "Blue Archive", ja: "ブルーアーカイブ", hant: "蔚藍檔案", ko: "블루 아카이브" },
};

/**
 * Band / club leftover that used to be a top-level `series`.
 * Old catalogs still ship those values; new ones write them as `group`
 * under the franchise. Both shapes must nest the same way in the store.
 */
const SERIES_PARENT: Record<string, string> = {
  Afterglow: "BanG Dream",
  "Hello, Happy World!": "BanG Dream",
  Morfonica: "BanG Dream",
  "Pastel＊Palettes": "BanG Dream",
  "Poppin'Party": "BanG Dream",
  "RAISE A SUILEN": "BanG Dream",
  Roselia: "BanG Dream",
  "MyGO!!!!!": "BanG Dream",
  "Ave Mujica": "BanG Dream",
};

/** Franchise-typical child order. Unknown labels sort after these, 「其他」 last. */
const GROUP_ORDER: string[] = [
  "研讨会",
  "真理部",
  "工程部",
  "游戏开发部",
  "特异现象搜查部",
  "阴阳部",
  "图书委员会",
  "Poppin'Party",
  "Afterglow",
  "Pastel＊Palettes",
  "Hello, Happy World!",
  "Roselia",
  "RAISE A SUILEN",
  "Morfonica",
  "MyGO!!!!!",
  "Ave Mujica",
];

const GROUP_FALLBACK: Record<
  string,
  { en?: string; ja?: string; hant?: string }
> = {
  "真理部": { en: "Veritas", ja: "ヴェリタス", hant: "真理部" },
  "工程部": { en: "Engineering", ja: "エンジニア部", hant: "工程部" },
  "研讨会": { en: "Seminar", ja: "セミナー", hant: "研討會" },
  "游戏开发部": { en: "Game Development", ja: "ゲーム開発部", hant: "遊戲開發部" },
  "特异现象搜查部": {
    en: "Super Phenomenon Task Force",
    ja: "特異現象特捜部",
    hant: "特異現象搜查部",
  },
  "阴阳部": { en: "Yin-Yang Club", ja: "陰陽部", hant: "陰陽部" },
  "图书委员会": { en: "Library Committee", ja: "図書委員会", hant: "圖書委員會" },
  Afterglow: { en: "Afterglow", ja: "Afterglow", hant: "Afterglow" },
  "Hello, Happy World!": {
    en: "Hello, Happy World!",
    ja: "ハロー、ハッピーワールド！",
    hant: "Hello, Happy World!",
  },
  Morfonica: { en: "Morfonica", ja: "Morfonica", hant: "Morfonica" },
  "Pastel＊Palettes": {
    en: "Pastel＊Palettes",
    ja: "Pastel＊Palettes",
    hant: "Pastel＊Palettes",
  },
  "Poppin'Party": { en: "Poppin'Party", ja: "Poppin'Party", hant: "Poppin'Party" },
  "RAISE A SUILEN": {
    en: "RAISE A SUILEN",
    ja: "RAISE A SUILEN",
    hant: "RAISE A SUILEN",
  },
  Roselia: { en: "Roselia", ja: "Roselia", hant: "Roselia" },
  "MyGO!!!!!": { en: "MyGO!!!!!", ja: "MyGO!!!!!", hant: "MyGO!!!!!" },
  "Ave Mujica": { en: "Ave Mujica", ja: "Ave Mujica", hant: "Ave Mujica" },
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

function seriesLabelOf(primary: string, locale: string, v?: NamedVoice): string {
  if (!primary) return "";
  const id = v ? str(v.id) : "";
  const fb = id ? BY_ID[id] : undefined;
  const seriesEn = str(v?.series_en) || fb?.series_en || SERIES_FALLBACK[primary]?.en || "";
  const seriesJa = str(v?.series_ja) || fb?.series_ja || SERIES_FALLBACK[primary]?.ja || "";
  const seriesHant =
    str(v?.series_zh_Hant) || fb?.series_hant || SERIES_FALLBACK[primary]?.hant || primary;

  if (locale === "ja-JP") return seriesJa || primary;
  if (locale === "zh-CN") return primary;
  if (locale === "zh-TW") return seriesHant;
  if (locale === "ko-KR") {
    return SERIES_FALLBACK[primary]?.ko || seriesEn || primary;
  }
  return seriesEn || primary;
}

function catalogSeriesRaw(v: NamedVoice): string {
  const id = str(v.id);
  const fb = id ? BY_ID[id] : undefined;
  return str(v.series) || fb?.series || "";
}

export function displayVoiceSeries(
  v: NamedVoice,
  locale?: LocaleCode | string,
): string {
  const loc = (locale || getTLocale() || "zh-CN") as string;
  return seriesLabelOf(catalogSeriesRaw(v), loc, v);
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
  const raw = catalogSeriesRaw(v);
  const parent = SERIES_PARENT[raw] || raw;
  return seriesLabelOf(parent, loc, SERIES_PARENT[raw] ? undefined : v);
}

/** Only BanG Dream keeps band folders; 蔚蓝档案 and everyone else stay one list. */
function isBangDreamSeries(v: NamedVoice): boolean {
  const raw = catalogSeriesRaw(v);
  return (SERIES_PARENT[raw] || raw) === "BanG Dream";
}

/** Club / band raw key used for sorting and stable focus ids. */
export function voiceGroupRaw(v: NamedVoice): string {
  if (!isBangDreamSeries(v)) return "";
  const g = str(v.group);
  if (g) return g;
  const raw = catalogSeriesRaw(v);
  if (SERIES_PARENT[raw]) return raw;
  return "";
}

/** Club / band label under the parent series. Empty when the series is flat. */
export function voiceChildGroup(
  v: NamedVoice,
  locale?: LocaleCode | string,
): string {
  if (!isBangDreamSeries(v)) return "";
  const loc = (locale || getTLocale() || "zh-CN") as string;
  const g = displayVoiceGroup(v, loc);
  if (g) return g;
  const raw = catalogSeriesRaw(v);
  if (SERIES_PARENT[raw]) return seriesLabelOf(raw, loc);
  return "";
}

export function compareVoiceGroups(aRaw: string, bRaw: string, other = ""): number {
  const rank = (raw: string) => {
    if (!raw || raw === other) return 1000;
    const i = GROUP_ORDER.indexOf(raw);
    return i < 0 ? 500 + raw.charCodeAt(0) : i;
  };
  const d = rank(aRaw) - rank(bRaw);
  if (d !== 0) return d;
  return aRaw.localeCompare(bRaw, "zh");
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
  return voiceAuthorList(v)
    .map((x) => x.name)
    .filter(Boolean)
    .join("、");
}

/** Club / department label inside a series (研讨会, Veritas, …). */
export function displayVoiceGroup(
  v: NamedVoice,
  locale?: LocaleCode | string,
): string {
  const loc = (locale || getTLocale() || "zh-CN") as string;
  const primary = pickFieldI18n(v, "group", loc) || str(v.group);
  if (!primary) return "";
  const fb = GROUP_FALLBACK[str(v.group)] || GROUP_FALLBACK[primary];
  if (loc === "ja-JP") return fb?.ja || primary;
  if (loc === "zh-CN") return primary;
  if (loc === "zh-TW") return fb?.hant || primary;
  return fb?.en || primary;
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
  const { zh, ja, en, hant, id } = resolveParts(v);
  const group = str(v.group);
  const gf = GROUP_FALLBACK[group];
  const rawSeries = catalogSeriesRaw(v);
  const parent = SERIES_PARENT[rawSeries] || "";
  const pf = parent ? SERIES_FALLBACK[parent] : undefined;
  return [
    zh,
    ja,
    en,
    hant,
    id,
    rawSeries,
    parent,
    pf?.en,
    pf?.ja,
    pf?.hant,
    pf?.ko,
    str(v.author),
    str(v.tag),
    group,
    gf?.en,
    gf?.ja,
    gf?.hant,
  ]
    .filter(Boolean)
    .join(" ");
}
