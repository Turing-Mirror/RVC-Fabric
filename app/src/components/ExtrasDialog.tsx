import { useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn } from "./ui";
import { SegmentControl } from "./SegmentControl";

export type ExtraGroup = "train" | "separate" | "other";

type Item = {
  key: string;
  label: string;
  dest: string;
  group?: ExtraGroup | string;
  recommended?: boolean;
  order?: number;
  notes?: string;
  size_bytes: number;
  files: string[];
  installed: boolean;
};

type List = {
  available?: boolean;
  items?: Item[];
  busy?: boolean;
};

type Progress = {
  key: string;
  phase: "run" | "done" | "error";
  done?: number;
  total?: number;
  message?: string;
};

/** 打开下载弹窗时预选哪一类；弹窗内仍可切换。 */
export type ExtrasFilter = "all" | ExtraGroup;

/** 单页条数。和广场更新日志一样固定 5，不做无限滚。 */
const PER_PAGE = 5;

type Category = "separate" | "train";

function mb(n: number) {
  if (!n) return "";
  return n >= 1024 * 1024 * 1024
    ? `${(n / 1024 / 1024 / 1024).toFixed(1)} GB`
    : `${Math.round(n / 1024 / 1024)} MB`;
}

function inferGroup(key: string): string {
  if (key.startsWith("pretrained")) return "train";
  if (key.startsWith("pymss") || key.startsWith("uvr")) return "separate";
  return "other";
}

/** 分类已经写在分段控件上，行内标题去掉重复前缀。 */
function shortLabel(it: Item, cat: Category): string {
  let l = it.label || it.key;
  if (cat === "separate") l = l.replace(/^人声分离\s*[·•]\s*/, "");
  if (cat === "train") l = l.replace(/^训练音色\s*[·•]\s*/, "");
  return l;
}

const CATEGORY_BLURB: Record<Category, string> = {
  separate:
    "训练前清理素材优先下「人声提取」。其余按场景按需下载；标「进阶」的体积大，日常一般用不到。",
  train:
    "按采样率下一套底模即可（三选一）。Hubert / RMVPE 已在补全引擎资源时装好，这里不用重复下。",
};

/**
 * 附加资源下载：分离模型、训练底模。
 *
 * 布局对齐广场「社区音色」：顶部分段切换分类（人声分离 / 训练音色，
 * 对应那边的「图灵镜源 / 第三方」），列表分页每页 5 条，不做无限滚动。
 * 弹窗本身加宽，否则用途说明一行字都折成三行。
 */
