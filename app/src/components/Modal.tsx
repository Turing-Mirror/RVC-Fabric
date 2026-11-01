import { useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useExit } from "../hooks/useExit";
import { useLeaving } from "./Presence";

/**
 * 所有弹窗共用的外壳：一层半透明底，中间放面板。
 *
 * 进场时底色淡入、面板从略小略低的位置浮上来；关闭时反过来，放完再卸掉。
 * 面板就是 children 本身，样式各弹窗自己定。
 *
 * open 为假时（或外层 Leave 正在退场时）按最后一次的内容画完退场。
 *
 * 盖住整个窗口的弹窗挂到 body 上：页面切换时页面层带着变换，弹窗留在页面里会被困在
 * 页面那一层，底栏的分段控件之类就会画到弹窗上面。
 */
export function Modal({
  open = true,
  onBackdrop,
  z = 100,
  contained = false,
  children,
}: {
  open?: boolean;
  /** 点底色时做什么。不传就是点了不关。 */
  onBackdrop?: () => void;
  z?: number;
  /** 盖住所在容器而不是整个窗口（开机引导那几层）。 */
  contained?: boolean;
  children?: ReactNode;
}) {
  const outerLeaving = useLeaving();
  const show = open && !outerLeaving;
  const { mounted, leaving } = useExit(show);
  const last = useRef<ReactNode>(null);
  if (show) last.current = children;
  if (!mounted) return null;
  const layer = (
    <div
      data-leaving={leaving || undefined}
      className={`modal-scrim ${contained ? "absolute" : "fixed"} inset-0 grid place-items-center p-6 bg-[color-mix(in_srgb,var(--ink)_28%,transparent)]`}
      style={{ zIndex: z }}
      onClick={leaving ? undefined : onBackdrop}
    >
      {show ? children : last.current}
    </div>
  );
  return contained ? layer : createPortal(layer, document.body);
}
