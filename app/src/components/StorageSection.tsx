import { useEffect, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Block, Btn } from "./ui";
import { Ring, type RingSegment } from "./Ring";
import { askConfirm } from "../lib/webDialog";
import { t } from "../i18n/t";
import { formatLocalizedList } from "../lib/voiceDisplay";

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

/** 训练实验里可清理的几类。后果写在勾选框旁边，不能只在确认框里说一次。 */
const TRAIN_KINDS = [
  { id: "snapshots", labelKey: "s.cleanupSnapshots", effectKey: "s.cleanupEffectNone" },
  { id: "checkpoints", labelKey: "s.cleanupCheckpoints", effectKey: "s.cleanupEffectNoResume" },
  { id: "dataset", labelKey: "s.cleanupDataset", effectKey: "s.cleanupEffectRestart" },
] as const;

/**
 * 可以整类清理的几项，与后端 paths::STORAGE_CLEAN_KINDS 一一对应。usage 是它在占用统计里的名字。
 * 原「其他 → 维护」里的「清理缓存」拆成了这里的临时文件、程序日志与诊断包三项。
 */
const DIRECT_KINDS = [
  { id: "temp", usage: "temp", labelKey: "s.storageTemp", effectKey: "s.cleanEffectTemp" },
  { id: "app_logs", usage: "app_logs", labelKey: "s.storageAppLogs", effectKey: "s.cleanEffectLogs" },
  { id: "diagnostics", usage: "diagnostics", labelKey: "s.storageDiagnostics", effectKey: "s.cleanEffectDiag" },
  { id: "perf_reports", usage: "perf_reports", labelKey: "s.storagePerf", effectKey: "s.cleanEffectPerf" },
  { id: "trash", usage: "trash", labelKey: "s.storageTrash", effectKey: "s.cleanEffectTrash" },
] as const;

/** 环形图里单独成段的几类，其余并入「其他」。颜色取 index.css 里的 --ring-* 令牌。 */
const RING_PARTS = [
  { names: ["models"], labelKey: "s.storageModels" },
  { names: ["logs", "weights"], labelKey: "s.storageTraining" },
  { names: ["update_cache"], labelKey: "s.storageUpdateCache" },
  { names: ["temp", "app_logs", "diagnostics", "perf_reports"], labelKey: "s.storageJunk" },
  { names: ["trash"], labelKey: "s.storageTrash" },
] as const;

/** 训练实验一页列几个。按占用从大到小排，最该处理的永远在第一页。 */
const PAGE_SIZE = 5;

