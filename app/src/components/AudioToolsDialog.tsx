import { useCallback, useEffect, useRef, useState } from "react";
import { DockableModal, TransferProgress } from "trm-ui";
import { listen } from "../lib/listen";
import { Btn } from "./ui";
import { ErrorNote } from "./ErrorNote";
import { t } from "../i18n/t";
import { useI18n } from "../i18n";
import { joinClauses } from "../lib/text";
import { audioToolsDownloading, ensureAudioTools } from "../lib/downloadModels";

type Phase = "ask" | "downloading" | "done" | "failed";

type Props = {
  open: boolean;
  /** 包体大小（字节），来自后端，提示里显示「约 xx MB」。 */
  sizeBytes?: number;
  minimized?: boolean;
  onMinimizedChange?: (minimized: boolean) => void;
  orbSlot?: number;
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
export function AudioToolsDialog({
  open,
  sizeBytes,
  minimized,
  onMinimizedChange,
  orbSlot = 0,
  onClose,
}: Props) {
  useI18n();
  const [phase, setPhase] = useState<Phase>("ask");
  const [error, setError] = useState("");
  const [pct, setPct] = useState(0);
  const [innerMin, setInnerMin] = useState(false);

  const isMin = minimized ?? innerMin;
  const minRef = useRef(isMin);
  useEffect(() => {
    minRef.current = isMin;
  }, [isMin]);

  const setMin = useCallback(
    (next: boolean) => {
      minRef.current = next;
      if (onMinimizedChange) onMinimizedChange(next);
      else setInnerMin(next);
    },
    [onMinimizedChange],
  );

  useEffect(() => {
    if (!open) {
      setMin(false);
      return;
    }
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
  }, [open, setMin]);

  const start = () => {
    setPhase("downloading");
    setError("");
    setPct(0);
    ensureAudioTools()
      .then(() => {
        if (minRef.current) {
          onClose();
        } else {
          setPhase("done");
        }
      })
      .catch((e) => {
        setError(String(e));
        setPhase("failed");
      });
  };

  const size = formatMb(sizeBytes);
  const tooltip = joinClauses([
    t("audioTools.title"),
    phase === "failed" ? error : t("audioTools.downloading"),
    phase === "downloading" && pct > 0 ? `${Math.round(pct)}%` : "",
  ]);

  return (
    <DockableModal
      open={open}
      minimized={isMin}
      onMinimizedChange={setMin}
      canMinimize={phase === "downloading" || isMin}
      onClose={phase !== "downloading" ? onClose : undefined}
      maxWidth={440}
      contained={false}
      z={60}
      slot={orbSlot}
      bottom={92}
      label={t("audioTools.title")}
      orbLabel={t("s.orbDownloadLabel")}
      percent={phase === "downloading" && pct > 0 ? pct : undefined}
      attention={phase === "failed" ? "error" : "idle"}
      tooltip={tooltip}
    >
      <div className="p-7">
        <h2 className="text-[22px] font-semibold m-0 mb-2">{t("audioTools.title")}</h2>
        {phase === "failed" ? (
          <div className="mb-5"><ErrorNote feature="download" text={error} compact /></div>
        ) : phase !== "downloading" ? (
          <p className="text-[13px] text-[var(--help)] m-0 mb-5 leading-relaxed">
            {phase === "done" ? t("audioTools.done") : t("audioTools.desc", { v0: size })}
          </p>
        ) : null}

        {phase === "downloading" ? (
          <div className="mb-5">
            <TransferProgress
              message={t("audioTools.downloading")}
              percent={pct > 0 ? pct : undefined}
            />
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
            <Btn onClick={() => setMin(true)}>{t("audioTools.background")}</Btn>
          ) : (
            <Btn primary onClick={onClose}>{t("audioTools.ok")}</Btn>
          )}
        </div>
      </div>
    </DockableModal>
  );
}
