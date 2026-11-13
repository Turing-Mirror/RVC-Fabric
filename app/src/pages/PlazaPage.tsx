import { useCallback, useEffect, useRef, useState, memo, type ReactNode } from "react";
import { Block, Btn, Group, PageHead, PagePad, Warn } from "../components/ui";
import { Pane, Panes, useNotify, usePageActive, usePaneOn } from "trm-ui";
import { CommunityActions, useCommunityAccount } from "../components/CommunityActions";
import { CommunityPublisher } from "../components/CommunityPublisher";
import { CommunitySubmissions } from "../components/CommunitySubmissions";
import { loadDrafts, newDraft, storeDrafts, type Draft, type Submission } from "../lib/communityPublication";
import { StoreSection } from "../components/StoreSection";
import { Pager } from "../components/Pager";
import { CatalogTransition } from "../components/CatalogTransition";
import { ExtrasPanel, type ExtrasFilter } from "../components/ExtrasDialog";
import { PinnedRow } from "../components/PinnedRow";
import { t } from "../i18n/t";
import {
  formatDate,
  openExternal,
  type ChangelogEntry,
  type PlazaFeed,
  type PlazaItem,
} from "../lib/plaza";
import { formatLocalizedList } from "../lib/voiceDisplay";
import { useI18n } from "../i18n";

/**
 * 广场：社区音色、投放、下载模型、更新日志，从上往下就是这个顺序。
 * DSP 预设不上广场（内置在模型页）。
 *
 * 社区音色排第一，因为这是用户主动进广场的唯一理由 —— 投放和更新日志是我们
 * 想让他看的，音色是他想看的。把想让人看的东西摆在人想看的东西前面，结果是
 * 两个都没人看。
 *
 * 投放卡片**不可关闭**：承载投放正是这一页存在的意义。可关闭的是模型页顶部
 * 那一条横幅，在那边单独处理。
 *
 * 刷新只有一个：右上角那个。一次点击把三块内容全刷了 —— 音色清单走
 * StoreSection 的 reloadToken，投放和更新日志走 onReload。三个各自的刷新
 * 按钮只会让人猜「我该点哪个」。
 *
 * 「下载模型」排在投放下面：它和社区音色是同一类事（都是往本机装东西），
 * 但用户主动来找它的次数少得多 —— 一台机器装一次引擎资源就完了。所以不跟
 * 社区音色抢第一屏，但也不能压到更新日志后面去。
 *
 * 它原来是「其他」页上弹出来的一个框。「其他」页现在只留一个入口，点了跳
 * 到这儿来 —— 和「模型」页的「社区音色」是一样的处理。
 */
/** 更新日志二级页每页几条。够看又不至于把滚动条拉成一条线。 */
const PER_PAGE = 5;

type PlazaProps = {
  feed: PlazaFeed;
  loading?: boolean;
  onReload?: () => void;
  downloadReason?: string;
  extrasFilter?: ExtrasFilter;
  scrollToDownloads?: number;
};

const communityPages = ["catalog", "changelog", "publish", "submissions"] as const;
type CommunityPage = (typeof communityPages)[number];

