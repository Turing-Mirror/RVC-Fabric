import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { t } from "../i18n/t";

/** 翻页动效时长，与 TRM UI 的推移一致。 */
const FLOW_MS = 420;
const EASE = "cubic-bezier(0.32, 0.72, 0, 1)";

/** 要显示的页码；null 是省略号。首尾两页和当前页前后一页总在。 */
export function pageList(page: number, pages: number): (number | null)[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, i) => i + 1);
  const keep = new Set([1, pages, page - 1, page, page + 1, ...(page <= 3 ? [2, 3, 4] : []), ...(page >= pages - 2 ? [pages - 3, pages - 2, pages - 1] : [])]);
  const list = [...keep].filter((p) => p >= 1 && p <= pages).sort((a, b) => a - b);
  return list.flatMap((p, i) => (i && p - list[i - 1] > 1 ? [null, p] : [p]));
}

type Box = { x: number; w: number; h: number };

function Chevron({ back }: { back?: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={back ? "M15 18l-6-6 6-6" : "M9 6l6 6-6 6"} />
    </svg>
  );
}

/**
 * 翻页（页码从 1 起）。只有一页时不显示；页码多时中间用省略号。
 * 换页时当前页的底色滑过去；留下的页码滑到新位置，新出现的页码淡入，离开的页码原地淡出。
 */
export function Pager({ page, pages, onChange, className = "mt-6" }: { page: number; pages: number; onChange: (p: number) => void; className?: string }) {
  const box = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<Box | null>(null);
  const [armed, setArmed] = useState(false);
  const lefts = useRef<Map<string, { x: number; label: string }> | null>(null);
  const [ghosts, setGhosts] = useState<{ key: string; x: number; label: string; seq: number }[]>([]);
  const list = pageList(page, pages);
  const keyed = list.map((p, i) => ({ p, key: p === null ? `gap-${list[i - 1]}` : `p${p}` }));

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const cur = el.querySelector<HTMLElement>(':scope > [aria-current="page"]');
    const next = cur ? { x: cur.offsetLeft, w: cur.offsetWidth, h: cur.offsetHeight } : null;
    setPos((p) => (p && next && p.x === next.x && p.w === next.w && p.h === next.h ? p : next));
    const now = new Map<string, { x: number; label: string }>();
    const quiet = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.querySelectorAll<HTMLElement>(":scope > [data-k]").forEach((node) => {
      const key = node.dataset.k ?? "";
      now.set(key, { x: node.offsetLeft, label: node.textContent ?? "" });
      const was = lefts.current?.get(key);
      if (quiet || !lefts.current || !node.animate) return;
      if (!was) node.animate([{ opacity: 0, transform: "scale(0.86)" }, { opacity: 1, transform: "none" }], { duration: FLOW_MS, easing: EASE });
      else if (was.x !== node.offsetLeft) node.animate([{ transform: `translate3d(${was.x - node.offsetLeft}px, 0, 0)` }, { transform: "none" }], { duration: FLOW_MS, easing: EASE });
    });
    const gone = lefts.current ? [...lefts.current].filter(([k]) => !now.has(k)) : [];
    lefts.current = now;
    if (gone.length && !quiet) setGhosts(gone.map(([key, v]) => ({ key, ...v, seq: Date.now() })));
  }, [page, pages]);

  useEffect(() => {
    if (!pos || armed) return;
    const id = requestAnimationFrame(() => setArmed(true));
    return () => cancelAnimationFrame(id);
  }, [pos, armed]);

  useEffect(() => {
    if (!ghosts.length) return;
    const id = window.setTimeout(() => setGhosts([]), FLOW_MS);
    return () => window.clearTimeout(id);
  }, [ghosts]);

  if (pages <= 1) return null;
  const btn = "relative h-8 min-w-8 px-2 grid place-items-center rounded-[var(--rs)] border-0 bg-transparent cursor-pointer text-[13px] tabular-nums transition-colors disabled:opacity-30 disabled:cursor-default";
  const hover = "enabled:hover:text-[var(--ink)] enabled:hover:bg-[color-mix(in_srgb,var(--ink)_4%,transparent)]";
  return (
    <nav aria-label={t("s.pagerLabel")} className={`${className} flex items-center justify-center gap-1`}>
      <button type="button" aria-label={t("s.b41561d807")} disabled={page <= 1} onClick={() => onChange(page - 1)} className={`${btn} text-[var(--ink-muted)] ${hover}`}>
        <Chevron back />
      </button>
      <div ref={box} className="relative flex items-center gap-1">
        {pos ? (
          <span
            aria-hidden
            className="absolute left-0 top-0 pointer-events-none rounded-[var(--rs)] bg-[color-mix(in_srgb,var(--ink)_6%,transparent)]"
            style={{
              width: pos.w,
              height: pos.h,
              transform: `translate3d(${pos.x}px, 0, 0)`,
              transition: armed ? `transform ${FLOW_MS}ms ${EASE}, width ${FLOW_MS}ms ${EASE}` : undefined,
            }}
          />
        ) : null}
        {keyed.map(({ p, key }) =>
          p === null ? (
            <span key={key} data-k={key} aria-hidden className="h-8 min-w-6 grid place-items-center text-[13px] text-[var(--meta)]">
              …
            </span>
          ) : (
            <button
              key={key}
              data-k={key}
              type="button"
              aria-current={p === page ? "page" : undefined}
              onClick={() => onChange(p)}
              className={`${btn} ${p === page ? "text-[var(--ink)] font-medium" : `text-[var(--ink-muted)] ${hover}`}`}
            >
              {p}
            </button>
          ),
        )}
        {ghosts.map((g) => (
          <span key={`${g.key}-${g.seq}`} aria-hidden className="pager-ghost absolute top-0 h-8 min-w-8 px-2 grid place-items-center text-[13px] tabular-nums text-[var(--ink-muted)] pointer-events-none" style={{ left: g.x }}>
            {g.label}
          </span>
        ))}
      </div>
      <button type="button" aria-label={t("s.67a246a344")} disabled={page >= pages} onClick={() => onChange(page + 1)} className={`${btn} text-[var(--ink-muted)] ${hover}`}>
        <Chevron />
      </button>
    </nav>
  );
}