function human(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

/**
 * 存储占用与清理。
 *
 * 上面一个环形图说清楚谁占了多少；下面一张清单，每一项写明大小和清理后的影响，
 * 勾选后一次清理。训练实验的中间文件逐个实验、逐类勾选。
 *
 * 明确不做「一键全选」：误删一次就是不可挽回的信任损失，而它省下的只是几次点击。
 */
export function StorageSection() {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [direct, setDirect] = useState<Set<string>>(new Set());
  const [train, setTrain] = useState<Record<string, Set<string>>>({});
  const [page, setPage] = useState(1);

  const sorted = useMemo(() => (rows ?? []).slice().sort((a, b) => b.total_bytes - a.total_bytes), [rows]);
  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const pageClamped = Math.min(page, totalPages);
  const pageRows = sorted.slice((pageClamped - 1) * PAGE_SIZE, pageClamped * PAGE_SIZE);
  const bytesOf = (name: string) => usage?.items.find((x) => x.name === name)?.bytes ?? 0;

  const scan = async () => {
    setBusy(true);
    try {
      const [u, r] = await Promise.all([invoke<Usage>("storage_usage"), invoke<Row[]>("train_cleanup_scan")]);
      setUsage(u);
      setRows(Array.isArray(r) ? r : []);
      setDirect(new Set());
      setTrain({});
      setPage(1);
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  };
  // 打开就统计一次，不用先找按钮
  useEffect(() => {
    void scan();
  }, []);

  const segments: RingSegment[] = usage
    ? RING_PARTS.map((p, i) => ({
        id: p.labelKey,
        label: t(p.labelKey),
        value: p.names.reduce((n, name) => n + bytesOf(name), 0),
        color: `var(--ring-${i + 1})`,
      }))
        .filter((s) => s.value > 0)
        .map((s) => ({ ...s, note: human(s.value) }))
    : [];

  const toggleDirect = (id: string) =>
    setDirect((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const toggleTrain = (exp: string, kind: string) =>
    setTrain((prev) => {
      const set = new Set(prev[exp] ?? []);
      if (set.has(kind)) set.delete(kind);
      else set.add(kind);
      return { ...prev, [exp]: set };
    });

  const pickedTrain = Object.entries(train).filter(([, kinds]) => kinds.size > 0);
  const pickedBytes =
    [...direct].reduce((n, id) => n + bytesOf(DIRECT_KINDS.find((k) => k.id === id)?.usage ?? ""), 0) +
    pickedTrain.reduce((n, [exp, kinds]) => n + [...kinds].reduce((m, k) => m + (rows?.find((r) => r.exp === exp)?.kinds[k]?.bytes ?? 0), 0), 0);
  const pickedCount = direct.size + pickedTrain.reduce((n, [, kinds]) => n + kinds.size, 0);

  const apply = async () => {
    if (!pickedCount || busy) return;
    const names = [
      ...DIRECT_KINDS.filter((k) => direct.has(k.id)).map((k) => t(k.labelKey)),
      ...pickedTrain.map(([exp, kinds]) => `${exp}（${formatLocalizedList([...kinds].map((k) => t(TRAIN_KINDS.find((x) => x.id === k)?.labelKey ?? k)))}）`),
    ];
    if (!(await askConfirm(t("s.cleanConfirm", { list: formatLocalizedList(names) })))) return;
    setBusy(true);
    let freed = 0;
    try {
      if (direct.size) freed += (await invoke<{ freed_bytes?: number }>("storage_clean", { kinds: [...direct] }))?.freed_bytes ?? 0;
      for (const [exp, kinds] of pickedTrain) {
        freed += (await invoke<{ freed_bytes?: number }>("train_cleanup_apply", { exp, kinds: [...kinds] }))?.freed_bytes ?? 0;
      }
      setMsg(t("s.cleanDone", { size: human(freed) }));
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
      await scan();
    }
  };

  const check = "w-[14px] h-[14px] flex-none accent-[var(--accent)]";
  return (
    <Block
      title={t("s.storageTitle")}
      note={usage ? t("s.storageTotal", { a0: human(usage.total_bytes), a1: usage.free_bytes == null ? "—" : human(usage.free_bytes) }) : undefined}
      action={
        <Btn onClick={() => void scan()} disabled={busy} busy={busy}>
          {busy ? t("s.storageScanning") : t("s.storageScan")}
        </Btn>
      }
    >
      <div className="bg-[var(--group)] rounded-[var(--r)] px-5 py-4">
        {usage ? (
          <Ring segments={segments} center={human(usage.total_bytes)} sub={t("s.storageTitle")} size={132} />
        ) : (
          <p className="m-0 text-[12.5px] text-[var(--meta)]">{busy ? t("s.storageScanning") : t("s.cleanupDesc")}</p>
        )}
      </div>

      {usage ? (
        <div className="mt-3 bg-[var(--group)] rounded-[var(--r)] px-5 py-4">
          <p className="m-0 text-[12.5px] font-medium">{t("s.cleanGroupDirect")}</p>
          <ul className="m-0 mt-2 list-none p-0 flex flex-col">
            {DIRECT_KINDS.map((k) => {
              const bytes = bytesOf(k.usage);
              const empty = bytes === 0;
              return (
                <li key={k.id}>
                  <label className={`flex items-center gap-2.5 py-1.5 text-[13px] ${empty ? "opacity-45" : "cursor-pointer"}`}>
                    <input type="checkbox" className={check} disabled={empty || busy} checked={direct.has(k.id)} onChange={() => toggleDirect(k.id)} />
                    <span>{t(k.labelKey)}</span>
                    <span className="text-[11.5px] text-[var(--meta)]">{t(k.effectKey)}</span>
                    <span className="ml-auto font-mono text-[11.5px] text-[var(--meta)] tabular-nums">{human(bytes)}</span>
                  </label>
                </li>
              );
            })}
          </ul>

          <div className="mt-4 flex items-baseline gap-3">
            <p className="m-0 text-[12.5px] font-medium">{t("s.cleanGroupTrain")}</p>
            {totalPages > 1 ? <span className="ml-auto font-mono text-[11.5px] text-[var(--meta)] tabular-nums">{t("s.pageOf", { cur: pageClamped, total: totalPages })}</span> : null}
          </div>
          <p className="m-0 mt-1 text-[11.5px] text-[var(--meta)] leading-relaxed">{t("s.cleanupDesc")}</p>
          {rows && rows.length === 0 ? <p className="m-0 mt-2 text-[12.5px] text-[var(--meta)]">{t("s.cleanupNothing")}</p> : null}
          <ul className="m-0 mt-1 list-none p-0">
            {pageRows.map((row) => (
              <li key={row.exp} className="py-2">
                <div className="flex items-baseline gap-3">
                  <span className="text-[13px] font-semibold truncate">{row.exp}</span>
                  <span className="ml-auto font-mono text-[11.5px] text-[var(--meta)] tabular-nums">{human(row.total_bytes)}</span>
                </div>
                <div className="mt-1 pl-1 flex flex-col">
                  {TRAIN_KINDS.map((k) => {
                    const info = row.kinds[k.id];
                    const empty = !info || info.bytes === 0;
                    return (
                      <label key={k.id} className={`flex items-center gap-2.5 py-1 text-[12.5px] ${empty ? "opacity-45" : "cursor-pointer"}`}>
                        <input type="checkbox" className={check} disabled={empty || busy} checked={train[row.exp]?.has(k.id) ?? false} onChange={() => toggleTrain(row.exp, k.id)} />
                        <span>{t(k.labelKey)}</span>
                        <span className="text-[11.5px] text-[var(--meta)]">{t(k.effectKey)}</span>
                        <span className="ml-auto font-mono text-[11px] text-[var(--meta)] tabular-nums">{human(info?.bytes ?? 0)}</span>
                      </label>
                    );
                  })}
                </div>
              </li>
            ))}
          </ul>
          {totalPages > 1 ? (
            <div className="flex items-center justify-center gap-3 pt-2 text-[12.5px] text-[var(--meta)]">
              <Btn disabled={pageClamped <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>{t("s.b41561d807")}</Btn>
              <span className="tabular-nums">{t("s.40a021ed44", { v0: pageClamped, v1: totalPages, v2: sorted.length })}</span>
              <Btn disabled={pageClamped >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>{t("s.67a246a344")}</Btn>
            </div>
          ) : null}

          <div className="mt-3 pt-3 flex items-center gap-3 shadow-[0_-1px_0_var(--hairline)]">
            <span className="text-[12.5px] text-[var(--meta)]" role="status">
              {msg || (pickedCount ? t("s.cleanPicked", { n: pickedCount, size: human(pickedBytes) }) : t("s.cleanNonePicked"))}
            </span>
            <span className="ml-auto">
              <Btn primary onClick={() => void apply()} busy={busy} disabled={busy || pickedCount === 0}>{t("s.cleanupApply")}</Btn>
            </span>
          </div>
        </div>
      ) : null}
    </Block>
  );
}
