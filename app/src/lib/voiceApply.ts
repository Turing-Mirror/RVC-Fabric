/**
 * 音色选择的「引擎侧应用」判定（B2）。
 *
 * 引擎合约（engine-contract.md）：`engine_swap_model` 只在精确 seq+路径
 * committed 后 resolve，失败/超时/旧 worker 一律 reject —— 壳层的
 * resolve/reject 本身就是结果，前端不再拿 status 字段或「能力标志位」
 * 二次猜。`engine_start_vc` 返回的是 status 对象而不是 reject：失败时
 * 可能是 `state:"error"` 的 resolve，必须显式判。
 */
import { startVc, swapModel, type EngineStatus } from "./engine";
import { t } from "../i18n/t";

/** applyVoiceChange 需要的最小引擎面。 */
export interface VoiceApplyEngine {
  running: boolean;
  status?: EngineStatus;
  /** 用户亲手发起的变声启动还在等结果（预热/boot 的 starting 不算）。 */
  userStartPending(): boolean;
  /** 等在途的用户启动落定并给出那份结果；没有在途启动时立刻给最近一次的。 */
  awaitUserStart(): Promise<EngineStatus>;
}

/**
 * startVc / 用户启动落定的判定：status 对象里 `state` 才是真结果。
 * `state:"error"` 或没回到 running 都算失败 —— status.json 是合并写的，
 * 里面粘着的旧 model_apply/model_active 字段不参与判定。
 */
export function vcApplyError(st: EngineStatus): string | null {
  if (st.state === "error") {
    return String(st.error || st.message || t("msg.vc.start_failed"));
  }
  if (st.state !== "running") {
    return String(st.error || st.message || t("msg.vc.need_model"));
  }
  return null;
}

function isDspOnly(st: EngineStatus): boolean {
  return (
    st.dsp_only === true || st.function === "fx" || st.worker_kind === "dsp"
  );
}

/**
 * 把「选了音色」落到引擎上。
 *
 * - 引擎空闲、也没有用户在途启动 → "idle"：只是记选择，绝不碰音频流。
 * - 用户的启动在途 → 等它落定：失败/没跑起来抛错；起来后补一次 swap
 *   （合约内同目标是 no-op）把最新选择顶进去 —— 启动时 worker 读到的
 *   可能还是旧 inuse，不补一下界面和声音会岔开。
 * - 在跑的纯 DSP worker → startVc（挂模型切到 RVC），status 显式判。
 * - 在跑的 RVC worker → swapModel，resolve 即 committed。
 *
 * 任何一步失败都 reject：调用方保持旧显示、报错、释放 pending。
 */
export async function applyVoiceToEngine(
  eng: VoiceApplyEngine,
): Promise<"idle" | "applied"> {
  let st = eng.status ?? {};
  // 有在途的用户启动就永远是它先落定：哪怕心跳此刻已报 running，
  // 那份 status 也不是这次启动的结果，不能拿来放行 swap。
  if (eng.userStartPending()) {
    st = await eng.awaitUserStart();
    // 落定成 idle：启动在落定前被取消/停掉，引擎最终没在跑 ——
    // 这次选择退化成「只是记下」，不算失败。
    if (!st.state || st.state === "idle") return "idle";
    const err = vcApplyError(st);
    if (err) throw new Error(err);
  } else if (!eng.running) {
    return "idle";
  }
  if (isDspOnly(st)) {
    const r = await startVc();
    const err = vcApplyError(r);
    if (err) throw new Error(err);
    return "applied";
  }
  await swapModel();
  return "applied";
}
