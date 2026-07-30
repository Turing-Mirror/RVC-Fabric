import { useEffect, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import {
  getProvisionStatus,
  startProvision,
  cancelProvision,
  type ProvisionStatus,
  type ProvisionProgress,
} from "../lib/engine";
import { Btn } from "./ui";

type Props = {
  open: boolean;
  initial?: ProvisionStatus;
  onDone: () => void;
  onDismiss?: () => void;
};

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
    let un: (() => void) | undefined;
    void listen<ProvisionProgress>("provision-progress", (ev) => {
      setProgress(ev.payload);
      if (ev.payload.phase === "error") {
        setError(ev.payload.message || "补全失败");
      }
    }).then((fn) => {
      un = fn;
    });
    return () => {
      un?.();
    };
  }, [open]);

  if (!open) return null;

  const variants =
    info.variants ||
    [
      { id: "nvidia", label: "NVIDIA（推荐大多数 N 卡）" },
      { id: "nvidia50", label: "NVIDIA 50 系（RTX 50xx）" },
      { id: "amd", label: "AMD / Intel（DirectML）" },
    ];

  const start = async () => {
    setBusy(true);
    setError("");
    setProgress({ phase: "prepare", done: 0, total: 1, percent: 0, message: "准备…" });
    try {
      const r = await startProvision(variant, false);
      if (r.ok) {
        onDone();
      } else {
        setError(r.message || "补全失败");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const pct = Math.round(Number(progress?.percent || 0));

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
                {v.label}
                {info.recommended_variant === v.id ? (
                  <span className="text-[11.5px] text-[var(--accent)] ml-2">推荐</span>
                ) : null}
              </button>
            );
          })}
        </div>

        {info.gpus && info.gpus.length > 0 ? (
          <p className="text-[12px] text-[var(--meta)] m-0 mb-4">
            检测到显卡：{info.gpus.join(" · ")}
          </p>
        ) : null}

        {busy && progress ? (
          <div className="mb-4">
            <div className="flex justify-between text-[12px] text-[var(--meta)] mb-1.5">
              <span>{progress.message || progress.phase}</span>
              <span>{pct}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-[color-mix(in_srgb,var(--ink)_10%,transparent)] overflow-hidden">
              <div
                className="h-full bg-[var(--accent)] rounded-full transition-[width] duration-200"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        ) : null}

        {error ? (
          <p className="text-[12.5px] text-[#c43] m-0 mb-3 leading-relaxed">{error}</p>
        ) : null}

        <div className="flex items-center gap-2 justify-end">
          {busy ? (
            <Btn onClick={() => void cancelProvision()}>取消</Btn>
          ) : (
            <>
              {onDismiss ? <Btn onClick={onDismiss}>稍后</Btn> : null}
              <Btn primary onClick={() => void start()}>
                开始下载
                {info.recommended_size_label
                  ? `（约 ${info.recommended_size_label}）`
                  : ""}
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
