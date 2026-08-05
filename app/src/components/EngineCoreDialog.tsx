import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn } from "./ui";
import { getAssetsStatus, type AssetsStatus } from "../lib/downloadModels";

type ProvProgress = {
  phase?: string;
  done?: number;
  total?: number;
  percent?: number;
  message?: string;
  speed_label?: string;
};

/**
 * 仅补全引擎资源（hubert / rmvpe / ffmpeg）。
 *
 * 给「开启变声」和打开音频工具用：不要跳进「下载模型」（人声分离 / 训练底模）
 * 那一套。用户只是想实时变声时，看见训练底模会误以为必须训模型。
 */
export function EngineCoreDialog({
  open,
  onClose,
  reason,
}: {
  open: boolean;
  onClose: () => void;
  reason?: string;
}) {
  const [assets, setAssets] = useState<AssetsStatus | null>(null);
  const [prog, setProg] = useState<ProvProgress | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const busyRef = useRef(false);

  const ready = assets == null ? null : Boolean(assets.engine_core_ready);

  useEffect(() => {
    if (!open) return;
    setMsg("");
    setProg(null);
    setAssets(null);
    void getAssetsStatus().then(setAssets).catch(() => setAssets({ engine_core_ready: false }));
    let disposed = false;
    let un: (() => void) | undefined;
    void listen<ProvProgress>("provision-progress", (ev) => {
      const ph = String(ev.payload?.phase || "");
      if (ph === "engine-core" || ph.includes("engine")) {
        setProg(ev.payload);
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

  if (!open) return null;

  const pct =
    prog?.percent != null
      ? Math.min(100, Math.max(0, Number(prog.percent)))
      : prog?.total
        ? Math.round(((prog.done ?? 0) / Math.max(prog.total, 1)) * 100)
        : 0;

  const start = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setMsg("");
    setProg({
      phase: "engine-core",
      done: 0,
      total: 1,
      percent: 0,
      message: "准备下载引擎资源…",
    });
    try {
      await invoke("assets_ensure_engine_core");
      const st = await getAssetsStatus();
      setAssets(st);
      setProg(null);
      if (st.engine_core_ready) {
        setMsg("引擎资源已就绪。关闭本窗口后，再点一次「开启变声」即可。");
      } else {
        setMsg(
          `下载后仍不完整：${(st.engine_core_missing || []).join("、") || "未知"}`,
        );
      }
    } catch (e) {
      setMsg(String(e));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[80] grid place-items-center p-6 bg-[color-mix(in_srgb,var(--ink)_28%,transparent)]"
      onClick={busy ? undefined : onClose}
    >
      <div
        className="w-full max-w-[480px] rounded-[var(--r)] bg-[var(--surface)] p-6 shadow-[0_20px_60px_rgba(0,0,0,0.22)]"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="m-0 mb-2 text-[17px] font-semibold">补全引擎资源</h3>
        <p className="m-0 mb-4 text-[12.5px] text-[var(--ink-muted)] leading-relaxed">
          {reason ||
            "实时变声需要 hubert / rmvpe / ffmpeg（约 720 MB）。与训练底模、人声分离模型无关，只下这一份即可。"}
        </p>

        <div className="rounded-[var(--rs)] bg-[color-mix(in_srgb,var(--accent)_8%,transparent)] shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--accent)_28%,transparent)] px-3.5 py-3">
          <div className="text-[13.5px] font-semibold">
            引擎资源
            {ready === true ? (
              <span className="ml-2 text-[12px] font-normal text-[var(--meta)]">
                已就绪
              </span>
            ) : ready === false ? (
              <span className="ml-2 text-[12px] font-normal text-[var(--accent)]">
                未安装 · 约 720 MB
              </span>
            ) : (
              <span className="ml-2 text-[12px] font-normal text-[var(--meta)]">
                检查中…
              </span>
            )}
          </div>
          <p className="m-0 mt-1 text-[12.5px] text-[var(--help)] leading-relaxed">
            hubert_base.pt、rmvpe、ffmpeg / ffprobe。全显卡共用。
            {assets?.engine_core_missing?.length
              ? ` 当前缺少：${assets.engine_core_missing.join("、")}`
              : ""}
          </p>
          {busy && prog ? (
            <div className="mt-3">
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-[color-mix(in_srgb,var(--ink)_10%,transparent)]">
                <div
                  className="h-full bg-[var(--accent)] transition-[width] duration-200 rounded-full"
                  style={{ width: `${Math.max(pct, pct > 0 ? 0.5 : 0)}%` }}
                />
              </div>
              <p className="m-0 mt-1.5 text-[12px] text-[var(--meta)]">
                {prog.message || "下载中…"}
                {prog.speed_label ? ` · ${prog.speed_label}` : ""}
                {pct > 0 ? ` · ${Math.round(pct)}%` : ""}
              </p>
            </div>
          ) : null}
        </div>

        {msg ? (
          <p className="m-0 mt-3 text-[12.5px] text-[var(--ink-muted)] leading-relaxed break-all">
            {msg}
          </p>
        ) : null}

        <div className="mt-5 flex justify-end gap-2.5">
          <Btn onClick={onClose} disabled={busy}>
            {ready === true ? "完成" : "取消"}
          </Btn>
          {ready !== true ? (
            <Btn primary disabled={busy || ready === null} onClick={() => void start()}>
              {busy ? "下载中…" : "下载引擎资源"}
            </Btn>
          ) : null}
        </div>
      </div>
    </div>
  );
}
