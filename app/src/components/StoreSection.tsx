import { listen } from "@tauri-apps/api/event";
import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import {
  cancelStoreDownload,
  colsForWidth,
  fetchStoreCatalog,
  installStoreVoice,
  installStagedVoice,
  stagedVoices,
  revealStagedVoice,
  discardStagedVoice,
  coverSrc,
  type StagedVoice,
  type StoreCatalog,
  type StoreVoice,
} from "../lib/voices";
import { Btn } from "./ui";
import { SegmentControl } from "./SegmentControl";
import { resolveCover, useCoverCache } from "../lib/cover";
import { t, getTLocale } from "../i18n/t";
import {
  compareVoiceGroups,
  displayVoiceAuthor,
  displayVoiceName,
  displayVoiceOrigin,
  displayVoiceTag,
  isCharacterAsGroup,
  isCharacterAsSeries,
  voiceChildGroup,
  voiceGroupRaw,
  voiceParentSeries,
  voiceSearchText,
} from "../lib/voiceDisplay";
import { askConfirm } from "../lib/webDialog";
import { openExternal } from "../lib/plaza";

/** Parent + child focus key. Tab never appears in series / group labels. */
const FOCUS_SEP = "\t";

type VoiceProg = {
  percent: number;
  done: number;
  total: number;
  message: string;
  phase: string;
};

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

function clearVoiceProg(
  setProg: Dispatch<SetStateAction<Record<string, VoiceProg>>>,
  id: string,
) {
  setProg((prev) => {
    if (!(id in prev)) return prev;
    const next = { ...prev };
    delete next[id];
    return next;
  });
}

