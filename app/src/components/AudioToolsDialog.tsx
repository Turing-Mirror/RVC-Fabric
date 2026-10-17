import { useEffect, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { Btn } from "./ui";
import { Modal } from "./Modal";
import { t } from "../i18n/t";
import { useI18n } from "../i18n";
import { audioToolsDownloading, ensureAudioTools } from "../lib/downloadModels";

type Phase = "ask" | "downloading" | "done" | "failed";

type Props = {
  open: boolean;
  /** 包体大小（字节），来自后端，提示里显示「约 xx MB」。 */
  sizeBytes?: number;
  onClose: () => void;
};

function formatMb(n?: number): string {
  return n && n > 0 ? `${Math.round(n / 1e6)} MB` : "";
}

/**
 * 音频组件（ffmpeg / ffprobe）的下载提示。
 *
 * 安装包不带这两个文件。与运行时的弹窗同一种样子：说明用途和大小，由用户
 * 决定下不下。下载中可以关掉窗口，任务在后台继续。
 */
export function AudioToolsDialog({ open, sizeBytes, onClose }: Props) {
  useI18n();
  const [phase, setPhase] = useState<Phase>("ask");
  const [error, setError] = useState("");
  const [pct, setPct] = useState(0);

  useEffect(() => {
    if (!open) return;
    setPhase(audioToolsDownloading() ? "downloading" : "ask");
    setError("");
    let disposed = false;
    let un: (() => void) | undefined;
    void listen<{ percent?: number }>("audio-tools-progress", (ev) => {
      setPct(Math.min(100, Math.max(0, Number(ev.payload.percent || 0))));
    }).then((fn) => {
      if (disposed) fn();
      else un = fn;
    });
    return () => {
      disposed = true;
      un?.();
    };
  }, [open]);

  const start = () => {
    setPhase("downloading");
    setError("");
    setPct(0);
    ensureAudioTools()
      .then(() => setPhase("done"))
      .catch((e) => {
        setError(String(e));
        setPhase("failed");
      });
  };

  const size = formatMb(sizeBytes);

  return (
    <Modal open={open} z={60}>
      <div className="w-full max-w-[440px] rounded-[var(--r)] bg-[var(--surface)] shadow-[0_22px_56px_-18px_rgba(20,26,33,.34)] p-7">
        <h2 className="text-[22px] font-semibold m-0 mb-2">{t("audioTools.title")}</h2>
        <p className="text-[13px] text-[var(--help)] m-0 mb-5 leading-relaxed whitespace-pre-line">
          {phase === "done"
            ? t("audioTools.done")
            : phase === "failed"
              ? error
              : t("audioTools.desc", { v0: size })}
        </p>

        {phase === "downloading" ? (
          <div className="mb-5">
            <div className="flex justify-between gap-3 text-[12px] text-[var(--meta)] mb-1.5">
              <span>{t("audioTools.downloading")}</span>
              <span className="tabular-nums">{`${Math.round(pct)}%`}</span>
            </div>
            <div className="h-1.5 rounded-full bg-[color-mix(in_srgb,var(--ink)_10%,transparent)] overflow-hidden">
              <div
                className="h-full bg-[var(--accent)] rounded-full transition-[width] duration-200"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        ) : null}

        <div className="flex items-center gap-2 justify-end">
          {phase === "ask" || phase === "failed" ? (
            <>
              <Btn onClick={onClose}>{t("audioTools.later")}</Btn>
              <Btn primary onClick={start}>
                {phase === "failed"
                  ? t("audioTools.retry")
                  : size
                    ? `${t("audioTools.download")}${t("s.e592773b6a", { v0: size })}`
                    : t("audioTools.download")}
              </Btn>
            </>
          ) : phase === "downloading" ? (
            <Btn onClick={onClose}>{t("audioTools.background")}</Btn>
          ) : (
            <Btn primary onClick={onClose}>{t("audioTools.ok")}</Btn>
          )}
        </div>
      </div>
    </Modal>
  );
}