export function ExtrasDialog({
  open,
  onClose,
  filter = "all",
  title,
}: {
  open: boolean;
  onClose: () => void;
  filter?: ExtrasFilter;
  title?: string;
}) {
  const [list, setList] = useState<List | null>(null);
  const [prog, setProg] = useState<Progress | null>(null);
  const [msg, setMsg] = useState("");
  const [busyKey, setBusyKey] = useState("");
  const [category, setCategory] = useState<Category>(
    filter === "train" ? "train" : "separate",
  );
  const [page, setPage] = useState(0);
  const busyRef = useRef(false);

  const load = async () => {
    setMsg("");
    try {
      setList(await invoke<List>("extra_list"));
    } catch (e) {
      setList({ available: false, items: [] });
      setMsg(String(e));
    }
  };

  useEffect(() => {
    if (!open) return;
    setList(null);
    setPage(0);
    setCategory(filter === "train" ? "train" : "separate");
    void load();
    let disposed = false;
    let un: (() => void) | undefined;
    void listen<Progress>("extra-progress", (ev) => {
      setProg(ev.payload);
      if (ev.payload.phase === "error") setMsg(ev.payload.message || "下载失败");
    }).then((fn) => {
      if (disposed) fn();
      else un = fn;
    });
    return () => {
      disposed = true;
      un?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 开窗一次拉清单
  }, [open, filter]);

  const filtered = useMemo(() => {
    const all = list?.items || [];
    return all.filter((i) => (i.group || inferGroup(i.key)) === category);
  }, [list, category]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PER_PAGE) || 1);
  const pageClamped = Math.min(page, totalPages - 1);
  const pageItems = filtered.slice(
    pageClamped * PER_PAGE,
    pageClamped * PER_PAGE + PER_PAGE,
  );

  if (!open) return null;

  const start = async (key: string) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusyKey(key);
    setMsg("");
    setProg(null);
    try {
      await invoke("extra_download", { key });
      setMsg("下载完成");
      void load();
    } catch (e) {
      setMsg(String(e));
    } finally {
      busyRef.current = false;
      setBusyKey("");
    }
  };

  const pct = prog?.total ? Math.round(((prog.done ?? 0) / prog.total) * 100) : 0;
  const heading = title || "下载模型";

  const emptyHint =
    list?.available === false
      ? "连不上服务器，检查网络后再试。"
      : category === "train"
        ? "暂时没有可下载的训练底模。"
        : "暂时没有可下载的分离模型。";

  return (
    <div
      className="fixed inset-0 z-[80] grid place-items-center p-6 bg-[color-mix(in_srgb,var(--ink)_28%,transparent)]"
      onClick={busyKey ? undefined : onClose}
    >
      <div
        className="flex max-h-[min(88vh,720px)] w-full max-w-[min(920px,96vw)] flex-col rounded-[var(--r)] bg-[var(--surface)] p-6 shadow-[0_20px_60px_rgba(0,0,0,0.22)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex flex-wrap items-start justify-between gap-3 mb-1">
          <h3 className="m-0 text-[17px] font-semibold">{heading}</h3>
          <SegmentControl<Category>
            value={category}
            onChange={(v) => {
              setCategory(v);
              setPage(0);
            }}
            options={[
              { id: "separate", label: "人声分离" },
              { id: "train", label: "训练音色" },
            ]}
          />
        </div>
        <p className="m-0 mb-3 text-[12.5px] text-[var(--ink-muted)] leading-snug">
          {CATEGORY_BLURB[category]}
        </p>

        {list === null ? (
          <div className="min-h-[280px] flex items-center">
            <p className="m-0 py-4 text-[13px] text-[var(--meta)]">正在读取清单…</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="min-h-[280px] flex items-center">
            <p className="m-0 py-4 text-[13px] text-[var(--ink-muted)]">{emptyHint}</p>
          </div>
        ) : (
          <div className="min-h-[280px] flex flex-col border-t border-[var(--hairline)]">
            {/* 固定 5 行区域，页脚分页，整窗不滚列表。 */}
            <div className="flex-1">
              {pageItems.map((it) => (
                <ItemRow
                  key={it.key}
                  it={it}
                  category={category}
                  busyKey={busyKey}
                  onStart={start}
                />
              ))}
            </div>

            {totalPages > 1 ? (
              <div className="flex items-center justify-center gap-3 pt-4 pb-1">
                <Btn
                  disabled={pageClamped <= 0 || !!busyKey}
                  onClick={() => setPage(pageClamped - 1)}
                >
                  上一页
                </Btn>
                <span className="text-[12.5px] text-[var(--meta)] tabular-nums min-w-[72px] text-center">
                  {pageClamped + 1} / {totalPages}
                </span>
                <Btn
                  disabled={pageClamped >= totalPages - 1 || !!busyKey}
                  onClick={() => setPage(pageClamped + 1)}
                >
                  下一页
                </Btn>
              </div>
            ) : (
              <p className="m-0 pt-3 text-[12px] text-[var(--meta)] text-center tabular-nums">
                共 {filtered.length} 项
              </p>
            )}
          </div>
        )}

        {busyKey && prog ? (
          <div className="mt-4">
            <div className="h-1 w-full overflow-hidden rounded bg-[color-mix(in_srgb,var(--ink)_10%,transparent)]">
              <div
                className="h-full bg-[var(--accent)] transition-[width] duration-200"
                style={{ width: `${pct}%` }}
              />
            </div>
            <p className="m-0 mt-2 text-[12px] text-[var(--meta)]">
              {prog.message} {pct}%
            </p>
          </div>
        ) : null}

        {msg ? (
          <p className="m-0 mt-3 text-[12.5px] text-[var(--ink-muted)] break-all">
            {msg}
          </p>
        ) : null}

        <div className="mt-5 flex justify-end gap-2.5">
          {busyKey ? (
            <Btn onClick={() => void invoke("extra_cancel")}>取消下载</Btn>
          ) : (
            <Btn onClick={onClose}>关闭</Btn>
          )}
        </div>
      </div>
    </div>
  );
}

function ItemRow({
  it,
  category,
  busyKey,
  onStart,
}: {
  it: Item;
  category: Category;
  busyKey: string;
  onStart: (key: string) => void;
}) {
  return (
    <div className="flex items-center gap-4 border-b border-[var(--hairline)] py-3.5">
      <span className="min-w-0 flex-1">
        <span className="block text-[14px] leading-snug">
          {shortLabel(it, category)}
          {it.recommended ? (
            <span className="ml-1.5 text-[11px] text-[var(--accent)] font-medium">
              推荐
            </span>
          ) : null}
        </span>
        {it.notes?.trim() ? (
          <span className="block mt-1 text-[12.5px] text-[var(--meta)] leading-snug">
            {it.notes}
          </span>
        ) : null}
        <span className="block mt-1 text-[12px] text-[var(--meta)] tabular-nums">
          {mb(it.size_bytes)}
          {it.files?.length ? ` · ${it.files.length} 个文件` : ""}
          {it.installed ? " · 已安装" : ""}
        </span>
      </span>
      {it.installed ? (
        <span className="shrink-0 text-[13px] text-[var(--ink-muted)] px-2">
          已安装
        </span>
      ) : (
        <Btn
          className="shrink-0 min-w-[72px]"
          disabled={!!busyKey}
          onClick={() => void onStart(it.key)}
        >
          {busyKey === it.key ? "下载中…" : "下载"}
        </Btn>
      )}
    </div>
  );
}
