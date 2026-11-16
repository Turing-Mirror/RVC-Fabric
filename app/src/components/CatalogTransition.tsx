import type { ReactNode } from "react";
import { Morph, QueueList } from "trm-ui";

/** Catalog identity changes slide; progress updates retain the current content. */
export function CatalogTransition({ scope, page = 1, order, dir, children }: {
  scope: string;
  page?: number;
  order?: readonly string[];
  dir?: -1 | 1;
  children: ReactNode;
}) {
  return (
    <Morph>
      <QueueList
        className="catalog-transition"
        scope={scope}
        page={page}
        order={order}
        dir={dir}
        items={[children]}
        keyOf={() => "content"}
        render={content => content}
      />
    </Morph>
  );
}
