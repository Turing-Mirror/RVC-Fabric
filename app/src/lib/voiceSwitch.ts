/**
 * 音色切换派发器（N03/B-05）。
 *
 * 首页、模型页、底栏共用这一条控制逻辑，四态一致：
 * 「收到选择」→ pendingKey 立刻置上（点下去就有视觉反馈，不等磁盘/IPC/模型）；
 * 「正在切换」→ 串行执行 selectVoice + setHot；
 * 「已生效」→ 完成时 apply（换 dock 与页面状态）；
 * 「失败」→ error 结果，旧选择保留。
 *
 * 语义：
 * - 同一目标在切换中再点 → 挂到同一个任务上，不重复提交（去重）。
 * - 快速点不同目标 → 只保留最新意图（队列深度 1），被顶掉的排队任务按
 *   superseded 结算，不无限堆积。
 * - 旧任务完成时若有更新意图在等 → 不 apply、不回写，避免过期结果覆盖。
 * - 全程不锁窗口：派发器只管切换这一件事。
 */

import { useSyncExternalStore } from "react";
import { setHot } from "./engine";
import { modelKey, selectVoice, type VoiceModel } from "./voices";

export type VoiceApplyInfo = {
  model: VoiceModel;
  pitch?: number;
  formant?: number;
  profileSummary?: string;
};

export type SwitchOutcome =
  | { kind: "done" }
  /** 被更新的意图接管：后端可能已选中过它，但界面以最新目标为准。 */
  | { kind: "superseded" }
  | { kind: "error"; error: string };

type Job = {
  key: string;
  model: Pick<VoiceModel, "path" | "dir" | "name">;
  apply: (info: VoiceApplyInfo) => void;
  waiters: Array<(o: SwitchOutcome) => void>;
};

let current: Job | null = null;
let next: Job | null = null;
let pumping = false;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

/** 正在切换/排队等待的目标 key，空串 = 空闲。供两个页面做同一个即时反馈。 */
export function voiceSwitchPendingKey(): string {
  return next?.key ?? current?.key ?? "";
}

export function onVoiceSwitchPending(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useVoiceSwitchPending(): string {
  return useSyncExternalStore(onVoiceSwitchPending, voiceSwitchPendingKey);
}

function settle(job: Job, outcome: SwitchOutcome) {
  job.waiters.forEach((w) => w(outcome));
}

async function run(job: Job): Promise<SwitchOutcome> {
  try {
    const res = await selectVoice(job.model);
    try {
      await setHot({
        dsp_enabled: false,
        dsp_preset: "",
        dsp_params: {},
        function: "vc",
        ...(res.pitch != null || res.formant != null
          ? {
              pitch: Number(res.pitch ?? 0),
              formant: Number(res.formant ?? 0),
            }
          : {}),
      });
    } catch {
      /* worker may be idle */
    }
    // 跑完时已有更新意图在排队：这次结果被接管，apply 只服务最新目标。
    if (next) {
      return { kind: "superseded" };
    }
    job.apply({
      model: (res.model as VoiceModel) || (job.model as VoiceModel),
      pitch: res.pitch as number | undefined,
      formant: res.formant as number | undefined,
      profileSummary: res.profile_summary,
    });
    return { kind: "done" };
  } catch (e) {
    return { kind: "error", error: String(e) };
  }
}

async function pump() {
  if (pumping) return;
  pumping = true;
  try {
    while (next) {
      const job = next;
      next = null;
      current = job;
      emit();
      const outcome = await run(job);
      // 先清 pending 再放行调用方 —— 调用方醒过来时状态必须已经一致。
      current = null;
      emit();
      settle(job, outcome);
    }
  } finally {
    pumping = false;
    emit();
  }
}

/**
 * 请求切换音色。立即返回 promise，并把目标 key 广播给所有订阅者做即时反馈。
 * 同一目标的重复点击复用同一任务；不同目标的快速点击只保留最新意图。
 */
export function requestVoiceSwitch(
  model: Pick<VoiceModel, "path" | "dir" | "name"> & Partial<VoiceModel>,
  apply: (info: VoiceApplyInfo) => void,
): Promise<SwitchOutcome> {
  const key = modelKey(model as VoiceModel);
  const existing = next?.key === key ? next : current?.key === key ? current : null;
  if (existing) {
    // 同一目标已在切换/排队：结果共享，不重复读取、发命令或加载模型。
    return new Promise<SwitchOutcome>((resolve) => {
      existing.waiters.push(resolve);
    });
  }
  return new Promise<SwitchOutcome>((resolve) => {
    const job: Job = { key, model, apply, waiters: [resolve] };
    if (next) {
      // 队列深度 1：顶掉的旧意图立即结算，不占着 pending。
      settle(next, { kind: "superseded" });
    }
    next = job;
    emit();
    void pump();
  });
}
