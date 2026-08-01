import { useState, memo } from "react";
import { Block, Btn, Group, PageHead, PagePad } from "../components/ui";
import {
  formatDate,
  openExternal,
  type ChangelogEntry,
  type PlazaFeed,
  type PlazaItem,
} from "../lib/plaza";

/**
 * Plaza: changelog + placements, both from the CNB release repo.
 *
 * Plaza cards are **not** dismissible — carrying placements is what this page
 * is for. The dismissible one is the single models-page banner, handled there.
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

  const changelog = feed?.changelog ?? [];
  const items = feed?.items ?? [];

  if (showAll) {
    const total = Math.max(1, Math.ceil(changelog.length / PER_PAGE));
    // 数据刷新后条目变少，页码可能已经越界；夹住而不是显示空白页。
    const cur = Math.min(pageNo, total - 1);
    const slice = changelog.slice(cur * PER_PAGE, cur * PER_PAGE + PER_PAGE);
    return (
      <PagePad>
        <PageHead
          title="更新日志"
          sub={`共 ${changelog.length} 个版本`}
          actions={
            <Btn
              onClick={() => {
                setShowAll(false);
                setPageNo(0);
              }}
            >
              返回广场
            </Btn>
          }
        />
        <Block title={`第 ${cur + 1} / ${total} 页`}>
          <Group>
            {slice.length ? (
              slice.map((e) => <Notes key={e.version} entry={e} />)
            ) : (
              <p className="py-3 m-0 text-[13.5px] text-[var(--help)]">
                暂时取不到更新日志。
              </p>
            )}
          </Group>
        </Block>
        {total > 1 ? (
          <div className="flex items-center justify-center gap-3 py-5">
            <Btn disabled={cur <= 0} onClick={() => setPageNo(cur - 1)}>
              上一页
            </Btn>
            <span className="text-[12.5px] text-[var(--meta)] tabular-nums min-w-[72px] text-center">
              {cur + 1} / {total}
            </span>
            <Btn disabled={cur >= total - 1} onClick={() => setPageNo(cur + 1)}>
              下一页
            </Btn>
          </div>
        ) : null}
      </PagePad>
    );
  }

  const shown = changelog.slice(0, 1);

  return (
    <PagePad>
      <PageHead
        title="广场"
        sub="图灵镜 · 更新与投放"
        actions={
          <Btn onClick={() => onReload?.()} disabled={loading}>
            {loading ? "刷新中" : "刷新"}
          </Btn>
        }
      />

      {feed?.errors?.length ? (
        <p className="text-[12.5px] text-[var(--notify)] m-0 mb-4">
          {feed.errors.join("；")}
        </p>
      ) : null}

      <Block
        title="更新日志"
        note={changelog[0]?.version || feed?.app_version || ""}
        action={
          changelog.length > 1 ? (
            <Btn
              onClick={() => {
                setPageNo(0);
                setShowAll(true);
              }}
            >
              查看全部
            </Btn>
          ) : undefined
        }
      >
        <Group>
          {loading && !changelog.length ? (
            <p className="py-3 m-0 text-[13.5px] text-[var(--help)]">读取中…</p>
          ) : shown.length ? (
            shown.map((e) => <Notes key={e.version} entry={e} />)
          ) : (
            <p className="py-3 m-0 text-[13.5px] text-[var(--help)]">
              暂时取不到更新日志。
            </p>
          )}
        </Group>
      </Block>

      <Block title="投放" note={items.length ? String(items.length) : ""}>
        <Group>
          {loading && !items.length ? (
            <p className="py-3 m-0 text-[13.5px] text-[var(--help)]">读取中…</p>
          ) : items.length ? (
            items.map((it) => <Feed key={it.id} item={it} />)
          ) : (
            <p className="py-3 m-0 text-[13.5px] text-[var(--help)]">
              暂时没有内容。
            </p>
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

function Feed({ item }: { item: PlazaItem }) {
  const [imgFailed, setImgFailed] = useState(false);
  const clickable = Boolean(item.url);
  // Three shapes, decided by the parser: 图灵镜推荐, 商业推广, or both.
  const tags: { label: string; ad?: boolean }[] = [];
  if (item.recommended) tags.push({ label: "图灵镜推荐" });
  if (item.is_ad) tags.push({ label: "商业推广", ad: true });

  return (
    <div
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
