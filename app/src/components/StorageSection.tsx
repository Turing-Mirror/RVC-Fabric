import { useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Block, Btn, Group, ListItem } from "./ui";
import { askConfirm } from "../lib/webDialog";
import { t } from "../i18n/t";

type Usage = {
  items: { name: string; bytes: number }[];
  total_bytes: number;
  free_bytes: number | null;
};

type Row = {
  exp: string;
  total_bytes: number;
  kinds: Record<string, { files: number; bytes: number }>;
};

/** 类别 → 文案与后果。后果必须写在勾选框旁边，不能只在确认框里说一次。 */
const KINDS = [
  { id: "snapshots", labelKey: "s.cleanupSnapshots", effectKey: "s.cleanupEffectNone" },
  { id: "checkpoints", labelKey: "s.cleanupCheckpoints", effectKey: "s.cleanupEffectNoResume" },
  { id: "dataset", labelKey: "s.cleanupDataset", effectKey: "s.cleanupEffectRestart" },
] as const;

const USAGE_LABEL: Record<string, string> = {
  logs: "s.storageLogs",
  weights: "s.storageWeights",
  models: "s.storageModels",
  update_cache: "s.storageUpdateCache",
  diagnostics: "s.storageDiagnostics",
  perf_reports: "s.storagePerf",
  app_logs: "s.storageAppLogs",
  trash: "s.storageTrash",
};

