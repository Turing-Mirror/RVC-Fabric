/** Navigation order — must match product shell (首页 广场 模型 设置 说明 其他). */
export const NAV_PAGES = [
  { id: "home", label: "首页" },
  { id: "plaza", label: "广场", badge: true },
  { id: "models", label: "模型" },
  { id: "settings", label: "设置" },
  { id: "help", label: "说明" },
  { id: "more", label: "其他" },
] as const;

export type PageId = (typeof NAV_PAGES)[number]["id"];

export function pageIndex(id: PageId): number {
  return NAV_PAGES.findIndex((p) => p.id === id);
}

/** Direction of page wipe: positive = navigate right in nav order. */
export function navDirection(from: PageId, to: PageId): 1 | -1 | 0 {
  const a = pageIndex(from);
  const b = pageIndex(to);
  if (a < 0 || b < 0 || a === b) return 0;
  return b > a ? 1 : -1;
}
