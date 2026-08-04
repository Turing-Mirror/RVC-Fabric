import { invoke } from "@tauri-apps/api/core";
import { useEffect, useMemo, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import {
  getProvisionStatus,
  startProvision,
  cancelProvision,
  type ProvisionStatus,
  type ProvisionProgress,
} from "../lib/engine";
import { Btn, HelpMark } from "./ui";
import { MainGpuPicker, MAIN_GPU_AUTO, MAIN_GPU_TIP } from "./MainGpuPicker";

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

function formatDuration(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s} 秒`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} 分 ${s % 60} 秒`;
  return `${Math.floor(m / 60)} 小时 ${m % 60} 分`;
}

/**
 * 多久没有新字节就算「卡住了」。
 *
 * 下载是分段并发的，单段重连、服务器限速抖动都会让字节暂停几秒，太短会天天
 * 误报。12 秒足够长到不误报，又足够短到用户还没开始怀疑软件坏了。
 */
const STALL_AFTER_MS = 12_000;

function isCancelError(e: unknown): boolean {
  const s = String(e ?? "");
  return s.includes("已取消") || s.toLowerCase().includes("cancel");
}

/**
 * First-run / missing-Runtime gate: Runtime + VB-Cable 安装包。
 *
 * 引擎资源（hubert / rmvpe / ffmpeg）不在这里下，改到「其他 → 下载模型」按需补。
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
  const [extra, setExtra] = useState("");
  // Runtime 下完后准备 VB-Cable：ready=可点安装，failed=下载失败仍可跳过。
  const [vbcable, setVbcable] = useState<null | "ready" | "installing" | "failed">(
    null,
  );
  const [vbcableMsg, setVbcableMsg] = useState("");
  // 主显卡。-1 = 自动。只有多块 N 卡时才有得选，所以下面按需渲染。
  const [mainGpu, setMainGpu] = useState<number>(MAIN_GPU_AUTO);

  useEffect(() => {
    if (!open) return;
    void invoke<Record<string, unknown>>("config_get")
      .then((c) => setMainGpu(Number(c.main_gpu ?? MAIN_GPU_AUTO)))
      .catch(() => {
        /* 浏览器预览下没有配置，保持自动 */
      });
  }, [open]);

  const pickMainGpu = (v: number) => {
    setMainGpu(v);
    void invoke("config_set", { patch: { main_gpu: v } }).catch(() => {});
  };

  // 「进度条不动」这件事本身，用户是没法判断的：可能真在下（大包前几个百分点
  // 走得很慢），也可能连不上服务器，也可能下着下着断了。下载线程只在真的收到
  // 字节时才发事件，所以「没有事件」是有信息量的 —— 把它显式说出来。
  //
  // now 每秒推一次，用来把「已用时间」和「静默了多久」算出来；lastMove 记的是
  // 最后一次进度真正变化的时刻，重渲染不该重置它，所以放 ref 不放 state。
  const [now, setNow] = useState(() => Date.now());
  const lastMove = useRef({ at: 0, done: -1, phase: "" });
  const startedAt = useRef(0);

  useEffect(() => {
    if (!busy) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [busy]);

  useEffect(() => {
    const d = Number(progress?.done || 0);
    const ph = String(progress?.phase || "");
    // 换阶段（下载完转解压、转补引擎资源）同样算「有动静」，否则解压一开始
    // 就会因为不再有字节而被判成卡住。
    if (d !== lastMove.current.done || ph !== lastMove.current.phase) {
      lastMove.current = { at: Date.now(), done: d, phase: ph };
      setNow(Date.now());
    }
  }, [progress]);

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

  /** Runtime 之后：下 VB-Cable 安装包（软失败可跳过），再让用户点安装。 */
  async function prepareVbcable() {
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

  const start = async () => {
    setBusy(true);
    setError("");
    setVbcable(null);
    setVbcableMsg("");
    startedAt.current = Date.now();
    lastMove.current = { at: Date.now(), done: -1, phase: "" };
    setNow(Date.now());
    setProgress({ phase: "prepare", done: 0, total: 1, percent: 0, message: "准备…" });
    try {
      const r = await startProvision(variant, false);
      if (r.ok) {
        // 引擎资源（hubert/rmvpe/ffmpeg）不在首次补全里，改到「下载模型」按需下。
        // VB-Cable 仍随首次补全准备，否则游戏里听不到变声。
        await prepareVbcable();
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
  // Only the download phase reports bytes. Extract / vbcable emit done=0 total=1.
  const isDownload = String(progress?.phase || "") === "download";
  const connecting =
    showBar &&
    done <= 0 &&
    (String(progress?.phase || "").startsWith("connecting") ||
      String(progress?.message || "").includes("连接"));

  // 静默多久了。lastMove.at 为 0 表示这一轮还没开始，别把它当成静默了 55 年。
  const idleMs = lastMove.current.at ? now - lastMove.current.at : 0;
  const stalled = Boolean(showBar) && idleMs > STALL_AFTER_MS;
  const elapsedMs = startedAt.current ? now - startedAt.current : 0;

  return (
    <div className="absolute inset-0 z-[50] flex items-center justify-center bg-[color-mix(in_srgb,var(--ink)_28%,transparent)] p-6">
      <div className="w-full max-w-[520px] rounded-[var(--r)] bg-[var(--surface)] shadow-[0_22px_56px_-18px_rgba(20,26,33,.34)] p-7">
        <h2 className="text-[22px] font-semibold m-0 mb-2">补全运行时</h2>
        <p className="text-[13px] text-[var(--help)] m-0 mb-5 leading-relaxed">
          {info.recommend_reason ||
            "首次使用需下载运行时环境（含 PyTorch，需几 GB 空间），下载后自动部署。"}
          <br />
          完成后会准备 VB-Cable 虚拟声卡安装包。引擎资源（hubert / rmvpe / ffmpeg）改在「其他 → 下载模型」里按需补全。
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

        {/* 多块 N 卡才问。只有一块的时候「主显卡」是个没有意义的问题，
            摆在首次安装的流程里只会让人卡住。 */}
        {(info.nvidia_gpus?.length ?? 0) > 1 ? (
          <div className="mb-5">
            <div className="text-[12.5px] text-[var(--meta)] mb-2 flex items-center gap-[9px]">
              主显卡
              <HelpMark title={MAIN_GPU_TIP} />
            </div>
            <MainGpuPicker
              full
              gpus={info.nvidia_gpus || []}
              value={mainGpu}
              onChange={pickMainGpu}
              disabled={busy}
            />
            <p className="text-[11.5px] text-[var(--meta)] m-0 mt-2 leading-relaxed">
              你有多块 N 卡。不指定的话引擎用排在第一的那块，不一定是最快的那块。
              以后也可以在「其他 → 运行状态」里改。
            </p>
          </div>
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

            {/* 已用时间。一条不动的进度条配上「已用 6 分 20 秒」，至少能看出
                软件还活着、这一轮跑了多久。 */}
            {elapsedMs > 3000 ? (
              <div className="mt-1.5 text-[11.5px] text-[var(--meta)] tabular-nums">
                已用 {formatDuration(elapsedMs)}
              </div>
            ) : null}

            {/* 真的卡住了就直说。不说的话用户面对的是一条不动的进度条，
                只能干等或者强退 —— 强退之前下的那部分其实是留着的。 */}
            {stalled ? (
              <div className="mt-2 rounded-[var(--rs)] bg-[color-mix(in_srgb,var(--notify)_16%,transparent)] px-3 py-2 text-[11.5px] text-[var(--ink-muted)] leading-relaxed">
                已经 {formatDuration(idleMs)} 没有收到新数据。
                {isDownload
                  ? "可能是网络波动或服务器无响应，不是软件卡死。"
                  : "这一步不报进度，通常是在解压或校验文件，请耐心等待。"}
                <br />
                可以继续等；也可以点「取消」再重来一次 ——
                已经下好的部分留在本地，重开会接着下，不会白下。
              </div>
            ) : null}
          </div>
        ) : null}

        {extra ? (
          <p className="text-[12.5px] text-[var(--ink-muted)] m-0 mb-3">{extra}</p>
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
                  ? "已启动官方安装程序，请在弹窗中确认（需要管理员权限）"
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
          支持断点续传，中断后重新开始即可。请保持网络畅通。
        </p>
      </div>
    </div>
  );
}
