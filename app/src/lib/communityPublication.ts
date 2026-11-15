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
export const PUBLICATION_PAGE_SIZE = 16;
export const AUTHOR_URL_LABEL_LIMIT = 80;
export type Category = { id: string; name: string; names: Record<string, string>; aliases: string[] };
export type CategoryChoice = { id: string } | { name: string; locale: string; translations?: Record<string, string> };
export type CategorySelection = { series: CategoryChoice; department?: CategoryChoice };
export const categoryTerm = (label: string) => label.normalize("NFKC").trim().replace(/\s+/g, " ").toLowerCase();

export type ModelMetadata = {
  family?: string;
  familyVersion?: string;
  format?: string;
  series?: string;
  seriesId?: string;
  group?: string;
  groupId?: string;
  language?: string;
  nameI18n?: Record<string, string>;
  seriesI18n?: Record<string, string>;
  groupI18n?: Record<string, string>;
};

export type PublishedPackage = {
  id: string;
  path: string;
  role: string;
  sizeBytes: number;
  sha256: string;
  sources: Array<{ canonicalUrl: string; revision: string; upstreamPath?: string; state?: string }>;
};
export type PublishedVersion = {
  id: string;
  label: string;
  metadata?: ModelMetadata;
  createdAt: string;
  files: PublishedPackage[];
};
export type CommunityAsset = Submission["asset"] & {
  id: string;
  ownerId?: string;
  upstreamUrl?: string;
  coverUrl?: string;
  communityAuthorId?: string;
  updatedAt?: string;
};
export type CatalogModel = CommunityAsset & {
  compatibleVersion: Omit<PublishedVersion, "files"> & {
    package: Pick<PublishedPackage, "id" | "path" | "sha256" | "sizeBytes">;
  };
};
export type ModelDetail = { asset: CommunityAsset; versions: PublishedVersion[] };
export type VersionContext = {
  modelTitle: string;
  coverUrl?: string;
  label: string;
  file: PublishedPackage;
  metadata?: ModelMetadata;
};

export type Submission = {
  id: string;
  publisherId?: string;
  batchId?: string;
  operation?: "create" | "new_version" | "metadata";
  assetId?: string;
  coverUploadId?: string | null;
  coverUrl?: string;
  categorySelection?: CategorySelection | null;
  state: ReviewState;
  asset: {
    title: string;
    description: string;
    originalAuthor: string;
    authorUrl?: string | null;
    authorUrlLabel?: string | null;
    publisherRole: PublisherRole;
    license: License;
    metadata?: ModelMetadata;
  };
  version: {
    id?: string;
    label: string;
    metadata?: { familyVersion?: string };
    files: Array<{ path: string; sha256: string; sources: Array<{ canonicalUrl: string; revision: string }> }>;
  };
  updatedAt: string;
  reviews: Array<{ reason: string; action?: "publish" | "reject" | "withdraw"; createdAt?: string }>;
};

type Selection = Omit<Source, "files" | "detectedLicense"> & { file: SourceFile; account: string };
type SubmissionBody = {
  operation: "create" | "new_version" | "metadata";
  assetId?: string;
  versionId?: string;
  previousSubmissionId?: string;
  categorySelection?: CategorySelection | null;
  asset: Submission["asset"] & { kind: "model"; upstreamUrl: string; metadata: ModelMetadata & { family: "rvc"; format: "voice_package" } };
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
  authorUrlLabel?: string;
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
  modelMetadata?: ModelMetadata;
  coverUploadId?: string;
  currentVersion?: VersionContext;
  metadataVersionId?: string;
  categorySelection?: CategorySelection | null;
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
    authorUrlLabel: previous?.asset.authorUrlLabel ?? undefined,
    publisherRole: previous?.asset.publisherRole ?? "original_author",
    license: previous?.asset.license ?? {},
    licenseEdited: Boolean(previous),
    label: previous?.version.label ?? "v1",
    series: previous?.asset.metadata?.series ?? "",
    group: previous?.asset.metadata?.group ?? "",
    language: previous?.asset.metadata?.language,
    modelMetadata: previous?.asset.metadata,
    categorySelection: previous?.categorySelection !== undefined ? previous.categorySelection
      : previous?.asset.metadata?.seriesId ? { series: { id: previous.asset.metadata.seriesId },
        department: previous.asset.metadata.groupId ? { id: previous.asset.metadata.groupId } : undefined } : undefined,
    cover: "",
    coverUploadId: previous?.coverUploadId ?? undefined,
    checksum: file?.sha256 ?? "",
    previousSubmissionId: assetId ? undefined : previous?.id,
    previousFilePath: file?.path,
    assetId: assetId ?? (previous?.operation === "new_version" || previous?.operation === "metadata" ? previous.assetId : undefined),
    metadataVersionId: previous?.operation === "metadata" ? previous.version.id : undefined,
  };
}

export function firstPackage(version: PublishedVersion) {
  return version.files.find((file) => file.role === "package");
}

export function newVersionDraft(asset: CommunityAsset, current: PublishedVersion): Draft | undefined {
  const file = firstPackage(current);
  if (!file) return undefined;
  const source = file.sources.find((item) => item.state === "available") ?? file.sources[0];
  const number = /^v([1-9][0-9]{0,5})$/.exec(current.label);
  return {
    ...newDraft({ id: "", state: "published", asset, version: current, updatedAt: "", reviews: [] }, asset.id),
    url: source?.canonicalUrl || asset.upstreamUrl || "",
    revision: "",
    checksum: "",
    previousFilePath: undefined,
    label: number ? "v" + (Number(number[1]) + 1) : "",
    currentVersion: { modelTitle: asset.title, coverUrl: asset.coverUrl, label: current.label, file, metadata: current.metadata },
  };
}

