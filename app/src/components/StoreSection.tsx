import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import {
  colsForWidth,
  fetchStoreCatalog,
  stagedVoices,
  revealStagedVoice,
  discardStagedVoice,
  coverSrc,
  type StagedVoice,
  type StoreCatalog,
  type StoreVoice,
} from "../lib/voices";
import {
  cancelStoreJob,
  enqueueStoreDownload,
  useStoreJobs,
  type VoiceProg,
} from "../lib/storeJobs";
import { TextInput } from "trm-ui";
import { Btn, Warn } from "./ui";
import { Select } from "./controls";
import { SegmentControl } from "./SegmentControl";
import { Pager } from "./Pager";
import { CatalogTransition } from "./CatalogTransition";
import { CatalogCover, useDir, useMenu, usePageActive, usePaneOn, type MenuItem } from "trm-ui";
import { resolveCover, useCoverCache } from "../lib/cover";
import { t, getTLocale } from "../i18n/t";
import {
  compareVoiceGroups,
  displayVoiceAuthor,
  displayVoiceFieldForGroup,
  displayVoiceName,
  isCharacterAsGroup,
  isCharacterAsSeries,
  voiceAuthorList,
  voiceChildGroup,
  voiceGroupRaw,
  voiceParentSeries,
  voiceSearchText,
  voiceVersionLabel,
} from "../lib/voiceDisplay";
import { askConfirm } from "trm-ui/fabric";
import { openExternal } from "../lib/plaza";
import { AuthorsDialog } from "./AuthorsDialog";
import type { VoiceAuthor } from "../lib/voices";
import { useI18n } from "../i18n";
import { Leave } from "./Presence";
import { joinClauses } from "../lib/text";

/** Parent + child focus key. Tab never appears in series / group labels. */
const FOCUS_SEP = "\t";
const OTHER_SERIES_KEY = "__other__";

const STALL_AFTER_MS = 12_000;

function formatDuration(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return t("s.0cc05a38ad", { v0: s });
  const m = Math.floor(s / 60);
  return t("s.2a94e5c93f", { v0: m, v1: s % 60 });
}

/** Integer 0% used to mean both "not started" and "first 800 KB of a 80 MB pack". */
function storePercentLabel(
  progress: VoiceProg | undefined,
  now: number,
  lastMoveAt: number,
): string {
  const done = progress?.done ?? 0;
  const pct = progress?.percent ?? 0;
  const idleMs = lastMoveAt ? now - lastMoveAt : 0;
  if (idleMs > STALL_AFTER_MS) {
    return t("s.2a4fa38f1e", { v0: formatDuration(idleMs) });
  }
  if (done <= 0) return t("s.502c5adda6");
  if (pct < 0.1) return "<0.1%";
  if (pct < 10) return `${pct.toFixed(1)}%`;
  return `${Math.round(pct)}%`;
}

type SeriesNode = {
  key: string;
  label: string;
  voices: StoreVoice[];
  groups: { raw: string; label: string; voices: StoreVoice[] }[];
};

function focusParts(focus: string): { parent: string; group: string } {
  if (!focus) return { parent: "", group: "" };
  const i = focus.indexOf(FOCUS_SEP);
  if (i < 0) return { parent: focus, group: "" };
  return { parent: focus.slice(0, i), group: focus.slice(i + FOCUS_SEP.length) };
}

function groupFocusKey(parent: string, group: string): string {
  return `${parent}${FOCUS_SEP}${group}`;
}

/**
 * 社区音色。原来是模型页上弹出来的一个对话框，现在是广场的第一块。
 *
 * 换位置带来的真正变化是宽度：对话框最宽 720px，只放得下一列列表行；广场是
 * 整页，所以改成和模型页一样的封面网格 —— 默认窗口一行五个、一页三行。挑音色
 * 是看脸的事，一行文字加一个 56px 的小图标没法挑。
 *
 * 列数不写死：跟着容器宽度用 colsForWidth 算，和模型页共用同一个函数，
 * 两个网格在任何窗口宽度下都是一样的密度。
 */

// 来源和组织方式是两个独立维度。原本压在一个 SegmentControl 里（最新合流 /
// 图灵镜源 / 第三方 / 系列专区），结果「原神系列里的第三方音色」这种组合根本
// 表达不出来 —— 选了系列就没法筛来源，选了第三方就没有系列分组。
type Source = "all" | "official" | "thirdparty";
type Grouping = "time" | "series";

/** 一个系列先铺几行，再多要点「查看全部」。 */
const SERIES_PREVIEW_ROWS = 1;
/** 一页几行。和模型页一样。 */
const PAGE_ROWS = 3;

