import { useEffect, useRef, useState } from "react";
import { t } from "../i18n/t";
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
  // 弹窗打开前焦点所在的控件（通常是触发按钮），最后一个弹窗关掉时还给它。
  const prevFocusRef = useRef<HTMLElement | null>(null);
  const focusHeldRef = useRef(false);
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
    if (!req) {
      if (focusHeldRef.current) {
        focusHeldRef.current = false;
        prevFocusRef.current?.focus();
        prevFocusRef.current = null;
      }
      return;
    }
    if (!focusHeldRef.current) {
      focusHeldRef.current = true;
      const el = document.activeElement;
      prevFocusRef.current = el instanceof HTMLElement ? el : null;
    }
    if (req.kind === "prompt") {
      setDraft(req.def);
      const id = window.setTimeout(() => inputRef.current?.focus(), 0);
      return () => window.clearTimeout(id);
    }
    setDraft("");
    const id = window.setTimeout(() => dialogRef.current?.focus(), 0);
    return () => window.clearTimeout(id);
  }, [req]);

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
      if (e.key === "Escape") {
        e.preventDefault();
        finishRef.current(cur.kind === "confirm" ? false : null);
        return;
      }
      if (e.key === "Tab") {
        // 焦点圈在弹窗里：遮罩后的页面不参与 Tab 序。
        const dlg = dialogRef.current;
        if (!dlg) return;
        const focusables = Array.from(
          dlg.querySelectorAll<HTMLElement>(
            "button, input, [tabindex]:not([tabindex='-1'])",
          ),
        ).filter((el) => !el.hasAttribute("disabled"));
        if (!focusables.length) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement;
        const inside = active instanceof HTMLElement && dlg.contains(active);
        if (!e.shiftKey && (!inside || active === last)) {
          e.preventDefault();
          first.focus();
        } else if (e.shiftKey && (!inside || active === first)) {
          e.preventDefault();
          last.focus();
        }
        return;
      }
      if (e.key !== "Enter") return;
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
              if (e.key === "Enter") {
                e.preventDefault();
                finish(draft);
              }
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
