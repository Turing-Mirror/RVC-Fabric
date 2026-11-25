import { ErrorNote } from "./ErrorNote";
import { diagnosticOf } from "../lib/diagnostics";
import { useEffect, useState } from "react";
import { Btn, Group, PageHead, PagePad, Warn, copyText, useNotify, usePageActive, usePaneOn } from "trm-ui";
import { useI18n } from "../i18n";
import { firstPackage, publication, publicationError, validUrl, type ModelDetail, type PublishedVersion } from "../lib/communityPublication";
import { openExternal } from "../lib/plaza";
import { CatalogTransition } from "./CatalogTransition";
import { StoreSection } from "./StoreSection";

export function CommunityModelDetail({ id, title, versionId, owner, onBack, onAuthor, onNewVersion, onEditListing }: {
  id: string;
  title: string;
  versionId?: string;
  owner?: true | string;
  onBack: () => void;
  onAuthor: (id: string) => void;
  onNewVersion: (model: ModelDetail, version: PublishedVersion) => void;
  onEditListing: (model: ModelDetail, version: PublishedVersion) => void;
}) {
  const { t, locale } = useI18n();
  const paneActive = usePaneOn();
  const pageActive = usePageActive();
  const active = paneActive && pageActive;
  const { tip } = useNotify();
  const [detail, setDetail] = useState<ModelDetail>();
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!active || detail) return;
    let current = true;
    void publication<ModelDetail>({ action: "asset", id }).then((result) => {
      if (current) setDetail(result);
    }).catch((cause) => { if (current) setError(publicationError(cause, "list")); });
    return () => { current = false; };
  }, [active, detail, id, retry]);

  const current = detail?.versions.find((version) => version.id === versionId) ?? detail?.versions.find(firstPackage);
  const canRevise = owner === true || (owner && owner === detail?.asset.ownerId);
  return <PagePad width="wide">
    <PageHead title={detail?.asset.metadata?.nameI18n?.[locale] || title} back={onBack}
      actions={detail && current && firstPackage(current) && canRevise && <>
        <Btn text onClick={() => onEditListing(detail, current)}>{t("publication.editListing")}</Btn>
        <Btn onClick={() => onNewVersion(detail, current)}>{t("publication.newVersion")}</Btn>
      </>} />
    <div className="mt-4">
      <StoreSection reloadToken={0} assetId={id} detail onAuthor={onAuthor} />
    </div>
    {error && <Warn>{diagnosticOf(error) ? <ErrorNote text={error} feature="store" /> : error} <Btn text onClick={() => { setError(""); setRetry((n) => n + 1); }}>{t("s.38108eaa1d")}</Btn></Warn>}
    <CatalogTransition scope={detail ? "versions" : "loading"}>
      {detail && detail.versions.length > 0 && <section className="mt-6">
        <h3 className="mb-3 mt-0 text-[16px] font-semibold">{t("publication.versions")}</h3>
        <Group>
          <div className="divide-y divide-[var(--hairline)]">
            {detail.versions.map((version) => {
              const file = firstPackage(version);
              const source = file?.sources.find((entry) => entry.state === "available") ?? file?.sources[0];
              const date = version.createdAt && new Date(version.createdAt);
              return <article key={version.id} className="space-y-2 py-3">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
                  <strong>{current?.id === version.id ? t("publication.currentVersion", { v0: version.label }) : version.label}</strong>
                  {date && !Number.isNaN(date.valueOf()) && <time dateTime={version.createdAt} className="text-[11.5px] text-[var(--help)]">
                    {new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(date)}
                  </time>}
                </div>
                {file && <div className="break-all text-[12.5px] text-[var(--help)]">{source?.upstreamPath || file.path}</div>}
                {source?.revision && <div className="break-all text-[11.5px] text-[var(--help)]">
                  {t("publication.fixedRevision", { v0: source.revision })}
                </div>}
                <div className="flex flex-wrap gap-3">
                  {source && validUrl(source.canonicalUrl) && <Btn text onClick={() => void openExternal(source.canonicalUrl)}>{t("s.voiceLinkSource")}</Btn>}
                  {file?.sha256 && <Btn text onClick={() => void copyText(file.sha256).then((copied) => tip(t(copied ? "publication.hashCopied" : "publication.copyFailed")))}>{t("publication.copyHash")}</Btn>}
                </div>
              </article>;
            })}
          </div>
        </Group>
      </section>}
    </CatalogTransition>
  </PagePad>;
}
