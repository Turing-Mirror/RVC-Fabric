/**
 * 行内「⋯」更多菜单：从 ModelsPage 提出的共用件（C-11），
 * 语音转换文件行与模型卡片共用同一套定位与关闭行为。
 */
import { useLayoutEffect, useRef, useState } from "react";
import { placePopup, type PopupAnchor, type PopupBox } from "../lib/popupPos";

export type MoreMenuItem = {
  label: string;
  action: () => void;
  danger?: boolean;
};

export type { PopupAnchor };

export function MoreMenuPopup({
  anchor,
  items,
}: {
  anchor: PopupAnchor;
  items: MoreMenuItem[];
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
        ),
      );
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [anchor, items.length]);

  return (
    <div
      ref={ref}
      className="fixed z-[90] min-w-[160px] py-1 rounded-[var(--rs)] bg-[var(--surface)] shadow-[0_8px_28px_rgba(0,0,0,0.18)] overflow-y-auto overflow-x-hidden"
      style={{
        left: box?.left ?? anchor.right,
        top: box?.top ?? anchor.bottom + 6,
        maxHeight: box?.maxHeight,
        maxWidth: "calc(100vw - 16px)",
        visibility: box ? "visible" : "hidden",
      }}
      onClick={(e) => e.stopPropagation()}
    >
      {items.map((it) => (
        <button
          key={it.label}
          type="button"
          className={[
            "block w-full text-left whitespace-nowrap border-0 bg-transparent px-3.5 py-2 text-[13px] cursor-pointer",
            it.danger
              ? "text-[var(--danger)] hover:bg-[color-mix(in_srgb,var(--danger)_10%,transparent)]"
              : "text-[var(--ink)] hover:bg-[color-mix(in_srgb,var(--ink)_5%,transparent)]",
          ].join(" ")}
          onClick={() => void it.action()}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}
