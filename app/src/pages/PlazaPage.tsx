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
function PlazaPageImpl({
  feed,
  loading = false,
  onReload,
}: {
  feed: PlazaFeed;
  loading?: boolean;
  onReload?: () => void;
}) {
  const [allNotes, setAllNotes] = useState(false);

  const changelog = feed?.changelog ?? [];
  const shown = allNotes ? changelog : changelog.slice(0, 1);
  const items = feed?.items ?? [];

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
            <Btn onClick={() => setAllNotes((v) => !v)}>
              {allNotes ? "只看最新" : "查看全部"}
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
