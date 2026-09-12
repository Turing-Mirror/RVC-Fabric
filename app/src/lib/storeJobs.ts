/**
 * Plaza voice downloads live here, not in StoreSection.
 *
 * PageHost unmounts the plaza as soon as you leave it. If the queue and the
 * in-flight invoke sit in that component, the UI forgets the job and the user
 * has to click Download again. Rust keeps transferring; this module keeps the
 * JS side of the same job until it finishes or the user cancels.
 */
import { useEffect, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { displayVoiceName } from "./voiceDisplay";
import {
  cancelStoreDownload,
  installStagedVoice,
  installStoreVoice,
  type StoreVoice,
} from "./voices";

export const MAX_STORE_JOBS = 2;

export type VoiceProg = {
  percent: number;
  done: number;
  total: number;
  message: string;
  phase: string;
};

export type StoreJobsSnap = {
  running: string[];
  queued: string[];
  prog: Record<string, VoiceProg>;
  error: string;
  generation: number;
  lastCompleted: string;
  lastCompletedThird: boolean;
};

type Kind = "pack" | "staged";

export function enqueueJobIds(
  id: string,
  running: string[],
  queued: string[],
  max = MAX_STORE_JOBS,
): { running: string[]; queued: string[]; launch: boolean } {
  if (running.includes(id) || queued.includes(id)) {
    return { running, queued, launch: false };
  }
  if (running.length >= max) {
    return { running, queued: [...queued, id], launch: false };
  }
  return { running: [...running, id], queued, launch: true };
}

function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

const entries = new Map<string, { voice: StoreVoice; kind: Kind }>();
let running: string[] = [];
let queued: string[] = [];
let prog: Record<string, VoiceProg> = {};
let error = "";
let generation = 0;
let lastCompleted = "";
let lastCompletedThird = false;
let listening = false;
const listeners = new Set<() => void>();

function snap(): StoreJobsSnap {
  return { running, queued, prog, error, generation, lastCompleted, lastCompletedThird };
}

function emit() {
  for (const fn of listeners) fn();
}

function ensureListen() {
  if (listening || !isTauri()) return;
  listening = true;
  void listen<{
    voice_id?: string;
    message?: string;
    percent?: number;
    phase?: string;
    done?: number;
    total?: number;
  }>("store-progress", (ev) => {
    const p = ev.payload;
    const id = (p.voice_id || "").trim();
    if (!id) return;
    const done = Number(p.done);
    const total = Number(p.total);
    const fromBytes =
      Number.isFinite(done) && Number.isFinite(total) && total > 0
        ? (done / total) * 100
        : undefined;
    const pctRaw =
      p.percent != null && !Number.isNaN(Number(p.percent))
        ? Number(p.percent)
        : fromBytes;
    const prev = prog[id];
    prog = {
      ...prog,
      [id]: {
        percent: pctRaw != null ? Math.max(0, Math.min(100, pctRaw)) : (prev?.percent ?? 0),
        done: Number.isFinite(done) ? done : (prev?.done ?? 0),
        total: Number.isFinite(total) && total > 0 ? total : (prev?.total ?? 0),
        message: p.message || prev?.message || "",
        phase: p.phase || prev?.phase || "",
      },
    };
    emit();
  }).catch(() => {
    listening = false;
  });
}

async function startOne(id: string) {
  const job = entries.get(id);
  if (!job) {
    running = running.filter((x) => x !== id);
    emit();
    pump();
    return;
  }
  const label = displayVoiceName(job.voice);
  try {
    if (job.kind === "staged") {
      await installStagedVoice({ ...job.voice, name: label });
    } else {
      await installStoreVoice({ ...job.voice, name: label });
    }
    generation += 1;
    lastCompleted = id;
    lastCompletedThird = job.voice.official === false;
  } catch (e) {
    error = `${label || id}：${String(e)}`;
  } finally {
    running = running.filter((x) => x !== id);
    if (id in prog) {
      const next = { ...prog };
      delete next[id];
      prog = next;
    }
    entries.delete(id);
    emit();
    pump();
  }
}

function pump() {
  while (running.length < MAX_STORE_JOBS && queued.length) {
    const id = queued[0];
    queued = queued.slice(1);
    running = [...running, id];
    emit();
    void startOne(id);
  }
}

export function enqueueStoreDownload(voice: StoreVoice, kind: Kind = "pack"): void {
  ensureListen();
  entries.set(voice.id, { voice, kind });
  error = "";
  const next = enqueueJobIds(voice.id, running, queued);
  running = next.running;
  queued = next.queued;
  emit();
  if (next.launch) void startOne(voice.id);
}

export function cancelStoreJob(id: string): void {
  if (queued.includes(id)) {
    queued = queued.filter((x) => x !== id);
    entries.delete(id);
    emit();
    return;
  }
  void cancelStoreDownload(id);
}

export function subscribeStoreJobs(fn: () => void): () => void {
  ensureListen();
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function getStoreJobs(): StoreJobsSnap {
  return snap();
}

export function useStoreJobs(): StoreJobsSnap {
  const [s, setS] = useState(snap);
  useEffect(() => subscribeStoreJobs(() => setS(snap())), []);
  return s;
}
