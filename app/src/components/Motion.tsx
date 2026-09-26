/**
 * 页内切换的动效：子页签、筛选结果、翻页。旧内容很快淡出、朝来处让一小步，
 * 新内容从去向那一侧浮上来，二者交叠，不是这边一灭、那边一亮。
 * 时长与 index.css 里 .swap-in、.swap-out 一致。
 */
import { memo, useEffect, useState, type CSSProperties, type ReactNode } from "react";

/** 旧内容留多久：等淡出放完。与 index.css 的 .swap-out 一致。 */
export const SWAP_OUT_MS = 180;
/** 依次浮现时相邻两项的间隔与最多排几项。 */
const STAGGER = { step: 24, max: 12 };

/** 第 i 项依次浮现的延迟。 */
export function stagger(i: number): CSSProperties {
  return { animationDelay: `${Math.min(i, STAGGER.max) * STAGGER.step}ms` };
}

/** 淡出中的旧内容原样留着，不跟着外面重绘。 */
const Frozen = memo(function Frozen({ node }: { node: ReactNode }) {
  return <>{node}</>;
});

/**
 * 同一处内容换了一批。k 变了，旧的淡出、新的浮上来；dir 为 1 从右边来，-1 从左边来，
 * 0 只有一点纵向的浮动。哪怕新旧是同一项、或只剩一项，也照样有这一下。
 */
export function Swap({ k, dir = 0, children, className = "" }: { k: string; dir?: -1 | 0 | 1; children: ReactNode; className?: string }) {
  const [cur, setCur] = useState({ k, node: children, seq: 0 });
  const [old, setOld] = useState<{ node: ReactNode; seq: number } | null>(null);
  if (cur.k !== k) {
    setOld({ node: cur.node, seq: cur.seq });
    setCur({ k, node: children, seq: cur.seq + 1 });
  } else if (cur.node !== children) {
    setCur({ ...cur, node: children });
  }
  useEffect(() => {
    if (!old) return;
    const id = window.setTimeout(() => setOld(null), SWAP_OUT_MS);
    return () => window.clearTimeout(id);
  }, [old]);
  const vars = { "--swap-dx": `${dir * 18}px`, "--swap-ox": `${dir * -10}px` } as CSSProperties;
  return (
    <div className={`relative ${className}`} style={vars}>
      {old ? (
        <div key={`out-${old.seq}`} inert aria-hidden className="swap-out absolute inset-x-0 top-0 pointer-events-none">
          <Frozen node={old.node} />
        </div>
      ) : null}
      <div key={cur.seq} className={cur.seq ? "swap-in" : ""}>
        {cur.node}
      </div>
    </div>
  );
}
