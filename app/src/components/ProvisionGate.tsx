import { invoke } from "@tauri-apps/api/core";
import { useEffect, useMemo, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import {
  getProvisionStatus,
  startProvision,
  cancelProvision,
  type ProvisionStatus,
  type ProvisionProgress,
} from "../lib/engine";
import { Btn } from "./ui";

type VariantRow = {
  id: string;
  label: string;
  size_bytes?: number;
  size_label?: string;
};

type Props = {
  open: boolean;
  initial?: ProvisionStatus;
  onDone: () => void;
  onDismiss?: () => void;
};

function formatBytes(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "—";
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)} KB`;
  return `${Math.round(n)} B`;
}

function isCancelError(e: unknown): boolean {
  const s = String(e ?? "");
  return s.includes("已取消") || s.toLowerCase().includes("cancel");
}

/**
 * First-run / missing-Runtime gate: pick variant, download + extract.
 * Only shown when need_provision; does not change everyday VC flow once ready.
 */
export function ProvisionGate({ open, initial, onDone, onDismiss }: Props) {
  const [info, setInfo] = useState<ProvisionStatus>(initial || {});
  const [variant, setVariant] = useState(
    initial?.recommended_variant && initial.recommended_variant !== "unknown"
      ? initial.recommended_variant
      : "nvidia",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState<ProvisionProgress | null>(null);
  // Must stay above the `if (!open) return null` below. Declared after it, the
  // hook count changed the moment the gate opened, React threw #310 and tore
  // down the whole tree — a blank window on exactly the machines that need the
  // gate (a fresh install with no Runtime yet).
  const [extra, setExtra] = useState<string>("");
  // Last step of first-run setup. The gate used to fetch the VB-Cable package
  // and then close on the spot, so the one thing the user still had to do —
  // actually run the driver installer — was never offered and the window just
  // disappeared. `null` means we are not at that step yet.
  const [vbcable, setVbcable] = useState<null | "ready" | "installing" | "failed">(
    null,
  );
  const [vbcableMsg, setVbcableMsg] = useState("");

  useEffect(() => {
    if (!open) return;
    void getProvisionStatus().then((p) => {
      setInfo(p);
      if (p.recommended_variant && p.recommended_variant !== "unknown") {
        setVariant(p.recommended_variant);
      }
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    // `listen` resolves asynchronously; closing the gate before it does used to
    // drop the unlisten handle on the floor and leak the registration.
    let disposed = false;
    let un: (() => void) | undefined;
    void listen<ProvisionProgress>("provision-progress", (ev) => {
      setProgress(ev.payload);
      if (ev.payload.phase === "error") {
        const msg = ev.payload.message || "补全失败";
        if (isCancelError(msg)) {
          // Cancel is not a failure to display; start()'s catch also handles it.
          return;
        }
        setError(msg);
      }
    }).then((fn) => {
      if (disposed) fn();
      else un = fn;
    });
    return () => {
      disposed = true;
      un?.();
    };
  }, [open]);

  const variants: VariantRow[] = useMemo(() => {
    const list = (info.variants || []) as VariantRow[];
    if (list.length > 0) return list;
    return [
      { id: "nvidia", label: "NVIDIA（推荐大多数 N 卡）" },
      { id: "nvidia50", label: "NVIDIA 50 系（RTX 50xx）" },
      { id: "amd", label: "AMD / Intel（DirectML）" },
    ];
  }, [info.variants]);

  const selectedSizeLabel = useMemo(() => {
    const row = variants.find((v) => v.id === variant);
    if (row?.size_label && row.size_label !== "0 B") return row.size_label;
    if (row?.size_bytes && row.size_bytes > 0) return formatBytes(row.size_bytes);
    // Fallback only when catalog had nothing for this id
    if (variant === info.recommended_variant && info.recommended_size_label) {
      return info.recommended_size_label;
    }
    return "";
  }, [variants, variant, info.recommended_variant, info.recommended_size_label]);

  if (!open) return null;

  const finishCancel = () => {
    setBusy(false);
    setProgress(null);
    setError("");
    setExtra("");
    // User asked to leave the gate after cancel (task already stopped).
    onDismiss?.();
  };

  const start = async () => {
    setBusy(true);
    setError("");
    setProgress({ phase: "prepare", done: 0, total: 1, percent: 0, message: "准备…" });
    try {
      const r = await startProvision(variant, false);
      if (r.ok) {
        // Runtime is only step one; engine-core and VB-Cable follow before the
        // gate is allowed to close. runExtras leaves the VB-Cable step on
        // screen, and that step's own buttons close the gate.
        await runExtras();
      } else if (isCancelError(r.message)) {
        finishCancel();
      } else {
        setError(r.message || "补全失败");
      }
    } catch (e) {
      if (isCancelError(e)) {
        finishCancel();
      } else {
        setError(String(e));
      }
    } finally {
      setBusy(false);
    }
  };

  const onCancelClick = () => {
    // Set the cancel flag first so the download stops, then leave the gate.
    // start()'s catch will also hit finishCancel (idempotent) when the long
    // invoke returns 「已取消」.
    void (async () => {
      try {
        await cancelProvision();
      } catch {
        /* cancel is best-effort */
      }
      finishCancel();
    })();
  };

  const done = Number(progress?.done || 0);
  const total = Math.max(Number(progress?.total || 0), 1);
  const pctRaw =
    progress?.percent != null && !Number.isNaN(Number(progress.percent))
      ? Number(progress.percent)
      : (done / total) * 100;
  const pct = Math.min(100, Math.max(0, pctRaw));
  // Multi-GB packages stay under 0.5% for a long time; never show bare "0%" once
  // any bytes have landed, and keep one decimal under 10%.
  const pctLabel =
    done > 0 && pct < 0.1
      ? "<0.1%"
      : pct < 10
        ? `${pct.toFixed(1)}%`
        : `${Math.round(pct)}%`;
  const speedLabel =
    progress?.speed_label && progress.speed_label !== "—"
      ? progress.speed_label
      : progress?.speed_bps && progress.speed_bps > 0
        ? formatBytes(progress.speed_bps) + "/s"
        : "";
  const barWidth =
    done > 0 && pct < 0.5 ? Math.max(pct, 0.5) : Math.min(100, pct);
  const showBar = busy && progress && progress.phase !== "error";
  // Only the download phase reports bytes. Extract / engine-core / vbcable all
  // emit done=0 total=1, which the byte line below used to read as "no bytes
  // yet" and answer with 「正在连接服务器」 — while the user was in fact
  // watching an unpack that had nothing to do with the network.
  const isDownload = String(progress?.phase || "") === "download";
  const connecting =
    showBar &&
    done <= 0 &&
    (String(progress?.phase || "").startsWith("connecting") ||
      String(progress?.message || "").includes("连接"));

  // Runtime alone is not a usable install: the worker needs engine-core
  // (hubert / rmvpe / ffmpeg) and the user needs VB-Cable for anyone to hear
  // the converted voice. Chain both right after the Runtime step.
  async function runExtras() {
    // engine-core is required: without hubert / rmvpe the worker cannot start
    // at all, so a failure here has to block.
    setExtra("正在补全引擎资源（hubert / rmvpe / ffmpeg）…");
    setProgress({
      phase: "engine-core",
      done: 0,
      total: 1,
      percent: 0,
      message: "正在补全引擎资源（hubert / rmvpe / ffmpeg）…",
    });
    try {
      await invoke("assets_ensure_engine_core");
    } catch (e) {
      setExtra(`引擎资源补全失败：${String(e)}`);
      throw e;
    }

    // VB-Cable is not required to open the app — without it you simply cannot
    // be heard in games, and 「监听自己」 still works. Blocking the whole
    // install on it would trap users behind a flaky download for something
    // they can fetch later from 「说明」.
    setExtra("正在准备虚拟声卡安装包…");
    setProgress({
      phase: "vbcable",
      done: 0,
      total: 1,
      percent: 0,
      message: "正在准备虚拟声卡安装包…",
    });
    try {
      await invoke("assets_ensure_vbcable");
      setExtra("");
      setVbcable("ready");
    } catch (e) {
      setExtra("");
      setVbcableMsg(String(e));
      setVbcable("failed");
    }
  }

  return (
    <div className="absolute inset-0 z-[50] flex items-center justify-center bg-[color-mix(in_srgb,var(--ink)_28%,transparent)] p-6">
      <div className="w-full max-w-[520px] rounded-[var(--r)] bg-[var(--surface)] shadow-[0_22px_56px_-18px_rgba(20,26,33,.34)] p-7">
        <h2 className="text-[22px] font-semibold m-0 mb-2">补全运行时</h2>
        <p className="text-[13px] text-[var(--help)] m-0 mb-5 leading-relaxed">
          {info.recommend_reason ||
            "首次使用需要下载 Python 运行时（含 PyTorch，体积数 GB）。安装包本身不含 Runtime。"}
        </p>

        <div className="text-[12.5px] text-[var(--meta)] mb-2">运行时版本</div>
        <div className="flex flex-col gap-2 mb-5">
          {variants.map((v) => {
            const on = v.id === variant;
            const sizeText =
              v.size_label && v.size_label !== "0 B"
                ? v.size_label
                : v.size_bytes && v.size_bytes > 0
                  ? formatBytes(v.size_bytes)
                  : "";
            return (
              <button
                key={v.id}
                type="button"
                disabled={busy}
                onClick={() => setVariant(v.id)}
                className={[
                  "text-left border-0 rounded-[var(--rs)] px-3.5 py-2.5 cursor-pointer",
                  "text-[13.5px] transition-colors",
                  on
                    ? "bg-[var(--accent-soft)] text-[var(--ink)] shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--accent)_40%,transparent)]"
                    : "bg-[color-mix(in_srgb,var(--ink)_4%,transparent)] text-[var(--ink-muted)]",
                ].join(" ")}
              >
                <span className="inline-flex items-center flex-wrap gap-x-2 gap-y-0.5">
                  <span>{v.label}</span>
                  {info.recommended_variant === v.id ? (
                    <span className="text-[11.5px] text-[var(--accent)]">推荐</span>
                  ) : null}
                  {sizeText ? (
                    <span className="text-[11.5px] text-[var(--meta)]">约 {sizeText}</span>
                  ) : null}
                </span>
              </button>
            );
          })}
        </div>

        {info.gpus && info.gpus.length > 0 ? (
          <p className="text-[12px] text-[var(--meta)] m-0 mb-4">
            检测到显卡：{info.gpus.join(" · ")}
          </p>
        ) : null}

        {extra ? (
          <p className="text-[12.5px] text-[var(--ink-muted)] m-0 mb-3">{extra}</p>
        ) : null}

        {showBar ? (
          <div className="mb-4">
            <div className="flex justify-between gap-3 text-[12px] text-[var(--meta)] mb-1.5">
              <span className="min-w-0 flex-1 truncate">
                {progress?.message || progress?.phase || "下载中…"}
              </span>
              <span className="shrink-0 tabular-nums flex items-center gap-2">
                {speedLabel ? (
                  <span className="text-[var(--accent)]">{speedLabel}</span>
                ) : null}
                <span>{connecting ? "…" : pctLabel}</span>
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-[color-mix(in_srgb,var(--ink)_10%,transparent)] overflow-hidden">
              {connecting ? (
                <div className="h-full w-1/3 bg-[var(--accent)] rounded-full animate-pulse" />
              ) : (
                <div
                  className="h-full bg-[var(--accent)] rounded-full transition-[width] duration-200"
                  style={{ width: `${barWidth}%` }}
                />
              )}
            </div>
            {isDownload && done > 0 ? (
              <div className="mt-1.5 text-[11.5px] text-[var(--meta)] tabular-nums flex justify-between gap-2">
                <span>
                  {formatBytes(done)} / {formatBytes(total)}
                </span>
                {speedLabel ? <span>{speedLabel}</span> : null}
              </div>
            ) : isDownload ? (
              <div className="mt-1.5 text-[11.5px] text-[var(--meta)]">
                正在连接服务器，稍后显示进度…
              </div>
            ) : null}
          </div>
        ) : null}

        {error ? (
          <p className="text-[12.5px] text-[#c43] m-0 mb-3 leading-relaxed">{error}</p>
        ) : null}

        {vbcable ? (
          <div className="rounded-[var(--rs)] bg-[color-mix(in_srgb,var(--ink)_4%,transparent)] px-3.5 py-3 mb-4">
            <div className="text-[13.5px] mb-1">最后一步：安装虚拟声卡</div>
            <div className="text-[12.5px] text-[var(--help)] leading-relaxed">
              {vbcable === "failed"
                ? `安装包没准备好：${vbcableMsg}。可以稍后在「说明」页重试。`
                : vbcable === "installing"
                  ? "已启动官方安装程序，请在弹出的窗口里确认（需要管理员权限）"
                  : "没有它，游戏和语音软件里的人听不到变声后的你。点「安装」会弹出官方安装程序和管理员确认。"}
            </div>
          </div>
        ) : null}

        <div className="flex items-center gap-2 justify-end">
          {vbcable ? (
            <>
              <Btn onClick={onDone}>{vbcable === "ready" ? "跳过" : "完成"}</Btn>
              {vbcable === "ready" ? (
                <Btn
                  primary
                  onClick={() => {
                    setVbcable("installing");
                    void invoke("assets_install_vbcable").catch((e) => {
                      setVbcableMsg(String(e));
                      setVbcable("failed");
                    });
                  }}
                >
                  安装
                </Btn>
              ) : null}
            </>
          ) : busy ? (
            <Btn onClick={onCancelClick}>取消</Btn>
          ) : (
            <>
              {onDismiss ? <Btn onClick={onDismiss}>稍后</Btn> : null}
              <Btn primary onClick={() => void start()}>
                开始下载
                {selectedSizeLabel ? `（约 ${selectedSizeLabel}）` : ""}
              </Btn>
            </>
          )}
        </div>
        <p className="text-[11.5px] text-[var(--meta)] m-0 mt-4 leading-relaxed">
          下载支持断点续传；文件缓存在 User_Data/update_cache/runtime。请保持网络畅通。
        </p>
      </div>
    </div>
  );
}
