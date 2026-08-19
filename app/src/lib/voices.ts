import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { t } from "../i18n/t";

function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export type VoiceModel = {
  name: string;
  path: string;
  file: string;
  dir: string;
  cover?: string;
  index?: string;
  has_index?: boolean;
  tag?: string;
  author?: string;
  author_url?: string;
  /** 来源仓库 / 发布页。第三方音色装完之后靠它查得到出处。 */
  source_url?: string;
  source?: string;
  missing?: boolean;
  pitch?: number;
  formant?: number;
  active_profile?: string;
  [key: string]: unknown;
};

export type VoicesCatalog = {
  models: VoiceModel[];
  selected_idx: number;
  models_dir?: string;
  recent_keys?: string[];
};

export type IndexItem = {
  path: string;
  label: string;
  badge: string;
  active: boolean;
};

export type ProfileItem = {
  id: string;
  name: string;
  source: string;
  source_label: string;
  score?: number | null;
  active: boolean;
  desc?: string;
};

export type StoreVoice = {
  id: string;
  name: string;
  /** Japanese display name when different from name */
  name_ja?: string;
  /** English / romanization */
  name_en?: string;
  /** Traditional Chinese */
  name_zh_Hant?: string;
  tag?: string;
  version?: string;
  pack_url?: string;
  pth_url?: string;
  /** Absolute https URL (preferred; filled by store.rs from cover/banner). */
  cover_url?: string;
  /** Relative path leftover from older caches, e.g. ch-banner/foo.jpg */
  cover?: string;
  size_bytes?: number;
  size_label?: string;
  sha256?: string;
  description?: string;
  author?: string;
  author_url?: string;
  date?: string;
  series?: string;
  series_ja?: string;
  series_en?: string;
  series_zh_Hant?: string;
  /** Club / department inside a series (e.g. 研讨会). */
  group?: string;
  group_i18n?: Record<string, string>;
  origin?: string;
  origin_label?: string;
  /** 本机 ch-banner 绝对路径；远程封面挂了时走 asset 协议。 */
  cover_local?: string;
  source_url?: string;
  official?: boolean;
  installed?: boolean;
};

export type StoreCatalog = {
  source?: string;
  voices?: StoreVoice[];
  thirdparty_voices?: StoreVoice[];
  fetch_error?: string;
};

export function coverSrc(path?: string): string {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  if (!isTauri()) return "";
  try {
    return convertFileSrc(path);
  } catch {
    return "";
  }
}

export async function listVoices(): Promise<VoicesCatalog> {
  if (!isTauri()) {
    return { models: [], selected_idx: -1 };
  }
  return invoke<VoicesCatalog>("voices_list");
}

export async function clearVoice() {
  if (!isTauri()) return { ok: false };
  return invoke<{ ok?: boolean }>("voices_clear");
}

export async function selectVoice(m: Pick<VoiceModel, "path" | "dir" | "name">) {
  if (!isTauri()) return { ok: false };
  return invoke<{
    ok?: boolean;
    model?: VoiceModel;
    pitch?: number;
    formant?: number;
    profile_summary?: string;
  }>("voices_select", {
    path: m.path || "",
    dir: m.dir || "",
    name: m.name || "",
  });
}

export async function currentVoice() {
  if (!isTauri()) {
    return {
      model: null,
      pitch: 0,
      formant: 0,
      // 空串，占位交给 Dock 在渲染时取。这里是模块早期就会跑到的路径，
      // 那时语言包还没加载完，t() 会把 DEFAULT_LOCALE 的字面量固化下来。
      profile_summary: "",
      index: 0,
      total: 0,
    };
  }
  return invoke<{
    model?: VoiceModel | null;
    pitch?: number;
    formant?: number;
    profile_summary?: string;
    /** 1-based position in the library, 0 when nothing is selected. */
    index?: number;
    total?: number;
    catalog?: VoicesCatalog;
  }>("voices_current");
}

export async function listIndex(modelDir: string) {
  if (!isTauri()) return { items: [] as IndexItem[] };
  return invoke<{ items: IndexItem[]; active?: string }>("voices_index_list", {
    modelDir,
  });
}

export async function applyIndex(modelDir: string, indexPath: string) {
  if (!isTauri()) return { items: [] as IndexItem[] };
  return invoke<{ items: IndexItem[] }>("voices_index_use", {
    modelDir,
    indexPath,
  });
}

export async function bindIndex(modelDir: string) {
  if (!isTauri()) return { items: [] as IndexItem[] };
  return invoke<{ items: IndexItem[] }>("voices_index_bind", {
    modelDir,
    indexSrc: null,
  });
}

export async function unbindIndex(modelDir: string, indexPath: string) {
  if (!isTauri()) return { items: [] as IndexItem[] };
  return invoke<{ items: IndexItem[] }>("voices_index_unbind", {
    modelDir,
    indexPath,
  });
}

