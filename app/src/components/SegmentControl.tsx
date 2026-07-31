import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type SegmentOption<T extends string> = {
  id: T;
  label: ReactNode;
  title?: string;
};

type Props<T extends string> = {
  options: SegmentOption<T>[];
  value: T;
  onChange: (id: T) => void;
  className?: string;
  /** Hide sliding thumb and fall back to per-item highlight (narrow layout). */
  compact?: boolean;
  role?: "tablist" | "group";
};

/**
 * Liquid-glass segment control: one sliding thumb, not per-button backgrounds.
 * Spec: cubic-bezier spring, squeeze on move, prefers-reduced-motion safe.
 */
export function SegmentControl<T extends string>({
  options,
  value,
  onChange,
  className = "",
  compact = false,
  role = "group",
}: Props<T>) {
  const rootRef = useRef<HTMLDivElement>(null);
  const btnRefs = useRef<Map<T, HTMLButtonElement>>(new Map());
  const [thumb, setThumb] = useState({ x: 0, w: 0 });
  const [squish, setSquish] = useState(false);
  const first = useRef(true);

  const place = useCallback(
    (animate: boolean) => {
      const root = rootRef.current;
      const btn = btnRefs.current.get(value);
      if (!root || !btn) return;
      // `offsetLeft` is measured from the container's padding box, which is
      // the same origin `left: 0` uses for the absolutely-positioned thumb —
      // so no padding correction belongs here. Subtracting the 3px padding put
      // the thumb 3px left of its button: flush against the container on the
      // left, 6px of slack on the right. That is the lopsided pill.
      const x = btn.offsetLeft;
      const w = btn.offsetWidth;
      setThumb({ x, w });
      if (animate && !first.current) {
        setSquish(false);
        // force reflow for re-trigger
        void root.offsetWidth;
        setSquish(true);
      }
      first.current = false;
    },
    [value],
  );

  useLayoutEffect(() => {
    place(!first.current);
  }, [place, compact]);

  useEffect(() => {
    const onResize = () => place(false);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [place]);

  return (
    <div
      ref={rootRef}
      role={role}
      className={[
        "relative flex p-[3px] rounded-full",
        "bg-[color-mix(in_srgb,var(--ink)_5%,transparent)]",
        className,
      ].join(" ")}
    >
      {!compact && (
        <span
          aria-hidden
          className={[
            "absolute top-[3px] bottom-[3px] left-0 rounded-full pointer-events-none",
            "bg-[color-mix(in_srgb,var(--surface)_86%,transparent)]",
            "backdrop-blur-[10px] backdrop-saturate-150",
            "shadow-[var(--glass)]",
            "transition-[transform,width] duration-[520ms] ease-[var(--spring)]",
            squish ? "seg-thumb-move" : "",
          ].join(" ")}
          style={{
            width: thumb.w,
            transform: `translateX(${thumb.x}px)`,
          }}
        />
      )}
      {options.map((opt) => {
        const on = opt.id === value;
        return (
          <button
            key={opt.id}
            type="button"
            role={role === "tablist" ? "tab" : undefined}
            aria-selected={role === "tablist" ? on : undefined}
            title={opt.title}
            ref={(el) => {
              if (el) btnRefs.current.set(opt.id, el);
              else btnRefs.current.delete(opt.id);
            }}
            onClick={() => onChange(opt.id)}
            className={[
              "relative z-[1] border-0 bg-transparent cursor-pointer whitespace-nowrap",
              "text-[13px] px-4 py-1.5 rounded-full",
              "text-[var(--ink-muted)] transition-[color,transform,background,box-shadow]",
              "duration-200 ease-[var(--ease)] active:scale-95",
              "focus-visible:outline-2 focus-visible:outline-[var(--accent)] focus-visible:outline-offset-2",
              on ? "text-[var(--ink)]" : "hover:text-[var(--ink)]",
              compact && on
                ? "bg-[color-mix(in_srgb,var(--surface)_88%,transparent)] shadow-[var(--glass)]"
                : "",
            ].join(" ")}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
