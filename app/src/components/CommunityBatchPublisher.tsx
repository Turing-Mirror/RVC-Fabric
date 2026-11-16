import { useEffect, useRef, useState } from "react";
import { useI18n as useUiI18n, Field, Pane, Panes, SearchBox, SegmentControl, TextArea, TextInput, useNotify, usePaged } from "trm-ui";
import { useI18n } from "../i18n";
import { chooseManifest, choosePacks, newBatch, readBatch, resolveBatchDraft, saveBatch, setBatchFile,
  batchRequest, matchesSnapshot, uniqueMatches, suggestedTitle, fillPackDetails, type BatchDraft, type BatchRow, type Pack } from "../lib/communityBatch";
import { AUTHOR_URL_LABEL_LIMIT, authorLinkName, isSha256, newDraft, prepareSubmission, providerHash, publication,
  publicationError, validUrl, type Draft, type Source, type SourceFile, type Submission, type PublisherRole } from "../lib/communityPublication";
import { Btn, PageHead, PagePad, Warn } from "./ui";
import { CatalogTransition } from "./CatalogTransition";
import { CommunityCategories } from "./CommunityCategories";
import { CommunityCover } from "./CommunityCover";
import { Pager } from "./Pager";
import { Select } from "./Select";
import type { CommunityAccount } from "./CommunityActions";

const steps = ["source", "details", "preview"] as const;
const pageSize = 10;
const previewPageSize = 6;
const submitChunk = 4;
type Step = (typeof steps)[number];
type BatchResult = { items: Array<{ key: string; error?: { code: string }; submission?: Submission }> };

function canSubmit(draft: Draft, signedIn: boolean, account: string) {
  return signedIn && draft.selection?.account === account
    && !!(providerHash(draft.selection.file) || isSha256(draft.checksum))
    && !!(draft.title.trim() && draft.originalAuthor.trim() && draft.description.trim() && draft.label.trim())
    && !!(draft.license.id?.trim() || draft.license.url?.trim() || draft.license.text?.trim())
    && (draft.publisherRole === "original_author" || !draft.authorUrl || validUrl(draft.authorUrl))
    && (!draft.license.url || validUrl(draft.license.url));
}