type Props = {
  /**
   * 外面（广场的「刷新」）每加一次这个数，就重新拉一次清单。
   *
   * 广场只有一个刷新按钮，一次点击刷新全部内容 —— 音色清单、投放、更新日志。
   * 用计数器而不是回调句柄：父组件不需要拿到子组件的方法，加一就行。
   */
  reloadToken: number;
  /** 装好一个音色。模型页下次进入时会自己重新列，这里只用来提示。 */
  onInstalled?: () => void;
};

function stagingId(voice: StoreVoice) {
  return voice.community_staging_id || voice.id;
}

export function StoreSection({ reloadToken, onInstalled }: Props) {
  const { locale } = useI18n();
  const pageActive = usePageActive();
  const paneActive = usePaneOn();
  const active = pageActive && paneActive;
  const [cat, setCat] = useState<StoreCatalog | null>(null);
  const [loading, setLoading] = useState(false);
  const [source, setSource] = useState<Source>("all");
  const [grouping, setGrouping] = useState<Grouping>("time");
  const [hideInstalled, setHideInstalled] = useState(false);
  /** 哪些系列被点了「查看全部」。 */
  const [seriesFull, setSeriesFull] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  /** 父系列下展开的子类（社团 / 乐队）。 */
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  /** 系列视图里定位到某一个系列或子类；空 = 列出全部折叠项。 */
  const [seriesFocus, setSeriesFocus] = useState("");
  /** 某个系列「查看全部」之后的页码。 */
  const [seriesPage, setSeriesPage] = useState<Record<string, number>>({});
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [cols, setCols] = useState(5);
  // Jobs live in storeJobs so leaving the plaza does not drop an in-flight pack.
  const jobs = useStoreJobs();
  const running = jobs.running;
  const queued = jobs.queued;
  const prog = jobs.prog;
  const [err, setErr] = useState("");
  const [thirdAck, setThirdAck] = useState(false);
  /** 第三方下完后滚到「确认安装」那张卡。 */
  const [scrollToId, setScrollToId] = useState("");
  // 官方源同样要过一次须知。第三方那条讲的是「来源不可信、pickle 有风险」，
  // 是安全问题；这一条讲的是声音权利，跟音色从哪来无关 —— 图灵镜自己训练的
  // 音色一样是拿别人的声音训出来的。两条内容不同，但都只弹一次。
  const [officialAck, setOfficialAck] = useState(false);
  // 已下载但还没装的第三方音色。第三方 .pth 是 pickle，加载即执行代码，
  // 所以下完停在这里，让用户先自己看一眼再决定装不装。
  const [staged, setStaged] = useState<Record<string, StagedVoice>>({});
  const gridRef = useRef<HTMLDivElement>(null);

  const loadStaged = useCallback(async () => {
    try {
      setStaged(await stagedVoices());
    } catch {
      /* 拿不到就当没有暂存，不影响下载本身 */
    }
  }, []);

  const refresh = useCallback(async (remote = true) => {
    setLoading(true);
    setErr("");
    try {
      const c = await fetchStoreCatalog(remote);
      setCat(c);
      if (c.fetch_error) setErr(c.fetch_error);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // Refresh on entry and when the user clicks Refresh. The mounted catalog
  // keeps its filters and page while the user opens another view.
  useEffect(() => {
    if (!pageActive) return;
    void refresh(true);
    void loadStaged();
  }, [pageActive, reloadToken, refresh, loadStaged]);

  // A job that finished while this page was unmounted still has to refresh the
  // catalog and the staged list, otherwise the card stays on 「下载」.
  useEffect(() => {
    if (jobs.generation === 0) return;
    void loadStaged();
    void refresh(false);
    onInstalled?.();
    if (jobs.lastCompletedThird && jobs.lastCompleted) setScrollToId(jobs.lastCompleted);
  }, [jobs.generation, jobs.lastCompleted, jobs.lastCompletedThird, loadStaged, refresh, onInstalled]);

  useEffect(() => {
    if (!active || !scrollToId) return;
    const voice = cat?.thirdparty_voices?.find((entry) => entry.id === scrollToId);
    if (!staged[voice ? stagingId(voice) : scrollToId]) return;
    const el = document.getElementById(`store-voice-${scrollToId}`);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
    el?.querySelector<HTMLElement>(".confirm-install")?.focus();
    setScrollToId("");
  }, [active, cat, scrollToId, staged]);

  // 列数跟着容器宽度走，和模型页同一个函数。
  useEffect(() => {
    const el = gridRef.current?.parentElement || gridRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      setCols(colsForWidth(entries[0]?.contentRect.width || window.innerWidth));
    });
    ro.observe(el);
    setCols(colsForWidth(el.clientWidth || window.innerWidth));
    return () => ro.disconnect();
  }, []);

  const list = useMemo(() => {
    // Derived inside the memo on purpose: `cat?.voices || []` allocates a fresh
    // array every render, so listing them as dependencies meant this filter and
    // sort re-ran on every keystroke elsewhere on the page.
    const official = cat?.voices || [];
    const third = cat?.thirdparty_voices || [];
    let base: StoreVoice[] =
      source === "official"
        ? [...official]
        : source === "thirdparty"
          ? [...third]
          : [...official, ...third];
    // 一律按收录日期倒序。分组视图也排，这样每个系列内部顺序是稳定的。
    base.sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));
    if (hideInstalled) base = base.filter((v) => !v.installed || v.update_available);
    const qq = q.trim().toLowerCase();
    if (qq) {
      base = base.filter((v) =>
        voiceSearchText(v).toLowerCase().includes(qq),
      );
    }
    return base;
  }, [source, hideInstalled, cat, q]);

  const seriesGroups = useMemo((): SeriesNode[] | null => {
    if (grouping !== "series") return null;
    // 父系列 → 子类。清单有 group 就按 group 展开，没有就整类平铺。
    // 没填 series 的落进「其他」。
    const other = t("s.1a26edf94a");
    const loc = locale;
    const map = new Map<
      string,
      { voices: StoreVoice[]; groups: Map<string, StoreVoice[]> }
    >();
    for (const v of list) {
      const rawSeries = (v.series || "").trim();
      const parentKey = rawSeries || OTHER_SERIES_KEY;
      let bucket = map.get(parentKey);
      if (!bucket) {
        bucket = { voices: [], groups: new Map() };
        map.set(parentKey, bucket);
      }
      bucket.voices.push(v);
      const rawGroup = voiceGroupRaw(v);
      if (!bucket.groups.has(rawGroup)) bucket.groups.set(rawGroup, []);
      bucket.groups.get(rawGroup)!.push(v);
    }
    const nodes: SeriesNode[] = [...map.entries()]
      .map(([key, bucket]) => {
        const rawSeries =
          bucket.voices.map((v) => (v.series || "").trim()).find(Boolean) || "";
        const parentLabel =
          displayVoiceFieldForGroup(bucket.voices, "series", loc).trim() ||
          rawSeries ||
          other;
        const gm = bucket.groups;
        const named = [...gm.keys()].some((r) => r);
        const groups = [...gm.entries()]
          .map(([raw, voices]) => {
            let label = named
              ? displayVoiceFieldForGroup(voices, "group", loc).trim() ||
                (raw ? raw : other)
              : "";
            // 子类名就是角色名时，不要再套一层「分类」。
            if (label && label !== other && isCharacterAsGroup(label, voices, loc)) {
              label = "";
            }
            return { raw, label, voices };
          })
          .sort((a, b) => compareVoiceGroups(a.label, b.label, other, loc));
        return {
          key,
          label: parentLabel,
          voices: groups.flatMap((g) => g.voices),
          groups,
        };
      })
      .sort((a, b) => {
        if (a.key === OTHER_SERIES_KEY) return 1;
        if (b.key === OTHER_SERIES_KEY) return -1;
        return a.label.localeCompare(b.label, loc);
      });

    // 系列名等于唯一角色名（如 ATRI / ATRI）时并进「其他」，
    // 否则「按分类查看」会把一个角色画成一个分类。
    const folded: StoreVoice[] = [];
    const kept: SeriesNode[] = [];
    for (const n of nodes) {
      if (n.key !== OTHER_SERIES_KEY && isCharacterAsSeries(n.key, n.voices, loc)) {
        folded.push(...n.voices);
      } else {
        kept.push(n);
      }
    }
    if (folded.length) {
      let extra = kept.find((n) => n.key === OTHER_SERIES_KEY);
      if (!extra) {
        extra = { key: OTHER_SERIES_KEY, label: other, voices: [], groups: [] };
        kept.push(extra);
      }
      extra.voices = extra.voices.concat(folded);
      const rawKey = "";
      const hit = extra.groups.find((g) => g.raw === rawKey);
      if (hit) hit.voices = hit.voices.concat(folded);
      else extra.groups.push({ raw: rawKey, label: "", voices: folded });
    }
    return kept;
  }, [grouping, list, locale]);

  const catalogDirection = useDir(["all", "official", "thirdparty"].indexOf(source) * 2 + (grouping === "series" ? 1 : 0));
  const perPage = cols * PAGE_ROWS;
  const totalPages = Math.max(1, Math.ceil(list.length / perPage));
  const pageClamped = Math.min(page, totalPages);
  const pageItems =
    grouping === "series"
      ? []
      : list.slice((pageClamped - 1) * perPage, pageClamped * perPage);

  // 预取当前可见的分页；收起的系列不占封面缓存请求。
  const coverUrls = useMemo(() => {
    const pick = (v: StoreVoice) => (v.cover_url || v.cover || "").trim();
    if (!seriesGroups) {
      const start = (pageClamped - 1) * perPage;
      return list.slice(start, start + perPage * 2).map(pick).filter(Boolean);
    }
    const { parent, group } = focusParts(seriesFocus);
    const visible: StoreVoice[] = [];
    const append = (key: string, voices: StoreVoice[], forcedFull: boolean) => {
      const { shown } = seriesSlice(voices, cols, perPage, forcedFull || seriesFull.has(key), seriesPage[key]);
      visible.push(...shown);
    };
    for (const node of seriesGroups) {
      if (parent ? node.key !== parent : !expanded.has(node.key)) continue;
      if ((parent && !group) || !node.groups.some(g => g.label)) {
        append(node.key, node.voices, Boolean(parent));
      } else {
        for (const entry of node.groups) {
          const key = groupFocusKey(node.key, entry.raw);
          if (group ? entry.raw === group : expandedGroups.has(key)) {
            append(key, entry.voices, Boolean(group));
          }
        }
      }
      if (visible.length >= 60) break;
    }
    return [...new Set(visible.map(pick).filter(Boolean))].slice(0, 60);
  }, [cols, expanded, expandedGroups, list, pageClamped, perPage, seriesFocus, seriesFull, seriesGroups, seriesPage]);
  const coverCache = useCoverCache(coverUrls);

  // 窗口变窄导致每页装得下的变少时，当前页可能已经越界。
  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  // 筛完之后焦点系列没了，退回「全部系列」。
  useEffect(() => {
    if (!seriesFocus || !seriesGroups) return;
    const { parent, group } = focusParts(seriesFocus);
    const node = seriesGroups.find((s) => s.key === parent);
    if (!node) {
      setSeriesFocus("");
      return;
    }
    if (group && !node.groups.some((g) => g.raw === group)) {
      setSeriesFocus("");
    }
  }, [seriesFocus, seriesGroups]);

  // 搜索时把命中的系列和子类都展开，免得人还要一个个点开找。
  useEffect(() => {
    if (!q.trim() || !seriesGroups?.length) return;
    setExpanded(new Set(seriesGroups.map((s) => s.key)));
    setExpandedGroups(
      new Set(
        seriesGroups.flatMap((s) =>
          s.groups
            .filter((g) => g.label)
            .map((g) => groupFocusKey(s.key, g.raw)),
        ),
      ),
    );
  }, [q, seriesGroups]);

  const installStaged = (v: StoreVoice) => {
    setErr("");
    enqueueStoreDownload(v, "staged");
  };

  const cancelOne = (id: string) => {
    cancelStoreJob(id);
  };

  const viewStaged = async (v: StoreVoice) => {
    try {
      await revealStagedVoice(stagingId(v));
    } catch (e) {
      setErr(String(e));
    }
  };

  const discard = async (v: StoreVoice) => {
    const s = staged[stagingId(v)];
    if (
      !(await askConfirm(
        t("s.de94f39aff", { v0: s?.file || v.name }),
      ))
    )
      return;
    try {
      await discardStagedVoice(stagingId(v));
      await loadStaged();
    } catch (e) {
      setErr(String(e));
    }
  };

  const install = async (v: StoreVoice) => {
    if ((v.installed && !v.update_available) || running.includes(v.id) || queued.includes(v.id)) return;
    if (v.official !== false && !officialAck) {
      const ok = await askConfirm(
        t("s.9a9349a407") +
          t("s.0ea68258a8") +
          t("s.f6453bbaae") +
          t("s.8ab59cc845") +
          t("s.63a937a39e"),
      );
      if (!ok) return;
      setOfficialAck(true);
    }
    if (v.official === false && !thirdAck) {
      const ok = await askConfirm(
        t("s.ba1368fee3") +
          t("s.1229f8d52c") +
          t("s.60d30d777c") +
          t("s.6c908a4301"),
      );
      if (!ok) return;
      setThirdAck(true);
    }
    enqueueStoreDownload(v);
  };

  const cardProps = (v: StoreVoice) => ({
    v,
    busy: running.includes(v.id),
    queued: queued.includes(v.id),
    progress: prog[v.id],
    onInstall: () => void install(v),
    onCancel: () => cancelOne(v.id),
    staged: staged[stagingId(v)],
    onView: () => void viewStaged(v),
    onInstallStaged: () => void installStaged(v),
    onDiscard: () => void discard(v),
    coverMap: coverCache,
  });

  const hasVoices = Boolean(cat?.voices?.length || cat?.thirdparty_voices?.length);
  const gridStyle = { gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` };

  return (
    <div>
      {hasVoices ? <div className="flex flex-wrap items-center gap-3 mb-[18px]">
        <div className="min-w-[200px] flex-1 max-w-[320px]">
          <TextInput
            value={q}
            onChange={(value) => {
              setQ(value);
              setPage(1);
            }}
            placeholder={t("store.searchHint")}
          />
        </div>
        <SegmentControl<Source>
          value={source}
          onChange={(v) => {
            setSource(v);
            setPage(1);
            setSeriesFocus("");
          }}
          options={[
            { id: "all", label: t("s.778fc8f994") },
            { id: "official", label: t("s.ef00eb8f3b") },
            { id: "thirdparty", label: t("s.4500b5dfc7") },
          ]}
        />
        <SegmentControl<Grouping>
          value={grouping}
          onChange={(v) => {
            setGrouping(v);
            setPage(1);
            setSeriesFocus("");
          }}
          options={[
            { id: "time", label: t("s.3d136b7951") },
            { id: "series", label: t("s.1ae90bfb23") },
          ]}
        />
        {grouping === "series" && seriesGroups && seriesGroups.length > 0 ? (
          <Select
            value={seriesFocus}
            width={160}
            onChange={(next) => {
              setSeriesFocus(next);
              if (!next) return;
              const { parent, group } = focusParts(next);
              setExpanded((prev) => new Set(prev).add(parent));
              setSeriesFull((prev) => new Set(prev).add(parent));
              setExpandedGroups((prev) => {
                const n = new Set(prev);
                const node = seriesGroups.find((s) => s.key === parent);
                if (!node) return n;
                if (group) n.add(groupFocusKey(parent, group));
                else {
                  for (const g of node.groups) {
                    if (g.label) n.add(groupFocusKey(parent, g.raw));
                  }
                }
                return n;
              });
            }}
            options={[
              { id: "", label: t("store.allSeries") },
              ...seriesGroups.flatMap((node) => [
                { id: node.key, label: `${node.label} (${node.voices.length})` },
                ...node.groups
                  .filter((g) => g.label)
                  .map((g) => ({
                    id: groupFocusKey(node.key, g.raw),
                    label: `${g.label} (${g.voices.length})`,
                    indent: true,
                  })),
              ]),
            ]}
          />
        ) : null}
        <label className="flex items-center gap-1.5 text-[12.5px] text-[var(--ink-muted)] cursor-pointer select-none">
          {/* design-allow: 勾选框样式与 Toggle 不同。 */}
          <input
            type="checkbox"
            checked={hideInstalled}
            onChange={(e) => {
              setHideInstalled(e.target.checked);
              setPage(1);
            }}
           
          />{t("s.85b3f0512b")}</label>
      </div> : null}

      {source !== "official" && cat?.thirdparty_voices?.some((voice) => !voice.community_version_id) ? (
        <Warn className="mb-3">{t("s.7fe9bcf336")}</Warn>
      ) : null}

      {err || jobs.error ? (
        <div className="mb-3 text-[12.5px] leading-relaxed whitespace-pre-line break-words text-[var(--danger-text)]">
          {err || jobs.error}
        </div>
      ) : null}

      {/* gridRef 挂在网格上，宽度是从它的父级量的 —— 系列视图下网格有好几个，
          但外面这一层永远只有一个，量它才稳。 */}
      <div ref={gridRef}>
        <CatalogTransition scope={JSON.stringify([source, grouping, seriesFocus, q, hideInstalled])}
          page={pageClamped} dir={catalogDirection || 1}>
          {grouping === "series" && seriesGroups ? (
            seriesGroups.length === 0 ? (
              <Empty loading={loading} />
            ) : (
              (focusParts(seriesFocus).parent
                ? seriesGroups.filter((s) => s.key === focusParts(seriesFocus).parent)
                : seriesGroups
              ).map((node) => {
                const { group: focusGroup } = focusParts(seriesFocus);
                const openS = seriesFocus ? true : expanded.has(node.key);
                const nested = node.groups.some((g) => g.label);
                // 下拉选中父类：整类平铺，不再先点一个同名子类。
                const parentAll = !!seriesFocus && !focusGroup;
                const groups = focusGroup
                  ? node.groups.filter((g) => g.raw === focusGroup)
                  : node.groups;
                return (
                  <div key={node.key} className="mb-3">
                    {seriesFocus ? null : (
                      <button
                        type="button"
                        className="w-full text-left border-0 bg-[var(--group)] rounded-[var(--rs)] px-3 py-2.5 cursor-pointer flex justify-between items-center"
                        onClick={() =>
                          setExpanded((prev) => {
                            const n = new Set(prev);
                            if (n.has(node.key)) n.delete(node.key);
                            else n.add(node.key);
                            return n;
                          })
                        }
                      >
                          <span className="font-semibold text-[13px]">{node.label}</span>
                        <span className="text-[12.5px] text-[var(--meta)]">
                          {t("s.c8542337dc", {
                            v0: node.voices.length,
                            v1: openS ? t("s.5d5815647c") : t("s.b0e24833f7"),
                          })}
                        </span>
                      </button>
                    )}
                    {openS ? (
                      nested && !parentAll ? (
                        groups.map((g) => {
                          const gk = groupFocusKey(node.key, g.raw);
                          const openG = !!focusGroup || expandedGroups.has(gk);
                          return (
                            <div key={gk} className="pl-3 mt-1.5">
                              {focusGroup ? null : (
                                <button
                                  type="button"
                                  className="w-full text-left border-0 bg-[var(--group)] rounded-[var(--rs)] px-3 py-2 cursor-pointer flex justify-between items-center"
                                  onClick={() =>
                                    setExpandedGroups((prev) => {
                                      const n = new Set(prev);
                                      if (n.has(gk)) n.delete(gk);
                                      else n.add(gk);
                                      return n;
                                    })
                                  }
                                >
                                  <span className="text-[13px]">{g.label}</span>
                                  <span className="text-[12.5px] text-[var(--meta)]">
                                    {t("s.c8542337dc", {
                                      v0: g.voices.length,
                                      v1: openG
                                        ? t("s.5d5815647c")
                                        : t("s.b0e24833f7"),
                                    })}
                                  </span>
                                </button>
                              )}
                              {openG ? (
                                <SeriesPageGrid
                                  seriesKey={gk}
                                  voices={g.voices}
                                  cols={cols}
                                  perPage={perPage}
                                  forcedFull={!!focusGroup}
                                  seriesFull={seriesFull}
                                  setSeriesFull={setSeriesFull}
                                  seriesPage={seriesPage}
                                  setSeriesPage={setSeriesPage}
                                  cardProps={cardProps}
                                  gridStyle={gridStyle}
                                />
                              ) : null}
                            </div>
                          );
                        })
                      ) : (
                        <SeriesPageGrid
                          seriesKey={node.key}
                          voices={node.voices}
                          cols={cols}
                          perPage={perPage}
                          forcedFull={!!seriesFocus}
                          seriesFull={seriesFull}
                          setSeriesFull={setSeriesFull}
                          seriesPage={seriesPage}
                          setSeriesPage={setSeriesPage}
                          cardProps={cardProps}
                          gridStyle={gridStyle}
                        />
                      )
                    ) : null}
                  </div>
                );
              })
            )
          ) : pageItems.length === 0 ? (
            <Empty loading={loading} />
          ) : (
            <div className="grid gap-x-4 gap-y-[22px]" style={gridStyle}>
              {pageItems.map((v) => (
                <VoiceCard key={v.id} {...cardProps(v)} />
              ))}
            </div>
          )}
        </CatalogTransition>
      </div>

      {grouping !== "series" ? (
        <Pager className="pt-5" page={pageClamped} pages={totalPages} onChange={setPage} />
      ) : null}
    </div>
  );
}

function Empty({ loading }: { loading: boolean }) {
  return (
    <div className="text-[13px] text-[var(--meta)] py-10 text-center">
      {loading ? t("s.f950213ab7") : t("s.83bc4b2a5f")}
    </div>
  );
}

type CardPropsFn = (v: StoreVoice) => {
  v: StoreVoice;
  busy: boolean;
  queued?: boolean;
  progress?: VoiceProg;
  onInstall: () => void;
  onCancel: () => void;
  staged?: StagedVoice;
  onView: () => void;
  onInstallStaged: () => void;
  onDiscard: () => void;
  coverMap?: Record<string, string>;
};

function seriesSlice(voices: StoreVoice[], cols: number, perPage: number, paged: boolean, page = 1) {
  const preview = cols * SERIES_PREVIEW_ROWS;
  const totalS = Math.max(1, Math.ceil(voices.length / perPage));
  const curS = Math.min(page, totalS);
  const shown = paged ? voices.slice((curS - 1) * perPage, curS * perPage) : voices.slice(0, preview);
  return { preview, totalS, curS, shown };
}

/** 一组卡片：先铺一行，再「查看全部」或分页。 */
function SeriesPageGrid({
  seriesKey,
  voices,
  cols,
  perPage,
  forcedFull,
  seriesFull,
  setSeriesFull,
  seriesPage,
  setSeriesPage,
  cardProps,
  gridStyle,
}: {
  seriesKey: string;
  voices: StoreVoice[];
  cols: number;
  perPage: number;
  forcedFull: boolean;
  seriesFull: Set<string>;
  setSeriesFull: Dispatch<SetStateAction<Set<string>>>;
  seriesPage: Record<string, number>;
  setSeriesPage: Dispatch<SetStateAction<Record<string, number>>>;
  cardProps: CardPropsFn;
  gridStyle: { gridTemplateColumns: string };
}) {
  const paged = forcedFull || seriesFull.has(seriesKey);
  const { preview, totalS, curS, shown } = seriesSlice(voices, cols, perPage, paged, seriesPage[seriesKey]);
  return (
    <>
      <CatalogTransition scope={seriesKey} page={curS}>
        <div className="grid gap-x-4 gap-y-[22px] mt-4" style={gridStyle}>
          {shown.map((v) => (
            <VoiceCard key={v.id} {...cardProps(v)} />
          ))}
        </div>
      </CatalogTransition>
      {voices.length > preview && !paged ? (
        <div className="mt-3 flex justify-center">
          <Btn
            onClick={() =>
              setSeriesFull((prev) => new Set(prev).add(seriesKey))
            }
          >
            {t("s.9d38fc19bb", { v0: voices.length })}
          </Btn>
        </div>
      ) : null}
      {paged ? (
        <Pager
          className="pt-5"
          page={curS}
          pages={totalS}
          onChange={(p) => setSeriesPage((prev) => ({ ...prev, [seriesKey]: p }))}
        />
      ) : null}
    </>
  );
}

/**
 * 一张音色卡。形状和模型页的卡一致：4:3 封面 + 名字 + 一行元信息。
 *
 * 按钮放在卡里而不是悬浮出现：悬浮按钮在触屏和「先扫一眼有哪些能下」的场景
 * 里都是负担 —— 得先把鼠标移上去才知道这张卡能不能点。
 */
function VoiceCard({
  v,
  busy,
  queued = false,
  progress,
  onInstall,
  onCancel,
  staged,
  onView,
  onInstallStaged,
  onDiscard,
  coverMap,
}: {
  v: StoreVoice;
  busy: boolean;
  /** Waiting behind the two running downloads. */
  queued?: boolean;
  progress?: VoiceProg;
  onInstall: () => void;
  onCancel: () => void;
  /** 已下载待确认的文件信息；没有就是还没下。 */
  staged?: StagedVoice;
  onView: () => void;
  onInstallStaged: () => void;
  onDiscard: () => void;
  /** 封面本地化缓存（url → 本地路径），见 lib/cover.ts。 */
  coverMap?: Record<string, string>;
}) {
  const [now, setNow] = useState(() => Date.now());
  const lastMove = useRef({ at: 0, done: -1 });
  const progressDoneRef = useRef(progress?.done ?? 0);
  progressDoneRef.current = progress?.done ?? 0;
  const loc = getTLocale();
  const title = displayVoiceName(v, loc);
  const remote = (v.cover_url || v.cover || "").trim();
  const local = (v.cover_local || "").trim();
  const legacy = (v.cover || "").trim();
  const sources = [
    resolveCover(remote, coverMap ?? {}),
    local ? coverSrc(local) : "",
    legacy !== remote ? resolveCover(legacy, {}) : "",
    resolveCover(remote, {}),
  ];
  useEffect(() => {
    if (!busy) return;
    lastMove.current = { at: Date.now(), done: progressDoneRef.current };
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(tick);
  }, [busy]);
  useEffect(() => {
    const d = progress?.done ?? 0;
    if (d !== lastMove.current.done) {
      lastMove.current = { at: Date.now(), done: d };
      setNow(Date.now());
    }
  }, [progress?.done]);
  const author = displayVoiceAuthor(v, loc);
  const parentLabel = voiceParentSeries(v, loc);
  const childLabel = voiceChildGroup(v, loc);
  const meta =
    joinClauses([parentLabel, childLabel, v.size_label]);
  // 发布日期当版本号（v26.07.31）：同一角色常有多个版本在架，下载前先看清
  // 自己装的是哪一版。没有日期就不画，不留一个空角标。
  const ver = voiceVersionLabel(v.date);
  // 第三方音色下下来是别人的东西：作者是谁、从哪个仓库发的，得在**下载之前**
  // 就能点开看，不能等装完了才在模型页的「⋯」里找得到。清单里两个地址常常
  // 只有一个，有哪条给哪条。作者可以有多位 —— 多位时点了先问一声开哪个。
  const [authorPick, setAuthorPick] = useState<VoiceAuthor[] | null>(null);
  const authors = voiceAuthorList(v).filter((a) =>
    /^https?:\/\//i.test(a.url || ""),
  );
  const sourceUrl = (v.source_url || "").trim();
  const license = v.license?.id || v.license?.text;
  const licenseUrl = v.license?.url;
  const menu = useMenu();
  const links: MenuItem[] = [];
  if (authors.length) {
    links.push({
      id: "author", label: t("s.voiceLinkAuthor"),
      onSelect: () => {
        if (authors.length === 1) void openExternal(authors[0].url || "");
        else setAuthorPick(authors);
      },
    });
  }
  if (/^https?:\/\//i.test(sourceUrl)) {
    links.push({ id: "source", label: t("s.voiceLinkSource"), onSelect: () => void openExternal(sourceUrl) });
  }
  if (licenseUrl && /^https:\/\//i.test(licenseUrl)) {
    links.push({ id: "license", label: t("community.license"), onSelect: () => void openExternal(licenseUrl) });
  }

  return (
    <div id={v.id ? `store-voice-${v.id}` : undefined}>
      <CatalogCover
        sources={sources}
        placeholder={title || v.id || ""}
        seed={v.id || title}
        release={ver}
        detail={v.community_version_id ? t("nav.plaza") : undefined}
        progress={busy && !staged ? progress?.percent ?? 0 : undefined}
        connecting={busy && !staged && (progress?.done ?? 0) <= 0}
      />
      <div className="text-[15px] font-semibold mt-2.5 truncate" title={title}>
        {title}
      </div>
      <div
        className="text-xs text-[var(--meta)] mt-0.5 truncate"
        title={author || undefined}
      >
        {author ? t("s.7feea73fa3", { v0: author }) : t("s.2af26573b0")}
      </div>
      {meta ? (
        <div className="text-[11.5px] text-[var(--meta)] truncate" title={meta}>
          {meta}
        </div>
      ) : null}
      {license && <div className="text-[11.5px] text-[var(--meta)] truncate" title={license}>{license}</div>}
      <Leave>{authorPick ? (
        <AuthorsDialog authors={authorPick} onClose={() => setAuthorPick(null)} />
      ) : null}</Leave>
      <div className="mt-1.5 flex items-center gap-1.5 flex-wrap">
        {v.installed && !v.update_available ? (
          <Btn on disabled>
            {t("s.eb88ff57c9")}
          </Btn>
        ) : staged ? (
          <>
            <Btn
              primary
              disabled={busy}
              className="confirm-install"
              onClick={onInstallStaged}
            >
              {busy ? t("s.b2c6913616") : t("store.confirmInstall")}
            </Btn>
            <Btn onClick={onView}>{t("s.f7acefd2d4")}</Btn>
            <Btn onClick={onDiscard}>{t("s.3755f56f2f")}</Btn>
          </>
        ) : busy ? (
          <>
            <Btn primary disabled>
              {t("s.65188d08a2")}
            </Btn>
            <Btn onClick={onCancel}>{t("s.4d0b4688c7")}</Btn>
            <span className="text-[11.5px] text-[var(--meta)] tabular-nums min-w-0 truncate">
              {storePercentLabel(progress, now, lastMove.current.at)}
            </span>
          </>
        ) : queued ? (
          <>
            <Btn primary disabled>
              {t("s.531e3e438f")}
            </Btn>
            <Btn onClick={onCancel}>{t("s.4d0b4688c7")}</Btn>
          </>
        ) : (
          <Btn primary onClick={onInstall}>
            {v.update_available ? t("community.update") : t("s.2b9d013177")}
          </Btn>
        )}
        {links.length ? (
          <Btn className="shrink-0 px-2.5" ariaLabel={t("models.more")} onClick={event => menu.open(event.currentTarget, links)}>
            ⋯
          </Btn>
        ) : null}
      </div>
      {menu.node}
    </div>
  );
}
