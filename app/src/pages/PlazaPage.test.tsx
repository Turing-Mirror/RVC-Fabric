// @vitest-environment happy-dom
import { act } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { NoticeProvider } from "trm-ui";
import { I18nProvider } from "../i18n";
import { ensurePack } from "../i18n/dict";
import { editListingDraft, newDraft, newVersionDraft, prepareSubmission, PUBLICATION_PAGE_SIZE, type CatalogModel, type CommunityAsset, type PublishedVersion } from "../lib/communityPublication";
import type { StagedVoice, StoreVoice } from "../lib/voices";
import { registerDialogHandler } from "trm-ui/fabric";
import { mount, tick, type Mounted } from "../test/dom";
import { PlazaPage } from "./PlazaPage";

const invoke = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));
vi.mock("../components/ExtrasDialog", () => ({ ExtrasPanel: () => null }));

const feed = { items: [], banner: null, changelog: [], errors: [], app_version: "", newest: "", unread: false };
const guest = { signedIn: false, authorId: null, displayName: null, email: null, offline: false };
const publisher = { signedIn: true, authorId: "publisher", displayName: "Test publisher", email: "publisher@example.test", offline: false };
const sourceUrl = "https://modelscope.cn/models/example/voices";
const accountUrl = "https://account.example.test/";
const source = {
  canonicalUrl: sourceUrl,
  revision: "fixed-revision",
  resolveId: "resolved-source",
  expiresAt: new Date(Date.now() + 60_000).toISOString(),
  files: [
    { id: "notes", path: "README.md", sizeBytes: 16 },
    { id: "voice", path: "voice.zip", sizeBytes: 128, providerDigest: { algorithm: "sha256", value: "a".repeat(64) } },
  ],
  detectedLicense: { license: { id: "CC-BY-4.0" } },
};

const listing: StoreVoice = {
  id: "approved-voice",
  name: "Approved voice",
  date: "20261115",
  official: false,
  community_file_id: "file",
  community_package_path: "voice.zip",
  community_version_id: "version",
  community_staging_id: "approved-voice-version",
  license: { id: "CC-BY-4.0" },
};

const thirdPartyListing: StoreVoice = {
  id: "tp-external",
  name: "Third-party voice",
  date: "20261015",
  official: false,
  pack_url: "https://example.test/voice.zip",
  source_url: "https://example.test/voices",
};

let mounted: Mounted | undefined;
let staged: Record<string, StagedVoice>;
let installed: boolean;
let updateAvailable: boolean;
let thirdPartyInstalled: boolean;
let submissionAttempts: number;

beforeEach(async () => {
  Object.assign(window, { __TAURI_INTERNALS__: {} });
  const matchMedia = window.matchMedia.bind(window);
  vi.spyOn(window, "matchMedia").mockImplementation((query) => {
    const result = matchMedia(query);
    if (query === "(prefers-reduced-motion: reduce)") Object.defineProperty(result, "matches", { value: true });
    return result;
  });
  await ensurePack("en-US");
  staged = {};
  installed = false;
  updateAvailable = false;
  thirdPartyInstalled = false;
  submissionAttempts = 0;
  invoke.mockReset().mockImplementation(async (command: string, args?: { request?: { action: string }; entry?: StoreVoice }) => {
    switch (command) {
      case "config_get": return { ui_locale: "en-US", ui_locale_picked: true };
      case "community_links": return { enabled: true, accountUrl: "https://account.example.test/" };
      case "community_account_status":
      case "community_account_sign_out": return guest;
      case "community_account_sign_in": return publisher;
      case "community_publication": {
        switch (args?.request?.action) {
          case "resolve": return source;
          case "cover": return { uploadId: "cropped-cover" };
          case "submit": {
            submissionAttempts++;
            if (submissionAttempts === 1) throw { code: "unavailable" };
            return { id: "submitted-voice" };
          }
          case "mine": return { items: [], page: 1, totalPages: 1 };
        }
        break;
      }
      case "store_catalog": return { thirdparty_voices: [
        { ...listing, installed, update_available: updateAvailable },
        { ...thirdPartyListing, installed: thirdPartyInstalled },
      ] };
      case "store_staged": return staged;
      case "store_install": {
        const entry = args!.entry!;
        staged = { [entry.community_staging_id || entry.id]: { dir: "staged", file: "voice.zip", size_bytes: 128 } };
        return { ok: true };
      }
      case "store_install_staged": {
        staged = {};
        if (args?.entry?.community_version_id) {
          installed = true;
          updateAvailable = false;
        } else {
          thirdPartyInstalled = true;
        }
        return { ok: true };
      }
    }
    return {};
  });
  registerDialogHandler((request) => {
    if (request.kind === "confirm") request.resolve(true);
  });
});

