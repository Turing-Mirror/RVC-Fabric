import { useEffect, useState } from "react";
import { subscribeNativeDialogHint } from "../lib/nativeDialog";

/**
 * 原生选择对话框开着时那条横幅。
 *
 * `pointer-events-none` 是有意的，不是顺手加的：它保证这个组件在最坏情况下
 * （invoke 卡住、横幅没被撤掉）也只是碍眼，挡不住任何点击。为「解释界面点不动」
 * 而引入一个「真的让界面点不动」的东西，那比原来的问题更糟。
 */
export function NativeDialogHint() {
  const [hint, setHint] = useState("");
  useEffect(() => subscribeNativeDialogHint(setHint), []);
  if (!hint) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 top-0 z-[120] flex justify-center px-4 pt-3"
    >
      <div className="max-w-[min(560px,92vw)] rounded-[var(--rs)] bg-[var(--surface)] px-3.5 py-2.5 text-[12.5px] leading-relaxed text-[var(--ink-muted)] shadow-[0_10px_30px_-12px_rgba(20,26,33,.38)]">
        {hint}
      </div>
    </div>
  );
}
