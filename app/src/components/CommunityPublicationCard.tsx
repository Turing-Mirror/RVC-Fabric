import type { ReactNode } from "react";
import { CatalogCover } from "trm-ui";
import { useI18n } from "../i18n";
import type { ModelMetadata } from "../lib/communityPublication";

export function publicationGroups(metadata: ModelMetadata | undefined, locale: string) {
  return [metadata?.seriesI18n?.[locale] || metadata?.series, metadata?.groupI18n?.[locale] || metadata?.group];
}

export function CommunityPublicationCards({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-[repeat(auto-fill,minmax(min(220px,100%),1fr))] items-start gap-4">{children}</div>;
}

export function CommunityPublicationCard({ id, title, description, cover, version, date, groups, size, actions }: {
  id: string;
  title: string;
  description?: string;
  cover?: string;
  version?: string;
  date?: string;
  groups?: Array<string | undefined>;
  size?: number;
  actions: ReactNode;
}) {
  const { locale } = useI18n();
  const formattedDate = date && Number.isFinite(Date.parse(date))
    ? new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(date))
    : undefined;
  const sizeLabel = size && size > 0 ? new Intl.NumberFormat(locale, {
    style: "unit", unit: "megabyte", maximumFractionDigits: 1,
  }).format(size / 1_000_000) : undefined;
  const categories = [...new Set(groups?.filter(Boolean))];
  return (
    <article className="min-w-0 rounded-[var(--r)] bg-[var(--surface)] p-3">
      <CatalogCover sources={cover ? [cover] : []} placeholder={title} seed={id}
        release={formattedDate && <time dateTime={date}>{formattedDate}</time>} />
      <div className="px-0.5 pt-2.5">
        <h3 className="m-0 break-words text-[15px] font-semibold">{title}</h3>
        {(categories.length > 0 || version || sizeLabel) && (
          <div className="mt-1 flex flex-wrap gap-x-2 gap-y-1 break-words text-[11.5px] text-[var(--help)]">
            {categories.map((label) => <span key={label}>{label}</span>)}
            {version && <span>{version}</span>}
            {sizeLabel && <span>{sizeLabel}</span>}
          </div>
        )}
        {description?.trim() && <p className="m-0 mt-2 line-clamp-2 break-words text-[12.5px] text-[var(--ink-muted)]">{description}</p>}
        <div className="mt-2 flex flex-wrap items-center gap-1">{actions}</div>
      </div>
    </article>
  );
}
