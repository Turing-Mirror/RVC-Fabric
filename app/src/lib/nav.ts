/** Navigation order — must match product shell (首页 广场 模型 设置 说明 其他). */

import { tStatic } from "../i18n";

export type PageId = "home" | "plaza" | "models" | "settings" | "help" | "more";

type NavDef = {
  id: PageId;
  /** i18n key under nav.* */
  labelKey: string;
  badge?: boolean;
};

const NAV_DEFS: readonly NavDef[] = [
  { id: "home", labelKey: "nav.home" },
  { id: "plaza", labelKey: "nav.plaza", badge: true },
  { id: "models", labelKey: "nav.models" },
  { id: "settings", labelKey: "nav.settings" },
  { id: "help", labelKey: "nav.help" },
  { id: "more", labelKey: "nav.more" },
] as const;

/** Resolved labels for the current static locale (call after locale is set). */
export function navPages(): { id: PageId; label: string; badge?: boolean }[] {
  return NAV_DEFS.map((p) => ({
    id: p.id,
    label: tStatic(p.labelKey),
    ...(p.badge ? { badge: true as const } : {}),
  }));
}

/**
 * @deprecated Prefer navPages() so labels follow locale.
 * Kept for modules that only need ids; labels may be zh-CN until locale loads.
 */
export const NAV_PAGES = NAV_DEFS.map((p) => ({
  id: p.id,
  get label() {
    return tStatic(p.labelKey);
  },
  ...(p.badge ? { badge: true as const } : {}),
}));

export function pageIndex(id: PageId): number {
  return NAV_DEFS.findIndex((p) => p.id === id);
}

/** Direction of page wipe: positive = navigate right in nav order. */
export function navDirection(from: PageId, to: PageId): 1 | -1 | 0 {
  const a = pageIndex(from);
  const b = pageIndex(to);
  if (a < 0 || b < 0 || a === b) return 0;
  return b > a ? 1 : -1;
}
