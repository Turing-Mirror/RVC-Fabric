import { useCallback, useEffect, useRef, useState } from "react";
import { Modal, SegmentControl, useI18n as useUiI18n, useNotify, usePageActive, usePaneOn } from "trm-ui";
import { useI18n } from "../i18n";
import { publication, publicationError, type Draft, type ReviewState, type Submission } from "../lib/communityPublication";
import type { CommunityAccount } from "./CommunityActions";
import { CatalogTransition } from "./CatalogTransition";
import { Pager } from "./Pager";
import { Btn, Group, PageHead, PagePad, Warn } from "./ui";

const states = ["draft", "pending", "rejected", "published", "withdrawn"] as const;
type State = "draft" | ReviewState;
const PER_PAGE = 8;

export function CommunitySubmissions({ auth, drafts, recent, onBack, onNew, onBatch, onEdit, onRemove, onRevise }: {
  auth: CommunityAccount;
  drafts: Draft[];
  recent?: Submission;
  onBack: () => void;
  onNew: () => void;
  onBatch: () => void;
  onEdit: (draft: Draft) => void;
  onRemove: (id: string) => void;
  onRevise: (submission: Submission) => void;
}) {
  const { t, locale } = useI18n();
  const { t: uiText } = useUiI18n();
  const { tip } = useNotify();
  const paneActive = usePaneOn();
  const pageActive = usePageActive();
  const active = paneActive && pageActive;
  const account = auth.account?.signedIn ? auth.account.email ?? "" : null;
  const [filter, setFilter] = useState<State>("draft");
  const [page, setPage] = useState(1);
  const [batch, setBatch] = useState<string>();
  const [snapshot, setSnapshot] = useState<{ account: string; state: ReviewState; page: number; totalPages: number; items: Submission[]; batch?: string }>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirm, setConfirm] = useState<{ id: string; kind: "draft" | "withdraw" }>();
  const [applying, setApplying] = useState(false);
  const request = useRef(0);
  const seen = useRef<string | undefined>(undefined);
  const lastSubmission = useRef<string | undefined>(undefined);
  const keyFor = (owner: string, state: ReviewState, page: number, batch?: string) => JSON.stringify([owner, state, page, batch]);

  const refresh = useCallback(async (owner: string, state: ReviewState, page: number, batch?: string) => {
    const current = ++request.current;
    seen.current = keyFor(owner, state, page, batch);
    setBusy(true);
    setError("");
    try {
      const read = () => publication<{ items: Submission[]; page: number; totalPages: number }>({
        action: "mine", state, page, limit: PER_PAGE, batch,
      });
      const result = await read().catch(async (error: unknown) => {
        if (typeof error !== "object" || error === null || !("code" in error) || error.code !== "unavailable" || request.current !== current) throw error;
        await new Promise<void>((resolve) => window.setTimeout(resolve, 450));
        if (request.current !== current) throw error;
        return read();
      });
      if (request.current !== current) return;
      setSnapshot({ account: owner, state, ...result, batch });
      if (result.page !== page) {
        seen.current = keyFor(owner, state, result.page, batch);
        setPage(result.page);
      }
    } catch (error) {
      if (request.current === current) setError(publicationError(error, "list"));
    } finally {
      if (request.current === current) setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (account === null) {
      ++request.current;
      seen.current = undefined;
      setSnapshot(undefined);
      setError("");
      setBusy(false);
      return;
    }
    if (!active) return;
    if (recent && recent.id !== lastSubmission.current) {
      lastSubmission.current = recent.id;
      setBatch(recent.batchId);
      seen.current = undefined;
      if (filter !== "pending" || page !== 1 || batch !== recent.batchId) {
        setFilter("pending");
        setPage(1);
        return;
      }
    }
    if (filter !== "draft" && seen.current !== keyFor(account, filter, page, batch)) void refresh(account, filter, page, batch);
  }, [account, active, filter, page, recent, refresh, batch]);

  const remote = snapshot?.account === account && snapshot?.state === filter && snapshot?.batch === batch ? snapshot : undefined;
  const pages = filter === "draft" ? Math.max(1, Math.ceil(drafts.length / PER_PAGE)) : remote?.totalPages ?? 1;
  const current = filter === "draft" ? Math.min(pages, page) : page;
  const items = filter === "draft" ? drafts.slice((current - 1) * PER_PAGE, current * PER_PAGE)
    : remote?.page === current ? remote.items : [];
  const date = (value?: string) => value ? new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "";
  const labels: Record<State, string> = {
    draft: t("publication.drafts"),
    pending: t("publication.pending"),
    rejected: t("publication.rejected"),
    published: t("publication.published"),
    withdrawn: t("publication.withdrawn"),
  };

  async function apply() {
    if (!confirm) return;
    if (confirm.kind === "draft") {
      onRemove(confirm.id);
      setConfirm(undefined);
      return;
    }
    if (account === null) return;
    setApplying(true);
    try {
      await publication<Submission>({ action: "withdraw", id: confirm.id });
      seen.current = undefined;
      setSnapshot(undefined);
      setConfirm(undefined);
      setFilter("withdrawn");
      setPage(1);
    } catch (error) {
      tip(publicationError(error, "list"));
    } finally {
      setApplying(false);
    }
  }

  return (
    <PagePad width="wide">
      <PageHead title={t("community.submissions")} actions={
        <>
          <Btn onClick={onBack}>{uiText("ui.common.back")}</Btn>
          {account !== null && filter !== "draft" && <Btn busy={busy} onClick={() => void refresh(account, filter, page, batch)}>{t("s.38108eaa1d")}</Btn>}
          {filter === "draft" && <Btn onClick={onBatch}>{t("publication.batch")}</Btn>}
          <Btn primary onClick={onNew}>{t("community.publish")}</Btn>
        </>
      } />
      <SegmentControl className="mb-5" value={filter} options={states.map((id) => ({ id, label: labels[id] }))}
        onChange={(next) => { setFilter(next); setPage(1); }} />
      {batch && filter !== "draft" && <Btn onClick={() => { setBatch(undefined); setPage(1); }}>{uiText("ui.common.clear")}</Btn>}
      {error && account !== null && filter !== "draft" && <Warn className="mb-3">{error}</Warn>}
      <CatalogTransition scope={filter} order={states} page={current}>
        {filter !== "draft" && account === null ? (
          <div className="flex items-center gap-3">
            <p className="text-[13px] text-[var(--help)]">{t("publication.signInRequired")}</p>
            <Btn busy={auth.action === "sign_in"} disabled={auth.loading} onClick={() => void auth.run("sign_in")}>{t("community.signIn")}</Btn>
          </div>
        ) : items.length ? (
          <Group>
            {items.map((item) => {
              const isDraft = "cover" in item;
              const title = isDraft ? item.title : item.asset.title;
              const description = isDraft ? item.description : item.asset.description;
              const note = isDraft ? undefined : item.reviews[item.reviews.length - 1]?.reason;
              return (
                <article key={item.id} className="flex flex-wrap items-center gap-3 py-3">
                  {isDraft && item.cover && <img src={item.cover} alt="" draggable={false} className="h-12 w-16 shrink-0 rounded-[var(--rs)] object-cover" />}
                  <div className="min-w-[170px] flex-1">
                    <div className="break-words text-[13px] font-semibold">{title || t("publication.untitled")}</div>
                    {description && <p className="m-0 mt-1 break-words text-[13px] text-[var(--ink-muted)]">{description}</p>}
                    <p className="m-0 mt-1 text-xs text-[var(--meta)]">{date(item.updatedAt)}</p>
                    {note && <p className="m-0 mt-2 whitespace-pre-wrap break-words text-[13px] text-[var(--ink-muted)]">{note}</p>}
                  </div>
                  {isDraft ? (
                    <div className="flex gap-2">
                      <Btn onClick={() => setConfirm({ id: item.id, kind: "draft" })}>{t("publication.removeDraft")}</Btn>
                      <Btn onClick={() => onEdit(item)}>{t("publication.edit")}</Btn>
                    </div>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {item.batchId && item.batchId !== batch && <Btn onClick={() => { setBatch(item.batchId); setPage(1); }}>{t("publication.batchFilter")}</Btn>}
                      {item.state === "pending" && <Btn onClick={() => setConfirm({ id: item.id, kind: "withdraw" })}>{t("publication.withdraw")}</Btn>}
                      {(item.state === "rejected" || item.state === "withdrawn") && <Btn onClick={() => onRevise(item)}>{t("publication.edit")}</Btn>}
                    </div>
                  )}
                </article>
              );
            })}
          </Group>
        ) : filter !== "draft" && error ? null : (
          <p className="py-6 text-[13px] text-[var(--help)]">
            {filter === "draft" ? t("publication.noDrafts") : busy ? t("s.f950213ab7") : t("publication.noSubmissions")}
          </p>
        )}
      </CatalogTransition>
      {pages > 1 && <Pager page={current} pages={pages} onChange={setPage} />}
      <Modal open={active && Boolean(confirm)} onClose={() => { if (!applying) setConfirm(undefined); }}
        label={t(confirm?.kind === "draft" ? "publication.removeDraft" : "publication.withdraw")} width={400}>
        <p className="mt-0 text-[13px]">{t(confirm?.kind === "draft" ? "publication.removeDraftConfirm" : "publication.withdrawConfirm")}</p>
        <div className="flex justify-end gap-2">
          <Btn disabled={applying} onClick={() => setConfirm(undefined)}>{uiText("ui.common.cancel")}</Btn>
          <Btn primary busy={applying} onClick={() => void apply()}>{uiText("ui.common.confirm")}</Btn>
        </div>
      </Modal>
    </PagePad>
  );
}
