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
  /** 返回 promise 时挂起整条任务直到应用落定（引擎换模型是异步的）。 */
  apply: (info: VoiceApplyInfo) => void | Promise<void>;
  waiters: Array<(o: SwitchOutcome) => void>;
  /** 结果已定形（superseded/done/error 已定），之后到达的同目标请求必须新开任务。 */
  closed?: boolean;
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
    // setHot 失败是真实失败（合约：空闲时后端结构性返回 Ok，只有出错才
    // 拒绝）—— 不再吞掉，否则参数没下发成功也会显示已切换。
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
    // 跑完时已有更新意图在排队：这次结果被接管，apply 只服务最新目标。
    if (next) {
      job.closed = true;
      return { kind: "superseded" };
    }
    // apply 可能是异步的（运行中换模型要等引擎真正换入）。任务在整个
    // 应用期间保持打开：同目标的点击仍按去重挂进来共享这次应用。
    await job.apply({
      model: (res.model as VoiceModel) || (job.model as VoiceModel),
      pitch: res.pitch as number | undefined,
      formant: res.formant as number | undefined,
      profileSummary: res.profile_summary,
    });
    // 应用落定这一刻结果才定形：等待 apply 期间到达的更新意图接管结论，
    // 之后到达的同目标请求必须新开任务。
    job.closed = true;
    if (next) {
      return { kind: "superseded" };
    }
    return { kind: "done" };
  } catch (e) {
    job.closed = true;
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
  apply: (info: VoiceApplyInfo) => void | Promise<void>,
): Promise<SwitchOutcome> {
  const key = modelKey(model as VoiceModel);
  if (next && next.key === key) {
    // 排队中的同目标：共享结果，不重复提交。
    const job = next;
    return new Promise<SwitchOutcome>((resolve) => {
      job.waiters.push(resolve);
    });
  }
  if (current && current.key === key && !current.closed) {
    // 在途的同目标本来就是最新意图。若另一个目标还排着队（A→B→A 里
    // 最后点回 A），它被这次点击顶掉 —— 最新意图是 current，不是 next。
    const job = current;
    const stale = next;
    next = null;
    if (stale) {
      emit();
      settle(stale, { kind: "superseded" });
    }
    return new Promise<SwitchOutcome>((resolve) => {
      job.waiters.push(resolve);
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