function PlazaPageImpl(props: PlazaProps) {
  const auth = useCommunityAccount();
  const { t } = useI18n();
  const { tip } = useNotify();
  const [page, setPage] = useState<CommunityPage>("catalog");
  const [editor, setEditor] = useState<Draft>();
  const [drafts, setDrafts] = useState(loadDrafts);
  const currentDrafts = useRef(drafts);
  const [recent, setRecent] = useState<Submission>();
  const [request, setRequest] = useState(props.scrollToDownloads);
  if (request !== props.scrollToDownloads) {
    setRequest(props.scrollToDownloads);
    if (props.scrollToDownloads) setPage("catalog");
  }

  function persist(update: (previous: Draft[]) => Draft[]) {
    try {
      const next = update(currentDrafts.current);
      storeDrafts(next);
      currentDrafts.current = next;
      setDrafts(next);
      return true;
    } catch {
      tip(t("publication.saveFailed"));
      return false;
    }
  }

  function save(draft: Draft) {
    return persist((previous) => [{ ...draft, updatedAt: new Date().toISOString() }, ...previous.filter((item) => item.id !== draft.id)]);
  }

  function remove(id: string) {
    persist((previous) => previous.filter((item) => item.id !== id));
  }

  function openEditor(draft = newDraft()) {
    setEditor(draft);
    setPage("publish");
  }

  function leaveEditor(draft: Draft, next: "catalog" | "submissions") {
    const hasContent = draft.url || draft.title || draft.description || draft.originalAuthor || draft.authorUrl || draft.licenseEdited || draft.cover || draft.updatedAt;
    if (!hasContent || save(draft)) setPage(next);
  }

  return (
    <Panes value={page} order={communityPages} transition="slide" keepScroll>
      <Pane id="catalog">
        <Catalog
          {...props}
          actions={<CommunityActions auth={auth} onPublish={() => openEditor()} onSubmissions={() => setPage("submissions")} />}
          onChangelog={() => setPage("changelog")}
        />
      </Pane>
      <Pane id="changelog">
        <ChangelogPage changelog={props.feed.changelog ?? []} onBack={() => setPage("catalog")} />
      </Pane>
      <Pane id="publish">
        {editor && (
          <CommunityPublisher
            key={editor.id}
            initial={editor}
            auth={auth}
            onBack={(draft) => leaveEditor(draft, "catalog")}
            onSave={save}
            onMySubmissions={(draft) => leaveEditor(draft, "submissions")}
            onSubmitted={(draft, submission) => {
              remove(draft.id);
              setRecent(submission);
              setPage((current) => current === "publish" ? "submissions" : current);
            }}
          />
        )}
      </Pane>
      <Pane id="submissions">
        <CommunitySubmissions
          auth={auth}
          drafts={drafts}
          recent={recent}
          onBack={() => setPage("catalog")}
          onNew={() => openEditor()}
          onEdit={openEditor}
          onRemove={remove}
          onRevise={(previous) => openEditor(newDraft(previous))}
        />
      </Pane>
    </Panes>
  );
}

