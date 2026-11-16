import { describe, expect, it } from "vitest";
import { fillPackDetails, matchesSnapshot, newBatch, resolveBatchDraft, setBatchFile, uniqueMatches } from "./communityBatch";
import { newDraft, type Source, type SourceFile } from "./communityPublication";

const digest = "a".repeat(64);
const file = { id: "one", sizeBytes: 30, path: "first.zip",
  providerDigest: { algorithm: "sha256", value: digest } };
const other = { id: "two", sizeBytes: 30, path: "second.zip" };
const local = { name: "the-local.zip", result: { sha256: digest.toUpperCase(), sizeBytes: 30,
  metadata: { name: "My model", author: "Original author", group: "Series group", license: "CC-BY-4.0" } } };
const source: Source = {
  resolveId: "source", expiresAt: "2026-11-14T11:00:00.000Z",
  canonicalUrl: "https://github.com/example/models/releases/tag/v1", revision: "v1", files: [file, other],
};

describe("repository-backed batch publishing", () => {
  it("matches the exact digest despite a different name", () => {
    expect([...uniqueMatches([file, other], [local])]).toEqual([[file, local.result]]);
  });

  it("leaves missing hashes, equal-size files, and duplicate hashes for manual selection", () => {
    expect(uniqueMatches([other], [local]).size).toBe(0);
    expect(uniqueMatches([file, { ...other, providerDigest: file.providerDigest }], [local]).size).toBe(0);
    expect(uniqueMatches([{ ...file, sizeBytes: 31 }], [local]).size).toBe(0);
  });

  it("prefills editable metadata while retaining deliberate edits and attribution", () => {
    const draft = fillPackDetails({ ...newDraft(), title: "My title", licenseEdited: true, license: { id: "Custom" } }, local.result);
    const batch = newBatch();
    batch.shared.publisherRole = "reposter";
    const prepared = resolveBatchDraft(batch, draft);
    expect(prepared).toMatchObject({
      title: "My title", originalAuthor: "Original author", group: "Series group",
      publisherRole: "reposter", license: { id: "Custom" }, checksum: digest,
    });
  });

  it("drops the old selection if the release attachment changes without a digest", () => {
    const before: SourceFile = { ...other, assetId: "release-file", updatedAt: "2026-11-11" };
    const draft = setBatchFile(newDraft(), source, before, "fixture");
    expect(matchesSnapshot(draft, source, { ...before })).toBe(true);
    expect(matchesSnapshot(draft, source, { ...before, updatedAt: "2026-11-12" })).toBe(false);
    expect(matchesSnapshot(draft, source, { ...before, assetId: "new-file" })).toBe(false);
  });
});
