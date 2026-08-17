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
import { isEngineCoreReady } from "../lib/downloadModels";
import { MainGpuPicker, MAIN_GPU_AUTO, mainGpuTip } from "./MainGpuPicker";
import { t } from "../i18n/t";

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
  if (s < 60) return t("s.0cc05a38ad", { v0: s });
  const m = Math.floor(s / 60);
  if (m < 60) return t("s.2a94e5c93f", { v0: m, v1: s % 60 });
  return t("s.f7c13500d5", { v0: Math.floor(m / 60), v1: m % 60 });
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
  return s.includes(t("s.a5ffdc95ee")) || s.toLowerCase().includes("cancel");
}

/**
 * First-run / missing-Runtime gate: Runtime + VB-Cable 安装包。
 *
 * 引擎资源（hubert / rmvpe / ffmpeg）不在这里下，改到「广场 → 下载模型」按需补。
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
  // Runtime 下完后准备 VB-Cable：ready=可点安装，installed=装完了，
  // failed=下载或安装失败，仍可跳过。
  // 运行库这一步排在虚拟声卡前面：没有它变声根本起不来，比"游戏里听不到"更基础。
  const [vcr, setVcr] = useState<
    null | "ready" | "installing" | "installed" | "failed"
  >(null);
  const [vcrMsg, setVcrMsg] = useState("");
  const [vbcable, setVbcable] = useState<
    null | "ready" | "installing" | "installed" | "failed"
  >(null);
  const [vbcableMsg, setVbcableMsg] = useState("");
  /**
   * 引擎资源（hubert / rmvpe / ffmpeg，约 720MB）这一步。
   *
   * `null` = 不用问（已经有了）；`ask` = 摆在补全后面让用户自己决定；
   * 之后是下载中 / 好了 / 失败。
   *
   * 刻意不并进首次补全：DSP 变声和人声分离都用不到这三个文件，无条件下载
   * 等于让这两类用户白等 720MB。摆成「下一步」，跳过也能直接去变声。
   */
  const [core, setCore] = useState<
    null | "ask" | "downloading" | "done" | "failed"
  >(null);
  const [coreMsg, setCoreMsg] = useState("");
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
        const msg = ev.payload.message || t("s.44c7946c76");
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
      { id: "nvidia", label: t("s.4c65a5e25e") },
      { id: "nvidia50", label: t("s.e7a64d4aaf") },
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

  /** Runtime 之后先看运行库：装过就整条跳过，一个字都不提。 */
  async function prepareVcredist() {
    try {
      // 已装的机器占绝大多数，不该为异常用户多一次点击、多一次下载。
      if (await invoke<boolean>("vcredist_installed")) return;
    } catch {
      // 拿不到结论就当装过：宁可漏提示，也不要给正常用户凭空多一步。
      return;
    }
    setExtra(t("s.vcrPreparing"));
    setProgress({
      phase: "vcredist",
      done: 0,
      total: 1,
      percent: 0,
      message: t("s.vcrPreparing"),
    });
    try {
      await invoke("assets_ensure_vcredist");
      setExtra("");
      setVcr("ready");
    } catch (e) {
      setExtra("");
      setVcrMsg(String(e));
      setVcr("failed");
    }
  }

  /** Runtime 之后：下 VB-Cable 安装包（软失败可跳过），再让用户点安装。 */
  async function prepareVbcable() {
    setExtra(t("s.094beaeab9"));
    setProgress({
      phase: "vbcable",
      done: 0,
      total: 1,
      percent: 0,
      message: t("s.094beaeab9"),
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
    setVcr(null);
    setVcrMsg("");
    setVbcable(null);
    setVbcableMsg("");
    setCore(null);
    setCoreMsg("");
    startedAt.current = Date.now();
    lastMove.current = { at: Date.now(), done: -1, phase: "" };
    setNow(Date.now());
    setProgress({ phase: "prepare", done: 0, total: 1, percent: 0, message: t("s.2105061e3e") });
    try {
      const r = await startProvision(variant, false);
      if (r.ok) {
        // 引擎资源不并进补全本体，但补全完要主动问一句 —— 以前完全不提，用户
        // 点开实时变声才发现还要再下 720MB，那一下的挫败是可以避免的。
        try {
          const ready = await isEngineCoreReady();
          setCore(ready ? null : "ask");
        } catch {
          /* 预览模式：拿不到状态就不问 */
        }
        await prepareVcredist();
        // VB-Cable 仍随首次补全准备，否则游戏里听不到变声。
        await prepareVbcable();
      } else if (isCancelError(r.message)) {
        finishCancel();
      } else {
        setError(r.message || t("s.44c7946c76"));
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
  const phase = String(progress?.phase || "");
  const isDownload = phase === "download";
  const retryN = (() => {
    const m = /^retry:(\d+)$/.exec(phase);
    return m ? Number(m[1]) : 0;
  })();
  const reconnecting = Boolean(showBar) && (phase === "retry" || retryN > 0);
  const connecting =
    showBar &&
    done <= 0 &&
    (reconnecting ||
      phase.startsWith("connecting") ||
      String(progress?.message || "").includes(t("s.7328deebb5")));

  // 静默多久了。lastMove.at 为 0 表示这一轮还没开始，别把它当成静默了 55 年。
  const idleMs = lastMove.current.at ? now - lastMove.current.at : 0;
  const stalled = Boolean(showBar) && idleMs > STALL_AFTER_MS;
  const elapsedMs = startedAt.current ? now - startedAt.current : 0;

  return (
    <div className="absolute inset-0 z-[50] flex items-center justify-center bg-[color-mix(in_srgb,var(--ink)_28%,transparent)] p-6">
      <div className="w-full max-w-[520px] rounded-[var(--r)] bg-[var(--surface)] shadow-[0_22px_56px_-18px_rgba(20,26,33,.34)] p-7">
        <h2 className="text-[22px] font-semibold m-0 mb-2">{t("s.405125fb37")}</h2>
        <p className="text-[13px] text-[var(--help)] m-0 mb-5 leading-relaxed">
          {info.recommend_reason ||
            t("s.1e1016e5c8")}
          <br />{t("s.7d4cfa5986")}</p>

        <div className="text-[12.5px] text-[var(--meta)] mb-2">{t("s.6a6564705b")}</div>
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
                    <span className="text-[11.5px] text-[var(--accent)]">{t("s.62b46f24ae")}</span>
                  ) : null}
                  {sizeText ? (
                    <span className="text-[11.5px] text-[var(--meta)]">
                      {t("s.244d1be15c", { v0: sizeText })}
                    </span>
                  ) : null}
                </span>
              </button>
            );
          })}
        </div>

        {info.gpus && info.gpus.length > 0 ? (
          <p className="text-[12px] text-[var(--meta)] m-0 mb-4">
            {t("s.af8a2d5711", { v0: info.gpus.join(" · ") })}
          </p>
        ) : null}

        {/* 多块 N 卡才问。只有一块的时候「主显卡」是个没有意义的问题，
            摆在首次安装的流程里只会让人卡住。 */}
        {(info.nvidia_gpus?.length ?? 0) > 1 ? (
          <div className="mb-5">
            <div className="text-[12.5px] text-[var(--meta)] mb-2 flex items-center gap-[9px]">{t("s.6b26feecc1")}<HelpMark title={mainGpuTip()} />
            </div>
            <MainGpuPicker
              full
              gpus={info.nvidia_gpus || []}
              value={mainGpu}
              onChange={pickMainGpu}
              disabled={busy}
            />
            <p className="text-[11.5px] text-[var(--meta)] m-0 mt-2 leading-relaxed">{t("s.2de72cf04d")}</p>
          </div>
        ) : null}

        {showBar ? (
          <div className="mb-4">
            <div className="flex justify-between gap-3 text-[12px] text-[var(--meta)] mb-1.5">
              <span className="min-w-0 flex-1 truncate">
                {progress?.message || progress?.phase || t("s.65188d08a2")}
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
              <div className="mt-1.5 text-[11.5px] text-[var(--meta)]">{t("s.502c5adda6")}</div>
            ) : null}

            {/* 已用时间。一条不动的进度条配上「已用 6 分 20 秒」，至少能看出
                软件还活着、这一轮跑了多久。 */}
            {elapsedMs > 3000 ? (
              <div className="mt-1.5 text-[11.5px] text-[var(--meta)] tabular-nums">
                {t("s.fa2f7e5279", { v0: formatDuration(elapsedMs) })}
              </div>
            ) : null}

            {/* 真的卡住了就直说。不说的话用户面对的是一条不动的进度条，
                只能干等或者强退 —— 强退之前下的那部分其实是留着的。 */}
            {stalled ? (
              <div className="mt-2 rounded-[var(--rs)] bg-[color-mix(in_srgb,var(--notify)_16%,transparent)] px-3 py-2 text-[11.5px] text-[var(--ink-muted)] leading-relaxed">
                {t("s.2a4fa38f1e", { v0: formatDuration(idleMs) })}
                {isDownload
                  ? t("s.7d2fe2ae0a")
                  : t("s.703e6f531a")}
                <br />{t("s.de5de9e783")}</div>
            ) : null}
          </div>
        ) : null}

        {extra ? (
          <p className="text-[12.5px] text-[var(--ink-muted)] m-0 mb-3">{extra}</p>
        ) : null}

        {error ? (
          <p className="text-[12.5px] text-[#c43] m-0 mb-3 leading-relaxed whitespace-pre-line">
            {error}
          </p>
        ) : null}

        {vcr ? (
          <div className="rounded-[var(--rs)] bg-[color-mix(in_srgb,var(--ink)_4%,transparent)] px-3.5 py-3 mb-4">
            <div className="text-[13.5px] mb-1">{t("s.vcrTitle")}</div>
            <div className="text-[12.5px] text-[var(--help)] leading-relaxed">
              {vcr === "failed"
                ? vcrMsg
                : vcr === "installing"
                  ? t("s.vcrInstalling")
                  : vcr === "installed"
                    ? t("s.vcrDone")
                    : t("s.vcrNeeded")}
            </div>
          </div>
        ) : null}

        {vbcable ? (
          <div className="rounded-[var(--rs)] bg-[color-mix(in_srgb,var(--ink)_4%,transparent)] px-3.5 py-3 mb-4">
            <div className="text-[13.5px] mb-1">{t("s.3d4e683008")}</div>
            <div className="text-[12.5px] text-[var(--help)] leading-relaxed">
              {vbcable === "failed"
                ? t("s.d80c650a49", { v0: vbcableMsg })
                : vbcable === "installing"
                  ? t("s.vbcableInstalling")
                  : vbcable === "installed"
                    ? t("s.vbcableDone")
                    : t("s.c946d45a63")}
            </div>
          </div>
        ) : null}

        {core ? (
          <div className="rounded-[var(--rs)] bg-[color-mix(in_srgb,var(--ink)_4%,transparent)] px-3.5 py-3 mb-4">
            <div className="text-[13.5px] mb-1">{t("extras.engineTitle")}</div>
            <div className="text-[12.5px] text-[var(--help)] leading-relaxed">
              {core === "failed"
                ? t("s.provCoreFailed", { v0: coreMsg })
                : core === "downloading"
                  ? t("s.provCoreDownloading")
                  : core === "done"
                    ? t("s.provCoreDone")
                    : t("s.provCoreAsk")}
            </div>
          </div>
        ) : null}

        <div className="flex items-center gap-2 justify-end">
          {core === "ask" || core === "failed" ? (
            <>
              {/* 跳过也能直接去变声：DSP 变声不需要这三个文件。 */}
              <Btn onClick={onDone}>{t("s.provCoreSkip")}</Btn>
              <Btn
                primary
                onClick={() => {
                  setCore("downloading");
                  setCoreMsg("");
                  void invoke("assets_ensure_engine_core")
                    .then(() => setCore("done"))
                    .catch((e) => {
                      setCoreMsg(String(e));
                      setCore("failed");
                    });
                }}
              >{t("s.provCoreGet")}</Btn>
            </>
          ) : core === "downloading" ? (
            <Btn disabled>{t("s.provCoreDownloading")}</Btn>
          ) : vcr === "ready" || vcr === "failed" ? (
            <>
              {/* 跳过也走得下去：跳过的人还能在设置页补装。 */}
              <Btn onClick={() => setVcr(null)}>{t("s.33246f6a5e")}</Btn>
              {vcr === "ready" ? (
                <Btn
                  primary
                  onClick={() => {
                    setVcr("installing");
                    setVcrMsg("");
                    void invoke("vcredist_install")
                      .then(() => setVcr("installed"))
                      .catch((e) => {
                        setVcrMsg(String(e));
                        setVcr("failed");
                      });
                  }}
                >{t("s.vcrInstall")}</Btn>
              ) : null}
            </>
          ) : vcr === "installing" ? (
            <Btn disabled>{t("s.vcrInstalling")}</Btn>
          ) : vbcable ? (
            <>
              <Btn onClick={onDone}>{vbcable === "ready" ? t("s.31a98593f1") : t("s.33246f6a5e")}</Btn>
              {vbcable === "ready" ? (
                <Btn
                  primary
                  onClick={() => {
                    setVbcable("installing");
                    // 静默安装，装完才 resolve —— 状态得跟到底，否则界面会
                    // 一直停在「正在安装」，用户不知道能不能关。
                    void invoke("assets_install_vbcable")
                      .then(() => setVbcable("installed"))
                      .catch((e) => {
                        setVbcableMsg(String(e));
                        setVbcable("failed");
                      });
                  }}
                >{t("s.087db63ab1")}</Btn>
              ) : null}
            </>
          ) : busy ? (
            <Btn onClick={onCancelClick}>{t("s.4d0b4688c7")}</Btn>
          ) : (
            <>
              {onDismiss ? <Btn onClick={onDismiss}>{t("s.479fcc1cc0")}</Btn> : null}
              <Btn primary onClick={() => void start()}>
                {t("s.92f35590d5")}
                {selectedSizeLabel ? t("s.e592773b6a", { v0: selectedSizeLabel }) : ""}
              </Btn>
            </>
          )}
        </div>
        <p className="text-[11.5px] text-[var(--meta)] m-0 mt-4 leading-relaxed">{t("s.9a79ee8bcd")}</p>
      </div>
    </div>
  );
}
