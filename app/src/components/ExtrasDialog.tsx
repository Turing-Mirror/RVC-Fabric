import { useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn } from "./ui";

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

/** 打开下载弹窗时指定只看哪一类功能依赖。 */
export type ExtrasFilter = "all" | ExtraGroup;

function mb(n: number) {
  if (!n) return "";
  return n >= 1024 * 1024 * 1024
    ? `${(n / 1024 / 1024 / 1024).toFixed(1)} GB`
    : `${Math.round(n / 1024 / 1024)} MB`;
}

const GROUP_META: Record<
  string,
  { title: string; blurb: string }
> = {
  train: {
    title: "训练音色",
    blurb:
      "按你要训的采样率下一套底模即可（三选一，不必全下）。Hubert / RMVPE 已在首次「补全引擎资源」时装好，这里不用重复下。",
  },
  separate: {
    title: "人声分离",
    blurb:
      "做训练素材清理时，优先下「人声提取」。其余按场景按需下载；标「进阶」的体积大，日常一般用不到。",
  },
  other: {
    title: "其他资源",
    blurb: "未归入训练或分离的附加资源。",
  },
};

/**
 * 附加资源下载：分离模型、训练底模。
 *
 * 列表按「功能」分组（训练 / 分离），每条带用途说明，避免用户面对一长串
 * pymss-xxx / pretrained-xxx 不知道该下哪个。
 */
