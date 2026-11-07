import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { dropListen } from "./tauriListen";

export type TrainJobState = "queued" | "running" | "cancelling" | "paused" | "interrupted" | "completed" | "failed" | "cancelled";
export type TrainStage = "preprocess" | "f0" | "feature" | "train" | "index";
export const TRAIN_STAGES: TrainStage[] = ["preprocess", "f0", "feature", "train", "index"];
export type TrainJob = {
  id: string;
  state: TrainJobState;
  req: { exp: string; sample_rate: string; dataset: string; total_epoch: number; batch_size: number };
  progress: { stage?: TrainStage; done?: number; total?: number; message_code?: string } | null;
  error: string;
  result?: { weights?: string; index?: string; leftover_bytes?: number } | null;
};
type Snapshot = { jobs: TrainJob[]; waiting_for_realtime?: boolean };
export const activeJob = (jobs: TrainJob[]) => jobs.find(j => j.state === "running" || j.state === "cancelling");
export const terminalJob = (job: TrainJob) => ["completed", "failed", "cancelled", "interrupted"].includes(job.state);
export function latestExperimentJob(jobs: TrainJob[], experiment: string): TrainJob | undefined {
  const name = experiment.trim();
  if (!name) return undefined;
  for (let index = jobs.length - 1; index >= 0; index -= 1) {
    if (jobs[index].req.exp.toLowerCase() === name.toLowerCase()) return jobs[index];
  }
  return undefined;
}
export function trainPercent(job?: TrainJob): number {
  if (job?.state === "completed") return 100;
  const p = job?.progress;
  const stage = p?.stage ? TRAIN_STAGES.indexOf(p.stage) : -1;
  if (stage < 0) return 0;
  const within = p?.total && typeof p.done === "number" ? Math.max(0, Math.min(1, p.done / p.total)) : 0;
  return Math.round(((stage + within) / TRAIN_STAGES.length) * 100);
}
export function useTrainingQueue() {
  const [jobs, setJobs] = useState<TrainJob[]>([]);
  const [error, setError] = useState("");
  const [waitingForRealtime, setWaitingForRealtime] = useState(false);
  const updates = useRef(0);
  const fetching = useRef(false);
  const refresh = useCallback(async () => {
    if (!("__TAURI_INTERNALS__" in window) || fetching.current) return;
    fetching.current = true;
    const revision = updates.current;
    try {
      const value = await invoke<Snapshot>("train_queue_list");
      if (revision === updates.current) { setJobs(value.jobs); setWaitingForRealtime(!!value.waiting_for_realtime); }
      setError("");
    } catch (e) { setError(String(e)); } finally { fetching.current = false; }
  }, []);
  useEffect(() => {
    if (!("__TAURI_INTERNALS__" in window)) return;
    let disposed = false;
    const un = listen<Snapshot>("train-queue", event => { if (!disposed) { updates.current += 1; setJobs(event.payload.jobs); setWaitingForRealtime(!!event.payload.waiting_for_realtime); } });
    // Subscribe before reading the snapshot to cover mounting during a transition.
    void un.then(() => { if (!disposed) void refresh(); }).catch(e => { if (!disposed) setError(String(e)); });
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => { disposed = true; window.clearInterval(timer); void un.then(dropListen).catch(() => {}); };
  }, [refresh]);
  const action = useCallback(async (id: string, action: string) => {
    try {
      await invoke("train_queue_action", { id, action });
      await refresh();
    } catch (e) { setError(String(e)); }
  }, [refresh]);
  return { jobs, error, waitingForRealtime, refresh, action };
}
