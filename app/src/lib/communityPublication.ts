import { invoke } from "@tauri-apps/api/core";
import { t } from "../i18n/t";

export type License = { id?: string; url?: string; text?: string };
export type SourceFile = {
  id: string;
  path: string;
  sizeBytes: number;
  assetId?: string;
  blobId?: string;
  updatedAt?: string;
  providerDigest?: { algorithm: string; value: string };
};
export type Source = {
  resolveId: string;
  expiresAt: string;
  canonicalUrl: string;
  revision: string;
  detectedLicense?: { license: License };
  files: SourceFile[];
};
export type PublisherRole = "original_author" | "reposter" | "maintainer";
export type ReviewState = "pending" | "published" | "rejected" | "withdrawn";
export type Submission = {
  id: string;
  operation?: "create" | "new_version";
  batchId?: string;
  assetId?: string;
  state: ReviewState;
  asset: {
    title: string;
    description: string;
    originalAuthor: string;
    authorUrl?: string;
    publisherRole: PublisherRole;
    license: License;
    metadata?: { series?: string; group?: string };
  };
  version: {
    label: string;
    metadata?: Record<string, unknown>;
    files: Array<{ path: string; sha256: string; sources: Array<{ canonicalUrl: string; revision: string }> }>;
  };
  updatedAt: string;
  reviews: Array<{ reason: string }>;
};

type Selection = Omit<Source, "files" | "detectedLicense"> & { file: SourceFile; account: string };
type SubmissionBody = {
  operation: "create" | "new_version";
  assetId?: string;
  previousSubmissionId?: string;
  asset: Submission["asset"] & { kind: "model"; upstreamUrl: string; metadata: { family: "rvc"; format: "voice_package"; series?: string; group?: string; language?: string } };
  version: { label: string; files: Array<{ path: string; role: "package"; resolveId: string; sourceFileId: string; sha256?: string }>; dependencies: [] };
  coverUploadId?: string;
};
export type Draft = {
  id: string;
  url: string;
  revision: string;
  title: string;
  description: string;
  originalAuthor: string;
  authorUrl: string;
  publisherRole: PublisherRole;
  license: License;
  licenseEdited?: boolean;
  label: string;
  series: string;
  group: string;
  cover: string;
  coverPath?: string;
  checksum: string;
  updatedAt?: string;
  selection?: Selection;
  previousSubmissionId?: string;
  previousFilePath?: string;
  assetId?: string;
  language?: string;
  pending?: { account: string; key: string; body: SubmissionBody };
};

export function newDraft(previous?: Submission, assetId?: string): Draft {
  const file = previous?.version.files[0];
  const source = file?.sources[0];
  return {
    id: crypto.randomUUID(),
    url: source?.canonicalUrl ?? "",
    revision: source?.revision ?? "",
    title: previous?.asset.title ?? "",
    description: previous?.asset.description ?? "",
    originalAuthor: previous?.asset.originalAuthor ?? "",
    authorUrl: previous?.asset.authorUrl ?? "",
    publisherRole: previous?.asset.publisherRole ?? "original_author",
    license: previous?.asset.license ?? {},
    licenseEdited: Boolean(previous),
    label: previous?.version.label ?? "v1",
    series: previous?.asset.metadata?.series ?? "",
    group: previous?.asset.metadata?.group ?? "",
    cover: "",
    checksum: file?.sha256 ?? "",
    previousSubmissionId: assetId ? undefined : previous?.id,
    assetId: assetId ?? (previous?.operation === "new_version" ? previous.assetId : undefined),
    previousFilePath: file?.path,
  };
}

const DRAFT_KEY = "fabric.community.voiceDrafts.v1";

export function loadDrafts(): Draft[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(DRAFT_KEY) ?? "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

export function storeDrafts(drafts: Draft[]) {
  localStorage.setItem(DRAFT_KEY, JSON.stringify(drafts));
}

export function validUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password;
  } catch {
    return false;
  }
}

export const isSha256 = (value: string) => /^[a-f0-9]{64}$/i.test(value.trim());
export const providerHash = (file: SourceFile) =>
  file.providerDigest?.algorithm.toLowerCase() === "sha256" && isSha256(file.providerDigest.value)
    ? file.providerDigest.value
    : undefined;

type PublicationRequest =
  | { action: "resolve"; url: string; revision?: string }
  | { action: "cover"; bytes: number[] }
  | { action: "submit"; key: string; body: SubmissionBody }
  | { action: "batch"; batchId: string; items: Array<{ key: string; body: SubmissionBody }> }
  | { action: "author"; id: string; cursor?: string }
  | { action: "owned"; cursor?: string }
  | { action: "mine"; state: ReviewState; page: number; limit: number; batch?: string }
  | { action: "withdraw"; id: string };

export function publication<T>(request: PublicationRequest) {
  return invoke<T>("community_publication", { request });
}

export async function prepareSubmission(draft: Draft, account: string, send = publication) {
  if (draft.pending?.account === account) return draft.pending;
  const selection = draft.selection;
  if (!selection || selection.account !== account || Date.parse(selection.expiresAt) <= Date.now()) {
    throw { code: "read_source" };
  }
  let coverUploadId: string | undefined;
  if (draft.cover) {
    const bytes = Array.from(atob(draft.cover.split(",")[1]), (character) => character.charCodeAt(0));
    coverUploadId = (await send<{ uploadId: string }>({ action: "cover", bytes })).uploadId;
  }

  const { file } = selection;
  const body: SubmissionBody = {
    operation: draft.assetId ? "new_version" : "create",
    assetId: draft.assetId,
    previousSubmissionId: draft.previousSubmissionId,
    coverUploadId,
    asset: {
      kind: "model",
      title: draft.title.trim(),
      description: draft.description.trim(),
      originalAuthor: draft.originalAuthor.trim(),
      authorUrl: draft.authorUrl.trim() || undefined,
      publisherRole: draft.publisherRole,
      upstreamUrl: selection.canonicalUrl,
      license: draft.license,
      metadata: {
        family: "rvc",
        format: "voice_package",
        series: draft.series.trim() || undefined,
        group: draft.group.trim() || undefined,
        language: draft.language?.trim() || undefined,
      },
    },
    version: {
      label: draft.label.trim(),
      files: [{ path: file.path, role: "package", resolveId: selection.resolveId, sourceFileId: file.id, sha256: draft.checksum.trim() || undefined }],
      dependencies: [],
    },
  };
  return { account, key: crypto.randomUUID(), body };
}

export function publicationError(error: unknown, action: "resolve" | "submit" | "list") {
  const code = typeof error === "object" && error !== null && "code" in error ? error.code : undefined;
  if (code === "unauthorized" || (code === "auth_required" && action !== "resolve")) return t("publication.signInRequired");
  if (action === "submit" && ["read_source", "conflict", "not_found"].includes(String(code))) return t("publication.readAgain");
  if (code === "invalid_cover") return t("publication.coverError");
  if (code === "source_changed") return t("publication.sourceChanged");
  if (code === "hash_mismatch") return t("publication.hashMismatch");
  if (code === "rate_limited") return t(action === "resolve" ? "publication.rateLimited" : "publication.retryQueued");
  if (action === "resolve" && (code === "auth_required" || code === "unsupported" || code === "not_found")) return t("publication.publicSource");
  return t("publication.requestFailed");
}
