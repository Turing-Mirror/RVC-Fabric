import { listen } from "@tauri-apps/api/event";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  cancelStoreDownload,
  colsForWidth,
  fetchStoreCatalog,
  installStoreVoice,
  installStagedVoice,
  stagedVoices,
  revealStagedVoice,
  discardStagedVoice,
  type StagedVoice,
  type StoreCatalog,
  type StoreVoice,
} from "../lib/voices";
import { Btn } from "./ui";
import { SegmentControl } from "./SegmentControl";

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
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [cols, setCols] = useState(5);
  // Two concurrent installs plus a queue — same as the Tk shell. Each download
  // now has its own cancel flag in Rust, so one cancel no longer kills the rest.
  const MAX_CONCURRENT = 2;
  const [running, setRunning] = useState<string[]>([]);
  const [queued, setQueued] = useState<string[]>([]);
  const [progress, setProgress] = useState("");
  const [err, setErr] = useState("");
  const [thirdAck, setThirdAck] = useState(false);
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

  // 首次挂载和每次「刷新」都走这里。reloadToken 初值也算一次，所以不用再单独
  // 写一个只跑一次的 effect。
  useEffect(() => {
    void refresh(true);
    void loadStaged();
  }, [reloadToken, refresh, loadStaged]);

  useEffect(() => {
    // 组件卸载早于 listen 兑现时，直接丢掉 unlisten 句柄会把注册泄漏到进程结束。
    let disposed = false;
    let un: (() => void) | undefined;
    void listen<{
      voice_id?: string;
      message?: string;
      percent?: number;
      phase?: string;
    }>("store-progress", (ev) => {
      const p = ev.payload;
      setProgress(
        `${p.message || p.phase || "下载中"} ${
          p.percent != null ? `· ${p.percent}%` : ""
        }`,
      );
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
        [v.name, v.tag, v.author, v.series, v.id]
          .map((x) => String(x || "").toLowerCase())
          .some((s) => s.includes(qq)),
      );
    }
    return base;
  }, [source, hideInstalled, cat, q]);

  const seriesGroups = useMemo(() => {
    if (grouping !== "series") return null;
    // 没填 series 的落进「其他」。上游原本先 filter 掉空 series，所以这里的
    // 「其他」是死代码，而那些音色在系列视图里是直接消失 —— 消失比归错类
    // 难查得多。
    const map = new Map<string, StoreVoice[]>();
    for (const v of list) {
      const s = (v.series || "").trim() || "其他";
      if (!map.has(s)) map.set(s, []);
      map.get(s)!.push(v);
    }
    return [...map.entries()].sort((a, b) => {
      if (a[0] === "其他") return 1;
      if (b[0] === "其他") return -1;
      return a[0].localeCompare(b[0], "zh");
    });
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

  const startOne = async (v: StoreVoice) => {
    setRunning((r) => [...r, v.id]);
    setErr("");
    try {
      await installStoreVoice(v);
      // 第三方到这里只是「下完了」，还没装。刷新暂存表让按钮换成
      // 「查看 / 安装」；官方源才是真的装好了。
      await loadStaged();
      onInstalled?.();
      await refresh(false);
    } catch (e) {
      setErr(`${v.name || v.id}：${String(e)}`);
    } finally {
      setRunning((r) => r.filter((x) => x !== v.id));
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
    try {
      await installStagedVoice(v);
      await loadStaged();
      onInstalled?.();
      await refresh(false);
    } catch (e) {
      setErr(`${v.name || v.id}：${String(e)}`);
    } finally {
      setRunning((r) => r.filter((x) => x !== v.id));
    }
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
      !window.confirm(
        `删除已下载的文件？\n\n${s?.file || v.name}\n\n删除后需要重新安装。`,
      )
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
      const ok = window.confirm(
        "音色使用须知\n\n" +
          "音色模型由声音素材训练而来，相关权利属于原声的权利人。\n" +
          "请勿用于冒充他人、欺诈、造谣或其他侵害他人权益的用途；\n" +
          "商用前请自行确认授权。\n\n" +
          "继续安装即表示你已了解。",
      );
      if (!ok) return;
      setOfficialAck(true);
    }
    if (v.official === false && !thirdAck) {
      const ok = window.confirm(
        "第三方音色免责声明\n\n" +
          "该音色来自第三方社区，图灵镜不做安全与质量保证。\n" +
          "请只从你信任的来源下载。\n\n" +
          "继续安装即表示你了解风险。",
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
    onInstall: () => void install(v),
    staged: staged[v.id],
    onView: () => void viewStaged(v),
    onInstallStaged: () => void installStaged(v),
    onDiscard: () => void discard(v),
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
          placeholder="搜索音色 / 标签 / 作者…"
          className="min-w-[200px] flex-1 max-w-[320px] px-[13px] py-[7px] rounded-[var(--rs)] text-[13px] bg-transparent text-[var(--ink)] shadow-[inset_0_0_0_1px_var(--line)] outline-none focus:shadow-[inset_0_0_0_1px_var(--accent)]"
        />
        <SegmentControl<Source>
          value={source}
          onChange={(v) => {
            setSource(v);
            setPage(1);
          }}
          options={[
            { id: "all", label: "全部" },
            { id: "official", label: "图灵镜源" },
            { id: "thirdparty", label: "第三方" },
          ]}
        />
        <SegmentControl<Grouping>
          value={grouping}
          onChange={(v) => {
            setGrouping(v);
            setPage(1);
          }}
          options={[
            { id: "time", label: "按时间" },
            { id: "series", label: "按系列" },
          ]}
        />
        <label className="flex items-center gap-1.5 text-[12.5px] text-[var(--ink-muted)] cursor-pointer select-none">
          <input
            type="checkbox"
            checked={hideInstalled}
            onChange={(e) => {
              setHideInstalled(e.target.checked);
              setPage(1);
            }}
            className="accent-[var(--accent)]"
          />
          只看未安装
        </label>
      </div>

      {source !== "official" ? (
        <div className="mb-3 text-[11.5px] leading-snug text-[var(--meta)] bg-[color-mix(in_srgb,var(--notify)_12%,transparent)] rounded-[var(--rs)] px-3 py-2">
          第三方音色未经图灵镜审核，请自行判断来源是否可靠，不要安装来路不明的音色。
        </div>
      ) : null}

      {err || progress ? (
        <div className="mb-3 text-[12px]">
          {progress ? <span className="text-[var(--accent)]">{progress}</span> : null}
          {err ? (
            <span className="text-[color-mix(in_srgb,#c44_90%,var(--ink))] block mt-0.5">
              {err}
            </span>
          ) : null}
          {running.length ? (
            <Btn
              className="mt-1"
              onClick={() => {
                void cancelStoreDownload();
                setRunning([]);
                setQueued([]);
                setProgress("已取消");
              }}
            >
              取消下载
            </Btn>
          ) : null}
        </div>
      ) : null}

      {/* gridRef 挂在网格上，宽度是从它的父级量的 —— 系列视图下网格有好几个，
          但外面这一层永远只有一个，量它才稳。 */}
      <div ref={gridRef}>
        {grouping === "series" && seriesGroups ? (
          seriesGroups.length === 0 ? (
            <Empty loading={loading} />
          ) : (
            seriesGroups.map(([series, voices]) => {
              const openS = expanded.has(series);
              const preview = cols * SERIES_PREVIEW_ROWS;
              const shown = seriesFull.has(series)
                ? voices
                : voices.slice(0, preview);
              return (
                <div key={series} className="mb-3">
                  <button
                    type="button"
                    className="w-full text-left border-0 bg-[var(--group)] rounded-[var(--rs)] px-3 py-2.5 cursor-pointer flex justify-between items-center"
                    onClick={() =>
                      setExpanded((prev) => {
                        const n = new Set(prev);
                        if (n.has(series)) n.delete(series);
                        else n.add(series);
                        return n;
                      })
                    }
                  >
                    <span className="font-semibold text-[14px]">{series}</span>
                    <span className="text-[12px] text-[var(--meta)]">
                      {voices.length} 个 · {openS ? "收起" : "展开"}
                    </span>
                  </button>
                  {openS ? (
                    <>
                      <div
                        className="grid gap-x-4 gap-y-[22px] mt-4"
                        style={gridStyle}
                      >
                        {shown.map((v) => (
                          <VoiceCard key={v.id} {...cardProps(v)} />
                        ))}
                      </div>
                      {/* 一个系列可能有八十多个角色（赛马娘、蔚蓝档案）。
                          展开就全渲染会当场卡住，先给一行。 */}
                      {voices.length > preview && !seriesFull.has(series) ? (
                        <div className="mt-3 flex justify-center">
                          <Btn
                            onClick={() =>
                              setSeriesFull((prev) => new Set(prev).add(series))
                            }
                          >
                            查看全部 {voices.length} 条
                          </Btn>
                        </div>
                      ) : null}
                    </>
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
          >
            上一页
          </Btn>
          <span className="tabular-nums">
            第 <b className="text-[var(--ink)]">{pageClamped}</b> /{" "}
            <b className="text-[var(--ink)]">{totalPages}</b> 页 · 共{" "}
            <b className="text-[var(--ink)]">{list.length}</b> 个
          </span>
          <Btn
            disabled={pageClamped >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            下一页
          </Btn>
        </div>
      ) : null}
    </div>
  );
}

function Empty({ loading }: { loading: boolean }) {
  return (
    <div className="text-[13px] text-[var(--meta)] py-10 text-center">
      {loading ? "读取中…" : "暂无音色条目。检查网络后点右上角「刷新」。"}
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
  onInstall,
  staged,
  onView,
  onInstallStaged,
  onDiscard,
}: {
  v: StoreVoice;
  busy: boolean;
  /** Waiting behind the two running downloads. */
  queued?: boolean;
  onInstall: () => void;
  /** 已下载待确认的文件信息；没有就是还没下。 */
  staged?: StagedVoice;
  onView: () => void;
  onInstallStaged: () => void;
  onDiscard: () => void;
}) {
  const [imgFailed, setImgFailed] = useState(false);
  // Catalog normalizes to cover_url (https://cnb.cool/…/ch-banner/…).
  // Older caches may only have a relative cover path — skip those (no convert).
  const coverHttp = (() => {
    const raw = (v.cover_url || v.cover || "").trim();
    return /^https?:\/\//i.test(raw) ? raw : "";
  })();
  const showImg = Boolean(coverHttp) && !imgFailed;
  const meta = [v.tag, v.author ? `作者 : ${v.author}` : "", v.size_label]
    .filter(Boolean)
    .join(" · ");

  return (
    <div>
      <div className="aspect-[4/3] rounded-[var(--r)] grid place-items-center relative overflow-hidden bg-[color-mix(in_srgb,var(--ink)_7%,transparent)] text-[color-mix(in_srgb,var(--ink)_32%,transparent)] text-2xl">
        {showImg ? (
          <img
            src={coverHttp}
            alt=""
            loading="lazy"
            referrerPolicy="no-referrer"
            draggable={false}
            onError={() => setImgFailed(true)}
            className="absolute inset-0 w-full h-full object-cover"
          />
        ) : (
          <span>{(v.name || v.id || "?").slice(0, 4)}</span>
        )}
        {v.installed ? (
          <span className="absolute top-2.5 right-2.5 text-[11px] text-[var(--accent)] font-semibold drop-shadow">
            已安装
          </span>
        ) : null}
        <span className="absolute left-2.5 bottom-2 text-[11px] text-[var(--meta)] drop-shadow">
          {v.origin_label || (v.official === false ? "第三方" : "图灵镜")}
        </span>
      </div>
      <div className="mt-2 text-[13.5px] leading-snug truncate" title={v.name}>
        {v.name}
      </div>
      {meta ? (
        <div className="text-[11.5px] text-[var(--meta)] truncate" title={meta}>
          {meta}
        </div>
      ) : null}
      <div className="mt-1.5 flex items-center gap-1.5 flex-wrap">
        {v.installed ? (
          <Btn on disabled>
            已安装
          </Btn>
        ) : staged ? (
          // 第三方下完不自动装：先给「查看」让用户自己开资源管理器看文件、
          // 要删也在那儿删，确认没问题再点「安装」。
          <>
            <Btn primary disabled={busy} onClick={onInstallStaged}>
              {busy ? "安装中…" : "安装"}
            </Btn>
            <Btn onClick={onView}>查看</Btn>
            <Btn onClick={onDiscard}>删除</Btn>
          </>
        ) : (
          <Btn primary disabled={busy || queued} onClick={onInstall}>
            {busy ? "下载中…" : queued ? "待下载" : "下载"}
          </Btn>
        )}
      </div>
    </div>
  );
}
