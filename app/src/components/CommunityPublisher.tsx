import { useState } from "react";
import { Field, Pane, Panes, SearchBox, SegmentControl, Select, TextArea, TextInput, useI18n as useUiI18n, useNotify } from "trm-ui";
import { useI18n } from "../i18n";
import {
  isSha256,
  prepareSubmission,
  providerHash,
  publication,
  publicationError,
  validUrl,
  type Draft,
  type PublisherRole,
  type Source,
  type SourceFile,
  type Submission,
} from "../lib/communityPublication";
import { CatalogTransition } from "./CatalogTransition";
import { CommunityCover } from "./CommunityCover";
import { Pager } from "./Pager";
import { Btn, PageHead, PagePad, Warn } from "./ui";
import type { CommunityAccount } from "./CommunityActions";

const steps = ["source", "details", "preview"] as const;
type Step = (typeof steps)[number];
const filesPerPage = 7;

function TextField({ label, value, onChange, limit, disabled, multiline = false }: {
  label: string; value: string; onChange: (value: string) => void;
  limit?: number; disabled?: boolean; multiline?: boolean;
}) {
  const props = {
    "aria-label": label,
    value,
    maxLength: limit,
    disabled,
    onChange,
  };
  return <Field label={label} control={multiline ? <TextArea {...props} rows={4} /> : <TextInput {...props} />} />;
}

