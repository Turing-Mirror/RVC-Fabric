import { useEffect, useRef, type RefObject } from "react";

/**
 * 弹层共用的一套键盘/焦点契约（C3）：打开时焦点收进弹层、Tab 在弹层里
 * 转圈、Escape 走「取消」语义、关掉时焦点还给打开前的控件。
 *
 * WebDialog 的确认/输入弹窗和 App 里 killAsk/closeAsk 这两个自定义确认层
 * 用同一套行为 —— 同一个窗口里不该有两套「Esc 关不掉、焦点散到背景」的
 * 弹层。动作语义（确认做什么、取消做什么）仍归调用方。
 */
export function useModalKeys(
  open: boolean,
  dialogRef: RefObject<HTMLElement | null>,
  opts: {
    /** Escape 的取消语义（confirm = 否，prompt = 取消）。 */
    onEscape?: () => void;
    /**
     * 打开时优先聚焦的元素；缺省聚焦弹层里第一个可聚焦控件，
     * 再退到弹层本身。
     */
    focus?: () => HTMLElement | null | undefined;
  } = {},
): void {
  const optsRef = useRef(opts);
  optsRef.current = opts;
  const prevFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const el = document.activeElement;
    prevFocusRef.current = el instanceof HTMLElement ? el : null;
    // 等一帧再聚焦：弹层刚挂进 DOM，同步 focus 会被浏览器丢掉。
    const id = window.setTimeout(() => {
      const dlg = dialogRef.current;
      const first = dlg?.querySelector<HTMLElement>(
        "button, input, [tabindex]:not([tabindex='-1'])",
      );
      (optsRef.current.focus?.() ?? first ?? dlg)?.focus();
    }, 0);
    const onKey = (e: KeyboardEvent) => {
      // 这按键已经回答过别的东西（比如弹窗输入框的 Enter 就地截停），
      // 或者还在 IME 组词 —— 都不算对弹层的回答。
      if (e.defaultPrevented || e.isComposing) return;
      if (e.key === "Escape") {
        // 长按不连关。
        if (e.repeat) return;
        e.preventDefault();
        optsRef.current.onEscape?.();
        return;
      }
      if (e.key !== "Tab") return;
      // 焦点圈在弹层里：遮罩后的页面不参与 Tab 序。
      const dlg = dialogRef.current;
      if (!dlg) return;
      const focusables = Array.from(
        dlg.querySelectorAll<HTMLElement>(
          "button, input, [tabindex]:not([tabindex='-1'])",
        ),
      ).filter((x) => !x.hasAttribute("disabled"));
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
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(id);
      window.removeEventListener("keydown", onKey);
      prevFocusRef.current?.focus();
      prevFocusRef.current = null;
    };
  }, [open, dialogRef]);
}