afterEach(() => {
  mounted?.unmount();
  mounted = undefined;
  vi.restoreAllMocks();
  registerDialogHandler(null);
  localStorage.removeItem("fabric.community.voiceDrafts.v1");
  Reflect.deleteProperty(window, "__TAURI_INTERNALS__");
});

async function openCommunity() {
  mounted = mount(<I18nProvider><NoticeProvider><PlazaPage feed={feed} /></NoticeProvider></I18nProvider>);
  await tick();
  return mounted.container;
}

function button(label: string, scope: ParentNode) {
  const result = [...scope.querySelectorAll("button")].find((node) => node.textContent?.trim() === label);
  if (!result) throw new Error("Missing button " + label);
  return result;
}

async function click(label: string, scope: ParentNode) {
  await act(async () => button(label, scope).click());
}

async function fill(scope: HTMLElement, label: string, value: string) {
  const field = scope.querySelector<HTMLInputElement | HTMLTextAreaElement>(`[aria-label="${label}"]`)!;
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(field), "value")!.set!;
  await act(async () => {
    setter.call(field, value);
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function pane(host: ParentNode, id: string) {
  return host.querySelector<HTMLElement>(`[data-trm-pane="${id}"]`)!;
}

it("shows the account menu after sign-in and lets the publisher sign out", async () => {
  const host = await openCommunity();
  const toolbar = button("Refresh", host).parentElement!;
  const labels = () => [...toolbar.querySelectorAll("button")].map((node) => node.textContent?.trim());
  expect(labels()).toEqual(["Publish", "Sign in", "Refresh"]);
  await click("Sign in", toolbar);
  expect(invoke).toHaveBeenCalledWith("community_account_sign_in");
  expect(labels()).toEqual(["Publish", "Test publisher", "Refresh"]);
  await click("Test publisher", toolbar);
  expect(button("My submissions", document.body)).toBeDefined();
  expect(button("Manage account", document.body)).toBeDefined();
  await click("Sign out", document.body);
  expect(invoke).toHaveBeenCalledWith("community_account_sign_out");
  expect(labels()).toEqual(["Publish", "Sign in", "Refresh"]);
});

it.each([
  { action: "Download", installedBefore: false },
  { action: "Update", installedBefore: true },
])("lets guests use $action on a reviewed Community voice without a direct ZIP URL", async ({ action, installedBefore }) => {
  installed = installedBefore;
  updateAvailable = installedBefore;
  const entry = { ...listing, installed, update_available: updateAvailable };
  const host = await openCommunity();
  const catalogButtons = [...pane(host, "catalog").querySelectorAll("button")].map(node => node.textContent?.trim());
  expect(catalogButtons).not.toContain("TRM source");
  expect(catalogButtons).toContain("Community");
  expect(catalogButtons).toContain("Third-party");
  expect(catalogButtons).toContain("By time");
  expect(catalogButtons).toContain("By series");
  await click("Community", pane(host, "catalog"));
  const card = host.querySelector<HTMLElement>("#store-voice-approved-voice")!;
  expect(card.textContent).not.toContain("Community");
  expect(host.querySelector("#store-voice-tp-external")).toBeNull();
  expect(card.textContent).toContain("2026-11-15");
  expect(card.textContent).toContain("CC-BY-4.0");
  expect(host.textContent).not.toContain("unreviewed third-party voices");
  await click(action, card);
  expect(invoke).toHaveBeenCalledWith("store_install", { entry });
  expect(button("Confirm install", card)).toBeDefined();
  await click("View", card);
  expect(invoke).toHaveBeenCalledWith("store_reveal_staged", { voiceId: listing.community_staging_id });
  await click("Confirm install", card);
  expect(invoke).toHaveBeenCalledWith("store_install_staged", { entry });
  expect(button("Installed", card).disabled).toBe(true);
  expect(invoke.mock.calls.some(([command]) => command === "community_account_sign_in")).toBe(false);
});

it("browses, downloads and installs third-party voices without losing the source filter on refresh", async () => {
  const host = await openCommunity();
  const catalog = pane(host, "catalog");
  expect(catalog.querySelector("#store-voice-approved-voice")).not.toBeNull();
  expect(catalog.querySelector("#store-voice-tp-external")).not.toBeNull();
  await click("Third-party", catalog);
  expect(catalog.querySelector("#store-voice-approved-voice")).toBeNull();
  expect(catalog.textContent).toContain("unreviewed third-party voices");
  const card = catalog.querySelector<HTMLElement>("#store-voice-tp-external")!;
  const entry = { ...thirdPartyListing, installed: false };
  await click("Download", card);
  expect(invoke).toHaveBeenCalledWith("store_install", { entry });
  expect(button("Confirm install", card)).toBeDefined();
  await click("View", card);
  expect(invoke).toHaveBeenCalledWith("store_reveal_staged", { voiceId: thirdPartyListing.id });
  await click("Confirm install", card);
  expect(invoke).toHaveBeenCalledWith("store_install_staged", { entry });
  expect(button("Installed", card).disabled).toBe(true);
  await click("Refresh", catalog);
  expect(catalog.querySelector("#store-voice-approved-voice")).toBeNull();
  expect(button("Installed", catalog.querySelector("#store-voice-tp-external")!).disabled).toBe(true);
  await click("All", catalog);
  expect(catalog.querySelector("#store-voice-approved-voice")).not.toBeNull();
});

it("saves, previews and retries an RVC voice submission with the publisher's edited license", async () => {
  const host = await openCommunity();
  await click("Publish", pane(host, "catalog"));
  const editor = pane(host, "publish");
  expect(editor.textContent).toContain("Choose an RVC voice ZIP from a public repository.");
  expect(editor.querySelector('select[aria-label="Base model"]')).toBeNull();

  await fill(editor, "Source link", sourceUrl);
  expect(button("Read source", editor).disabled).toBe(true);
  await click("Sign in", editor);
  await click("Read source", editor);
  expect(editor.textContent).toContain("voice.zip");
  expect(editor.textContent).not.toContain("README.md");
  await click("Next", pane(editor, "source"));

  const details = pane(editor, "details");
  expect(details.querySelector<HTMLInputElement>('[aria-label="License"]')!.value).toBe("CC-BY-4.0");
  await fill(details, "Voice name", "Example voice");
  await fill(details, "Description", "A voice for testing.");
  await fill(details, "Original author", "Test author");
  expect(details.querySelector('input[aria-label="Author page link"]')).toBeNull();
  await fill(details, "License", "Custom license");
  await click("Save draft", editor);
  expect(localStorage.getItem("fabric.community.voiceDrafts.v1")).toContain("Custom license");
  await click("Next", details);

  const preview = pane(editor, "preview");
  expect(preview.textContent).toContain("Custom license");
  await click("Submit for review", preview);
  expect(editor.textContent).toContain("Could not complete the request. Try again.");
  await click("Submit for review", preview);
  const requests = invoke.mock.calls
    .filter(([command, args]) => command === "community_publication" && args.request.action === "submit")
    .map(([, { request }]) => request);
  expect(requests).toHaveLength(2);
  expect(requests[1]).toEqual(requests[0]);
  expect(requests[0].body.asset).toMatchObject({
    title: "Example voice",
    license: { id: "Custom license" },
  });
  expect(requests[0].body.asset).not.toHaveProperty("authorUrl");
  expect(requests[0].body.asset.metadata).toMatchObject({ family: "rvc", format: "voice_package" });
  expect(requests[0].body.version.files[0]).toMatchObject({ path: "voice.zip", role: "package", sourceFileId: "voice" });
  expect(invoke).toHaveBeenCalledWith("community_publication", { request: { action: "mine", state: "pending", page: 1, limit: PUBLICATION_PAGE_SIZE } });
  expect(localStorage.getItem("fabric.community.voiceDrafts.v1")).toBe("[]");
});

it("uploads the cropped cover separately from its local original", async () => {
  const pending = await prepareSubmission({
    ...newDraft(),
    cover: "data:image/jpeg;base64,/9j/",
    coverPath: "C:\\sample\\original.png",
    selection: {
      account: publisher.email,
      canonicalUrl: sourceUrl,
      revision: source.revision,
      resolveId: source.resolveId,
      expiresAt: source.expiresAt,
      file: source.files[1],
    },
  }, publisher.email);
  expect(invoke).toHaveBeenCalledWith("community_publication", { request: { action: "cover", bytes: [255, 216, 255] } });
  expect(pending.body.coverUploadId).toBe("cropped-cover");
  expect(JSON.stringify(pending.body)).not.toContain("original.png");
});

it("keeps one published read across status switches and preserves results during refresh", async () => {
  function pendingRead() {
    let resolve!: (page: { items: CatalogModel[] }) => void;
    const promise = new Promise<{ items: CatalogModel[] }>((finish) => { resolve = finish; });
    return { promise, resolve };
  }
  const first = pendingRead();
  const refreshed = pendingRead();
  const asset: CatalogModel = {
    id: "published-voice", title: "Published voice", description: "", originalAuthor: "Test publisher",
    publisherRole: "original_author", license: { id: "CC-BY-4.0" },
    compatibleVersion: {
      id: "version-one", label: "v1", createdAt: "2026-11-15T10:00:00Z",
      package: { id: "package", path: "voice.zip", sha256: "a".repeat(64), sizeBytes: 32 },
    },
  };
  let ownedReads = 0;
  invoke.mockImplementation(async (command: string, input?: { request?: { action: string } }) => {
    if (command === "community_links") return { enabled: true, accountUrl };
    if (command === "community_account_status") return publisher;
    if (input?.request?.action === "owned") return ++ownedReads === 1 ? first.promise : refreshed.promise;
    return {};
  });

  const host = await openCommunity();
  await act(async () => button("Test publisher", host).click());
  await act(async () => button("My submissions", document.querySelector<HTMLElement>('[role="menu"]:not([inert])')!).click());
  const list = host.querySelector<HTMLElement>('[data-trm-pane="submissions"]')!;

  await act(async () => button("Published", list).click());
  expect(ownedReads).toBe(1);
  await act(async () => button("Drafts", list).click());
  await act(async () => first.resolve({ items: [asset] }));
  await act(async () => button("Published", list).click());
  expect(ownedReads).toBe(1);
  expect(list.querySelector("article")?.textContent).toContain("Published voice");

  await act(async () => button("Refresh", list).click());
  expect(ownedReads).toBe(2);
  expect(list.querySelector("article")?.textContent).toContain("Published voice");
  expect(button("Refresh", list).disabled).toBe(true);
  await act(async () => refreshed.resolve({ items: [{ ...asset, title: "Updated voice" }] }));
  expect(ownedReads).toBe(2);
  expect(list.querySelector("article")?.textContent).toContain("Updated voice");
});

it("can jump straight to the last owned page and return from the public author page", async () => {
  const coverUrl = "https://example.test/cover.webp";
  const model: CatalogModel = {
    id: "model-a", title: "First model", description: "First result", coverUrl, originalAuthor: publisher.displayName,
    publisherRole: "original_author", license: { id: "CC-BY-4.0" },
    compatibleVersion: {
      id: "version-one", label: "v1", createdAt: "2026-11-15T10:00:00Z",
      package: { id: "package", path: "voice.zip", sha256: "a".repeat(64), sizeBytes: 32 },
    },
  };
  let finishPage!: (result: { items: CatalogModel[]; page: number; totalPages: number }) => void;
  const last = new Promise<{ items: CatalogModel[]; page: number; totalPages: number }>(resolve => { finishPage = resolve; });
  const requested: number[] = [];
  invoke.mockImplementation(async (command: string, input?: {
    request?: { action: string; id?: string; page?: number };
    update?: { url: string; label: string };
  }) => {
    if (command === "community_account_author_profile") {
      return input?.update
        ? { configured: true, url: "https://github.com/example", label: "GitHub" }
        : { configured: false, url: null, label: null };
    }
    if (command === "community_links") return { enabled: true, accountUrl };
    if (command === "community_account_status") return publisher;
    if (input?.request?.action === "owned") {
      const page = input.request.page!;
      requested.push(page);
      return page === 18 ? last : { items: [model], page, totalPages: 18 };
    }
    if (input?.request?.action === "author") {
      expect(input.request.id).toBe(publisher.authorId);
      return { items: [model], page: 1, totalPages: 18, name: "Public name",
        authorUrl: "https://space.bilibili.com/123", authorUrlLabel: "哔哩哔哩" };
    }
    return {};
  });
  const host = await openCommunity();
  await act(async () => button(publisher.displayName, host).click());
  await act(async () => button("My submissions", document.body).click());
  const submissions = host.querySelector<HTMLElement>('[data-trm-pane="submissions"]')!;
  await act(async () => button("Published", submissions).click());
  expect(submissions.querySelector("article")?.textContent).toContain("First result");
  await act(async () => button("18", submissions).click());
  expect(requested).toEqual([1, 18]);
  expect(submissions.querySelector("article")?.textContent).toContain("First result");
  await act(async () => finishPage({ items: [{ ...model, id: "model-last", title: "Last model" }], page: 18, totalPages: 18 }));
  expect(submissions.querySelector("article")?.textContent).toContain("Last model");
  expect(submissions.querySelector('[aria-current="page"]')?.textContent).toBe("18");
  await act(async () => button("Author page", submissions).click());
  const author = host.querySelector<HTMLElement>('[data-trm-pane="author"]')!;
  expect(author.hidden).toBe(false);
  expect(author.querySelector("h2")?.textContent).toContain("Public name");
  expect(author.querySelector("article")?.textContent).toContain("First model");
  await act(async () => button("哔哩哔哩", author).click());
  expect(invoke).toHaveBeenCalledWith("open_external", { url: "https://space.bilibili.com/123" });
  await act(async () => button("Edit author page", author).click());
  const profileEditor = document.body.querySelector<HTMLElement>('[role="dialog"]:not([inert])')!;
  const linkInput = profileEditor.querySelector<HTMLInputElement>('input[aria-label="Author page link"]')!;
  expect(linkInput.value).toBe("https://space.bilibili.com/123");
  await act(async () => profileEditor.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  expect(invoke).toHaveBeenCalledWith("community_account_author_profile", { update: { url: linkInput.value, label: "哔哩哔哩" } });
  expect(button("GitHub", author)).toBeDefined();
  expect(author.querySelector('button[aria-label="More"]')).toBeNull();
  await act(async () => author.querySelector<HTMLButtonElement>("h2 button")!.click());
  expect(submissions.hidden).toBe(false);
  expect(submissions.querySelector("article")?.textContent).toContain("Last model");
  expect(requested).toEqual([1, 18]);
});

it("manages an owned model in My submissions and requires its updated ZIP for a new version", async () => {
  const asset: CommunityAsset = {
    id: "rin", title: "Rin (Chinese)", description: "An RVC voice package.", originalAuthor: "Test publisher",
    authorUrl: "https://github.com/example", authorUrlLabel: "GitHub",
    publisherRole: "original_author", license: { id: "CC-BY-4.0" }, coverUrl: "https://example.test/cover.webp",
    metadata: { family: "rvc", series: "Blue Archive", group: "General Affairs Department",
      groupI18n: { "zh-CN": "总务部" }, language: "zh" },
  };
  const oldHash = "a".repeat(64);
  const path = "characters/zh/rin-voice.zip";
  const repository = "https://modelscope.cn/models/example/characters";
  const current: PublishedVersion = {
    id: "rin-public-v1", label: "v1", createdAt: "2026-11-10T10:00:00Z",
    files: [{ id: "rin-package", path: "rin-voice.zip", role: "package", sizeBytes: 24, sha256: oldHash,
      sources: [{ canonicalUrl: repository, revision: "fixed-revision-for-v1", upstreamPath: path }] }],
  };
  const { files: [pack], ...version } = current;
  invoke.mockImplementation(async (name: string, input?: { request?: { action: string } }) => {
    if (name === "community_links") return { enabled: true, accountUrl };
    if (name === "community_account_status") return publisher;
    if (input?.request?.action === "owned") return { items: [{ ...asset, compatibleVersion: { ...version, package: pack } }] };
    if (input?.request?.action === "version") return { asset, version: current };
    if (input?.request?.action === "asset") return { asset, versions: [current] };
    if (input?.request?.action === "resolve") return {
      resolveId: "fixed", canonicalUrl: repository, revision: "new-revision", expiresAt: new Date(Date.now() + 60_000).toISOString(),
      files: [
        { id: "rin-zip", path, sizeBytes: 24, providerDigest: { algorithm: "sha256", value: oldHash } },
        { id: "new-rin-zip", path: "characters/zh/rin-voice-v2.zip", sizeBytes: 26,
          providerDigest: { algorithm: "sha256", value: "b".repeat(64) } },
      ],
    };
    return {};
  });
  const host = await openCommunity();
  await act(async () => button("Test publisher", host).click());
  await act(async () => button("My submissions", document.body).click());
  const publications = host.querySelector<HTMLElement>('[data-trm-pane="submissions"]')!;
  await act(async () => button("Published", publications).click());
  expect(invoke).toHaveBeenCalledWith("community_publication", { request: { action: "owned", page: 1, limit: 16 } });

  await act(async () => button("View", publications).click());
  const detail = host.querySelector<HTMLElement>('[data-trm-pane="model"]')!;
  expect(button("Edit listing", detail)).toBeDefined();
  expect(button("New version", detail)).toBeDefined();
  await act(async () => button("Edit listing", detail).click());
  const listingEditor = host.querySelector<HTMLElement>('[data-trm-pane="publish"]')!;
  expect(listingEditor.querySelector("h2")?.textContent).toContain("Edit listing");
  expect(listingEditor.querySelector<HTMLTextAreaElement>('textarea[aria-label="Description"]')?.value).toBe(asset.description);
  expect(listingEditor.querySelector('input[aria-label="Link name"]')).toBeNull();
  expect(listingEditor.querySelector<HTMLElement>('[data-trm-pane="details"]')?.hidden).toBe(false);

  await act(async () => listingEditor.querySelector<HTMLButtonElement>('h2 button')!.click());
  await act(async () => detail.querySelector<HTMLButtonElement>('h2 button')!.click());
  expect(publications.hidden).toBe(false);
  expect(localStorage.getItem("fabric.community.voiceDrafts.v1")).toBeNull();
  await act(async () => publications.querySelector<HTMLButtonElement>('button[aria-label="More"]')!.click());
  const actions = document.querySelector<HTMLElement>('[role="menu"]:not([inert])')!;
  await act(async () => button("New version", actions).click());
  expect(invoke).toHaveBeenCalledWith("community_publication", { request: { action: "version", id: asset.id, versionId: current.id } });
  const editor = host.querySelector<HTMLElement>('[data-trm-pane="publish"]')!;
  expect(editor.textContent).toContain("Current version v1");
  expect(editor.textContent).toContain(path);
  expect(editor.textContent).toContain("fixed-revision-for-v1");
  expect(editor.querySelector<HTMLInputElement>('input[aria-label="Source link"]')?.value).toBe(repository);
  await act(async () => button("Read source", editor).click());
  const row = [...editor.querySelectorAll("label")].find((label) => label.textContent?.includes(path));
  expect(row).toBeDefined();
  const radio = row!.querySelector("input")!;
  expect(radio.checked).toBe(false);
  await act(async () => radio.click());
  expect(button("Next", editor).disabled).toBe(true);
  expect(editor.textContent).toContain("This ZIP is already used by the current version.");

  const draft = newVersionDraft(asset, current)!;
  const prepared = await prepareSubmission({
    ...draft,
    selection: {
      account: publisher.email, resolveId: "new-source", revision: "new-revision", canonicalUrl: repository,
      expiresAt: new Date(Date.now() + 60_000).toISOString(),
      file: { id: "new-rin", path: "rin-new.zip", sizeBytes: 26, providerDigest: { algorithm: "sha256", value: "b".repeat(64) } },
    },
  }, publisher.email);
  expect(prepared.body.operation).toBe("new_version");
  expect(prepared.body.assetId).toBe(asset.id);
  expect(prepared.body.asset.metadata.groupI18n).toEqual({ "zh-CN": "总务部" });
  expect(prepared.body.asset.metadata.language).toBe("zh");
  expect(prepared.body.version.label).toBe("v2");
  expect(prepared.body.version.files[0].sha256).toBeUndefined();

  const listing = editListingDraft(asset, current)!;
  const metadata = await prepareSubmission({ ...listing, description: "Updated description" }, publisher.email);
  expect(metadata.body.asset).not.toHaveProperty("authorUrl");
  const credit = await prepareSubmission({ ...listing, publisherRole: "reposter", authorUrlLabel: "Code" }, publisher.email);
  expect(credit.body.asset).toMatchObject({ authorUrl: asset.authorUrl, authorUrlLabel: "Code" });
  expect(metadata.body).toMatchObject({
    operation: "metadata", assetId: asset.id, versionId: current.id,
    asset: { description: "Updated description", upstreamUrl: repository },
  });
  expect(metadata.body.version.files).toEqual([]);
});