function Catalog({ feed, loading = false, onReload, downloadReason = "", extrasFilter = "all", scrollToDownloads = 0, actions, onChangelog }: PlazaProps & { actions: ReactNode; onChangelog: () => void }) {
  useI18n();
  const paneActive = usePaneOn();
  const pageActive = usePageActive();
  const active = paneActive && pageActive;
  // 加一就是「再拉一次音色清单」。父组件不需要拿到 StoreSection 的方法。
  const [reloadToken, setReloadToken] = useState(0);
  // 被置顶卡片点中的那条投放。高亮完就清掉，不是持久状态。
  const [spotlight, setSpotlight] = useState("");
  const spotTimer = useRef<number | null>(null);
  // 从别处跳过来找「下载模型」的：这一页很长，不滚过去等于没跳。
  const extrasRef = useRef<HTMLDivElement>(null);
  const lastScroll = useRef(0);
  useEffect(() => {
    if (!active || !scrollToDownloads || lastScroll.current === scrollToDownloads) return;
    const frame = requestAnimationFrame(() => {
      lastScroll.current = scrollToDownloads;
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      extrasRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    });
    return () => cancelAnimationFrame(frame);
  }, [active, scrollToDownloads]);
  useEffect(
    () => () => {
      if (spotTimer.current) window.clearTimeout(spotTimer.current);
    },
    [],
  );

  const changelog = feed?.changelog ?? [];
  const items = feed?.items ?? [];
  // 后端已经把置顶削到最多五条，这里筛一下就行，不用再 slice。
  const pinned = items.filter((it) => it.pinned);

  // 点置顶卡 → 滚到下面那条投放，并让它亮一下。
  //
  // 只滚不亮不行：投放区可能有十几条，滚过去之后用户还得自己找「刚才点的是
  // 哪条」。亮一下是**告诉他落点在哪**，所以 1.6 秒后自动灭 —— 一个一直亮着
  // 的高亮会被当成「选中状态」，而这里没有选中这回事。
  const pick = useCallback((id: string) => {
    setSpotlight(id);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.getElementById(`plaza-item-${id}`)?.scrollIntoView({
      behavior: reduce ? "auto" : "smooth",
      block: "center",
    });
    if (spotTimer.current) window.clearTimeout(spotTimer.current);
    spotTimer.current = window.setTimeout(() => setSpotlight(""), 1600);
  }, []);

  const shown = changelog.slice(0, 1);

  return (
    <PagePad>
      <PageHead
        title={t("s.a8776899a4")}
        actions={
          <>
            {actions}
            <Btn
              onClick={() => {
                onReload?.();
                setReloadToken((n) => n + 1);
              }}
              disabled={loading}
            >
              {loading ? t("s.d47379f917") : t("s.38108eaa1d")}
            </Btn>
          </>
        }
      />

      {feed?.errors?.length ? (
        <Warn className="mb-4">{formatLocalizedList(feed.errors)}</Warn>
      ) : null}

      {/* 置顶排在社区音色之上。它只有一排卡片高，压不住下面的东西，而它指向的
          就是这一页最该被看到的几条 —— 排在第一屏才有意义。
          一条都没置顶时整块不出现，不留一个空标题在那儿。 */}
      {pinned.length ? (
        <Block title={t("s.7bcf18641f")}>
          <PinnedRow items={pinned} onPick={pick} />
        </Block>
      ) : null}

      <Block title={t("s.b2be174f0f")} note={t("s.95344bde41")}>
        <StoreSection reloadToken={reloadToken} />
      </Block>

      {items.length ? (
        <Block title={t("s.aff4b0df8a")} note={String(items.length)}>
          <Group>{items.map((it) => <Feed key={it.id} item={it} spotlight={spotlight === it.id} />)}</Group>
        </Block>
      ) : null}

      <Block title={t("s.1252c81119")}>
        <div id="download-models" ref={extrasRef} className="scroll-mt-4">
          <ExtrasPanel filter={extrasFilter} reason={downloadReason} />
        </div>
      </Block>

      <Block
        title={t("s.185368440e")}
        note={changelog[0]?.version || feed?.app_version || ""}
        action={
          changelog.length > 1 ? (
            <Btn
              onClick={onChangelog}
            >{t("s.ed2172fd78")}</Btn>
          ) : undefined
        }
      >
        <Group>
          {loading && !changelog.length ? (
            <p className="py-3 m-0 text-[13px] text-[var(--help)]">{t("s.f950213ab7")}</p>
          ) : shown.length ? (
            shown.map((e) => <Notes key={e.version} entry={e} />)
          ) : (
            <p className="py-3 m-0 text-[13px] text-[var(--help)]">{t("s.0a432092e4")}</p>
          )}
        </Group>
      </Block>

    </PagePad>
  );
}

function ChangelogPage({ changelog, onBack }: { changelog: ChangelogEntry[]; onBack: () => void }) {
  useI18n();
  const [pageNo, setPageNo] = useState(0);
  function back() {
    setPageNo(0);
    onBack();
  }
  const total = Math.max(1, Math.ceil(changelog.length / PER_PAGE));
  // 数据刷新后条目变少，页码可能已经越界；夹住而不是显示空白页。
  const cur = Math.min(pageNo, total - 1);
  const slice = changelog.slice(cur * PER_PAGE, cur * PER_PAGE + PER_PAGE);
  return (
    <PagePad>
      <PageHead
        title={t("s.185368440e")}
        sub={t("s.6ca99d2c45", { v0: changelog.length })}
        actions={
          <Btn
            onClick={back}
          >{t("s.5b254c438b")}</Btn>
        }
      />
      <Block title={t("s.pageOf", { cur: cur + 1, total })}>
        <CatalogTransition scope="changelog" page={cur + 1}>
          <Group>
            {slice.length ? (
              slice.map((e) => <Notes key={e.version} entry={e} />)
            ) : (
              <p className="py-3 m-0 text-[13px] text-[var(--help)]">{t("s.0a432092e4")}</p>
            )}
          </Group>
        </CatalogTransition>
      </Block>
      <Pager className="py-5" page={cur + 1} pages={total} onChange={(p) => setPageNo(p - 1)} />
    </PagePad>
  );
}

