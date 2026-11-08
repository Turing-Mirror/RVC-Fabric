import { useState } from "react";
import { Pager, QueueList, Tag, usePaged } from "trm-ui";
import { Btn } from "./ui";
import { ErrorNote } from "./ErrorNote";
import { t } from "../i18n/t";
import { terminalJob, trainPercent, type TrainJob, type TrainJobState } from "../lib/trainQueue";

const STATE_KEYS: Record<TrainJobState, string> = {
  queued: "trainingQueue.Queued", running: "trainingQueue.Running", cancelling: "trainingQueue.Cancelling",
  paused: "trainingQueue.Paused", interrupted: "trainingQueue.Interrupted", completed: "trainingQueue.Completed",
  failed: "trainingQueue.Failed", cancelled: "trainingQueue.Cancelled",
};
const STAGE_KEYS = { preprocess: "s.1a37ffe775", f0: "s.bda11a3c2d", feature: "s.672c1db9d8", train: "s.796e01d5af", index: "s.79f9110607" };
export function TrainingQueue({ jobs, error, loaded = true, waitingForRealtime, eta, onAction, onBatch }: {
  jobs: TrainJob[]; error: string; loaded?: boolean; waitingForRealtime: boolean; eta?: string; onBatch?: () => void; onAction: (id: string, action: string) => Promise<void>;
}) {
  const paged = usePaged(jobs, 5);
  const [pending, setPending] = useState<string[]>([]);
  const action = async (id: string, kind: string) => {
    setPending(p => [...p, id]);
    try { await onAction(id, kind); } finally { setPending(p => p.filter(x => x !== id)); }
  };
  return <div className="mt-4 flex flex-col min-h-0 gap-2.5">
    <div className="flex items-center justify-between gap-2">
      <h3 className="text-[15.5px] font-semibold m-0">{t("trainingQueue.Title")}</h3>
      {jobs.some(terminalJob) ? <Btn disabled={pending.includes("")} onClick={() => void action("", "clear")}>{t("trainingQueue.Clear")}</Btn> : null}
    </div>
    {error ? <ErrorNote text={error} /> : null}
    {waitingForRealtime ? <p className="m-0 text-[12.5px] text-[var(--ink-muted)]">{t("trainingQueue.WaitRealtime")}</p> : null}
    <div className="rounded-[var(--r)] bg-[var(--group)] p-3.5 min-h-0 overflow-y-auto">
      <QueueList scope="training" page={paged.page} items={paged.slice} keyOf={job => job.id}
        className="flex flex-col gap-4"
        empty={loaded ? <div className="text-[12.5px] text-[var(--help)]">{t("trainingQueue.Empty")}</div> : null}
        render={job => {
            const running = job.state === "running" || job.state === "cancelling";
            const stage = job.progress?.stage;
            const disabled = pending.includes(job.id);
            return <div key={job.id} className="flex flex-col gap-2">
              <div className="flex items-start justify-between gap-2 text-[13px]">
                <span className="font-medium break-all">{job.req.exp}</span>
                <Tag tone={job.state === "failed" ? "warn" : running || job.state === "completed" ? "accent" : "muted"}>{t(STATE_KEYS[job.state])}</Tag>
              </div>
              <div className="text-[12px] text-[var(--meta)]">{job.req.sample_rate}</div>
              <div className="text-[12px] text-[var(--help)]">{t("trainingQueue.Parameters", { v0: String(job.req.total_epoch), v1: String(job.req.batch_size) })}</div>
              {running ? <>
                <div className="flex justify-between gap-2 text-[12px] text-[var(--help)]">
                  <span>{stage && stage in STAGE_KEYS ? t(STAGE_KEYS[stage]) : t("trainingQueue.Running")}</span>
                  <span className="tabular-nums">{job.progress?.total ? `${job.progress.done ?? 0} / ${job.progress.total}` : ""}</span>
                </div>
                <div className="h-[5px] rounded-full bg-[var(--line)] overflow-hidden">
                  <div className="h-full bg-[var(--accent)] transition-[width] duration-150" style={{ width: `${trainPercent(job)}%` }} />
                </div>
                {eta ? <div className="text-[12px] text-[var(--meta)]">{eta}</div> : null}
              </> : null}
              {job.state === "failed" && job.error ? <ErrorNote text={job.error} code={job.progress?.message_code} extraAction={job.progress?.message_code === "train.oom" && onBatch ? { label: t("s.errActBatch"), run: onBatch } : null} /> : null}
              <div className="flex items-center gap-2 flex-wrap">
                {running ? <Btn disabled={disabled || job.state === "cancelling"} onClick={() => void action(job.id, "cancel")}>{t("s.44e681a374")}</Btn> : <>
                  {terminalJob(job) || job.state === "paused" ? <Btn disabled={disabled} onClick={() => void action(job.id, "retry")}>{t(job.state === "paused" ? "trainingQueue.Continue" : "trainingQueue.Retry")}</Btn> : null}
                  <Btn disabled={disabled} onClick={() => void action(job.id, "remove")}>{t("trainingQueue.Remove")}</Btn>
                </>}
              </div>
            </div>;
        }}
      />
      <Pager page={paged.page} pages={paged.pages} onChange={paged.setPage} />
    </div>
  </div>;
}