export function CommunityPublisher({ initial, auth, onBack, onSave, onSubmitted, onMySubmissions, onBatch }: {
  initial: Draft;
  auth: CommunityAccount;
  onBack: (draft: Draft) => void;
  onSave: (draft: Draft) => boolean;
  onSubmitted: (draft: Draft, submission: Submission) => void;
  onMySubmissions: (draft: Draft) => void;
  onBatch: (draft: Draft) => void;
}) {
  const { t, locale } = useI18n();
  const { t: uiText } = useUiI18n();
  const { tip } = useNotify();
  const [step, setStep] = useState<Step>("source");
  const [draft, setDraft] = useState(initial);
  const [source, setSource] = useState<Source>();
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState<"resolve" | "submit">();
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(Boolean(initial.updatedAt));
  const signedIn = auth.account?.signedIn === true;
  const account = auth.account?.email || "";
  const pack = draft.selection?.file;
  const digest = pack ? providerHash(pack) : undefined;
  const sourceComplete = Boolean(pack && (digest || isSha256(draft.checksum)));
  const license = draft.license;
  const hasDetails = Boolean(draft.title.trim() && draft.description.trim() && draft.originalAuthor.trim() &&
    draft.label.trim() && (license.id?.trim() || license.url?.trim() || license.text?.trim()) &&
    (!license.url || validUrl(license.url)) && (!draft.authorUrl || validUrl(draft.authorUrl)));
  const matching = source?.files.filter((file) => file.path.toLowerCase().endsWith(".zip") && file.path.toLowerCase().includes(query.trim().toLowerCase())) ?? [];
  const total = Math.max(1, Math.ceil(matching.length / filesPerPage));
  const currentPage = Math.min(total, page);

  function update(changes: Partial<Draft>) {
    setDraft((previous) => ({ ...previous, ...changes, pending: undefined }));
    setSaved(false);
    setError("");
  }

  function updateSource(changes: Partial<Draft>) {
    setSource(undefined);
    setPage(1);
    setQuery("");
    update({ selection: undefined, checksum: "", previousFilePath: undefined, ...changes });
  }

  function select(source: Source, file: SourceFile) {
    const { canonicalUrl, resolveId, revision, expiresAt } = source;
    const previous = draft.selection;
    const sameFile = previous
      ? previous.canonicalUrl === canonicalUrl && previous.revision === revision && previous.file.path === file.path
      : draft.previousFilePath === file.path && draft.url === canonicalUrl && draft.revision === revision;
    update({
      selection: { canonicalUrl, resolveId, revision, expiresAt, file, account },
      checksum: !providerHash(file) && sameFile ? draft.checksum : "",
      previousFilePath: undefined,
    });
  }

  async function readSource() {
    setBusy("resolve");
    setError("");
    try {
      const next = await publication<Source>({ action: "resolve", url: draft.url.trim(), revision: draft.revision.trim() || undefined });
      setSource(next);
      setPage(1);
      setQuery("");
      const files = next.files.filter((file) => file.path.toLowerCase().endsWith(".zip"));
      const selectedPath = draft.selection?.file.path ?? draft.previousFilePath;
      const matchingFile = files.find((file) => file.path === selectedPath) ?? (files.length === 1 ? files[0] : undefined);
      if (matchingFile) select(next, matchingFile);
      else if (draft.selection) update({ selection: undefined, checksum: "" });
      if (!draft.licenseEdited) update({ license: next.detectedLicense?.license ?? {} });
    } catch (error) {
      setError(publicationError(error, "resolve"));
    } finally {
      setBusy(undefined);
    }
  }

  async function submit() {
    if (busy) return;
    setBusy("submit");
    setError("");
    try {
      const pending = await prepareSubmission(draft, account);
      const snapshot = { ...draft, pending };
      if (!onSave(snapshot)) return;
      setDraft(snapshot);
      setSaved(true);
      const result = await publication<Submission>({ action: "submit", key: pending.key, body: pending.body });
      onSubmitted(snapshot, result);
      tip(t("publication.sent"));
    } catch (error) {
      setError(publicationError(error, "submit"));
    } finally {
      setBusy(undefined);
    }
  }

  const labels = {
    source: t("publication.source"),
    details: t("publication.details"),
    preview: t("publication.preview"),
  };
  const signIn = (
    <Btn busy={auth.action === "sign_in"} disabled={auth.loading} onClick={() => void auth.run("sign_in")}>
      {t("community.signIn")}
    </Btn>
  );
  const sourceReady = validUrl(draft.url) && signedIn;

  return (
    <PagePad width="wide">
      <PageHead title={t("publication.title")} actions={
        <>
          <Btn disabled={Boolean(busy)} onClick={() => onBack(draft)}>{uiText("ui.common.back")}</Btn>
          {draft.assetId === undefined && !draft.previousSubmissionId && <Btn disabled={Boolean(busy)} onClick={() => onBatch(draft)}>{t("publication.batch")}</Btn>}
          <Btn disabled={Boolean(busy)} onClick={() => onMySubmissions(draft)}>{t("community.submissions")}</Btn>
          <Btn disabled={Boolean(busy)} onClick={() => {
            if (onSave(draft)) {
              setSaved(true);
              tip(t("publication.saved"));
            }
          }}>{t("publication.save")}</Btn>
        </>
      } />
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <SegmentControl value={step} onChange={(next) => { setStep(next); setError(""); }}
          options={steps.map((id) => ({
            id, label: labels[id],
            disabled: Boolean(busy) || (id === "details" && !sourceComplete) || (id === "preview" && (!sourceComplete || !hasDetails)),
          }))}
        />
        {saved && <span role="status" className="text-xs text-[var(--meta)]">{t("publication.saved")}</span>}
      </div>
      {error && <Warn className="mb-4">{error}</Warn>}
      <Panes value={step} order={steps} transition="slide" keepScroll>
        <Pane id="source">
          <div className="space-y-4 pb-4">
            <p className="text-[13px] text-[var(--help)]">{t("publication.sourceHint")}</p>
            <div className="grid gap-4 md:grid-cols-[2fr_1fr]">
              <TextField label={t("publication.sourceLink")} value={draft.url} limit={2048} disabled={Boolean(busy)} onChange={(url) => updateSource({ url })} />
              <TextField label={t("publication.revision")} value={draft.revision} limit={500} disabled={Boolean(busy)} onChange={(revision) => updateSource({ revision })} />
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Btn disabled={!sourceReady || Boolean(busy)} busy={busy === "resolve"} onClick={() => void readSource()}>{t("publication.readSource")}</Btn>
              {!signedIn && signIn}
              {!signedIn && <span className="text-[13px] text-[var(--help)]">{t("publication.signInRequired")}</span>}
            </div>
            {source && (
              <section className="space-y-2">
                <SearchBox full ariaLabel={uiText("ui.common.search")} value={query}
                  onChange={(value) => { setQuery(value); setPage(1); }} />
                <CatalogTransition scope={query} page={currentPage}>
                  <div className="grid gap-1">
                    {matching.slice((currentPage - 1) * filesPerPage, currentPage * filesPerPage).map((file) => (
                      <label key={file.id} className="flex min-w-0 items-center gap-3 rounded-[var(--rs)] px-3 py-2 text-[13px] hover:bg-[var(--stage)]">
                        <input type="radio" name="voice-package" checked={pack?.id === file.id} onChange={() => select(source, file)} disabled={Boolean(busy)} />
                        <span className="min-w-0 break-all">{file.path}</span>
                        <span className="ml-auto shrink-0 text-[var(--meta)]">{Intl.NumberFormat(locale, { style: "unit", unit: "megabyte", maximumFractionDigits: 1 }).format(file.sizeBytes / 1_000_000)}</span>
                      </label>
                    ))}
                    {!matching.length && <p className="text-[13px] text-[var(--help)]">{t("publication.noFiles")}</p>}
                  </div>
                </CatalogTransition>
                {total > 1 && <Pager page={currentPage} pages={total} onChange={setPage} />}
              </section>
            )}
            {pack && !source && <p className="break-all text-[13px] text-[var(--ink-muted)]">{pack.path}</p>}
            <div className="max-w-lg">
              {pack && !digest && (
                <TextField label="SHA-256" value={draft.checksum} limit={64} disabled={Boolean(busy)} onChange={(checksum) => update({ checksum })} />
              )}
            </div>
            <div className="flex justify-end">
              <Btn primary disabled={!sourceComplete || Boolean(busy)} onClick={() => setStep("details")}>{t("publication.next")}</Btn>
            </div>
          </div>
        </Pane>
        <Pane id="details">
          <div className="grid items-start gap-6 pb-4 md:grid-cols-[2fr_1fr]">
            <div className="space-y-4">
              <TextField label={t("publication.name")} value={draft.title} limit={200} onChange={(title) => update({ title })} />
              <TextField label={t("publication.description")} value={draft.description} limit={20000} multiline onChange={(description) => update({ description })} />
              <div className="grid gap-4 sm:grid-cols-2">
                <TextField label={t("publication.author")} value={draft.originalAuthor} limit={200} onChange={(originalAuthor) => update({ originalAuthor })} />
                <TextField label={t("publication.authorLink")} value={draft.authorUrl} limit={2048} onChange={(authorUrl) => update({ authorUrl })} />
                <Field label={t("publication.publisherRole")} control={
                  <Select full ariaLabel={t("publication.publisherRole")} value={draft.publisherRole}
                    options={[
                      { id: "original_author", label: t("publication.author") },
                      { id: "maintainer", label: t("publication.maintainer") },
                      { id: "reposter", label: t("publication.reposter") },
                    ]} onChange={(role) => update({ publisherRole: role as PublisherRole })} />
                } />
                <TextField label={t("publication.version")} value={draft.label} limit={100} onChange={(label) => update({ label })} />
                <TextField label={t("publication.series")} value={draft.series} limit={100} onChange={(series) => update({ series })} />
                <TextField label={t("publication.department")} value={draft.group} limit={100} onChange={(group) => update({ group })} />
                <TextField label={t("community.license")} value={license.id ?? ""} limit={200} onChange={(id) => update({ license: { ...license, id }, licenseEdited: true })} />
                <TextField label={t("publication.licenseLink")} value={license.url ?? ""} limit={2048} onChange={(url) => update({ license: { ...license, url }, licenseEdited: true })} />
              </div>
              <TextField label={t("publication.licenseTerms")} value={license.text ?? ""} limit={10000} multiline onChange={(text) => update({ license: { ...license, text }, licenseEdited: true })} />
            </div>
            <CommunityCover name={draft.title} value={draft.cover} original={draft.coverPath}
              disabled={Boolean(busy)} onChange={(cover, coverPath) => update({ cover, coverPath })} />
          </div>
          <div className="flex justify-end gap-2 pb-4">
            <Btn onClick={() => setStep("source")}>{uiText("ui.common.back")}</Btn>
            <Btn primary disabled={!hasDetails} onClick={() => setStep("preview")}>{t("publication.next")}</Btn>
          </div>
        </Pane>
        <Pane id="preview">
          <div className="grid gap-6 md:grid-cols-[1fr_2fr]">
            {draft.cover && <img src={draft.cover} draggable={false} alt={t("publication.cover")} className="w-full max-w-[320px] rounded-[var(--rs)]" />}
            <div className="min-w-0 space-y-3">
              <h2 className="m-0 text-xl font-semibold">{draft.title}</h2>
              <p className="m-0 text-[13px] text-[var(--help)]">{draft.originalAuthor}　{draft.label}</p>
              {draft.authorUrl && <p className="break-all text-[13px] text-[var(--help)]">{draft.authorUrl}</p>}
              <p className="whitespace-pre-wrap break-words text-[13px]">{draft.description}</p>
              <p className="break-all text-[13px] text-[var(--ink-muted)]">{pack?.path}</p>
              {(license.id || license.url || license.text) &&
                <p className="whitespace-pre-wrap break-words text-[13px] text-[var(--help)]">{[license.id, license.url, license.text].filter(Boolean).join("\n")}</p>}
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2 pt-5 pb-4">
            <Btn disabled={Boolean(busy)} onClick={() => setStep("details")}>{uiText("ui.common.back")}</Btn>
            {!signedIn ? signIn : <Btn primary busy={busy === "submit"} disabled={!sourceComplete || !hasDetails || Boolean(busy)} onClick={() => void submit()}>{t("publication.submit")}</Btn>}
          </div>
        </Pane>
      </Panes>
    </PagePad>
  );
}
