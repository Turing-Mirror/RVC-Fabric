import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useI18n as useUiI18n, SearchBox, useMenu, usePageActive, usePaneOn, type MenuItem } from "trm-ui";
import { useI18n } from "../i18n";
import { openExternal } from "../lib/plaza";
import { PUBLICATION_PAGE_SIZE, publication, publicationError, validUrl, type CatalogModel } from "../lib/communityPublication";
import { Btn, PageHead, Warn } from "./ui";
import { CatalogTransition } from "./CatalogTransition";
import { CommunityAuthorProfileActions } from "./CommunityAuthorProfileActions";
import { CommunityPublicationCard, CommunityPublicationCards, publicationGroups } from "./CommunityPublicationCard";
import { Pager } from "./Pager";

type ModelPage = {
  name?: string;
  authorUrl?: string | null;
  authorUrlLabel?: string;
  items: CatalogModel[];
  page?: number;
  totalPages?: number;
  nextCursor?: string;
};
type ModelListState = {
  scope: string | null;
  opened: boolean;
  query: string;
  search: string;
  page: number;
  visiblePage: number;
  totalPages?: number;
  pages: Record<number, ModelPage>;
  profile?: { name?: string; link?: { url: string; label?: string | null } };
  error: string;
  busy: boolean;
  refreshing: boolean;
};

function emptyList(scope: string | null): ModelListState {
  return { scope, opened: false, query: "", search: "", page: 1, visiblePage: 1, pages: {}, error: "", busy: false, refreshing: false };
}

export function useCommunityModels({ account, author, own, active }: {
  account?: string | null;
  author?: string;
  own?: boolean;
  active: boolean;
}) {
  const scope = author ?? account ?? null;
  const [state, setState] = useState(() => emptyList(scope));
  const { opened, query, search, page, visiblePage, totalPages, pages, profile, error, busy, refreshing } = state;
  const cached = pages[page];
  const legacy = totalPages === undefined && page > 1;
  const cursor = legacy ? pages[page - 1]?.nextCursor : undefined;
  if (state.scope !== scope) {
    setState(emptyList(scope));
  } else if (active && scope !== null && !opened) {
    setState({ ...state, opened: true });
  }

  useEffect(() => {
    const next = query.trim();
    if (next === search) return;
    const timer = window.setTimeout(() => {
      setState((value) => ({ ...value, search: next, pages: {}, page: 1, visiblePage: 1, totalPages: undefined, error: "", busy: false, refreshing: false }));
    }, 180);
    return () => window.clearTimeout(timer);
  }, [query, scope, search]);

  useEffect(() => {
    if (!opened || scope === null || error || (cached && !refreshing) || (legacy && !cursor)) return;
    let current = true;
    const isCurrentRequest = (value: ModelListState) => value.scope === scope &&
      value.search === search && value.page === page && value.refreshing === refreshing;
    setState((value) => isCurrentRequest(value) ? { ...value, busy: true } : value);
    const options = { query: search || undefined, ...(legacy ? { cursor } : { page }), limit: PUBLICATION_PAGE_SIZE };
    const load = author ? publication<ModelPage>({ action: "author", id: author, ...options })
      : publication<ModelPage>({ action: "owned", ...options });
    void load.catch((cause: unknown): ModelPage => {
      if (own && typeof cause === "object" && cause !== null && "code" in cause && cause.code === "not_found") {
        return { items: [], page: 1, totalPages: 1 };
      }
      throw cause;
    }).then((next) => {
      if (!current) return;
      const receivedPage = next.page ?? page;
      const fallback = author && next.authorUrl === undefined
        ? next.items.find((item) => item.authorUrl && validUrl(item.authorUrl))
        : undefined;
      const url = next.authorUrl || fallback?.authorUrl;
      const link = author && url && validUrl(url)
        ? { url, label: next.authorUrlLabel ?? fallback?.authorUrlLabel }
        : undefined;
      setState((value) => isCurrentRequest(value) ? {
        ...value,
        page: receivedPage,
        visiblePage: receivedPage,
        totalPages: next.totalPages,
        pages: { ...(refreshing ? {} : value.pages), [receivedPage]: next },
        profile: author ? { name: next.name ?? value.profile?.name, link } : undefined,
        busy: false,
        refreshing: false,
      } : value);
    }).catch((cause) => {
      if (current) setState((value) => isCurrentRequest(value)
        ? { ...value, page: value.pages[value.visiblePage] ? value.visiblePage : value.page, error: publicationError(cause, "list"), busy: false, refreshing: false }
        : value);
    });
    return () => { current = false; };
  }, [author, cached, cursor, error, legacy, opened, own, page, refreshing, scope, search]);

  const furthest = Math.max(1, ...Object.keys(pages).map(Number));
  const availablePages = totalPages ?? (pages[furthest]?.nextCursor ? furthest + 1 : furthest);
  const result = pages[visiblePage];

  return {
    query, search, page, visiblePage, result, profile, error, busy, availablePages,
    setQuery: (query: string) => setState((value) => ({ ...value, query })),
    setPage: (page: number) => setState((value) => value.page === page ? value
      : { ...value, page, visiblePage: value.pages[page] ? page : value.visiblePage, busy: false, refreshing: false, error: "" }),
    refresh: () => setState((value) => value.busy || value.refreshing ? value
      : { ...value, page: value.totalPages === undefined ? 1 : value.page, refreshing: true, error: "" }),
    retry: () => setState((value) => ({ ...value, error: "", refreshing: Boolean(value.pages[value.page]) })),
  };
}