function Notes({ entry }: { entry: ChangelogEntry }) {
  return (
    <div className="py-3">
      <div className="text-[15px] font-semibold">
        {entry.version}
        {entry.date ? (
          <span className="font-normal text-[var(--meta)] text-[12.5px] ml-2.5">
            {formatDate(entry.date)}
          </span>
        ) : null}
      </div>
      {entry.title ? (
        <div className="text-[13px] text-[var(--ink-muted)] mt-1">{entry.title}</div>
      ) : null}
      <ul className="m-2.5 ml-0 p-0 list-none">
        {entry.notes.map((t) => (
          <li
            key={t}
            className="text-[13px] text-[var(--ink-muted)] leading-relaxed pl-[18px] relative before:content-['•'] before:absolute before:left-1.5 before:text-[var(--meta)]"
          >
            {t}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Feed({
  item,
  spotlight = false,
}: {
  item: PlazaItem;
  /** 刚被上面的置顶卡点中，亮一下。 */
  spotlight?: boolean;
}) {
  const [imgFailed, setImgFailed] = useState(false);
  const clickable = Boolean(item.url);
  // Three shapes, decided by the parser: 图灵镜推荐, 商业推广, or both.
  const tags: { label: string; ad?: boolean }[] = [];
  if (item.recommended) tags.push({ label: t("s.d077c504cc") });
  if (item.is_ad) tags.push({ label: t("s.3d13883b98"), ad: true });

  return (
    <div
      // 置顶卡片靠这个 id 找到落点。
      id={`plaza-item-${item.id}`}
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={clickable ? () => void openExternal(item.url) : undefined}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                void openExternal(item.url);
              }
            }
          : undefined
      }
      className={[
        "flex gap-[18px] items-start py-4 -mx-3.5 px-3.5 rounded-[var(--rs)] transition-colors",
        clickable
          ? "cursor-pointer hover:bg-[color-mix(in_srgb,var(--ink)_4%,transparent)] focus-visible:outline-2 focus-visible:outline-[var(--accent)] focus-visible:outline-offset-[-2px]"
          : "",
        spotlight ? "spotlight" : "",
      ].join(" ")}
    >
      {item.image_url && !imgFailed ? (
        <img
          src={item.image_url}
          alt=""
          loading="lazy"
          onError={() => setImgFailed(true)}
          className="w-[104px] h-16 rounded-[var(--rs)] flex-none object-cover max-[720px]:w-[76px] max-[720px]:h-[50px]"
        />
      ) : (
        <div className="w-[104px] h-16 rounded-[var(--rs)] flex-none bg-[color-mix(in_srgb,var(--ink)_7%,transparent)] max-[720px]:w-[76px] max-[720px]:h-[50px]" />
      )}
      <div>
        <h4 className="m-0 mb-1.5 text-[15px] font-semibold flex items-center gap-2 flex-wrap">
          {item.title}
          {tags.map((t) => (
            <span
              key={t.label}
              className={[
                "text-[11.5px] px-2 py-0.5 rounded-[var(--rs)] whitespace-nowrap shadow-[inset_0_0_0_1px_var(--line)]",
                t.ad
                  ? "text-[var(--notify)] shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--notify)_48%,transparent)]"
                  : "text-[var(--meta)]",
              ].join(" ")}
            >
              {t.label}
            </span>
          ))}
        </h4>
        <p className="m-0 text-[12.5px] text-[var(--help)] leading-relaxed">{item.body}</p>
        {item.sponsor ? (
          <p className="m-0 mt-1 text-[11.5px] text-[var(--meta)]">
            {t("s.0b38f69017", { v0: item.sponsor })}
          </p>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Memoised: App re-renders on every engine status tick (2.5x a second while
 * converting). Without this the whole page tree was rebuilt each time for a
 * mic-level change that only the dock cares about.
 */
export const PlazaPage = memo(PlazaPageImpl);
