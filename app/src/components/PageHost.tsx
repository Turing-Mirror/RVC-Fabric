import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { navDirection, type PageId } from "../lib/nav";
import { noteMount, noteUnmount } from "../lib/lifecycle";

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
 * 离场层挂多久。**必须和 index.css 里 `.page-leave-*` 的动画时长一致。**
 *
 * 短了就是动画放到一半节点被拔掉，旧页「啪」一下消失；长了则是一个已经看不见
 * 的图层继续占着，白白多一层。以前这里写死 300ms 而动画是 420ms，旧页在
 * 淡出到七成的时候被砍掉。
 */
const LEAVE_MS = 420;

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
    }, LEAVE_MS);
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

  // 同一页在「当前」和「离场」之间只换类名不换 key，子树保持挂载：
  // 离场动画放完才卸载，期间不会把页面的取数/订阅副作用再跑一遍。
  // 快速来回切时，仍在离场动画里的页直接回到当前位，装卸各只发生一次。
  const shown =
    phase.leaving && phase.leaving !== phase.page
      ? [phase.leaving, phase.page]
      : [phase.page];

  return (
    <div className="relative flex-1 overflow-hidden">
      {shown.map((id) => {
        const leaving = id === phase.leaving;
        return (
          <PagePane
            key={id}
            id={id}
            paneRef={leaving ? undefined : paneRef}
            className={
              leaving
                ? `absolute inset-0 overflow-hidden pointer-events-none z-[1] ${leaveCls}`
                : `absolute inset-0 overflow-y-auto z-[2] ${enterCls}`
            }
          >
            {children(id)}
          </PagePane>
        );
      })}
    </div>
  );
}

/**
 * 一层页面容器。key 就是页面 id，装卸次数记进生命周期台账，
 * 供 C-01 的「切页 100 次不留净增长」验收。
 */
function PagePane({
  id,
  paneRef,
  className,
  children,
}: {
  id: PageId;
  paneRef?: React.RefObject<HTMLDivElement | null>;
  className: string;
  children: ReactNode;
}) {
  useEffect(() => {
    noteMount(`page:${id}`);
    return () => noteUnmount(`page:${id}`);
  }, [id]);
  return (
    <div ref={paneRef} className={className}>
      {children}
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
