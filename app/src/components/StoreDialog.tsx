import { listen } from "@tauri-apps/api/event";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  cancelStoreDownload,
  fetchStoreCatalog,
  installStoreVoice,
  type StoreCatalog,
  type StoreVoice,
} from "../lib/voices";
import { Btn, Group, ListItem } from "./ui";
import { SegmentControl } from "./SegmentControl";

type View = "latest" | "official" | "thirdparty" | "series";

type Props = {
  open: boolean;
  onClose: () => void;
  onInstalled: () => void;
};

const PER_PAGE = 8;

export function StoreDialog({ open, onClose, onInstalled }: Props) {
  const [cat, setCat] = useState<StoreCatalog | null>(null);
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState<View>("latest");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  // Two concurrent installs plus a queue — same as the Tk shell. Each download
  // now has its own cancel flag in Rust, so one cancel no longer kills the rest.
  const MAX_CONCURRENT = 2;
  const [running, setRunning] = useState<string[]>([]);
  const [queued, setQueued] = useState<string[]>([]);
  const [progress, setProgress] = useState("");
  const [err, setErr] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [thirdAck, setThirdAck] = useState(false);

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

  useEffect(() => {
    if (!open) return;
    void refresh(true);
    setPage(1);
    setQ("");
    setView("latest");
    setThirdAck(false);
  }, [open, refresh]);

  useEffect(() => {
    if (!open) return;
    // Closing the dialog before `listen` resolves used to drop the unlisten
    // handle, leaking the registration for the life of the app.
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
  }, [open]);

  const list = useMemo(() => {
    // Derived inside the memo on purpose: `cat?.voices || []` allocates a fresh
    // array every render, so listing them as dependencies meant this filter and
    // sort re-ran on every keystroke elsewhere in the dialog.
    const official = cat?.voices || [];
    const third = cat?.thirdparty_voices || [];
    let base: StoreVoice[] = [];
    if (view === "official") base = official;
    else if (view === "thirdparty") base = third;
    else if (view === "series") {
      base = [...official, ...third].filter((v) => (v.series || "").trim());
    } else {
      // latest: merge by date desc
      base = [...official, ...third].sort((a, b) =>
        String(b.date || "").localeCompare(String(a.date || "")),
      );
    }
    const qq = q.trim().toLowerCase();
    if (qq) {
      base = base.filter((v) =>
        [v.name, v.tag, v.author, v.series, v.id]
          .map((x) => String(x || "").toLowerCase())
          .some((s) => s.includes(qq)),
      );
    }
    return base;
  }, [view, cat, q]);

  const seriesGroups = useMemo(() => {
    if (view !== "series") return null;
    const map = new Map<string, StoreVoice[]>();
    for (const v of list) {
      const s = (v.series || "其他").trim() || "其他";
      if (!map.has(s)) map.set(s, []);
      map.get(s)!.push(v);
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0], "zh"));
  }, [view, list]);

  const totalPages = Math.max(1, Math.ceil(list.length / PER_PAGE));
  const pageClamped = Math.min(page, totalPages);
  const pageItems =
    view === "series"
      ? []
      : list.slice((pageClamped - 1) * PER_PAGE, pageClamped * PER_PAGE);

  const startOne = async (v: StoreVoice) => {
    setRunning((r) => [...r, v.id]);
    setErr("");
    try {
      await installStoreVoice(v);
      onInstalled();
      await refresh(false);
    } catch (e) {
      setErr(`${v.name || v.id}：${String(e)}`);
    } finally {
      setRunning((r) => r.filter((x) => x !== v.id));
      // Promote the next queued item, if any.
      setQueued((q) => {
        const [next, ...rest] = q;
        if (next) {
          const nv = list.find((x) => x.id === next);
          if (nv) void startOne(nv);
        }
        return rest;
      });
    }
  };

  const install = async (v: StoreVoice) => {
    if (v.installed || running.includes(v.id) || queued.includes(v.id)) return;
    if (v.official === false && !thirdAck) {
      const ok = window.confirm(
        "第三方音色免责声明\n\n" +
          "该音色来自第三方社区，图灵镜未做安全与质量保证。\n" +
          "模型文件为 pickle 格式，请只从你信任的来源下载。\n\n" +
          "继续安装即表示你了解风险。",
      );
      if (!ok) return;
      setThirdAck(true);
    }
    if (running.length >= MAX_CONCURRENT) {
      setQueued((q) => [...q, v.id]);
      return;
    }
    void startOne(v);
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center p-6 bg-[color-mix(in_srgb,var(--ink)_28%,transparent)]"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[720px] max-h-[min(86vh,760px)] flex flex-col rounded-[var(--r)] bg-[var(--surface)] shadow-[0_20px_60px_rgba(0,0,0,0.22)] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 pt-4 pb-3 flex items-start justify-between gap-3">
          <div>
            <h3 className="text-[18px] font-semibold m-0">社区音色</h3>
            <div className="text-[12px] text-[var(--meta)] mt-1">
              图灵镜源与第三方源 · 双源并发下载（安装逐个进行）
              {cat?.source ? ` · 清单：${cat.source}` : ""}
            </div>
          </div>
          <div className="flex gap-2">
            <Btn onClick={() => void refresh(true)} disabled={loading}>
              {loading ? "刷新中…" : "刷新清单"}
            </Btn>
            <Btn onClick={onClose}>关闭</Btn>
          </div>
        </div>

        <div className="px-5 pb-3 flex flex-wrap items-center gap-3">
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
            placeholder="搜索音色 / 标签 / 作者…"
            className="min-w-[200px] flex-1 px-[13px] py-[7px] rounded-[var(--rs)] text-[13px] bg-transparent text-[var(--ink)] shadow-[inset_0_0_0_1px_var(--line)] outline-none focus:shadow-[inset_0_0_0_1px_var(--accent)]"
          />
          <SegmentControl<View>
            value={view}
            onChange={(v) => {
              setView(v);
              setPage(1);
            }}
            options={[
              { id: "latest", label: "最新合流" },
              { id: "official", label: "图灵镜源" },
              { id: "thirdparty", label: "第三方" },
              { id: "series", label: "系列专区" },
            ]}
          />
        </div>

        {view === "thirdparty" || view === "latest" ? (
          <div className="mx-5 mb-2 text-[11.5px] leading-snug text-[var(--meta)] bg-[color-mix(in_srgb,var(--notify)_12%,transparent)] rounded-[var(--rs)] px-3 py-2">
            第三方音色未经图灵镜审核，请自行判断来源与安全性。模型为
            pickle，仅从信任渠道安装。
          </div>
        ) : null}

        {(err || progress) && (
          <div className="px-5 pb-2 text-[12px]">
            {progress ? (
              <span className="text-[var(--accent)]">{progress}</span>
            ) : null}
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
        )}

        <div className="flex-1 overflow-y-auto px-5 pb-4">
          {view === "series" && seriesGroups ? (
            seriesGroups.length === 0 ? (
              <Empty />
            ) : (
              seriesGroups.map(([series, voices]) => {
                const openS = expanded.has(series);
                return (
                  <div key={series} className="mb-3">
                    <button
                      type="button"
                      className="w-full text-left border-0 bg-[var(--group)] rounded-[var(--rs)] px-3 py-2.5 cursor-pointer flex justify-between items-center"
                      onClick={() => {
                        setExpanded((prev) => {
                          const n = new Set(prev);
                          if (n.has(series)) n.delete(series);
                          else n.add(series);
                          return n;
                        });
                      }}
                    >
                      <span className="font-semibold text-[14px]">{series}</span>
                      <span className="text-[12px] text-[var(--meta)]">
                        {voices.length} 个 · {openS ? "收起" : "展开"}
                      </span>
                    </button>
                    {openS ? (
                      <Group>
                        {voices.map((v) => (
                          <VoiceRow
                            key={v.id}
                            v={v}
                            busy={running.includes(v.id)}
                            queued={queued.includes(v.id)}
                            onInstall={() => void install(v)}
                          />
                        ))}
                      </Group>
                    ) : null}
                  </div>
                );
              })
            )
          ) : pageItems.length === 0 ? (
            <Empty />
          ) : (
            <Group>
              {pageItems.map((v) => (
                <VoiceRow
                  key={v.id}
                  v={v}
                  busy={running.includes(v.id)}
                  queued={queued.includes(v.id)}
                  onInstall={() => void install(v)}
                />
              ))}
            </Group>
          )}

          {view !== "series" && totalPages > 1 ? (
            <div className="flex items-center justify-center gap-3 mt-4 text-[12.5px] text-[var(--meta)]">
              <Btn
                disabled={pageClamped <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                上一页
              </Btn>
              <span>
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
      </div>
    </div>
  );
}

function Empty() {
  return (
    <div className="text-[13px] text-[var(--meta)] py-10 text-center">
      暂无音色条目。检查网络后点「刷新清单」。
    </div>
  );
}

function VoiceRow({
  v,
  busy,
  queued = false,
  onInstall,
}: {
  v: StoreVoice;
  busy: boolean;
  /** Waiting behind the two running downloads. */
  queued?: boolean;
  onInstall: () => void;
}) {
  return (
    <ListItem
      meta={v.origin_label || (v.official === false ? "第三方" : "图灵镜")}
      title={v.name}
      desc={[
        v.tag,
        v.author ? `作者 · ${v.author}` : "",
        v.size_label,
        v.series ? `系列 · ${v.series}` : "",
        v.date,
      ]
        .filter(Boolean)
        .join(" · ")}
      right={
        v.installed ? (
          <Btn on uw disabled>
            已安装
          </Btn>
        ) : (
          <Btn primary uw disabled={busy || queued} onClick={onInstall}>
            {busy ? "安装中…" : queued ? "待下载" : "下载"}
          </Btn>
        )
      }
    />
  );
}
