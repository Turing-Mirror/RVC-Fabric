import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { useExit } from "../hooks/useExit";
import { t } from "../i18n/t";

export type SelectOption = {
  id: string;
  label: string;
  /** 悬停时显示的完整名称（列表里的名字被截断时用）。 */
  title?: string;
  /** 下一级条目，往里缩一格。 */
  indent?: boolean;
};

/** 默认的外框：一圈细线，聚焦或展开时换成强调色。工具窗口里的表单用 box 传自己那一套。 */
const BOX =
  "border-0 px-3.5 py-[7px] rounded-[var(--rs)] shadow-[inset_0_0_0_1px_var(--line)] focus-visible:shadow-[inset_0_0_0_1px_var(--accent)] data-[open]:shadow-[inset_0_0_0_1px_var(--accent)]";

/** 工具窗口表单里的外框，和同一行的输入框一样用细边框。 */
export const TOOL_BOX =
  "rounded-[var(--rs)] border border-[var(--hairline)] px-2 py-1.5 focus-visible:border-[var(--accent)] data-[open]:border-[var(--accent)]";

/** 列表离控件的距离，和离窗口边缘至少留的距离。 */
const GAP = 4;
const EDGE = 8;

type Place = { left: number; top: number; width: number; maxHeight: number; above: boolean };

/**
 * 下拉选择。列表由我们自己画，从控件正下方展开（下方放不下时从上方），
 * 宽度不小于控件本身；不再用系统那张会盖住控件、深色下还会白底白字的列表。
 *
 * 键盘：方向键移动，Enter/空格选中，Esc 或 Tab 收起。
 */
