import { useEffect, useRef, useState } from "react";
import { listVoices, modelKey } from "../lib/voices";
import type { EngineStatus } from "../lib/engine";

export type ActiveVoiceLabel = { id: string; name: string; tag: string };

/** 分隔符与大小写归一后的路径比较：Windows 路径两种斜杠、盘符大小写都算同一个。 */
function normPath(p: string): string {
  return p.replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
}

/** 归一化后的绝对路径判定：`c:/`、`/`（POSIX/UNC 已折成 `//`）。 */
function isAbsolute(p: string): boolean {
  return /^([a-z]:)?\//i.test(p);
}

/**
 * 「使用中」对账的语义身份：worker 寿命（pid）+ 库根 + 在用的 pth/index。
 *
 * 心跳每 ~400ms 换一份 status 对象，但身份没变就还是同一件事 —— effect 只挂
 * 在这个 key 上，同身份的心跳不打断在途的目录查询。worker 重启换 pid、
 * 换了 index、换了库根，都算新身份要重新对账。
 */
function activeKey(running: boolean, status: EngineStatus | undefined): string {
  if (!running) return "";
  const active = status?.model_active;
  if (active === undefined) return "";
  const pid = String(status?.pid ?? "");
  const root = normPath(String(status?.product_root || ""));
  if (active === null) return `${pid}|${root}|<null>`;
  return `${pid}|${root}|${normPath(String(active.pth_path || ""))}|${normPath(
    String(active.index_path || ""),
  )}`;
}

/** 目录拉不下来时的原地重试上限；身份变了照样重新计数。 */
const MAX_RETRY = 3;

/**
 * 「使用中」徽标的对账：合约 worker 运行中上报 model_active（音频线程
 * 真正在用的模型），以它为准把徽标贴回事实，而不是持久化的选择意图。
 *
 * - 匹配只认精确身份：归一化后的 path 相等、相对路径按
 *   `status.product_root`（没有则 `catalog.models_dir`）归到根再比、
 *   或 modelKey 相等。两个目录里的同名 .pth 绝不能靠文件名撞上。
 * - 每次身份变化记一代 generation；迟到的上一次查目录结果被丢弃，
 *   不许覆盖更新的 active 状态（A/B 交替时慢的那次返回不能赢）。
 * - `model_active` 字段缺席 = 旧 worker：不动显示，宁可留着旧徽标也不猜。
 *   明确 `null` = worker 说没有在用的模型 → 清掉徽标。
 * - 目录拉不到：不 latch，原地重试几次；停流/字段缺席会把对账作废，
 *   worker 再起时同一路径也重新确认。
 */
export function useActiveVoiceReconcile(
  running: boolean,
  status: EngineStatus | undefined,
  onResolve: (v: ActiveVoiceLabel) => void,
): void {
  const key = activeKey(running, status);
  const gen = useRef(0);
  // 上一次「对完账」的身份。成功、明确 null、目录里查无此模（已如实退
  // 文件名显示）才算 done —— 失败不 latch，留给重试或下一次身份变化。
  const doneKey = useRef("");
  const fails = useRef(0);
  const [retrySeq, setRetrySeq] = useState(0);
  const cbRef = useRef(onResolve);
  cbRef.current = onResolve;
  // status 本体只在回调里读：进依赖的话每次心跳都把在途查询作废。
  const statusRef = useRef(status);
  statusRef.current = status;

  useEffect(() => {
    if (!key) {
      // 没在跑 / 旧 worker 字段缺席：对账作废，下次起来重新确认。
      doneKey.current = "";
      fails.current = 0;
      return;
    }
    if (key === doneKey.current) return;
    const g = ++gen.current;
    const active = statusRef.current?.model_active;
    const pth = String(active?.pth_path || "");
    if (!pth) {
      // 明确回报「没有在用的模型」（纯 DSP / 尚未应用）→ 显示也清空。
      doneKey.current = key;
      fails.current = 0;
      cbRef.current({ id: "", name: "", tag: "" });
      return;
    }
    void listVoices()
      .then((cat) => {
        if (g !== gen.current) return;
        const models = Array.isArray(cat.models) ? cat.models : [];
        const want = normPath(pth);
        // 相对路径按库根解析后再比 —— 不是拿文件名去全目录碰运气。
        const rooted = isAbsolute(want)
          ? []
          : [statusRef.current?.product_root, cat.models_dir]
              .map((r) => String(r || ""))
              .filter(Boolean)
              .map((r) => normPath(`${r}/${pth}`));
        const hit = models.find(
          (m) =>
            normPath(String(m.path || "")) === want ||
            rooted.includes(normPath(String(m.path || ""))) ||
            modelKey(m) === pth,
        );
        doneKey.current = key;
        fails.current = 0;
        if (hit) {
          cbRef.current({
            id: modelKey(hit),
            name: String(hit.name || ""),
            tag: String((hit as { tag?: string }).tag || ""),
          });
        } else {
          // 目录里没有这个模型：仍如实显示它在用，名字退成文件名。
          const stem = (pth.split(/[\\/]/).pop() || pth).replace(
            /\.pth$/i,
            "",
          );
          cbRef.current({ id: pth, name: stem, tag: "" });
        }
      })
      .catch(() => {
        if (g !== gen.current) return;
        // 失败不 latch：身份没变就原地重试，变了一切重来。
        if (fails.current < MAX_RETRY) {
          fails.current += 1;
          setRetrySeq((n) => n + 1);
        }
      });
    // 身份变了或组件卸载才把这一代作废：同身份的心跳不进这里，
    // 在途的 listVoices 得以落定。
    return () => {
      gen.current += 1;
    };
  }, [key, retrySeq]);
}
