import { useState } from "react";
import { CoverPlaceholder, ThumbImage } from "trm-ui";

export function CommunityThumb({ title, src }: { title: string; src?: string }) {
  const [failed, setFailed] = useState<string>();
  return (
    <div className="relative h-12 w-16 shrink-0 overflow-hidden rounded-[var(--rs)] bg-[var(--stage)]" aria-hidden="true">
      <CoverPlaceholder name={title} className="absolute inset-0 text-[16px]" />
      {src && failed !== src && <ThumbImage src={src} px={160} alt="" draggable={false}
        className="absolute inset-0 h-full w-full bg-[var(--stage)] object-contain" onError={() => setFailed(src)} />}
    </div>
  );
}