export function CommunityBatchPublisher({ auth, sourceLink = "", onBack, onSubmitted }: {
  auth: CommunityAccount; sourceLink?: string; onBack: () => void; onSubmitted: (last: Submission) => void;
}) {
  const { t, locale } = useI18n();
  const { t: uiText } = useUiI18n();
  const { tip } = useNotify();
  const signedIn = auth.account?.signedIn === true;
  const account = auth.account?.email || "";
  const [batch, setBatch] = useState(newBatch);
  const [loadedFor, setLoadedFor] = useState<string>();
  const ready = loadedFor === account;
  const ownerRef = useRef<string | undefined>(undefined);
  const [source, setSource] = useState<Source>();
  const [step, setStep] = useState<Step>("source");
  const [active, setActive] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState<"resolve" | "packs" | "submit" | "save">();
  const [error, setError] = useState("");
  const [submitProgress, setSubmitProgress] = useState(0);
  const [waiting, setWaiting] = useState(false);
  const rows = Object.values(batch.rows);
  const preview = usePaged(Object.entries(batch.rows), previewPageSize, batch.id);
  const hasSubmission = rows.some((item) => item.submitted || item.draft.pending);
  const remaining = rows.filter((row) => !row.submitted);
  const files = source?.files.filter((file) => file.path.toLowerCase().endsWith(".zip")) ?? [];
  const query = search.trim().toLowerCase();
  const filtered = files.filter((file) => file.path.toLowerCase().includes(query));
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const current = Math.min(page, pages);
  const row = batch.rows[active];
  const allReady = ready && remaining.length > 0 && remaining.every(({ draft }) => canSubmit(resolveBatchDraft(batch, draft), signedIn, account));

  useEffect(() => {
    let mounted = true;
    const wasGuest = ownerRef.current === "";
    ownerRef.current = account;
    void readBatch(account).then((saved) => {
      if (mounted) {
        setBatch((old) => saved ?? (wasGuest && account ? old : { ...newBatch(), url: sourceLink }));
        setSource(undefined);
        setStep("source");
        setActive("");
      }
    }).catch(() => {
      if (mounted) setError(t("publication.saveFailed"));
    }).finally(() => {
      if (mounted) setLoadedFor(account);
    });
    return () => { mounted = false; };
  }, [account, sourceLink, t]);

  const update = (change: Partial<BatchDraft>) => setBatch((old) => ({ ...old, ...change }));
  const put = (id: string, row: BatchRow) => setBatch((old) => ({ ...old, rows: { ...old.rows, [id]: row } }));
  const updateRow = (id: string, changes: Partial<Draft>) => {
    const item = batch.rows[id];
    if (item) put(id, { draft: { ...item.draft, ...changes, pending: undefined }, submitted: item.submitted });
  };

  function changeSource(change: Partial<BatchDraft>) {
    setSource(undefined); setPage(1); setSearch(""); setError("");
    update(Object.keys(batch.rows).length ? { ...change, id: crypto.randomUUID(), rows: {} } : change);
  }

  async function readSource() {
    setBusy("resolve"); setError("");
    try {
      const next = await publication<Source>({ action: "resolve", url: batch.url.trim(), revision: batch.revision.trim() || undefined });
      const byId = new Map(next.files.map((file) => [file.id, file]));
      const selected: Record<string, BatchRow> = {};
      for (const [id, item] of Object.entries(batch.rows)) {
        const file = byId.get(id);
        if (item.submitted || item.draft.pending) selected[id] = item;
        else if (file && matchesSnapshot(item.draft, next, file)) {
          selected[id] = { draft: setBatchFile(item.draft, next, file, account) };
        } else if (item.draft.selection) {
          selected[id] = { draft: { ...item.draft, selection: undefined, checksum: "" }, error: t("publication.sourceChanged") };
        }
      }
      update({
        rows: selected,
        shared: {
          ...batch.shared,
          originalAuthor: batch.shared.originalAuthor || auth.account?.displayName || "",
          license: batch.shared.licenseEdited ? batch.shared.license : next.detectedLicense?.license ?? {},
        },
      });
      setSource(next); setPage(1); setSearch("");
    } catch (cause) { setError(publicationError(cause, "resolve")); }
    finally { setBusy(undefined); }
  }

  function toggle(file: SourceFile) {
    if (!source || batch.rows[file.id]?.submitted || batch.rows[file.id]?.draft.pending) return;
    if (batch.rows[file.id] && !batch.rows[file.id].draft.selection) {
      put(file.id, { draft: setBatchFile(batch.rows[file.id].draft, source, file, account) });
    } else if (batch.rows[file.id]) {
      const next = { ...batch.rows };
      delete next[file.id];
      update({ rows: next });
    } else {
      put(file.id, { draft: setBatchFile(newDraft(), source, file, account) });
    }
  }

  function selectResults() {
    if (!source) return;
    const next = { ...batch.rows };
    for (const file of filtered) {
      if (!Object.prototype.hasOwnProperty.call(next, file.id)) next[file.id] = { draft: setBatchFile(newDraft(), source, file, account) };
    }
    update({ rows: next });
  }

  async function matchPacks(manifest: boolean, manual?: string) {
    if (!source) return;
    setBusy("packs"); setError("");
    try {
      const packs: Pack[] = (await (manifest ? chooseManifest() : choosePacks())) ?? [];
      if (!packs.length) return;
      const next = { ...batch.rows };
      if (manual) {
        const item = next[manual];
        const file = item?.draft.selection?.file;
        const pack = packs.length === 1 ? packs[0].result : undefined;
        if (!file || !pack || file.sizeBytes !== pack.sizeBytes
          || (providerHash(file) && providerHash(file)?.toLowerCase() !== pack.sha256.toLowerCase())) {
          setError(t("publication.hashMismatch")); return;
        }
        put(manual, { draft: fillPackDetails(item.draft, pack) });
        return;
      }
      const matched = uniqueMatches(files, packs);
      for (const [file, pack] of matched) {
        const existing = next[file.id];
        if (existing?.submitted || existing?.draft.pending) continue;
        const draft = existing?.draft ?? setBatchFile(newDraft(), source, file, account);
        next[file.id] = { draft: fillPackDetails(draft, pack) };
      }
      update({ rows: next });
      if (!matched.size) setError(t("publication.noMatches"));
      else tip(t("publication.matchedCount", { v0: matched.size }));
    } catch { setError(t("publication.packReadError")); }
    finally { setBusy(undefined); }
  }

  async function persist(leave = false) {
    setBusy("save");
    try {
      await saveBatch(account, batch);
      if (leave) onBack();
      else tip(t("publication.saved"));
    } catch { setError(t("publication.saveFailed")); }
    finally { setBusy(undefined); }
  }

  async function submit() {
    if (!allReady || busy) return;
    setBusy("submit"); setError(""); setSubmitProgress(rows.length - remaining.length);
    const send = async <T,>(request: Parameters<typeof publication>[0]) => {
      try { return await batchRequest<T>(request, () => setWaiting(true)); }
      finally { setWaiting(false); }
    };
    let snapshot = batch;
    let last: Submission | undefined;
    try {
      const queued = Object.entries(batch.rows).filter(([, item]) => !item.submitted);
      for (let cursor = 0; cursor < queued.length; cursor += submitChunk) {
        const chunk = queued.slice(cursor, cursor + submitChunk);
        const items: Array<Awaited<ReturnType<typeof prepareSubmission>>> = [];
        const target = new Map<string, string>();
        for (const [id, item] of chunk) {
          try {
            const pending = await prepareSubmission(resolveBatchDraft(snapshot, item.draft), account, send);
            snapshot = { ...snapshot, rows: { ...snapshot.rows, [id]: { draft: { ...item.draft, pending } } } };
            items.push(pending);
            target.set(pending.key, id);
          } catch (cause) {
            if (typeof cause === "object" && cause && "code" in cause && ["rate_limited", "unauthorized"].includes(String(cause.code))) throw cause;
            snapshot = { ...snapshot, rows: { ...snapshot.rows, [id]: { draft: item.draft, error: publicationError(cause, "submit") } } };
          }
        }
        if (!items.length) continue;
        await saveBatch(account, snapshot);
        setBatch(snapshot);
        const results = await send<BatchResult>({
          action: "batch", batchId: snapshot.id, items: items.map(({ key, body }) => ({ key, body })),
        });
        for (const response of results.items) {
          const id = target.get(response.key);
          if (!id) continue;
          const old = snapshot.rows[id];
          if (response.submission) {
            last = response.submission;
            snapshot.rows[id] = { draft: { ...old.draft, pending: undefined, cover: "" }, submitted: true };
          } else {
            snapshot.rows[id] = { draft: { ...old.draft, pending: ["unavailable", "rate_limited"].includes(response.error?.code ?? "") ? old.draft.pending : undefined },
              error: publicationError(response.error, "submit") };
          }
        }
        snapshot = { ...snapshot, rows: { ...snapshot.rows } };
        await saveBatch(account, snapshot);
        setBatch(snapshot);
        setSubmitProgress(Object.values(snapshot.rows).filter((item) => item.submitted).length);
        if (results.items.some((item) => item.error?.code === "rate_limited")) {
          setError(t("publication.retryQueued"));
          break;
        }
      }
      if (last && Object.values(snapshot.rows).every((item) => item.submitted)) {
        await saveBatch(account, newBatch());
        tip(t("publication.sent"));
        onSubmitted(last);
      }
    } catch (cause) { setError(publicationError(cause, "submit")); }
    finally {
      setBatch(snapshot);
      setBusy(undefined);
      setWaiting(false);
    }
  }

  const labels = { source: t("publication.source"), details: t("publication.details"), preview: t("publication.preview") };
  const details = row && resolveBatchDraft(batch, row.draft);
  const field = (label: string, value: string, change: (value: string) => void,
    { multiline, locked, limit }: { multiline?: boolean; locked?: boolean; limit?: number } = {}) =>
    <Field label={label} control={multiline
      ? <TextArea aria-label={label} value={value} onChange={change} disabled={locked || Boolean(busy)} rows={3} />
      : <TextInput aria-label={label} value={value} onChange={change} maxLength={limit} disabled={locked || Boolean(busy)} />} />;
  const sharedField = (key: "originalAuthor" | "authorUrl" | "authorUrlLabel" | "description", label: string, multiline = false) =>
    field(label, batch.shared[key] ?? "", (value) => update({ shared: { ...batch.shared, [key]: value } }),
      { multiline, limit: key === "authorUrlLabel" ? AUTHOR_URL_LABEL_LIMIT : undefined });

  return <PagePad width="wide">
    <PageHead title={t("publication.batch")} actions={<>
      <Btn disabled={Boolean(busy)} onClick={() => void persist(true)}>{uiText("ui.common.back")}</Btn>
      <Btn disabled={!ready || Boolean(busy)} onClick={() => void persist()}>{t("publication.save")}</Btn>
    </>} />
    <SegmentControl value={step} options={steps.map((id) => ({ id, label: labels[id], disabled: id !== "source" && !rows.length }))}
      onChange={(value) => { if (!busy) setStep(value as Step); }} />
    {error && <Warn className="my-3">{error}</Warn>}
    <Panes value={step} order={steps} transition="slide" className="mt-4" keepScroll>
      <Pane id="source">
        <div className="space-y-4 py-3">
          {field(t("publication.sourceLink"), batch.url, (url) => changeSource({ url }), { locked: hasSubmission })}
          {field(t("publication.revision"), batch.revision, (revision) => changeSource({ revision }), { locked: hasSubmission })}
          <div className="flex flex-wrap gap-2">
            {signedIn
              ? <Btn disabled={!ready || !validUrl(batch.url) || Boolean(busy)} busy={busy === "resolve"} onClick={() => void readSource()}>{t("publication.readSource")}</Btn>
              : <Btn busy={auth.action === "sign_in"} onClick={() => void auth.run("sign_in")}>{t("community.signIn")}</Btn>}
            {source && <>
              <Btn disabled={Boolean(busy)} onClick={() => void matchPacks(false)}>{t("publication.matchPacks")}</Btn>
              <Btn disabled={Boolean(busy)} onClick={() => void matchPacks(true)}>{t("publication.matchManifest")}</Btn>
            </>}
          </div>
          {source && <>
            <SearchBox full ariaLabel={uiText("ui.common.search")} value={search}
              onChange={(value) => { setPage(1); setSearch(value); }} />
            {filtered.length > 1 && (
              <Btn disabled={Boolean(busy)} onClick={selectResults}>
                {t(query ? "publication.selectResults" : "publication.selectAll")}
              </Btn>
            )}
            <CatalogTransition scope={search} page={current}>
              {filtered.slice((current - 1) * pageSize, current * pageSize).map((file) => (
                <label key={file.id} className="flex min-w-0 items-center gap-3 rounded-[var(--rs)] px-3 py-2 text-[13px] hover:bg-[var(--stage)]">
                  <input type="checkbox" className="trm-check" disabled={Boolean(busy) || Boolean(batch.rows[file.id]?.submitted || batch.rows[file.id]?.draft.pending)}
                    checked={Boolean(batch.rows[file.id]?.draft.selection)} onChange={() => toggle(file)} />
                  <span className="min-w-0 flex-1 break-all">{file.path}</span>
                  <span className="shrink-0 text-[var(--meta)]">{Intl.NumberFormat(locale, { style: "unit", unit: "megabyte", maximumFractionDigits: 1 }).format(file.sizeBytes / 1_000_000)}</span>
                </label>
              ))}
            </CatalogTransition>
            {!filtered.length && <p>{t("publication.noFiles")}</p>}
            {pages > 1 && <Pager page={current} pages={pages} onChange={setPage} />}
          </>}
          <div className="flex flex-wrap items-center justify-end gap-3">
            <span className="text-[13px] text-[var(--help)]">{t("publication.selectedCount", { v0: rows.length })}</span>
            <Btn primary disabled={!rows.length || Boolean(busy)} onClick={() => { setActive(active || Object.keys(batch.rows)[0]); setStep("details"); }}>{t("publication.next")}</Btn>
          </div>
        </div>
      </Pane>
      <Pane id="details">
        <div className="grid gap-6 md:grid-cols-2 pb-4">
          <div className="space-y-4">
            <h2 className="text-base font-semibold">{t("publication.sharedDetails")}</h2>
            {sharedField("originalAuthor", t("publication.author"))}
            <Field label={t("publication.publisherRole")} control={<Select full ariaLabel={t("publication.publisherRole")}
              disabled={Boolean(busy)} value={batch.shared.publisherRole}
              options={[
                { id: "original_author", label: t("publication.author") },
                { id: "maintainer", label: t("publication.maintainer") },
                { id: "reposter", label: t("publication.reposter") },
              ]} onChange={(publisherRole) => update({ shared: { ...batch.shared, publisherRole: publisherRole as PublisherRole } })} />} />
            {batch.shared.publisherRole !== "original_author" && <>
              {sharedField("authorUrl", t("publication.originalAuthorLink"))}
              {sharedField("authorUrlLabel", t("publication.authorLinkName"))}
            </>}
            {sharedField("description", t("publication.description"), true)}
            <CommunityCategories value={batch.shared.categorySelection} series={batch.shared.series} group={batch.shared.group} disabled={Boolean(busy)}
              onChange={(categorySelection) => update({ shared: { ...batch.shared, categorySelection, series: "", group: "" } })} />
            {field(t("community.license"), batch.shared.license.id || "", (id) => update({ shared: { ...batch.shared, license: { ...batch.shared.license, id }, licenseEdited: true } }))}
            {field(t("publication.licenseLink"), batch.shared.license.url || "", (url) => update({ shared: { ...batch.shared, license: { ...batch.shared.license, url }, licenseEdited: true } }))}
            {field(t("publication.licenseTerms"), batch.shared.license.text || "", (text) => update({ shared: { ...batch.shared, license: { ...batch.shared.license, text }, licenseEdited: true } }), { multiline: true })}
          </div>
          <div className="space-y-4 min-w-0">
            <Field label={t("publication.package")} control={<Select full ariaLabel={t("publication.package")} value={active}
              options={[{ id: "", label: t("publication.selectPackage") }, ...Object.entries(batch.rows).map(([id, item]) => ({
                id, label: item.draft.title || suggestedTitle(item.draft.selection?.file.path || id),
              }))]} onChange={setActive} />} />
            {row && !row.submitted && !row.draft.pending && <>
              {field(t("publication.name"), row.draft.title || suggestedTitle(row.draft.selection?.file.path || ""), (title) => updateRow(active, { title }))}
              {field(t("publication.author"), row.draft.originalAuthor, (originalAuthor) => updateRow(active, { originalAuthor }))}
              {batch.shared.publisherRole !== "original_author" && <>
                {field(t("publication.originalAuthorLink"), row.draft.authorUrl, (authorUrl) => updateRow(active, { authorUrl }))}
                {field(t("publication.authorLinkName"), row.draft.authorUrlLabel ?? "",
                  (authorUrlLabel) => updateRow(active, { authorUrlLabel }), { limit: AUTHOR_URL_LABEL_LIMIT })}
              </>}
              {field(t("publication.description"), row.draft.description, (description) => updateRow(active, { description }), { multiline: true })}
              {details && <CommunityCategories key={row.draft.id} value={details.categorySelection} series={details.series} group={details.group} disabled={Boolean(busy)}
                onChange={(categorySelection) => updateRow(active, { categorySelection, series: "", group: "" })} />}
              {field(t("publication.language"), row.draft.language || "", (language) => updateRow(active, { language }))}
              {field(t("publication.version"), row.draft.label, (label) => updateRow(active, { label }))}
              {field(t("community.license"), row.draft.license.id || "", (id) => updateRow(active, { license: { ...row.draft.license, id }, licenseEdited: true }))}
              {field(t("publication.licenseLink"), row.draft.license.url || "", (url) => updateRow(active, { license: { ...row.draft.license, url }, licenseEdited: true }))}
              {field(t("publication.licenseTerms"), row.draft.license.text || "", (text) => updateRow(active, { license: { ...row.draft.license, text }, licenseEdited: true }), { multiline: true })}
              {row.draft.selection && <>
                {!providerHash(row.draft.selection.file) && field("SHA-256", row.draft.checksum, (checksum) => updateRow(active, { checksum }))}
                <Btn disabled={Boolean(busy) || !source} onClick={() => void matchPacks(false, active)}>{t("publication.useLocalZip")}</Btn>
              </>}
              <CommunityCover value={row.draft.cover} original={row.draft.coverPath} name={row.draft.title}
                onChange={(cover, coverPath) => updateRow(active, { cover, coverPath })} disabled={Boolean(busy)} />
            </>}
            {row?.error && <Warn>{row.error}</Warn>}
            {details && (row?.submitted || row?.draft.pending) && <p className="text-[13px]">{t(row.submitted ? "publication.sent" : "publication.retryQueued")}</p>}
          </div>
        </div>
        <div className="flex justify-end py-3">
          <Btn primary disabled={!rows.length || Boolean(busy)} onClick={() => setStep("preview")}>{t("publication.next")}</Btn>
        </div>
      </Pane>
      <Pane id="preview">
        <CatalogTransition scope={batch.id} page={preview.page}>
          <div className="space-y-2 pb-4">
            {preview.slice.map(([id, item]) => {
              const draft = resolveBatchDraft(batch, item.draft);
              return <div key={id} className="flex items-start gap-3 py-2 text-[13px]">
                {draft.cover && <img src={draft.cover} alt="" draggable={false} className="h-12 w-16 rounded-[var(--rs)] object-cover" />}
                <div className="min-w-0 flex-1 break-words">
                  <div>{draft.title || draft.selection?.file.path}</div>
                  <div className="text-[var(--help)]">{[draft.originalAuthor, draft.label, draft.license.id].filter(Boolean).join("  ")}</div>
                  {draft.publisherRole !== "original_author" && draft.authorUrl && <div className="break-words text-[var(--help)]"
                    title={draft.authorUrl}>{authorLinkName(draft.authorUrl, draft.authorUrlLabel)}</div>}
                  {item.error && <div className="text-[var(--warn)]">{item.error}</div>}
                </div>
                {item.submitted ? <span className="text-[var(--help)]">{t("publication.pending")}</span> :
                  <Btn disabled={Boolean(busy)} onClick={() => { setActive(id); setStep("details"); }}>
                    {t(canSubmit(draft, signedIn, account) ? "publication.edit" : "publication.needsDetails")}
                  </Btn>}
                {!item.submitted && !item.draft.pending && <Btn disabled={Boolean(busy)} onClick={() => {
                  const copy = { ...batch.rows };
                  delete copy[id];
                  update({ rows: copy });
                  if (active === id) setActive("");
                }}>{t("publication.removeDraft")}</Btn>}
              </div>;
            })}
          </div>
        </CatalogTransition>
        <Pager className="mb-4" page={preview.page} pages={preview.pages} onChange={preview.setPage} />
        <div className="flex flex-wrap items-center justify-end gap-3">
          {busy === "submit" && <span role="status" className="text-[13px] text-[var(--help)]">
            {waiting ? t("publication.retryQueued") : submitProgress + " / " + rows.length}
          </span>}
          <Btn primary disabled={!allReady || Boolean(busy)} busy={busy === "submit"} onClick={() => void submit()}>{t("publication.submit")}</Btn>
        </div>
      </Pane>
    </Panes>
  </PagePad>;
}
