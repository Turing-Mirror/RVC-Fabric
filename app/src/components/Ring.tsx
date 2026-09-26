/**
 * 环形占比图：一圈按比例分段，中间写总量，旁边是图例。用在「占用了多少、各是什么」这类地方。
 * 颜色由外面给，只从令牌取；段与段之间留一点缝，不画描边。
 */
import type { ReactNode } from "react";

export type RingSegment = { id: string; label: string; value: number; color: string; note?: string };

export function Ring({ segments, center, sub, size = 150 }: { segments: RingSegment[]; center: ReactNode; sub?: ReactNode; size?: number }) {
  const r = 44;
  const c = 2 * Math.PI * r;
  const total = segments.reduce((n, s) => n + Math.max(0, s.value), 0) || 1;
  const gap = segments.length > 1 ? 2 : 0;
  let offset = 0;
  return (
    <div className="flex items-center gap-6 flex-wrap">
      <div className="relative flex-none" style={{ width: size, height: size }}>
        <svg viewBox="0 0 120 120" width={size} height={size} aria-hidden className="-rotate-90">
          <circle cx="60" cy="60" r={r} fill="none" stroke="color-mix(in srgb, var(--ink) 7%, transparent)" strokeWidth="14" />
          {segments.map((s) => {
            const len = (Math.max(0, s.value) / total) * c;
            const dash = Math.max(0, len - gap);
            const el = <circle key={s.id} className="ring-seg" cx="60" cy="60" r={r} fill="none" stroke={s.color} strokeWidth="14" strokeDasharray={`${dash} ${c}`} strokeDashoffset={-offset} />;
            offset += len;
            return el;
          })}
        </svg>
        <div className="absolute inset-0 grid place-items-center text-center">
          <div>
            <div className="text-[18px] font-semibold tabular-nums">{center}</div>
            {sub ? <div className="text-[11.5px] text-[var(--meta)]">{sub}</div> : null}
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-2 text-[13px]">
        {segments.map((s) => (
          <div key={s.id} className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-[3px] flex-none" style={{ background: s.color }} />
            <span className="text-[var(--ink)]">{s.label}</span>
            {s.note ? <span className="text-[var(--meta)] tabular-nums">{s.note}</span> : null}
          </div>
        ))}
      </div>
    </div>
  );
}
