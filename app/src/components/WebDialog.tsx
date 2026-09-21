import { useEffect, useRef, useState } from "react";
import { t } from "../i18n/t";
import { useModalKeys } from "../hooks/useModalKeys";
import {
  registerDialogHandler,
  type DialogRequest,
} from "../lib/webDialog";

/**
 * 主窗和工具窗各挂一份。队列在模块里，哪个 webview 的 handler 在，就在哪画。
 */
export function WebDialogHost() {
  const [req, setReq] = useState<DialogRequest | null>(null);
  const reqRef = useRef<DialogRequest | null>(null);
  const queue = useRef<DialogRequest[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const okRef = useRef<HTMLButtonElement>(null);
  const [draft, setDraft] = useState("");
  const draftRef = useRef(draft);
  draftRef.current = draft;

  const show = (next: DialogRequest | null) => {
    reqRef.current = next;
    setReq(next);
  };

  useEffect(() => {
    registerDialogHandler((next) => {
      if (reqRef.current) queue.current.push(next);
      else show(next);
    });
    return () => registerDialogHandler(null);
  }, []);

  useEffect(() => {
    // draft 跟着请求走；焦点/键盘契约统一走 useModalKeys。
    setDraft(req?.kind === "prompt" ? req.def : "");
  }, [req]);

  // 与自定义弹层（App 的 killAsk/closeAsk）共用同一套键盘/焦点契约：
  // 打开收焦点、Tab 圈内转、Escape 取消、关闭还焦点。队列里还有下一个
  // 请求时 open 不落地，焦点也不还 —— 直到最后一个弹窗关掉。
  useModalKeys(!!req, dialogRef, {
    onEscape: () => {
      const cur = reqRef.current;
      if (cur) finishRef.current(cur.kind === "confirm" ? false : null);
    },
    focus: () =>
      req?.kind === "prompt" ? inputRef.current : dialogRef.current,
  });

  const finish = (value: boolean | string | null) => {
    const cur = reqRef.current;
    // 同一个弹窗只许回答一次：Enter 的 keydown 处理和按钮 click 撞在一起时，
    // 第二次调用不能再去队列里多弹一个请求出来。
    if (!cur) return;
    if (cur.kind === "confirm") cur.resolve(value === true);
    else cur.resolve(typeof value === "string" ? value : null);
    show(queue.current.shift() ?? null);
  };
  const finishRef = useRef(finish);
  finishRef.current = finish;

  useEffect(() => {
    if (!req) return;
    const onKey = (e: KeyboardEvent) => {
      const cur = reqRef.current;
      if (!cur) return;
      // 这个按键已经回答过一个请求（比如输入框里的 Enter）：finish 同步
      // 就把下一个排队请求推上来了，同一个事件不许对它再作答。
      if (e.defaultPrevented) return;
      // IME 组词中的按键只是选词，不是对弹窗的回答。
      if (e.isComposing) return;
      // Escape/Tab 由 useModalKeys 统一处理；这里只管 Enter 的作答语义。
      // 长按 Enter 产生的 repeat 不许替用户连续作答排队弹窗。
      if (e.key !== "Enter" || e.repeat) return;
      const active = document.activeElement;
      if (cur.kind === "confirm") {
        // Enter 走当前焦点按钮的语义：焦点在「取消」上就是取消，
        // 在「确认」或弹窗空白处（默认动作）才是确认。preventDefault
        // 同时按住按钮的原生激活 click，避免同一个弹窗被回答两次。
        e.preventDefault();
        finishRef.current(active === cancelRef.current ? false : true);
      } else if (active === cancelRef.current) {
        e.preventDefault();
        finishRef.current(null);
      } else if (active === okRef.current) {
        e.preventDefault();
        finishRef.current(draftRef.current);
      }
      // prompt：焦点留在输入框里时，Enter 由输入框自己的处理负责。
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [req]);

  if (!req) return null;

  return (
    <div
      className="fixed inset-0 z-[100] grid place-items-center p-6 bg-[color-mix(in_srgb,var(--ink)_28%,transparent)]"
      onClick={() => finish(req.kind === "confirm" ? false : null)}
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        className="w-full max-w-[420px] rounded-[var(--r)] bg-[var(--surface)] shadow-[0_22px_56px_-18px_rgba(20,26,33,.34)] p-6 outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="text-[13px] text-[var(--ink)] m-0 mb-4 leading-relaxed whitespace-pre-wrap">
          {req.message}
        </p>
        {req.kind === "prompt" ? (
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (
                e.key !== "Enter" ||
                e.nativeEvent.isComposing ||
                e.repeat
              ) {
                return;
              }
              e.preventDefault();
              // 这次按键已经回答了当前请求：就地截停，不许冒泡到
              // window 处理器再对刚弹出的下一个请求作答。
              e.stopPropagation();
              finish(draft);
            }}
            className="w-full mb-4 px-[13px] py-[7px] rounded-[var(--rs)] text-[13px] bg-transparent text-[var(--ink)] shadow-[inset_0_0_0_1px_var(--line)] outline-none focus:shadow-[inset_0_0_0_1px_var(--accent)]"
          />
        ) : null}
        <div className="flex gap-2.5 justify-end">
          <button
            ref={cancelRef}
            type="button"
            onClick={() => finish(req.kind === "confirm" ? false : null)}
            className="text-[13px] px-3.5 py-2 rounded-[var(--rs)] bg-transparent text-[var(--ink-muted)] border-0 cursor-pointer shadow-[inset_0_0_0_1px_var(--line)]"
          >
            {t("dialog.cancel")}
          </button>
          <button
            ref={okRef}
            type="button"
            onClick={() => finish(req.kind === "prompt" ? draft : true)}
            className="text-[13px] font-semibold px-3.5 py-2 rounded-[var(--rs)] bg-[var(--accent)] text-[var(--accent-ink)] border-0 cursor-pointer"
          >
            {t("dialog.ok")}
          </button>
        </div>
      </div>
    </div>
  );
}
