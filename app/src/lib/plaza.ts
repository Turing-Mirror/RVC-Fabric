import { invoke } from "@tauri-apps/api/core";

/** One feed row. Mirrors `plaza::PlazaItem`. */
export type PlazaItem = {
  id: string;
  type: string;
  title: string;
  body: string;
  image_url: string;
  url: string;
  action_label: string;
  date: string;
  priority: number;
  pinned: boolean;
  /** Plaza rows are always false — the plaza exists to carry placements. */
  dismissible: boolean;
  placements: string[];
  sponsor: string;
  is_ad: boolean;
  recommended: boolean;
};

export type ChangelogEntry = {
  version: string;
  date: string;
  title: string;
  notes: string[];
};

export type PlazaFeed = {
  items: PlazaItem[];
  banner: PlazaItem | null;
  changelog: ChangelogEntry[];
  /** Per-feed failures. One feed being down must not blank the other. */
  errors: string[];
  app_version: string;
};

const EMPTY: PlazaFeed = {
  items: [],
  banner: null,
  changelog: [],
  errors: [],
  app_version: "",
};

function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function fetchPlaza(): Promise<PlazaFeed> {
  if (!isTauri()) return { ...EMPTY, errors: ["浏览器预览无法联网拉取广场内容"] };
  return invoke<PlazaFeed>("plaza_fetch");
}

/** Only ever called for the models-page banner; plaza rows have no close. */
export async function dismissAd(id: string): Promise<void> {
  if (!isTauri()) return;
  await invoke("plaza_dismiss", { id });
}

/** Open a placement's link in the user's own browser. */
export async function openExternal(url: string): Promise<void> {
  if (!url) return;
  if (!isTauri()) {
    window.open(url, "_blank", "noopener,noreferrer");
    return;
  }
  await invoke("open_external", { url });
}

/** `260730` → `2026-07-30`. The feed stores the compact form. */
export function formatDate(yymmdd: string): string {
  if (!/^\d{6}$/.test(yymmdd)) return yymmdd;
  return `20${yymmdd.slice(0, 2)}-${yymmdd.slice(2, 4)}-${yymmdd.slice(4, 6)}`;
}
