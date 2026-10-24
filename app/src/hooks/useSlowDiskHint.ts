import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { StartupStep } from "../lib/engine";

/** 启动引擎、载入推理库这两步在机械硬盘上会读几 GB 文件。 */
const DISK_BOUND_STEPS = 2;
/** 固态硬盘上这两步通常十秒内走完；超过这个时长才提示。 */
export const SLOW_START_MS = 30_000;

let onHdd: Promise<boolean> | null = null;
function installOnHdd(): Promise<boolean> {
  onHdd ??= invoke<boolean>("install_on_hdd").catch(() => false);
  return onHdd;
}

/** 装在机械硬盘上，且开启变声卡在读盘的那两步超过 SLOW_START_MS 时为 true。 */
export function useSlowDiskHint(step: StartupStep | null): boolean {
  const diskBound = !!step && step.index < DISK_BOUND_STEPS;
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (!diskBound) {
      setSlow(false);
      return;
    }
    let alive = true;
    const timer = window.setTimeout(() => {
      void installOnHdd().then((hdd) => alive && setSlow(hdd));
    }, SLOW_START_MS);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [diskBound]);

  return diskBound && slow;
}
