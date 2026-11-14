import { invoke } from "@tauri-apps/api/core";
import { isSha256, newDraft, providerHash, publication, validUrl, type Draft, type Source, type SourceFile } from "./communityPublication";

export type Pack = {
  name: string;
  result?: { sha256: string; sizeBytes: number; metadata: Record<string, unknown> };
  error?: string;
};
export type BatchRow = { draft: Draft; submitted?: boolean; error?: string };
export type BatchDraft = { id: string; url: string; revision: string; shared: Draft; rows: Record<string, BatchRow> };

export const newBatch = (): BatchDraft => ({ id: crypto.randomUUID(), url: "", revision: "", shared: newDraft(), rows: {} });
export const choosePacks = () => invoke<Pack[]>("publication_read_packs");
export const chooseManifest = () => invoke<Pack[] | null>("publication_read_manifest");

export function matchesSnapshot(draft: Draft, source: Source, file: SourceFile) {
  const old = draft.selection;
  return old?.canonicalUrl === source.canonicalUrl && old.revision === source.revision
    && old.file.id === file.id && old.file.path === file.path && old.file.sizeBytes === file.sizeBytes
    && old.file.assetId === file.assetId && old.file.blobId === file.blobId && old.file.updatedAt === file.updatedAt
    && old.file.providerDigest?.algorithm === file.providerDigest?.algorithm
    && old.file.providerDigest?.value === file.providerDigest?.value;
}

function retryDelay(cause: unknown) {
  if (!cause || typeof cause !== "object" || !("code" in cause) || cause.code !== "rate_limited") return 0;
  const details = "details" in cause ? cause.details : undefined;
  if (!details || typeof details !== "object" || !("retryAfter" in details)) return 0;
  const seconds = details.retryAfter;
  return typeof seconds === "number" && seconds > 0 && seconds <= 60 ? seconds * 1000 : 0;
}

export async function batchRequest<T>(request: Parameters<typeof publication>[0], onWait: () => void) {
  try {
    return await publication<T>(request);
  } catch (cause) {
    const delay = retryDelay(cause);
    if (!delay) throw cause;
    onWait();
    await new Promise<void>((resolve) => window.setTimeout(resolve, delay + 250));
    return publication<T>(request);
  }
}

export function uniqueMatches(files: SourceFile[], packs: Pack[]) {
  const sources = new Map<string, SourceFile[]>();
  for (const file of files) {
    const sha256 = providerHash(file)?.toLowerCase();
    if (!sha256) continue;
    const candidates = sources.get(sha256) ?? [];
    candidates.push(file);
    sources.set(sha256, candidates);
  }
  const matches = new Map<SourceFile, NonNullable<Pack["result"]>>();
  for (const { result } of packs) {
    if (!result || !isSha256(result.sha256)) continue;
    const matchesByHash = sources.get(result.sha256.toLowerCase());
    const file = matchesByHash?.length === 1 ? matchesByHash[0] : undefined;
    if (file && (!result.sizeBytes || result.sizeBytes === file.sizeBytes) && !matches.has(file)) matches.set(file, result);
  }
  return matches;
}

export function fillPackDetails(draft: Draft, pack: NonNullable<Pack["result"]>): Draft {
  const meta = pack.metadata;
  const text = (key: string, max = 200) => typeof meta[key] === "string" ? meta[key].trim().slice(0, max) : "";
  const link = text("author_url", 2048);
  return {
    ...draft,
    title: draft.title || text("name"),
    originalAuthor: draft.originalAuthor || text("author"),
    description: draft.description || text("description", 50_000),
    authorUrl: draft.authorUrl || (validUrl(link) ? link : ""),
    series: draft.series || text("series"),
    group: draft.group || text("group") || text("club"),
    language: draft.language || text("language", 50) || text("lang", 50),
    license: !draft.licenseEdited && text("license") ? { id: text("license") } : draft.license,
    checksum: pack.sha256.toLowerCase(),
    pending: undefined,
  };
}

export function setBatchFile(draft: Draft, source: Source, file: SourceFile, account: string): Draft {
  const { canonicalUrl, resolveId, revision, expiresAt } = source;
  return {
    ...draft,
    url: canonicalUrl,
    revision,
    selection: { canonicalUrl, resolveId, revision, expiresAt, file, account },
  };
}

export function suggestedTitle(path: string) {
  const fileName = path.split("/").pop() || "";
  return fileName.replace(/\.zip$/i, "").replace(/[_-](?:voice|package|pack)$/i, "").replace(/_/g, " ").trim().slice(0, 200);
}

export function resolveBatchDraft(batch: BatchDraft, row: Draft): Draft {
  const { shared } = batch;
  return {
    ...row,
    title: row.title || suggestedTitle(row.selection?.file.path ?? ""),
    description: row.description || shared.description,
    originalAuthor: row.originalAuthor || shared.originalAuthor,
    publisherRole: shared.publisherRole,
    authorUrl: row.authorUrl || shared.authorUrl,
    series: row.series || shared.series,
    group: row.group || shared.group,
    license: row.license.id || row.license.url || row.license.text ? row.license : shared.license,
  };
}

function batchStorage(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("fabric-community", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("drafts");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function readBatch(account: string) {
  const db = await batchStorage();
  try {
    return await new Promise<BatchDraft | undefined>((resolve, reject) => {
      const request = db.transaction("drafts").objectStore("drafts").get(account);
      request.onsuccess = () => resolve(request.result as BatchDraft | undefined);
      request.onerror = () => reject(request.error);
    });
  } finally { db.close(); }
}

export async function saveBatch(account: string, batch: BatchDraft) {
  const db = await batchStorage();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction("drafts", "readwrite");
      tx.objectStore("drafts").put(batch, account);
      tx.oncomplete = () => resolve();
      tx.onabort = () => reject(tx.error);
    });
  } finally { db.close(); }
}