export function CommunityAuthorModels({ author, own, ownName, onBack, onView }: {
  author: string;
  own?: boolean;
  ownName?: string | null;
  onBack: () => void;
  onView: (item: CatalogModel) => void;
}) {
  const paneActive = usePaneOn();
  const pageActive = usePageActive();
  const active = paneActive && pageActive;
  const list = useCommunityModels({ author, own, active });
  return <CommunityModelList list={list} ownName={ownName} ownAuthor={own} authorActive={active} onBack={onBack} onView={onView} />;
}

export function CommunityModelList({ list, ownName, ownAuthor, authorActive, onBack, onManage, onView }: {
  list: ReturnType<typeof useCommunityModels>;
  ownName?: string | null;
  ownAuthor?: boolean;
  authorActive?: boolean;
  onBack?: () => void;
  onManage?: (item: CatalogModel, action: "listing" | "version") => void;
  onView: (item: CatalogModel) => void;
}) {
  const { t, locale } = useI18n();
  const { t: uiText } = useUiI18n();
  const menu = useMenu();
  const { query, search, profile, page, visiblePage, result, error, busy, availablePages, setQuery, setPage, retry } = list;
  const results = useRef<HTMLDivElement>(null);
  const oldPage = useRef(visiblePage);
  useLayoutEffect(() => {
    if (oldPage.current === visiblePage) return;
    oldPage.current = visiblePage;
    const content = results.current;
    if (!content || content.closest("[hidden], [inert]")) return;
    const scroller = content.closest<HTMLElement>("[data-page-scroll]");
    if (scroller) scroller.scrollTop = 0;
  }, [visiblePage]);

  function showActions(item: CatalogModel, anchor: HTMLElement) {
    const actions: MenuItem[] = [];
    if (onManage) actions.push(
      { id: "edit", label: t("publication.editListing"), onSelect: () => onManage(item, "listing") },
      { id: "version", label: t("publication.newVersion"), onSelect: () => onManage(item, "version") },
    );
    if (item.upstreamUrl && validUrl(item.upstreamUrl)) actions.push({
      id: "source", label: t("s.voiceLinkSource"), onSelect: () => void openExternal(item.upstreamUrl!),
    });
    if (actions.length) menu.open(anchor, actions);
  }

  return <>
    {onBack && <PageHead title={profile?.name || ownName || t("s.voiceLinkAuthor")} back={onBack}
      actions={<CommunityAuthorProfileActions fallback={profile?.link} own={ownAuthor} active={authorActive} />} />}
    <div className="mb-4 mt-3"><SearchBox value={query} ariaLabel={uiText("ui.common.search")} onChange={setQuery} /></div>
    {error && <Warn className="mb-4">{error} <Btn text onClick={retry}>{t("s.38108eaa1d")}</Btn></Warn>}
    <div ref={results} aria-busy={busy}>
      <CatalogTransition scope={search} page={visiblePage}>
        {result?.items.length ? (
          <CommunityPublicationCards>
            {result.items.map((item) => {
              const name = item.metadata?.nameI18n?.[locale] || item.title;
              const hasMenu = onManage || (item.upstreamUrl && validUrl(item.upstreamUrl));
              return <CommunityPublicationCard key={item.id} id={item.id} title={name} description={item.description}
                cover={item.coverUrl} version={item.compatibleVersion.label} groups={publicationGroups(item.metadata, locale)}
                date={item.compatibleVersion.createdAt} size={item.compatibleVersion.package.sizeBytes}
                actions={<>
                  <Btn text onClick={() => onView(item)}>{t("s.f7acefd2d4")}</Btn>
                  {hasMenu && <Btn text ariaLabel={uiText("ui.common.more")} onClick={(event) => showActions(item, event.currentTarget)}>⋯</Btn>}
                </>} />;
            })}
          </CommunityPublicationCards>
        ) : !error && <p className="py-4 text-[13px] text-[var(--help)]" role="status">
          {result ? t(search ? "publication.noMatchingModels" : "publication.noModels") : t("s.f950213ab7")}
        </p>}
      </CatalogTransition>
    </div>
    {availablePages > 1 && <Pager page={page} pages={availablePages} onChange={setPage} />}
    {menu.node}
  </>;
}
