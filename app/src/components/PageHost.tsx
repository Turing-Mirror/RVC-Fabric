import { useEffect, type ReactNode } from "react";
import { PageHost as SlideHost } from "trm-ui";
import { navDirection, type PageId } from "../lib/nav";
import { noteMount, noteUnmount } from "../lib/lifecycle";

type Props = {
  page: PageId;
  children: (id: PageId) => ReactNode;
};

const nav = { direction: navDirection };

/**
 * 按导航顺序整页推移，动效由 TRM UI 的 PageHost 提供：
 * 新旧两页首尾相接一起平移，中途改主意时从当前位置接着走。
 */
export function PageHost({ page, children }: Props) {
  return (
    <SlideHost nav={nav} page={page}>
      {(id) => <Ledger id={id}>{children(id)}</Ledger>}
    </SlideHost>
  );
}

/** 装卸次数记进生命周期台账，供 C-01 的「切页 100 次不留净增长」验收。 */
function Ledger({ id, children }: { id: PageId; children: ReactNode }) {
  useEffect(() => {
    noteMount(`page:${id}`);
    return () => noteUnmount(`page:${id}`);
  }, [id]);
  return <>{children}</>;
}
