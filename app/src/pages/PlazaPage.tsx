import { useCallback, useEffect, useRef, useState, memo } from "react";
import { Block, Btn, Group, PageHead, PagePad } from "../components/ui";
import { StoreSection } from "../components/StoreSection";
import { PinnedRow } from "../components/PinnedRow";
import { t } from "../i18n/t";
import {
  formatDate,
  openExternal,
  type ChangelogEntry,
  type PlazaFeed,
  type PlazaItem,
} from "../lib/plaza";

/**
 * 广场：社区音色、投放、更新日志，从上往下就是这个顺序。
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
 */
/** 更新日志二级页每页几条。够看又不至于把滚动条拉成一条线。 */
const PER_PAGE = 5;

function PlazaPageImpl({
  feed,
  loading = false,
  onReload,
}: {
  feed: PlazaFeed;
  loading?: boolean;
  onReload?: () => void;
}) {
  // 「查看全部」进的是独立一页，不是在原地展开一条长列表 —— 版本多了以后
  // 原地展开会把「投放」挤到看不见的地方，而且没有尽头。
  const [showAll, setShowAll] = useState(false);
  const [pageNo, setPageNo] = useState(0);
  // 加一就是「再拉一次音色清单」。父组件不需要拿到 StoreSection 的方法。
  const [reloadToken, setReloadToken] = useState(0);
  // 被置顶卡片点中的那条投放。高亮完就清掉，不是持久状态。
  const [spotlight, setSpotlight] = useState("");
  const spotTimer = useRef<number | null>(null);
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

  if (showAll) {
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
              onClick={() => {
                setShowAll(false);
                setPageNo(0);
              }}
            >{t("s.5b254c438b")}</Btn>
          }
        />
        <Block title={t("s.pageOf", { cur: cur + 1, total })}>
          <Group>
            {slice.length ? (
              slice.map((e) => <Notes key={e.version} entry={e} />)
            ) : (
              <p className="py-3 m-0 text-[13.5px] text-[var(--help)]">{t("s.0a432092e4")}</p>
            )}
          </Group>
        </Block>
        {total > 1 ? (
          <div className="flex items-center justify-center gap-3 py-5">
            <Btn disabled={cur <= 0} onClick={() => setPageNo(cur - 1)}>{t("s.b41561d807")}</Btn>
            <span className="text-[12.5px] text-[var(--meta)] tabular-nums min-w-[72px] text-center">
              {cur + 1} / {total}
            </span>
            <Btn disabled={cur >= total - 1} onClick={() => setPageNo(cur + 1)}>{t("s.67a246a344")}</Btn>
          </div>
        ) : null}
      </PagePad>
    );
  }

  const shown = changelog.slice(0, 1);

  return (
    <PagePad>
      <PageHead
        title={t("s.a8776899a4")}
        actions={
          <Btn
            onClick={() => {
              onReload?.();
              setReloadToken((n) => n + 1);
            }}
            disabled={loading}
          >
            {loading ? t("s.d47379f917") : t("s.38108eaa1d")}
          </Btn>
        }
      />

      {feed?.errors?.length ? (
        <p className="text-[12.5px] text-[var(--notify)] m-0 mb-4">
          {feed.errors.join("；")}
        </p>
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

      <Block title={t("s.aff4b0df8a")} note={items.length ? String(items.length) : ""}>
        <Group>
          {loading && !items.length ? (
            <p className="py-3 m-0 text-[13.5px] text-[var(--help)]">{t("s.f950213ab7")}</p>
          ) : items.length ? (
            items.map((it) => (
              <Feed key={it.id} item={it} spotlight={spotlight === it.id} />
            ))
          ) : (
            <p className="py-3 m-0 text-[13.5px] text-[var(--help)]">{t("s.f9f2a78f9f")}</p>
          )}
        </Group>
      </Block>

      <Block
        title={t("s.185368440e")}
        note={changelog[0]?.version || feed?.app_version || ""}
        action={
          changelog.length > 1 ? (
            <Btn
              onClick={() => {
                setPageNo(0);
                setShowAll(true);
              }}
            >{t("s.ed2172fd78")}</Btn>
          ) : undefined
        }
      >
        <Group>
          {loading && !changelog.length ? (
            <p className="py-3 m-0 text-[13.5px] text-[var(--help)]">{t("s.f950213ab7")}</p>
          ) : shown.length ? (
            shown.map((e) => <Notes key={e.version} entry={e} />)
          ) : (
            <p className="py-3 m-0 text-[13.5px] text-[var(--help)]">{t("s.0a432092e4")}</p>
          )}
        </Group>
      </Block>

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
            className="text-[13.5px] text-[var(--ink-muted)] leading-relaxed pl-[18px] relative before:content-['·'] before:absolute before:left-1.5 before:text-[var(--meta)]"
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
        <h4 className="m-0 mb-1.5 text-[14.5px] font-semibold flex items-center gap-2 flex-wrap">
          {item.title}
          {tags.map((t) => (
            <span
              key={t.label}
              className={[
                "text-[11.5px] px-2 py-0.5 rounded-[5px] whitespace-nowrap shadow-[inset_0_0_0_1px_var(--line)]",
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
          <p className="m-0 mt-1 text-[11.5px] text-[var(--meta)]">由 {item.sponsor} 投放</p>
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
