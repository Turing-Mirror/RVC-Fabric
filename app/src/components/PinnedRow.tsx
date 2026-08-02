import { useEffect, useRef, useState } from "react";
import { colsForWidth } from "../lib/voices";
import type { PlazaItem } from "../lib/plaza";

/**
 * 广场顶部的「置顶」一排。
 *
 * 它**不是**第四种内容，而是下面「投放」的一个索引：同一条内容，上面出封面
 * 和标题，点一下滚到下面那条正文并高亮一下。所以这里不放正文、不放角标、
 * 也不放「查看详情」——那些下面都有，抄一遍只会让人以为是两条不同的东西。
 *
 * 卡片形状和模型页、社区音色完全一样（4:3 封面 + 一行标题），列数也走同一个
 * `colsForWidth`：默认窗口一行五张。发布侧最多只让五条带上 pinned，所以这里
 * 永远是一行，不会换行。
 *
 * 标题优先用 `pin_title`。投放标题是按整行排的，常常十几二十字，塞进一张卡
 * 只能截断；给置顶留一个短标题的口子，封面和跳转目标仍然共用同一条内容。
 */
export function PinnedRow({
  items,
  onPick,
}: {
  items: PlazaItem[];
  /** 点了哪一条。父组件负责滚过去并高亮。 */
  onPick: (id: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [cols, setCols] = useState(5);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((e) => {
      setCols(colsForWidth(e[0]?.contentRect.width || window.innerWidth));
    });
    ro.observe(el);
    setCols(colsForWidth(el.clientWidth || window.innerWidth));
    return () => ro.disconnect();
  }, []);

  if (!items.length) return null;

  return (
    <div
      ref={ref}
      className="grid gap-x-[18px] gap-y-4"
      style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
    >
      {items.map((it) => (
        <PinCard key={it.id} item={it} onPick={() => onPick(it.id)} />
      ))}
    </div>
  );
}

function PinCard({ item, onPick }: { item: PlazaItem; onPick: () => void }) {
  const [imgFailed, setImgFailed] = useState(false);
  const label = item.pin_title || item.title;
  const showImg = Boolean(item.image_url) && !imgFailed;

  return (
    <button
      type="button"
      onClick={onPick}
      title={label}
      className={[
        "text-left bg-transparent border-0 p-0 cursor-pointer block w-full",
        "focus-visible:outline-2 focus-visible:outline-[var(--accent)] focus-visible:outline-offset-2",
        "rounded-[var(--r)] transition-transform duration-200 ease-[var(--ease)]",
        "hover:-translate-y-0.5 active:scale-[0.985]",
      ].join(" ")}
    >
      <div className="aspect-[4/3] rounded-[var(--r)] grid place-items-center relative overflow-hidden bg-[color-mix(in_srgb,var(--ink)_7%,transparent)] text-[color-mix(in_srgb,var(--ink)_32%,transparent)] text-2xl">
        {showImg ? (
          <img
            src={item.image_url}
            alt=""
            loading="lazy"
            referrerPolicy="no-referrer"
            draggable={false}
            onError={() => setImgFailed(true)}
            className="absolute inset-0 w-full h-full object-cover"
          />
        ) : (
          <span>{label.slice(0, 4)}</span>
        )}
      </div>
      <div className="mt-2 text-[13.5px] leading-snug truncate">{label}</div>
    </button>
  );
}
