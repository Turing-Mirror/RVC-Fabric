import { useEffect, useState } from "react";
import { publication } from "../lib/communityPublication";

export function useSubmissionCover(coverId?: string | null) {
  const [preview, setPreview] = useState<{ id: string; url: string }>();
  useEffect(() => {
    if (!coverId) return;
    let current = true;
    void publication<{ url: string }>({ action: "cover_preview", id: coverId })
      .then(({ url }) => { if (current) setPreview({ id: coverId, url }); })
      .catch(() => undefined);
    return () => { current = false; };
  }, [coverId]);
  return preview && preview.id === coverId ? preview.url : undefined;
}