export function Select({
  value,
  options,
  onChange,
  full = false,
  width,
  disabled = false,
  box = BOX,
  className = "",
  ariaLabel,
  placeholder,
}: {
  value: string;
  options: SelectOption[];
  onChange: (v: string) => void;
  full?: boolean;
  width?: number;
  disabled?: boolean;
  /** 外框样式。 */
  box?: string;
  /** 额外的布局类（flex-1、min-w-0 之类）。 */
  className?: string;
  ariaLabel?: string;
  /** 没有任何选项时显示的字。 */
  placeholder?: string;
}) {
  const listId = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [place, setPlace] = useState<Place | null>(null);
  const { mounted, leaving } = useExit(open, 140);

  // 已保存的设备不在当前列表里（拔掉了、驱动重置）时，照样显示出来并注明，
  // 不能显示成空白 —— 那样看着像没设，引擎其实还在用它。
  const missing = Boolean(value) && !options.some((o) => o.id === value);
  const items: SelectOption[] = [
    ...(options.length === 0 && !missing ? [{ id: "", label: placeholder ?? t("s.e6b7c3d266") }] : []),
    ...(missing ? [{ id: value, label: value + t("s.1cab0503c2") }] : []),
    ...options,
  ];
  const current = items.find((o) => o.id === value) ?? items[0];

  const measure = () => {
    const a = trigger.current?.getBoundingClientRect();
    const el = list.current;
    if (!a || !el) return;
    const h = el.scrollHeight;
    const below = window.innerHeight - a.bottom - GAP - EDGE;
    const aboveRoom = a.top - GAP - EDGE;
    const above = h > below && aboveRoom > below;
    const maxHeight = Math.max(80, above ? aboveRoom : below);
    const w = Math.max(a.width, el.scrollWidth);
    const left = Math.min(Math.max(EDGE, a.left), Math.max(EDGE, window.innerWidth - w - EDGE));
    const top = above ? a.top - GAP - Math.min(h, maxHeight) : a.bottom + GAP;
    setPlace({ left, top, width: a.width, maxHeight, above });
  };

  useLayoutEffect(() => {
    if (open) measure();
  }, [open]);

  // 打开时让当前项进入视野。
  useEffect(() => {
    if (!open || active < 0) return;
    list.current?.querySelectorAll<HTMLElement>("[role=option]")[active]?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => {
      const n = e.target as Node;
      if (trigger.current?.contains(n) || list.current?.contains(n)) return;
      setOpen(false);
    };
    const onScroll = (e: Event) => {
      if (list.current?.contains(e.target as Node)) return;
      setOpen(false);
    };
    const close = () => setOpen(false);
    window.addEventListener("pointerdown", outside, true);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", close);
    window.addEventListener("blur", close);
    return () => {
      window.removeEventListener("pointerdown", outside, true);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", close);
      window.removeEventListener("blur", close);
    };
  }, [open]);

  const show = () => {
    if (disabled) return;
    setActive(Math.max(0, items.findIndex((o) => o.id === value)));
    setPlace(null);
    setOpen(true);
  };

  const pick = (o: SelectOption) => {
    setOpen(false);
    trigger.current?.focus();
    if (o.id !== value) onChange(o.id);
  };

  const onKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        show();
      }
      return;
    }
    if (e.key === "Escape" || e.key === "Tab") {
      if (e.key === "Escape") e.preventDefault();
      setOpen(false);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(items.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    } else if (e.key === "Home" || e.key === "End") {
      e.preventDefault();
      setActive(e.key === "Home" ? 0 : items.length - 1);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      const o = items[active];
      if (o) pick(o);
    }
  };

  return (
    <>
      <button
        ref={trigger}
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        data-open={open || undefined}
        aria-controls={open ? listId : undefined}
        aria-label={ariaLabel}
        disabled={disabled}
        title={current?.title}
        onClick={() => (open ? setOpen(false) : show())}
        onKeyDown={onKey}
        style={width ? { minWidth: width } : undefined}
        className={[
          "inline-flex items-center gap-2 min-w-0 bg-transparent text-left cursor-pointer",
          "text-[13px] text-[var(--ink)] outline-none transition-shadow",
          "disabled:opacity-50 disabled:cursor-default",
          box,
          full ? "w-full" : "",
          className,
        ].join(" ")}
      >
        <span className="min-w-0 flex-1 truncate">{current?.label.trim()}</span>
        <svg
          aria-hidden
          viewBox="0 0 12 12"
          className={`w-[10px] h-[10px] flex-none text-[var(--meta)] transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        >
          <path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {mounted
        ? createPortal(
            <div
              ref={list}
              id={listId}
              role="listbox"
              aria-label={ariaLabel}
              className={[
                "fixed z-[400] py-1 overflow-y-auto overflow-x-hidden",
                "rounded-[var(--rs)] bg-[var(--surface)]",
                "shadow-[0_10px_30px_-8px_rgba(0,0,0,.28),inset_0_0_0_1px_var(--hairline)]",
                leaving ? "menu-out" : "menu-in",
              ].join(" ")}
              style={{
                left: place?.left ?? -9999,
                top: place?.top ?? -9999,
                minWidth: place?.width,
                maxWidth: "calc(100vw - 16px)",
                maxHeight: place?.maxHeight,
                visibility: place ? "visible" : "hidden",
                transformOrigin: place?.above ? "bottom center" : "top center",
              }}
            >
              {items.map((o, i) => {
                const selected = o.id === value;
                return (
                  <div
                    key={`${o.id}|${i}`}
                    role="option"
                    aria-selected={selected}
                    title={o.title}
                    onPointerEnter={() => setActive(i)}
                    onClick={() => pick(o)}
                    className={[
                      "mx-1 flex items-center gap-2 rounded-[6px] py-[6px] pr-3 text-[13px] whitespace-nowrap cursor-pointer",
                      o.indent ? "pl-6" : "pl-2.5",
                      selected ? "text-[var(--accent)]" : "text-[var(--ink)]",
                      i === active ? "bg-[color-mix(in_srgb,var(--ink)_6%,transparent)]" : "",
                    ].join(" ")}
                  >
                    <span className="flex-1">{o.label.trim()}</span>
                    <span aria-hidden className={`w-3 text-[11px] text-right ${selected ? "" : "invisible"}`}>
                      ✓
                    </span>
                  </div>
                );
              })}
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