function human(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

/**
 * 存储占用与训练残留清理。
 *
 * 一个训练实验的中间产物动辄三四个 GB，而用户完全看不见 —— 他只知道 C 盘满了，
 * 不知道是谁占的，于是来群里问「能不能删」。这里把占用摊开，并且只允许逐个实验、
 * 逐类勾选后清除。
 *
 * 明确不做「一键清理全部实验」：这套判据先在真实用户那边跑过一个版本再说。误删
 * 一次就是不可挽回的信任损失，而它省下的只是几次点击。
 */
export function StorageSection() {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [picked, setPicked] = useState<Record<string, Set<string>>>({});
  // 实验一多（每个三四个 GB 的主儿），一整列铺下去「其他」页就成了账本。
  // 每页五个，按占用从大到小排 —— 最该处理的永远在第一页。
  const PAGE_SIZE = 5;
  const [page, setPage] = useState(1);

  const sorted = useMemo(
    () =>
      (rows ?? [])
        .slice()
        .sort((a, b) => b.total_bytes - a.total_bytes),
    [rows],
  );
  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const pageClamped = Math.min(page, totalPages);
  const pageRows = sorted.slice(
    (pageClamped - 1) * PAGE_SIZE,
    pageClamped * PAGE_SIZE,
  );

  const scan = async () => {
    setBusy(true);
    setMsg("");
    try {
      const [u, r] = await Promise.all([
        invoke<Usage>("storage_usage"),
        invoke<Row[]>("train_cleanup_scan"),
      ]);
      setUsage(u);
      setRows(Array.isArray(r) ? r : []);
      setPicked({});
      setPage(1);
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  };

  const toggle = (exp: string, kind: string) => {
    setPicked((prev) => {
      const next = { ...prev };
      const set = new Set(next[exp] ?? []);
      if (set.has(kind)) set.delete(kind);
      else set.add(kind);
      next[exp] = set;
      return next;
    });
  };

  const apply = async (row: Row) => {
    const kinds = [...(picked[row.exp] ?? [])];
    if (kinds.length === 0 || busy) return;
    const names = kinds
      .map((k) => t(KINDS.find((x) => x.id === k)?.labelKey ?? k))
      .join("、");
    if (!(await askConfirm(t("s.cleanupConfirm", { a0: row.exp, a1: names })))) return;
    setBusy(true);
    try {
      const r = await invoke<{ freed_bytes?: number }>("train_cleanup_apply", {
        exp: row.exp,
        kinds,
      });
      setMsg(t("s.cleanupDone", { v0: human(r?.freed_bytes ?? 0) }));
      await scan();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Block title={t("s.storageTitle")}>
      <Group>
        <ListItem
          title={t("s.storageTitle")}
          desc={
            msg ||
            (usage
              ? t("s.storageTotal", {
                  a0: human(usage.total_bytes),
                  a1: usage.free_bytes == null ? "—" : human(usage.free_bytes),
                })
              : t("s.cleanupDesc"))
          }
          right={
            <Btn onClick={() => void scan()} disabled={busy} busy={busy}>
              {busy ? t("s.storageScanning") : t("s.storageScan")}
            </Btn>
          }
        />
        {usage ? (
          <div className="px-4 py-3">
            <ul className="m-0 list-none p-0">
              {usage.items.map((it) => (
                <li
                  key={it.name}
                  className="flex justify-between gap-3 text-[12.5px] leading-relaxed"
                >
                  <span className="text-[var(--ink-muted)]">
                    {t(USAGE_LABEL[it.name] ?? it.name)}
                  </span>
                  <span className="font-mono text-[11.5px] text-[var(--meta)] tabular-nums">
                    {human(it.bytes)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {rows && rows.length === 0 ? (
          <ListItem title={t("s.cleanupTitle")} desc={t("s.cleanupNothing")} />
        ) : null}
        {rows && rows.length ? (
          <div className="px-4 py-3">
            <div className="flex items-baseline justify-between gap-3 mb-2">
              <p className="m-0 text-[12.5px] text-[var(--ink-muted)]">
                {t("s.cleanupTitle")}
              </p>
              <span className="font-mono text-[11.5px] text-[var(--meta)] tabular-nums">
                {t("s.pageOf", { cur: pageClamped, total: totalPages })}
              </span>
            </div>
            <p className="m-0 mb-3 text-[12px] text-[var(--meta)] leading-relaxed">
              {t("s.cleanupDesc")}
            </p>
            <ul className="m-0 list-none p-0">
              {pageRows.map((row, i) => (
                <li key={row.exp} className="relative py-3 first:pt-0">
                  {i > 0 ? (
                    <div
                      aria-hidden
                      className="absolute top-0 left-0 right-0 h-px bg-[var(--hairline)]"
                    />
                  ) : null}
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-[13px] font-semibold">{row.exp}</span>
                    <span className="font-mono text-[11.5px] text-[var(--meta)] tabular-nums">
                      {human(row.total_bytes)}
                    </span>
                  </div>
                  <div className="mt-1.5 flex flex-col gap-1">
                    {KINDS.map((k) => {
                      const info = row.kinds[k.id];
                      const empty = !info || info.bytes === 0;
                      return (
                        <label
                          key={k.id}
                          className={
                            "flex items-center gap-2 text-[12.5px] " +
                            (empty ? "opacity-45" : "cursor-pointer")
                          }
                        >
                          <input
                            type="checkbox"
                            disabled={empty || busy}
                            checked={picked[row.exp]?.has(k.id) ?? false}
                            onChange={() => toggle(row.exp, k.id)}
                            className="accent-[var(--accent)]"
                          />
                          <span>{t(k.labelKey)}</span>
                          <span className="font-mono text-[11px] text-[var(--meta)] tabular-nums">
                            {human(info?.bytes ?? 0)}
                          </span>
                          {/* 后果写在勾选框旁边，不是只在确认框里说一次。 */}
                          <span className="text-[11.5px] text-[var(--meta)]">
                            {t(k.effectKey)}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                  <div className="mt-2">
                    <Btn
                      onClick={() => void apply(row)}
                      busy={busy}
                      disabled={busy || (picked[row.exp]?.size ?? 0) === 0}
                    >
                      {t("s.cleanupApply")}
                    </Btn>
                  </div>
                </li>
              ))}
            </ul>
            {totalPages > 1 ? (
              <div className="flex items-center justify-center gap-3 pt-4 text-[12.5px] text-[var(--meta)]">
                <Btn
                  disabled={pageClamped <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  {t("s.b41561d807")}
                </Btn>
                <span className="tabular-nums">
                  {t("s.40a021ed44", {
                    v0: pageClamped,
                    v1: totalPages,
                    v2: sorted.length,
                  })}
                </span>
                <Btn
                  disabled={pageClamped >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                >
                  {t("s.67a246a344")}
                </Btn>
              </div>
            ) : null}
          </div>
        ) : null}
      </Group>
    </Block>
  );
}