export function editListingDraft(asset: CommunityAsset, current: PublishedVersion): Draft | undefined {
  const draft = newVersionDraft(asset, current);
  return draft && { ...draft, label: current.label, metadataVersionId: current.id };
}

export function versionIssue(draft: Draft): "unchanged_package" | "unchanged_version" | undefined {
  const current = draft.currentVersion;
  if (!current || draft.metadataVersionId) return undefined;
  const file = draft.selection?.file;
  const digest = file && (providerHash(file) || draft.checksum.trim());
  if (digest && digest.toLowerCase() === current.file.sha256.toLowerCase()) return "unchanged_package";
  if (draft.label.trim().toLowerCase() === current.label.trim().toLowerCase()) return "unchanged_version";
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

export function authorLinkName(url: string, label?: string | null) {
  const name = label?.trim();
  if (name) return name;
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
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
  | { action: "author"; id: string; page?: number; cursor?: string; query?: string; limit?: number }
  | { action: "owned"; page?: number; cursor?: string; query?: string; limit?: number }
  | { action: "asset"; id: string }
  | { action: "version"; id: string; versionId: string }
  | { action: "cover_preview"; id: string }
  | { action: "categories"; parent?: string }
  | { action: "mine"; state: ReviewState; page: number; limit: number; batch?: string }
  | { action: "withdraw"; id: string };

export function publication<T>(request: PublicationRequest) {
  return invoke<T>("community_publication", { request });
}

export async function prepareSubmission(draft: Draft, account: string, send = publication) {
  const issue = versionIssue(draft);
  if (issue) throw { code: issue };
  if (draft.pending?.account === account) return draft.pending;
  const selection = draft.selection;
  const metadataOnly = Boolean(draft.metadataVersionId);
  if (!metadataOnly && (!selection || selection.account !== account || Date.parse(selection.expiresAt) <= Date.now())) {
    throw { code: "read_source" };
  }
  let coverUploadId = draft.coverUploadId;
  if (draft.cover) {
    const bytes = Array.from(atob(draft.cover.split(",")[1]), (character) => character.charCodeAt(0));
    coverUploadId = (await send<{ uploadId: string }>({ action: "cover", bytes })).uploadId;
  }

  const file = selection?.file;
  const authorUrl = draft.authorUrl.trim();
  const creditLink = draft.publisherRole !== "original_author";
  const body: SubmissionBody = {
    operation: metadataOnly ? "metadata" : draft.assetId ? "new_version" : "create",
    assetId: draft.assetId,
    versionId: draft.metadataVersionId,
    previousSubmissionId: draft.previousSubmissionId,
    categorySelection: draft.categorySelection,
    coverUploadId,
    asset: {
      kind: "model",
      title: draft.title.trim(),
      description: draft.description.trim(),
      originalAuthor: draft.originalAuthor.trim(),
      ...(creditLink ? {
        authorUrl: authorUrl || (draft.assetId ? null : undefined),
        authorUrlLabel: authorUrl && draft.authorUrlLabel !== undefined ? draft.authorUrlLabel.trim() || null : undefined,
      } : {}),
      publisherRole: draft.publisherRole,
      upstreamUrl: selection?.canonicalUrl || draft.url.trim(),
      license: draft.license,
      metadata: {
        nameI18n: draft.modelMetadata?.nameI18n,
        seriesI18n: draft.series.trim() === draft.modelMetadata?.series ? draft.modelMetadata?.seriesI18n : undefined,
        groupI18n: draft.group.trim() === draft.modelMetadata?.group ? draft.modelMetadata?.groupI18n : undefined,
        family: "rvc",
        familyVersion: draft.modelMetadata?.familyVersion,
        format: "voice_package",
        series: draft.series.trim() || undefined,
        group: draft.group.trim() || undefined,
        language: draft.language?.trim() || undefined,
      },
    },
    version: {
      label: draft.label.trim(),
      files: selection && file && !metadataOnly ? [
        { path: file.path, role: "package", resolveId: selection.resolveId, sourceFileId: file.id, sha256: draft.checksum.trim() || undefined },
      ] : [],
      dependencies: [],
    },
  };
  return { account, key: crypto.randomUUID(), body };
}

export function publicationError(error: unknown, action: "resolve" | "submit" | "list") {
  const code = typeof error === "object" && error !== null && "code" in error ? error.code : undefined;
  if (code === "unauthorized" || (code === "auth_required" && action !== "resolve")) return t("publication.signInRequired");
  if (action === "submit" && ["read_source", "conflict", "not_found"].includes(String(code))) return t("publication.readAgain");
  if (code === "source_changed") return t("publication.sourceChanged");
  if (code === "invalid_cover") return t("publication.coverError");
  if (code === "unchanged_package") return t("publication.unchangedPackage");
  if (code === "unchanged_version") return t("publication.unchangedVersion");
  if (code === "hash_mismatch") return t("publication.hashMismatch");
  if (code === "rate_limited") return t(action === "resolve" ? "publication.rateLimited" : "publication.retryQueued");
  if (action === "resolve" && (code === "auth_required" || code === "unsupported" || code === "not_found")) return t("publication.publicSource");
  return t("publication.requestFailed");
}
