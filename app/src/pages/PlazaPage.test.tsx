// @vitest-environment happy-dom
import { act } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { NoticeProvider } from "trm-ui";
import { I18nProvider } from "../i18n";
import { ensurePack } from "../i18n/dict";
import { newDraft, prepareSubmission } from "../lib/communityPublication";
import type { StagedVoice, StoreVoice } from "../lib/voices";
import { registerDialogHandler } from "trm-ui/fabric";
import { mount, tick, type Mounted } from "../test/dom";
import { PlazaPage } from "./PlazaPage";

const invoke = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));
vi.mock("../components/ExtrasDialog", () => ({ ExtrasPanel: () => null }));

const feed = { items: [], banner: null, changelog: [], errors: [], app_version: "", newest: "", unread: false };
const guest = { signedIn: false, displayName: null, email: null, offline: false };
const publisher = { signedIn: true, displayName: "Test publisher", email: "publisher@example.test", offline: false };
const sourceUrl = "https://modelscope.cn/models/example/voices";
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
  official: false,
  community_file_id: "file",
  community_package_path: "voice.zip",
  community_version_id: "version",
  community_staging_id: "approved-voice-version",
  license: { id: "CC-BY-4.0" },
};

let mounted: Mounted | undefined;
let staged: Record<string, StagedVoice>;
let installed: boolean;
let updateAvailable: boolean;
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
  submissionAttempts = 0;
  invoke.mockReset().mockImplementation(async (command: string, args?: { request?: { action: string } }) => {
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
      case "store_catalog": return { thirdparty_voices: [{ ...listing, installed, update_available: updateAvailable }] };
      case "store_staged": return staged;
      case "store_install": {
        staged = { [listing.community_staging_id!]: { dir: "staged", file: "voice.zip", size_bytes: 128 } };
        return { ok: true };
      }
      case "store_install_staged": {
        staged = {};
        installed = true;
        updateAvailable = false;
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
  const card = host.querySelector<HTMLElement>("#store-voice-approved-voice")!;
  expect(card.textContent).toContain("Community");
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
  await fill(details, "Author page (optional)", "https://example.test/author");
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
    authorUrl: "https://example.test/author",
    license: { id: "Custom license" },
  });
  expect(requests[0].body.asset.metadata).toEqual({ family: "rvc", format: "voice_package", series: undefined, group: undefined });
  expect(requests[0].body.version.files[0]).toMatchObject({ path: "voice.zip", role: "package", sourceFileId: "voice" });
  expect(invoke).toHaveBeenCalledWith("community_publication", { request: { action: "mine", state: "pending", page: 1, limit: 8 } });
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
