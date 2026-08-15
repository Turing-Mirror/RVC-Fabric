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
  const queue = useRef<DialogRequest[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    registerDialogHandler((next) => {
      setReq((cur) => {
        if (cur) {
          queue.current.push(next);
          return cur;
        }
        return next;
      });
    });
    return () => registerDialogHandler(null);
  }, []);

  useEffect(() => {
    if (!req) return;
    if (req.kind === "prompt") {
      setDraft(req.def);
      const id = window.setTimeout(() => inputRef.current?.focus(), 0);
      return () => window.clearTimeout(id);
    }
    setDraft("");
  }, [req]);

  const finish = (value: boolean | string | null) => {
    if (!req) return;
    if (req.kind === "confirm") req.resolve(value === true);
    else req.resolve(typeof value === "string" ? value : null);
    const next = queue.current.shift() ?? null;
    setReq(next);
  };
  const finishRef = useRef(finish);
  finishRef.current = finish;

  useEffect(() => {
    if (!req) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        finishRef.current(req.kind === "confirm" ? false : null);
      }
      if (e.key === "Enter" && req.kind === "confirm") {
        e.preventDefault();
        finishRef.current(true);
      }
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
        role="dialog"
        aria-modal="true"
        className="w-full max-w-[420px] rounded-[var(--r)] bg-[var(--surface)] shadow-[0_22px_56px_-18px_rgba(20,26,33,.34)] p-6"
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
            type="button"
            onClick={() => finish(req.kind === "confirm" ? false : null)}
            className="text-[13px] px-3.5 py-2 rounded-[var(--rs)] bg-transparent text-[var(--ink-muted)] border-0 cursor-pointer shadow-[inset_0_0_0_1px_var(--line)]"
          >
            {t("dialog.cancel")}
          </button>
          <button
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