export async function listProfiles(modelDir: string) {
  if (!isTauri()) return { items: [] as ProfileItem[] };
  return invoke<{ items: ProfileItem[]; active_id?: string }>(
    "voices_profiles_list",
    { modelDir },
  );
}

export async function applyProfile(modelDir: string, profileId: string) {
  if (!isTauri()) return {};
  return invoke<{
    pitch?: number;
    formant?: number;
    profile_summary?: string;
    profiles?: { items: ProfileItem[] };
    hot?: Record<string, number | undefined>;
  }>("voices_profile_use", { modelDir, profileId });
}

export async function saveProfile(modelDir: string, name: string) {
  if (!isTauri()) return {};
  return invoke("voices_profile_save", { modelDir, name });
}

export async function deleteProfile(modelDir: string, profileId: string) {
  if (!isTauri()) return {};
  return invoke("voices_profile_delete", { modelDir, profileId });
}

export async function importProfile(modelDir: string) {
  if (!isTauri()) return {};
  return invoke("voices_profile_import", { modelDir });
}

export async function exportProfile(modelDir: string) {
  if (!isTauri()) return {};
  return invoke("voices_profile_export", { modelDir });
}

export async function importVoices(currentModelDir?: string) {
  if (!isTauri()) return { models: [], errors: [] };
  return invoke<{
    models?: unknown[];
    indices?: unknown[];
    errors?: { path: string; error: string }[];
  }>("voices_import", {
    paths: null,
    currentModelDir: currentModelDir || null,
  });
}

export async function deleteVoice(modelDir: string) {
  if (!isTauri()) return;
  return invoke("voices_delete", { modelDir });
}

export async function renameVoice(modelDir: string, newName: string) {
  if (!isTauri()) return;
  return invoke("voices_rename", { modelDir, newName });
}

export async function promoteLegacy(pthPath: string) {
  if (!isTauri()) return;
  return invoke("voices_promote", { pthPath });
}

export async function openModelsDir() {
  if (!isTauri()) return;
  return invoke("voices_open_dir");
}

export async function fetchStoreCatalog(preferRemote = true) {
  if (!isTauri()) {
    return {
      source: "demo",
      voices: [],
      thirdparty_voices: [],
      fetch_error: t("s.d15a7a3da1"),
    } satisfies StoreCatalog;
  }
  return invoke<StoreCatalog>("store_catalog", { preferRemote });
}

export async function installStoreVoice(entry: StoreVoice) {
  if (!isTauri()) return { ok: false };
  return invoke("store_install", { entry });
}

/** 已下载但还没安装的第三方音色：{ voiceId: { dir, file, size_bytes } }。 */
export type StagedVoice = { dir: string; file: string; size_bytes: number };

export async function stagedVoices(): Promise<Record<string, StagedVoice>> {
  if (!isTauri()) return {};
  return (await invoke<Record<string, StagedVoice>>("store_staged")) || {};
}

/** 在资源管理器里打开暂存目录，用户自己看、自己删。 */
export async function revealStagedVoice(voiceId: string) {
  if (!isTauri()) return;
  return invoke("store_reveal_staged", { voiceId });
}

export async function discardStagedVoice(voiceId: string) {
  if (!isTauri()) return;
  return invoke("store_discard_staged", { voiceId });
}

/** 把已下载的第三方音色真正装进音色库。 */
export async function installStagedVoice(entry: StoreVoice) {
  if (!isTauri()) return { ok: false };
  return invoke("store_install_staged", { entry });
}

/** Cancel one voice's download, or all of them when `voiceId` is omitted. */
export async function cancelStoreDownload(voiceId?: string) {
  if (!isTauri()) return;
  return invoke("store_cancel", { voiceId: voiceId ?? "" });
}

export function filterSortModels(
  models: VoiceModel[],
  query: string,
  sort: "default" | "name" | "index",
): VoiceModel[] {
  const q = query.trim().toLowerCase();
  let out = q
    ? models.filter((m) =>
        [m.name, m.tag, m.file, m.author]
          .map((x) => String(x || "").toLowerCase())
          .some((s) => s.includes(q)),
      )
    : [...models];
  if (sort === "name") {
    out.sort((a, b) =>
      String(a.name || "").localeCompare(String(b.name || ""), "zh"),
    );
  } else if (sort === "index") {
    out.sort((a, b) => {
      const ai = a.has_index || a.index ? 0 : 1;
      const bi = b.has_index || b.index ? 0 : 1;
      if (ai !== bi) return ai - bi;
      return String(a.name || "").localeCompare(String(b.name || ""), "zh");
    });
  }
  return out;
}

export function modelKey(m: VoiceModel): string {
  if (m.path) return m.path;
  return `${m.dir || ""}|${m.name || ""}`;
}

export function colsForWidth(w: number): number {
  // card_min ≈ 180 + gap; max 5
  const usable = Math.max(w - 48, 320);
  return Math.max(1, Math.min(5, Math.floor(usable / 200)));
}
