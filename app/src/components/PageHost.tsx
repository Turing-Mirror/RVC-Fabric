import { useEffect, useRef, useState, type ReactNode } from "react";
import { navDirection, type PageId } from "../lib/nav";

type Props = {
  page: PageId;
  children: (id: PageId) => ReactNode;
};

type Phase = {
  current: PageId;
  leaving: PageId | null;
  dir: 1 | -1 | 0;
};

/**
 * Directional page wipe following nav order.
 * Entering page from the right when navigating right, etc.
 */
export function PageHost({ page, children }: Props) {
  const [phase, setPhase] = useState<Phase>({
    current: page,
    leaving: null,
    dir: 0,
  });
  const reduce = usePrefersReducedMotion();
  const leaveTimer = useRef<number | null>(null);

  useEffect(() => {
    if (page === phase.current) return;
    const dir = navDirection(phase.current, page);
    if (reduce || dir === 0) {
      setPhase({ current: page, leaving: null, dir: 0 });
      return;
    }
    setPhase({ current: page, leaving: phase.current, dir });
    if (leaveTimer.current) window.clearTimeout(leaveTimer.current);
    leaveTimer.current = window.setTimeout(() => {
      setPhase((p) => ({ ...p, leaving: null }));
    }, 300);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-run on page id change
  }, [page, reduce]);

  useEffect(
    () => () => {
      if (leaveTimer.current) window.clearTimeout(leaveTimer.current);
    },
    [],
  );

  const enterCls =
    phase.dir === 1 ? "page-enter-l" : phase.dir === -1 ? "page-enter-r" : "";
  const leaveCls =
    phase.dir === 1 ? "page-leave-l" : phase.dir === -1 ? "page-leave-r" : "";

  return (
    <div className="relative flex-1 overflow-hidden">
      {phase.leaving ? (
        <div
          key={`leave-${phase.leaving}`}
          className={`absolute inset-0 overflow-y-auto pointer-events-none z-[1] ${leaveCls}`}
        >
          {children(phase.leaving)}
        </div>
      ) : null}
      <div
        key={`cur-${phase.current}`}
        className={`absolute inset-0 overflow-y-auto z-[2] ${enterCls}`}
        ref={(el) => {
          if (el) el.scrollTop = 0;
        }}
      >
        {children(phase.current)}
      </div>
    </div>
  );
}

function usePrefersReducedMotion(): boolean {
  const [v, setV] = useState(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const fn = () => setV(mq.matches);
    mq.addEventListener("change", fn);
    return () => mq.removeEventListener("change", fn);
  }, []);
  return v;
}
