/**
 * 「点了就该有回执」的统一做法。
 *
 * 耗时按钮以前各写各的：有的用一个 running 布尔值，有的靠 try/finally，有的
 * 干脆没有。结果是同一款软件里，有的按钮点完会变灰，有的点完什么都不发生，
 * 用户只能再点一次 —— 而再点一次有时候会真的再跑一遍。
 *
 * 这个 hook 只做两件事：请求在途时把按钮标成 busy，以及挡住重复点击。可见的
 * 那部分交给 `Btn` 的 busy 属性（文字前面三个动着的点），不是只变灰。
 */
import { useCallback, useRef, useState } from "react";

export function useBusyAction<A extends unknown[]>(
  fn: (...args: A) => Promise<void> | void,
): { busy: boolean; run: (...args: A) => void } {
  const [busy, setBusy] = useState(false);
  // state 更新是异步的：连点两下时第二下可能在 setBusy(true) 生效之前就进来了。
  // 真正挡住重复的是这个 ref，busy 只负责显示。
  const inFlight = useRef(false);

  const run = useCallback(
    (...args: A) => {
      if (inFlight.current) return;
      inFlight.current = true;
      setBusy(true);
      void (async () => {
        try {
          await fn(...args);
        } finally {
          inFlight.current = false;
          setBusy(false);
        }
      })();
    },
    [fn],
  );

  return { busy, run };
}
