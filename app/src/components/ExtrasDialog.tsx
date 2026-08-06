import { useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn } from "./ui";
import { SegmentControl } from "./SegmentControl";
import { t } from "../i18n/t";
import {
  getAssetsStatus,
  type AssetsStatus,
} from "../lib/downloadModels";

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

type ProvProgress = {
  phase?: string;
  done?: number;
  total?: number;
  percent?: number;
  message?: string;
  speed_label?: string;
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

/** Prefer locale pack extras.items.<key>; fall back to catalog Chinese with prefix strip. */
function extraLabel(it: Item, cat: Category): string {
  const localized = t(`extras.items.${it.key}.label`);
  if (localized && !localized.startsWith("extras.items.")) return localized;
  let l = it.label || it.key;
  if (cat === "separate") l = l.replace(/^人声分离\s*[·•]\s*/, "");
  if (cat === "train") l = l.replace(/^训练音色\s*[·•]\s*/, "");
  return l;
}

function extraNotes(it: Item): string {
  const localized = t(`extras.items.${it.key}.notes`);
  if (localized && !localized.startsWith("extras.items.")) return localized;
  return (it.notes || "").trim();
}

function categoryBlurb(cat: Category): string {
  return cat === "separate" ? t("s.63fa37071e") : t("s.5b422f44dd");
}

/**
 * 附加资源下载：引擎资源 + 分离模型 + 训练底模。
 *
 * 布局对齐广场「社区音色」：顶部分段切换分类（人声分离 / 训练音色），
 * 列表分页每页 5 条。引擎资源是前置依赖：未就绪时先下载它，再选模型。
 *
 * 这里只有内容，没有弹窗那层壳。两个地方用它：
 *
 * * 广场「下载模型」区块 —— 主窗口里这是唯一的入口，直接铺在页面上；
 * * `ExtrasDialog` —— 工具窗口（人声分离 / 训练音色）里缺资源时弹的那个框。
 *   那是独立的窗口，没有广场可去，只能就地弹。
 */
export function ExtrasPanel({
  onClose,
  filter = "all",
  title,
  reason,
  onBusyChange,
}: {
  /** 给了才画「关闭」按钮。嵌在页面里时没有可关的东西。 */
  onClose?: () => void;
  filter?: ExtrasFilter;
  /** 给了才画标题。嵌在 Block 里时标题由 Block 出，这里再写一遍就重了。 */
  title?: string;
  /** 从工具入口跳转时的说明（缺引擎资源等）。 */
  reason?: string;
  /** 正在下载时告诉外面的弹窗别让点空白关掉。 */
  onBusyChange?: (busy: boolean) => void;
}) {
  const [list, setList] = useState<List | null>(null);
  const [assets, setAssets] = useState<AssetsStatus | null>(null);
  const [prog, setProg] = useState<Progress | null>(null);
  const [coreProg, setCoreProg] = useState<ProvProgress | null>(null);
  const [msg, setMsg] = useState("");
  const [busyKey, setBusyKey] = useState("");
  const [coreBusy, setCoreBusy] = useState(false);
  const [category, setCategory] = useState<Category>(
    filter === "train" ? "train" : "separate",
  );
  const [page, setPage] = useState(0);
  const busyRef = useRef(false);

  /** null = 还在查；false = 缺引擎资源；true = 已就绪 */
  const engineReady: boolean | null =
    assets == null ? null : Boolean(assets.engine_core_ready);

  const load = async () => {
    setMsg("");
    try {
      const [a, l] = await Promise.all([
        getAssetsStatus(),
        invoke<List>("extra_list"),
      ]);
      setAssets(a);
      setList(l);
    } catch (e) {
      setList({ available: false, items: [] });
      setMsg(String(e));
    }
  };

  useEffect(() => {
    setList(null);
    setAssets(null);
    setPage(0);
    setCategory(filter === "train" ? "train" : "separate");
    setCoreProg(null);
    void load();
    let disposed = false;
    const unsubs: Array<() => void> = [];
    void listen<Progress>("extra-progress", (ev) => {
      setProg(ev.payload);
      if (ev.payload.phase === "error") setMsg(ev.payload.message || t("s.e0dab22b1a"));
    }).then((fn) => {
      if (disposed) fn();
      else unsubs.push(fn);
    });
    // 引擎资源下载复用 provision-progress（phase=engine-core）
    void listen<ProvProgress>("provision-progress", (ev) => {
      if (ev.payload?.phase === "engine-core" || String(ev.payload?.phase || "").includes("engine")) {
        setCoreProg(ev.payload);
      }
    }).then((fn) => {
      if (disposed) fn();
      else unsubs.push(fn);
    });
    return () => {
      disposed = true;
      unsubs.forEach((f) => f());
    };
    // `load` 每次渲染都是新函数，列进依赖会变成「渲染一次拉一次清单」。
    // 这个 effect 要的是「挂载时拉一次，filter 变了再拉一次」。
  }, [filter]);

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

  const downloadEngineCore = async () => {
    if (busyRef.current || coreBusy) return;
    busyRef.current = true;
    setCoreBusy(true);
    setMsg("");
    setCoreProg({
      phase: "engine-core",
      done: 0,
      total: 1,
      percent: 0,
      message: t("s.c7ea0cf156"),
    });
    try {
      await invoke("assets_ensure_engine_core");
      setMsg(t("s.33dadd8dd6"));
      setAssets(await getAssetsStatus());
      setCoreProg(null);
    } catch (e) {
      setMsg(String(e));
    } finally {
      busyRef.current = false;
      setCoreBusy(false);
    }
  };

  const start = async (key: string) => {
    if (busyRef.current || coreBusy) return;
    if (engineReady === false) {
      setMsg(t("s.e8a77f003d"));
      return;
    }
    busyRef.current = true;
    setBusyKey(key);
    setMsg("");
    setProg(null);
    try {
      await invoke("extra_download", { key });
      setMsg(t("s.4bbcf94739"));
      void load();
    } catch (e) {
      setMsg(String(e));
    } finally {
      busyRef.current = false;
      setBusyKey("");
    }
  };

  const pct = prog?.total ? Math.round(((prog.done ?? 0) / prog.total) * 100) : 0;
  const corePct =
    coreProg?.percent != null
      ? Math.min(100, Math.max(0, Number(coreProg.percent)))
      : coreProg?.total
        ? Math.round(((coreProg.done ?? 0) / Math.max(coreProg.total, 1)) * 100)
        : 0;

  const emptyHint =
    list?.available === false
      ? t("s.122abe360d")
      : category === "train"
        ? t("s.2b9ddc0b69")
        : t("s.7e9782377b");

  const locked = engineReady === false;
  const anyBusy = !!busyKey || coreBusy;
  useEffect(() => {
    onBusyChange?.(anyBusy);
  }, [anyBusy, onBusyChange]);

  return (
    <>
        <div className="flex flex-wrap items-start justify-between gap-3 mb-1">
          {title ? (
            <h3 className="m-0 text-[17px] font-semibold">{title}</h3>
          ) : null}
          <SegmentControl<Category>
            className={title ? "" : "ml-auto"}
            value={category}
            onChange={(v) => {
              setCategory(v);
              setPage(0);
            }}
            options={[
              { id: "separate", label: t("s.8fd038283b") },
              { id: "train", label: t("s.ba65bd5595") },
            ]}
          />
        </div>
        <p className="m-0 mb-3 text-[12.5px] text-[var(--ink-muted)] leading-snug">
          {categoryBlurb(category)}
        </p>

        {reason ? (
          <p className="m-0 mb-3 rounded-[var(--rs)] bg-[color-mix(in_srgb,var(--notify)_14%,transparent)] px-3 py-2 text-[12.5px] text-[var(--ink-muted)] leading-relaxed">
            {reason}
          </p>
        ) : null}

        {/* 引擎资源前置卡：CNB engine-core，约 720MB */}
        <div
          className={[
            "mb-4 rounded-[var(--rs)] px-3.5 py-3",
            locked
              ? "bg-[color-mix(in_srgb,var(--accent)_8%,transparent)] shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--accent)_28%,transparent)]"
              : "bg-[color-mix(in_srgb,var(--ink)_4%,transparent)]",
          ].join(" ")}
        >
          <div className="flex items-start gap-3 flex-wrap">
            <div className="min-w-0 flex-1">
              <div className="text-[13.5px] font-semibold">
                {t("extras.engineTitle")}
                {engineReady === true ? (
                  <span className="ml-2 text-[12px] font-normal text-[var(--meta)]">{t("s.f2afde8960")}</span>
                ) : engineReady === false ? (
                  <span className="ml-2 text-[12px] font-normal text-[var(--accent)]">{t("s.f9cbb1e0c6")}</span>
                ) : (
                  <span className="ml-2 text-[12px] font-normal text-[var(--meta)]">{t("s.5fc65af5b3")}</span>
                )}
              </div>
              <p className="m-0 mt-1 text-[12.5px] text-[var(--help)] leading-relaxed">
                {t("extras.engineDesc")}
                {assets?.engine_core_missing?.length
                  ? t("extras.missingList", {
                      list: assets.engine_core_missing.join("、"),
                    })
                  : ""}
              </p>
              {coreBusy && coreProg ? (
                <div className="mt-2">
                  <div className="h-1 w-full overflow-hidden rounded bg-[color-mix(in_srgb,var(--ink)_10%,transparent)]">
                    <div
                      className="h-full bg-[var(--accent)] transition-[width] duration-200"
                      style={{ width: `${corePct}%` }}
                    />
                  </div>
                  <p className="m-0 mt-1.5 text-[12px] text-[var(--meta)]">
                    {coreProg.message || t("s.65188d08a2")}
                    {coreProg.speed_label ? ` · ${coreProg.speed_label}` : ""}
                    {corePct > 0 ? ` · ${Math.round(corePct)}%` : ""}
                  </p>
                </div>
              ) : null}
            </div>
            {engineReady === false ? (
              <Btn
                primary
                className="shrink-0"
                disabled={coreBusy || !!busyKey}
                onClick={() => void downloadEngineCore()}
              >
                {coreBusy ? t("s.65188d08a2") : t("s.cbf7f4dada")}
              </Btn>
            ) : engineReady === true ? (
              <span className="shrink-0 text-[13px] text-[var(--ink-muted)] px-2 py-1">{t("s.eb88ff57c9")}</span>
            ) : null}
          </div>
        </div>

        {locked ? (
          <div className="min-h-[200px] flex items-center">
            <p className="m-0 py-4 text-[13px] text-[var(--ink-muted)] leading-relaxed">{t("s.70927369db")}</p>
          </div>
        ) : list === null ? (
          <div className="min-h-[200px] flex items-center">
            <p className="m-0 py-4 text-[13px] text-[var(--meta)]">{t("s.cd178d24a2")}</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="min-h-[200px] flex items-center">
            <p className="m-0 py-4 text-[13px] text-[var(--ink-muted)]">{emptyHint}</p>
          </div>
        ) : (
          <div className="min-h-[200px] flex flex-col border-t border-[var(--hairline)]">
            <div className="flex-1">
              {pageItems.map((it) => (
                <ItemRow
                  key={it.key}
                  it={it}
                  category={category}
                  busyKey={busyKey}
                  disabled={coreBusy}
                  onStart={start}
                />
              ))}
            </div>

            {totalPages > 1 ? (
              <div className="flex items-center justify-center gap-3 pt-4 pb-1">
                <Btn
                  disabled={pageClamped <= 0 || anyBusy}
                  onClick={() => setPage(pageClamped - 1)}
                >{t("s.b41561d807")}</Btn>
                <span className="text-[12.5px] text-[var(--meta)] tabular-nums min-w-[72px] text-center">
                  {pageClamped + 1} / {totalPages}
                </span>
                <Btn
                  disabled={pageClamped >= totalPages - 1 || anyBusy}
                  onClick={() => setPage(pageClamped + 1)}
                >{t("s.67a246a344")}</Btn>
              </div>
            ) : (
              <p className="m-0 pt-3 text-[12px] text-[var(--meta)] text-center tabular-nums">
                {t("extras.countItems", { n: filtered.length })}
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

        {busyKey || onClose ? (
          <div className="mt-5 flex justify-end gap-2.5">
            {busyKey ? (
              <Btn onClick={() => void invoke("extra_cancel")}>{t("s.7115f2e29d")}</Btn>
            ) : onClose ? (
              <Btn onClick={onClose} disabled={coreBusy}>{t("s.6c14bd7f6f")}</Btn>
            ) : null}
          </div>
        ) : null}
    </>
  );
}

/**
 * 弹窗形态。只剩工具窗口在用 —— 主窗口那份已经搬进广场了。
 *
 * 下载中不许点空白关掉：那一下会把面板卸载，下载虽然还在后台跑，但进度条
 * 没了，用户会以为自己把它取消了。
 */
export function ExtrasDialog({
  open,
  onClose,
  filter = "all",
  title,
  reason,
}: {
  open: boolean;
  onClose: () => void;
  filter?: ExtrasFilter;
  title?: string;
  reason?: string;
}) {
  const [busy, setBusy] = useState(false);
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-[80] grid place-items-center p-6 bg-[color-mix(in_srgb,var(--ink)_28%,transparent)]"
      onClick={busy ? undefined : onClose}
    >
      <div
        className="flex max-h-[min(88vh,720px)] w-full max-w-[min(920px,96vw)] flex-col rounded-[var(--r)] bg-[var(--surface)] p-6 shadow-[0_20px_60px_rgba(0,0,0,0.22)]"
        onClick={(e) => e.stopPropagation()}
      >
        <ExtrasPanel
          onClose={onClose}
          filter={filter}
          title={title || t("s.1252c81119")}
          reason={reason}
          onBusyChange={setBusy}
        />
      </div>
    </div>
  );
}

function ItemRow({
  it,
  category,
  busyKey,
  disabled,
  onStart,
}: {
  it: Item;
  category: Category;
  busyKey: string;
  disabled?: boolean;
  onStart: (key: string) => void;
}) {
  return (
    <div className="flex items-center gap-4 border-b border-[var(--hairline)] py-3.5">
      <span className="min-w-0 flex-1">
        <span className="block text-[14px] leading-snug">
          {extraLabel(it, category)}
          {it.recommended ? (
            <span className="ml-1.5 text-[11px] text-[var(--accent)] font-medium">{t("s.62b46f24ae")}</span>
          ) : null}
        </span>
        {extraNotes(it) ? (
          <span className="block mt-1 text-[12.5px] text-[var(--meta)] leading-snug">
            {extraNotes(it)}
          </span>
        ) : null}
        <span className="block mt-1 text-[12px] text-[var(--meta)] tabular-nums">
          {mb(it.size_bytes)}
          {it.files?.length ? t("s.8e7dddc185", { v0: it.files.length }) : ""}
          {it.installed ? t("s.f7b11922f6") : ""}
        </span>
      </span>
      {it.installed ? (
        <span className="shrink-0 text-[13px] text-[var(--ink-muted)] px-2">{t("s.eb88ff57c9")}</span>
      ) : (
        <Btn
          className="shrink-0 min-w-[72px]"
          disabled={!!busyKey || !!disabled}
          onClick={() => void onStart(it.key)}
        >
          {busyKey === it.key ? t("s.65188d08a2") : t("s.2b9d013177")}
        </Btn>
      )}
    </div>
  );
}
