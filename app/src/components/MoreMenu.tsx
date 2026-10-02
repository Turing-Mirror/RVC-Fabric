/**
 * 行内「⋯」更多菜单：从 ModelsPage 提出的共用件（C-11），
 * 语音转换文件行、模型卡片与音频页来源行共用同一套定位与关闭行为。
 */
import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { placePopup, type PopupAnchor, type PopupBox } from "../lib/popupPos";

export type MoreMenuItem = {
  label: string;
  action: () => void;
  danger?: boolean;
  /** 操作在途时禁用对应项，和行内按钮的 busy 表现一致。 */
  disabled?: boolean;
};

export type { PopupAnchor };

export function MoreMenuPopup({
  anchor,
  items,
  onClose,
  align = "right",
}: {
  anchor: PopupAnchor;
  items: MoreMenuItem[];
  /** 传了之后：选中项前先关闭，Esc 也走这个关闭 —— 焦点回到打开处的逻辑由调用方挂在它上面。 */
  onClose?: () => void;
  /** 右键就地打开时用 "left"，菜单左缘贴着指针而不是右缘。 */
  align?: "left" | "right";
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<PopupBox | null>(null);

  useLayoutEffect(() => {
    const place = () => {
      const el = ref.current;
      if (!el) return;
      setBox(
        placePopup(
          anchor,
          { width: Math.max(el.offsetWidth, el.scrollWidth), height: el.scrollHeight },
          { width: window.innerWidth, height: window.innerHeight },
          8,
          align,
        ),
      );
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [anchor, items.length, align]);

  // 打开时把焦点放进菜单第一项：键盘打开菜单后方向键直接可用，Esc 也能收到。
  useEffect(() => {
    ref.current?.querySelectorAll<HTMLElement>("[role=menuitem]")[0]?.focus();
  }, []);

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const opts = Array.from(
      ref.current?.querySelectorAll<HTMLElement>("[role=menuitem]:not([disabled])") ?? [],
    );
    if (!opts.length) return;
    const i = opts.findIndex((el) => el === document.activeElement);
    const focusAt = (next: number) => {
      e.preventDefault();
      opts[next]?.focus();
    };
    if (e.key === "ArrowDown") focusAt(i < 0 ? 0 : (i + 1) % opts.length);
    else if (e.key === "ArrowUp") focusAt(i < 0 ? opts.length - 1 : (i - 1 + opts.length) % opts.length);
    else if (e.key === "Home") focusAt(0);
    else if (e.key === "End") focusAt(opts.length - 1);
    else if (e.key === "Escape") {
      e.preventDefault();
      onClose?.();
    }
  };

  return (
    <div
      ref={ref}
      role="menu"
      className="menu-in fixed z-[90] min-w-[160px] py-1 rounded-[var(--rs)] bg-[var(--surface)] shadow-[0_8px_28px_rgba(0,0,0,0.18)] overflow-y-auto overflow-x-hidden overscroll-contain"
      style={{
        left: box?.left ?? anchor.right,
        top: box?.top ?? anchor.bottom + 6,
        maxHeight: box?.maxHeight,
        maxWidth: "calc(100vw - 16px)",
        visibility: box ? "visible" : "hidden",
      }}
      onClick={(e) => e.stopPropagation()}
      onContextMenu={(e) => {
        e.preventDefault();
        e.stopPropagation();
      }}
      onKeyDown={onKey}
    >
      {items.map((it) => (
        <button
          key={it.label}
          type="button"
          role="menuitem"
          disabled={it.disabled}
          className={[
            "block w-full text-left whitespace-nowrap border-0 bg-transparent px-3.5 py-2 text-[13px] cursor-pointer",
            it.danger
              ? "text-[var(--danger)] hover:bg-[color-mix(in_srgb,var(--danger)_10%,transparent)] focus-visible:bg-[color-mix(in_srgb,var(--danger)_10%,transparent)]"
              : "text-[var(--ink)] hover:bg-[color-mix(in_srgb,var(--ink)_5%,transparent)] focus-visible:bg-[color-mix(in_srgb,var(--ink)_5%,transparent)]",
            it.disabled ? "opacity-50 cursor-default" : "",
          ].join(" ")}
          onClick={() => {
            onClose?.();
            void it.action();
          }}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}