export function ExtrasDialog({
  open,
  onClose,
  filter = "all",
  title,
}: {
  open: boolean;
  onClose: () => void;
  /** 只显示某一功能分组；默认全部。 */
  filter?: ExtrasFilter;
  title?: string;
}) {
  const [list, setList] = useState<List | null>(null);
  const [prog, setProg] = useState<Progress | null>(null);
  const [msg, setMsg] = useState("");
  const [busyKey, setBusyKey] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
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
    setShowAdvanced(false);
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
  }, [open]);

  const items = useMemo(() => {
    const all = list?.items || [];
    if (filter === "all") return all;
    return all.filter((i) => (i.group || inferGroup(i.key)) === filter);
  }, [list, filter]);

  // 分离组里：推荐/常用 vs 进阶。
  // 老清单没有 recommended 时绝不整组塞进进阶，否则用户只看到「显示进阶」按钮。
  const { primary, advanced } = useMemo(() => {
    if (filter === "train") {
      return { primary: items, advanced: [] as Item[] };
    }
    const hasRec = items.some((i) => i.recommended);
    const primary: Item[] = [];
    const advanced: Item[] = [];
    for (const it of items) {
      const g = it.group || inferGroup(it.key);
      if (g !== "separate") {
        primary.push(it);
        continue;
      }
      const byLabel = String(it.label).includes("进阶");
      const byMeta =
        hasRec && !it.recommended && (it.order ?? 100) >= 70;
      if (byLabel || byMeta) advanced.push(it);
      else primary.push(it);
    }
    return { primary, advanced };
  }, [items, filter]);

  const sections = useMemo(() => {
    // filter 指定了某一组 → 单段；否则按 train / separate / other 拆。
    if (filter !== "all") {
      return [{ group: filter, items: primary }];
    }
    const order = ["train", "separate", "other"] as const;
    return order
      .map((g) => ({
        group: g,
        items: primary.filter((i) => (i.group || inferGroup(i.key)) === g),
      }))
      .filter((s) => s.items.length > 0);
  }, [filter, primary]);

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
  const heading =
    title ||
    (filter === "train"
      ? "下载训练底模"
      : filter === "separate"
        ? "下载分离模型"
        : "下载模型");

  const emptyHint =
    list?.available === false
      ? "连不上服务器，检查网络后再试。"
      : filter === "train"
        ? "暂时没有可下载的训练底模。"
        : filter === "separate"
          ? "暂时没有可下载的分离模型。"
          : "暂时没有可下载的模型。";

  return (
    <div
      className="fixed inset-0 z-[80] grid place-items-center p-6 bg-[color-mix(in_srgb,var(--ink)_28%,transparent)]"
      onClick={busyKey ? undefined : onClose}
    >
      <div
        className="flex max-h-[min(80vh,640px)] w-full max-w-[560px] flex-col rounded-[var(--r)] bg-[var(--surface)] p-6 shadow-[0_20px_60px_rgba(0,0,0,0.22)]"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="m-0 mb-1 text-[17px] font-semibold">{heading}</h3>
        <p className="m-0 mb-4 text-[12.5px] text-[var(--ink-muted)]">
          {filter === "all"
            ? "按功能分组：训练音色下一套底模，人声分离优先下「人声提取」。体积较大，下载后自动校验，支持断点续传。"
            : filter === "train"
              ? "训练前只需下载与采样率对应的一套底模。体积较大，下载后自动校验。"
              : "分离模型按用途下载；训练前清伴奏优先「人声提取」。体积较大，下载后自动校验。"}
        </p>

        {list === null ? (
          <div className="min-h-0 flex-1">
            <p className="m-0 py-4 text-[13px] text-[var(--meta)]">正在读取清单…</p>
          </div>
        ) : items.length === 0 ? (
          <div className="min-h-0 flex-1">
            <p className="m-0 py-4 text-[13px] text-[var(--ink-muted)]">{emptyHint}</p>
          </div>
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto border-t border-[var(--hairline)]">
            {sections.map((sec) => {
              const meta = GROUP_META[sec.group] || GROUP_META.other;
              const showHeader = filter === "all";
              return (
                <div key={sec.group}>
                  {showHeader ? (
                    <div className="sticky top-0 z-[1] bg-[var(--surface)] pt-3 pb-1">
                      <div className="text-[13px] font-semibold text-[var(--ink)]">
                        {meta.title}
                      </div>
                      <p className="m-0 mt-0.5 mb-1 text-[12px] text-[var(--meta)] leading-snug">
                        {meta.blurb}
                      </p>
                    </div>
                  ) : (
                    <p className="m-0 pt-3 pb-1 text-[12px] text-[var(--meta)] leading-snug">
                      {meta.blurb}
                    </p>
                  )}
                  {sec.items.map((it) => (
                    <ItemRow
                      key={it.key}
                      it={it}
                      busyKey={busyKey}
                      onStart={start}
                    />
                  ))}
                </div>
              );
            })}

            {advanced.length > 0 ? (
              <div className="pt-2 pb-1">
                <button
                  type="button"
                  className="border-0 bg-transparent p-0 cursor-pointer text-[12.5px] text-[var(--accent)]"
                  onClick={() => setShowAdvanced((v) => !v)}
                >
                  {showAdvanced
                    ? "收起进阶模型"
                    : `显示进阶模型（${advanced.length}）`}
                </button>
                {showAdvanced
                  ? advanced.map((it) => (
                      <ItemRow
                        key={it.key}
                        it={it}
                        busyKey={busyKey}
                        onStart={start}
                      />
                    ))
                  : null}
              </div>
            ) : null}
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

function inferGroup(key: string): string {
  if (key.startsWith("pretrained")) return "train";
  if (key.startsWith("pymss") || key.startsWith("uvr")) return "separate";
  return "other";
}

function ItemRow({
  it,
  busyKey,
  onStart,
}: {
  it: Item;
  busyKey: string;
  onStart: (key: string) => void;
}) {
  return (
    <div className="flex items-start gap-3 border-b border-[var(--hairline)] py-3">
      <span className="min-w-0 flex-1">
        <span className="block text-[13.5px] leading-snug">
          {it.label}
          {it.recommended ? (
            <span className="ml-1.5 text-[11px] text-[var(--accent)] font-medium">
              推荐
            </span>
          ) : null}
        </span>
        <span className="block mt-0.5 text-[12px] text-[var(--meta)] leading-snug">
          {it.notes?.trim()
            ? it.notes
            : `${mb(it.size_bytes)}${it.files?.length ? ` · ${it.files.length} 个文件` : ""}`}
        </span>
        <span className="block mt-0.5 text-[11.5px] text-[var(--meta)]">
          {mb(it.size_bytes)}
          {it.installed ? " · 已安装" : ""}
        </span>
      </span>
      {it.installed ? (
        <span className="shrink-0 pt-0.5 text-[12.5px] text-[var(--ink-muted)]">
          已安装
        </span>
      ) : (
        <Btn
          disabled={!!busyKey}
          onClick={() => void onStart(it.key)}
        >
          {busyKey === it.key ? "下载中…" : "下载"}
        </Btn>
      )}
    </div>
  );
}
