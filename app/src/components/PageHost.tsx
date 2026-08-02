import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { navDirection, type PageId } from "../lib/nav";

type Props = {
  page: PageId;
  children: (id: PageId) => ReactNode;
};

type Phase = {
  /** Named `page`, not `current`: `x.current` reads as a ref. */
  page: PageId;
  leaving: PageId | null;
  dir: 1 | -1 | 0;
};

/**
 * Directional page wipe following nav order.
 * Entering page from the right when navigating right, etc.
 */
export function PageHost({ page, children }: Props) {
  const [phase, setPhase] = useState<Phase>({
    page,
    leaving: null,
    dir: 0,
  });
  const reduce = usePrefersReducedMotion();
  const leaveTimer = useRef<number | null>(null);

  useEffect(() => {
    if (page === phase.page) return;
    const dir = navDirection(phase.page, page);
    if (reduce || dir === 0) {
      setPhase({ page, leaving: null, dir: 0 });
      return;
    }
    setPhase({ page, leaving: phase.page, dir });
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

  // Scroll to the top when the *page* changes — not on every render.
  //
  // This used to be an inline `ref={(el) => { if (el) el.scrollTop = 0 }}`.
  // An inline callback has a new identity every render, so React detached and
  // reattached it every time, running the reset each pass. The engine status
  // poll re-renders App 2.5x a second while converting, which meant the
  // settings and models pages snapped back to the top continuously and could
  // not be scrolled at all with the voice changer running.
  const paneRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (paneRef.current) paneRef.current.scrollTop = 0;
  }, [phase.page]);

  const enterCls =
    phase.dir === 1 ? "page-enter-l" : phase.dir === -1 ? "page-enter-r" : "";
  const leaveCls =
    phase.dir === 1 ? "page-leave-l" : phase.dir === -1 ? "page-leave-r" : "";

  return (
    <div className="relative flex-1 overflow-hidden">
      {phase.leaving ? (
        <div
          key={`leave-${phase.leaving}`}
          // 离场层不需要能滚：它是新挂上去的节点，scrollTop 本来就是 0，
          // 300ms 后就卸载了。留着 overflow-y-auto 只是多一个滚动容器，
          // 切页那一瞬间会跟着画出第二根滚动条。
          className={`absolute inset-0 overflow-hidden pointer-events-none z-[1] ${leaveCls}`}
        >
          {children(phase.leaving)}
        </div>
      ) : null}
      <div
        key={`cur-${phase.page}`}
        ref={paneRef}
        className={`absolute inset-0 overflow-y-auto z-[2] ${enterCls}`}
      >
        {children(phase.page)}
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