type SeriesNode = {
  key: string;
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

export function StoreSection({ reloadToken, onInstalled }: Props) {
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
  // Two concurrent installs plus a queue — same as the Tk shell. Each download
  // now has its own cancel flag in Rust, so one cancel no longer kills the rest.
  const MAX_CONCURRENT = 2;
  const [running, setRunning] = useState<string[]>([]);
  const [queued, setQueued] = useState<string[]>([]);
  /** Per-voice download progress. The old single string at the top of the
   *  section was overwritten when two downloads ran at once. */
  const [prog, setProg] = useState<Record<string, VoiceProg>>({});
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
  // 封面本地化：全部远程封面一次性交给 Rust 下载缓存，卡片走本地，
  // 不再每次打开商店全量重拉（国内访问 CNB 间歇失败曾导致随机缺图）。
  const coverCache = useCoverCache(
    useMemo(() => {
      if (!cat) return [];
      return [...(cat.voices ?? []), ...(cat.thirdparty_voices ?? [])]
        .map((v) => (v.cover_url || v.cover || "").trim())
        .filter(Boolean);
    }, [cat]),
  );

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

  // 首次挂载和每次「刷新」都走这里。reloadToken 初值也算一次，所以不用再单独
  // 写一个只跑一次的 effect。
  useEffect(() => {
    void refresh(true);
    void loadStaged();
  }, [reloadToken, refresh, loadStaged]);

  useEffect(() => {
    if (!scrollToId || !staged[scrollToId]) return;
    const el = document.getElementById(`store-voice-${scrollToId}`);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
    const btn = el?.querySelector<HTMLElement>(".confirm-install");
    btn?.focus();
    setScrollToId("");
  }, [scrollToId, staged]);

  useEffect(() => {
    // 组件卸载早于 listen 兑现时，直接丢掉 unlisten 句柄会把注册泄漏到进程结束。
    let disposed = false;
    let un: (() => void) | undefined;
    void listen<{
      voice_id?: string;
      message?: string;
      percent?: number;
      phase?: string;
      done?: number;
      total?: number;
    }>("store-progress", (ev) => {
      const p = ev.payload;
      const id = (p.voice_id || "").trim();
      if (!id) return;
      const done = Number(p.done);
      const total = Number(p.total);
      const fromBytes =
        Number.isFinite(done) && Number.isFinite(total) && total > 0
          ? (done / total) * 100
          : undefined;
      const pctRaw =
        p.percent != null && !Number.isNaN(Number(p.percent))
          ? Number(p.percent)
          : fromBytes;
      setProg((prev) => ({
        ...prev,
        [id]: {
          percent: pctRaw != null ? Math.max(0, Math.min(100, pctRaw)) : (prev[id]?.percent ?? 0),
          done: Number.isFinite(done) ? done : (prev[id]?.done ?? 0),
          total: Number.isFinite(total) && total > 0 ? total : (prev[id]?.total ?? 0),
          message: p.message || prev[id]?.message || "",
          phase: p.phase || prev[id]?.phase || "",
        },
      }));
    }).then((fn) => {
      if (disposed) fn();
      else un = fn;
    });
    return () => {
      disposed = true;
      un?.();
    };
  }, []);

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
    if (hideInstalled) base = base.filter((v) => !v.installed);
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
    // 父系列 → 子类。只有 BanG Dream 按乐队拆；蔚蓝档案和其他系列整类平铺。
    // 没填 series 的落进「其他」；旧清单把乐队写成顶层 series，仍收到 BanG Dream 下。
    const other = t("s.1a26edf94a");
    const loc = getTLocale();
    const map = new Map<string, Map<string, StoreVoice[]>>();
    for (const v of list) {
      const parent =
        voiceParentSeries(v, loc).trim() ||
        (v.series || "").trim() ||
        other;
      const raw = voiceGroupRaw(v);
      if (!map.has(parent)) map.set(parent, new Map());
      const gm = map.get(parent)!;
      if (!gm.has(raw)) gm.set(raw, []);
      gm.get(raw)!.push(v);
    }
    const nodes: SeriesNode[] = [...map.entries()]
      .sort((a, b) => {
        if (a[0] === other) return 1;
        if (b[0] === other) return -1;
        return a[0].localeCompare(b[0], "zh");
      })
      .map(([key, gm]) => {
        const named = [...gm.keys()].some((r) => r);
        const groups = [...gm.entries()]
          .sort((a, b) => compareVoiceGroups(a[0], b[0], other))
          .map(([raw, voices]) => {
            let label = named
              ? voiceChildGroup(voices[0], loc) || (raw ? raw : other)
              : "";
            // 子类名就是角色名时，不要再套一层「分类」。
            if (label && label !== other && isCharacterAsGroup(label, voices, loc)) {
              label = "";
            }
            return { raw, label, voices };
          });
        return {
          key,
          voices: groups.flatMap((g) => g.voices),
          groups,
        };
      });

    // 系列名等于唯一角色名（如 ATRI / ATRI）时并进「其他」，
    // 否则「按分类查看」会把一个角色画成一个分类。
    const folded: StoreVoice[] = [];
    const kept: SeriesNode[] = [];
    for (const n of nodes) {
      if (n.key !== other && isCharacterAsSeries(n.key, n.voices, loc)) {
        folded.push(...n.voices);
      } else {
        kept.push(n);
      }
    }
    if (folded.length) {
      let extra = kept.find((n) => n.key === other);
      if (!extra) {
        extra = { key: other, voices: [], groups: [] };
        kept.push(extra);
      }
      extra.voices = extra.voices.concat(folded);
      const rawKey = "";
      const hit = extra.groups.find((g) => g.raw === rawKey);
      if (hit) hit.voices = hit.voices.concat(folded);
      else extra.groups.push({ raw: rawKey, label: "", voices: folded });
    }
    return kept;
  }, [grouping, list]);

  const perPage = cols * PAGE_ROWS;
  const totalPages = Math.max(1, Math.ceil(list.length / perPage));
  const pageClamped = Math.min(page, totalPages);
  const pageItems =
    grouping === "series"
      ? []
      : list.slice((pageClamped - 1) * perPage, pageClamped * perPage);

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
    if (group && !node.groups.some((g) => g.label === group)) {
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
            .map((g) => groupFocusKey(s.key, g.label)),
        ),
      ),
    );
  }, [q, seriesGroups]);

  const startOne = async (v: StoreVoice) => {
    setRunning((r) => [...r, v.id]);
    setErr("");
    const label = displayVoiceName(v);
    try {
      // 装进本地库的显示名跟当前界面语言一致（仍保留清单里的多语字段作缓存）
      await installStoreVoice({ ...v, name: label });
      // 第三方到这里只是「下完了」，还没装。刷新暂存表让按钮换成
      // 「查看 / 确认安装」；官方源才是真的装好了。
      await loadStaged();
      onInstalled?.();
      await refresh(false);
      if (v.official === false) setScrollToId(v.id);
    } catch (e) {
      setErr(`${label || v.id}：${String(e)}`);
    } finally {
      setRunning((r) => r.filter((x) => x !== v.id));
      clearVoiceProg(setProg, v.id);
      // Promote the next queued item, if any.
      setQueued((qq) => {
        const [next, ...rest] = qq;
        if (next) {
          const nv = list.find((x) => x.id === next);
          if (nv) void startOne(nv);
        }
        return rest;
      });
    }
  };

  const installStaged = async (v: StoreVoice) => {
    setRunning((r) => [...r, v.id]);
    setErr("");
    const label = displayVoiceName(v);
    try {
      await installStagedVoice({ ...v, name: label });
      await loadStaged();
      onInstalled?.();
      await refresh(false);
    } catch (e) {
      setErr(`${label || v.id}：${String(e)}`);
    } finally {
      setRunning((r) => r.filter((x) => x !== v.id));
      clearVoiceProg(setProg, v.id);
    }
  };

  const cancelOne = (id: string) => {
    if (queued.includes(id)) {
      setQueued((qq) => qq.filter((x) => x !== id));
      return;
    }
    void cancelStoreDownload(id);
  };

  const viewStaged = async (v: StoreVoice) => {
    try {
      await revealStagedVoice(v.id);
    } catch (e) {
      setErr(String(e));
    }
  };

  const discard = async (v: StoreVoice) => {
    const s = staged[v.id];
    if (
      !(await askConfirm(
        t("s.de94f39aff", { v0: s?.file || v.name }),
      ))
    )
      return;
    try {
      await discardStagedVoice(v.id);
      await loadStaged();
    } catch (e) {
      setErr(String(e));
    }
  };

  const install = async (v: StoreVoice) => {
    if (v.installed || running.includes(v.id) || queued.includes(v.id)) return;
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
    if (running.length >= MAX_CONCURRENT) {
      setQueued((qq) => [...qq, v.id]);
      return;
    }
    void startOne(v);
  };

  const cardProps = (v: StoreVoice) => ({
    v,
    busy: running.includes(v.id),
    queued: queued.includes(v.id),
    progress: prog[v.id],
    onInstall: () => void install(v),
    onCancel: () => cancelOne(v.id),
    staged: staged[v.id],
    onView: () => void viewStaged(v),
    onInstallStaged: () => void installStaged(v),
    onDiscard: () => void discard(v),
    coverMap: coverCache,
  });

  const gridStyle = { gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` };

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 mb-[18px]">
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
          placeholder={t("store.searchHint")}
          className="min-w-[200px] flex-1 max-w-[320px] px-[13px] py-[7px] rounded-[var(--rs)] text-[13px] bg-transparent text-[var(--ink)] shadow-[inset_0_0_0_1px_var(--line)] outline-none focus:shadow-[inset_0_0_0_1px_var(--accent)]"
        />
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
          <select
            value={seriesFocus}
            onChange={(e) => {
              const next = e.target.value;
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
                    if (g.label) n.add(groupFocusKey(parent, g.label));
                  }
                }
                return n;
              });
            }}
            className="min-w-[160px] px-[13px] py-[7px] rounded-[var(--rs)] text-[13px] bg-transparent text-[var(--ink)] shadow-[inset_0_0_0_1px_var(--line)] outline-none focus:shadow-[inset_0_0_0_1px_var(--accent)]"
          >
            <option value="">{t("store.allSeries")}</option>
            {seriesGroups.map((node) => {
              const nested = node.groups.filter((g) => g.label);
              return (
                <Fragment key={node.key}>
                  <option value={node.key}>
                    {node.key} ({node.voices.length})
                  </option>
                  {nested.map((g) => (
                    <option
                      key={groupFocusKey(node.key, g.label)}
                      value={groupFocusKey(node.key, g.label)}
                    >
                      {`\u00A0\u00A0${g.label} (${g.voices.length})`}
                    </option>
                  ))}
                </Fragment>
              );
            })}
          </select>
        ) : null}
        <label className="flex items-center gap-1.5 text-[12.5px] text-[var(--ink-muted)] cursor-pointer select-none">
          <input
            type="checkbox"
            checked={hideInstalled}
            onChange={(e) => {
              setHideInstalled(e.target.checked);
              setPage(1);
            }}
            className="accent-[var(--accent)]"
          />{t("s.85b3f0512b")}</label>
      </div>

      {source !== "official" ? (
        <div className="mb-3 text-[11.5px] leading-snug text-[var(--meta)] bg-[color-mix(in_srgb,var(--notify)_12%,transparent)] rounded-[var(--rs)] px-3 py-2">{t("s.7fe9bcf336")}</div>
      ) : null}

      {err ? (
        <div className="mb-3 text-[12px] leading-relaxed whitespace-pre-line break-words text-[color-mix(in_srgb,#c44_90%,var(--ink))]">
          {err}
        </div>
      ) : null}

      {/* gridRef 挂在网格上，宽度是从它的父级量的 —— 系列视图下网格有好几个，
          但外面这一层永远只有一个，量它才稳。 */}
      <div ref={gridRef}>
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
                ? node.groups.filter((g) => g.label === focusGroup)
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
                      <span className="font-semibold text-[14px]">{node.key}</span>
                      <span className="text-[12px] text-[var(--meta)]">
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
                        const gk = groupFocusKey(node.key, g.label);
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
                                <span className="text-[12px] text-[var(--meta)]">
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
      </div>

      {grouping !== "series" && totalPages > 1 ? (
        <div className="flex items-center justify-center gap-3 pt-5 text-[12.5px] text-[var(--meta)]">
          <Btn
            disabled={pageClamped <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >{t("s.b41561d807")}</Btn>
          <span className="tabular-nums">
            {t("s.40a021ed44", {
              v0: pageClamped,
              v1: totalPages,
              v2: list.length,
            })}
          </span>
          <Btn
            disabled={pageClamped >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >{t("s.67a246a344")}</Btn>
        </div>
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
  const preview = cols * SERIES_PREVIEW_ROWS;
  const paged = forcedFull || seriesFull.has(seriesKey);
  const totalS = Math.max(1, Math.ceil(voices.length / perPage));
  const curS = Math.min(seriesPage[seriesKey] || 1, totalS);
  const shown = paged
    ? voices.slice((curS - 1) * perPage, curS * perPage)
    : voices.slice(0, preview);
  return (
    <>
      <div className="grid gap-x-4 gap-y-[22px] mt-4" style={gridStyle}>
        {shown.map((v) => (
          <VoiceCard key={v.id} {...cardProps(v)} />
        ))}
      </div>
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
      {paged && totalS > 1 ? (
        <div className="flex items-center justify-center gap-3 pt-5 text-[12.5px] text-[var(--meta)]">
          <Btn
            disabled={curS <= 1}
            onClick={() =>
              setSeriesPage((prev) => ({
                ...prev,
                [seriesKey]: Math.max(1, curS - 1),
              }))
            }
          >
            {t("s.b41561d807")}
          </Btn>
          <span className="tabular-nums">
            {t("s.40a021ed44", {
              v0: curS,
              v1: totalS,
              v2: voices.length,
            })}
          </span>
          <Btn
            disabled={curS >= totalS}
            onClick={() =>
              setSeriesPage((prev) => ({
                ...prev,
                [seriesKey]: Math.min(totalS, curS + 1),
              }))
            }
          >
            {t("s.67a246a344")}
          </Btn>
        </div>
      ) : null}
    </>
  );
}

/** Thin fill on the cover — stays on the card, no banner jumping around. */
function CardProgressBar({
  percent,
  connecting,
}: {
  percent: number;
  connecting?: boolean;
}) {
  const pct = Math.max(0, Math.min(100, percent));
  const barWidth = connecting ? 33 : pct > 0 && pct < 0.5 ? Math.max(pct, 0.5) : pct;
  const reduce =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  return (
    <div
      className="absolute left-0 right-0 bottom-0 h-[3px] bg-[color-mix(in_srgb,var(--ink)_16%,transparent)]"
      aria-hidden
    >
      <div
        className={`h-full bg-[var(--accent)]${connecting && !reduce ? " animate-pulse" : ""}`}
        style={{
          width: `${barWidth}%`,
          transition: reduce || connecting ? undefined : "width 160ms var(--ease)",
        }}
      />
    </div>
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
  const [imgFailed, setImgFailed] = useState(false);
  const [useLocalCover, setUseLocalCover] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const lastMove = useRef({ at: 0, done: -1 });
  const loc = getTLocale();
  const title = displayVoiceName(v, loc);
  // Catalog normalizes to cover_url (https://cnb.cool/…/ch-banner/…).
  // Older caches may only have a relative cover path — skip those (no convert).
  // 本地化后走本地缓存（一次成功永久可用），失败回退远程直连。
  const coverRemote = (v.cover_url || "").trim();
  const coverRel = (v.cover || "").trim();
  const coverAbs = (v.cover_local || "").trim();
  const coverHttp = resolveCover(coverRemote || coverRel, coverMap ?? {});
  const coverLocal =
    (coverAbs ? coverSrc(coverAbs) : "") ||
    (coverRel && coverRel !== coverRemote ? resolveCover(coverRel, {}) : "");
  const shownCover = useLocalCover && coverLocal ? coverLocal : coverHttp || coverLocal;
  const showImg = Boolean(shownCover) && !imgFailed;
  // src 变化（如重试成功后换成本地缓存路径）时解除失败占位，
  // img 换 src 会自动重新加载 —— 不被 imgFailed 永久卡死。
  useEffect(() => {
    setImgFailed(false);
    setUseLocalCover(false);
  }, [coverHttp]);
  useEffect(() => {
    if (!busy) return;
    lastMove.current = { at: Date.now(), done: progress?.done ?? 0 };
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
    [parentLabel, childLabel, v.size_label].filter(Boolean).join(" · ") ||
    displayVoiceTag(v, loc);
  const coverBadge = author || displayVoiceOrigin(v);
  // 第三方音色下下来是别人的东西：作者是谁、从哪个仓库发的，得在**下载之前**
  // 就能点开看，不能等装完了才在模型页的「⋯」里找得到。清单里两个地址常常
  // 只有一个，有哪条给哪条。
  const links = (
    [
      [(v.author_url || "").trim(), t("s.voiceLinkAuthor")],
      [(v.source_url || "").trim(), t("s.voiceLinkSource")],
    ] as const
  ).filter(([url]) => /^https?:\/\//i.test(url));

  return (
    <div id={v.id ? `store-voice-${v.id}` : undefined}>
      <div className="aspect-[4/3] rounded-[var(--r)] grid place-items-center relative overflow-hidden bg-[color-mix(in_srgb,var(--ink)_7%,transparent)] text-[color-mix(in_srgb,var(--ink)_32%,transparent)] text-2xl">
        {showImg ? (
          <img
            // src 变化时重建 img：避免旧 src（远程直连）的 onError 晚到，
            // 把已经换成本地缓存路径的图错误地置回失败占位。
            key={shownCover}
            src={shownCover}
            alt=""
            loading="lazy"
            referrerPolicy="no-referrer"
            draggable={false}
            onError={() => {
              if (!useLocalCover && coverLocal) setUseLocalCover(true);
              else setImgFailed(true);
            }}
            // contain：竖向立绘在 4:3 卡里用 cover 会裁成胸口/腿；完整展示优先。
            className="absolute inset-0 w-full h-full object-contain"
          />
        ) : (
          <span>{(title || v.id || "?").slice(0, 4)}</span>
        )}
        {v.installed ? (
          <span className="absolute top-2.5 right-2.5 text-[11px] text-[var(--accent)] font-semibold drop-shadow">{t("s.eb88ff57c9")}</span>
        ) : null}
        <span className="absolute left-2.5 bottom-2 text-[11px] text-[var(--ink)] drop-shadow">
          {coverBadge}
        </span>
        {busy && !staged ? (
          <CardProgressBar
            percent={progress?.percent ?? 0}
            connecting={(progress?.done ?? 0) <= 0}
          />
        ) : null}
      </div>
      <div className="text-[14.5px] font-semibold mt-2.5 truncate" title={title}>
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
      {links.length ? (
        <div className="mt-1 flex items-center gap-3 flex-wrap">
          {links.map(([url, label]) => (
            <button
              key={label}
              type="button"
              // 走壳打开，落到用户自己的浏览器；顺带过一遍 http/https 白名单
              // —— 清单里的地址是第三方写的，不能当可信输入。
              onClick={() => void openExternal(url)}
              title={url}
              className="border-0 bg-transparent p-0 text-[11.5px] text-[var(--meta)] cursor-pointer underline decoration-dotted underline-offset-2 hover:text-[var(--ink)]"
            >
              {label}
            </button>
          ))}
        </div>
      ) : null}
      <div className="mt-1.5 flex items-center gap-1.5 flex-wrap">
        {v.installed ? (
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
            {t("s.2b9d013177")}
          </Btn>
        )}
      </div>
    </div>
  );
}
