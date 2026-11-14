import { useEffect, useState } from "react";
import { usePaneOn, useI18n as useUiI18n } from "trm-ui";
import { useI18n } from "../i18n";
import { openExternal } from "../lib/plaza";
import { newDraft, publication, publicationError, validUrl, type Draft, type Submission } from "../lib/communityPublication";
import { Btn, Group, PageHead, PagePad, Warn } from "./ui";

type AuthorAsset = Submission["asset"] & {
  id: string; upstreamUrl?: string; coverUrl?: string;
  compatibleVersion: { label: string; metadata?: Submission["version"]["metadata"]; package: { path: string; sha256: string } };
};
type AuthorList = { name?: string; items: AuthorAsset[]; nextCursor?: string };

export function CommunityAuthor({ author, owned, onBack, onNewVersion, onView }: {
  author?: string; owned?: boolean; onBack: () => void; onNewVersion?: (draft: Draft) => void;
  onView: (id: string, title: string) => void;
}) {
  const { t } = useI18n();
  const { t: uiText } = useUiI18n();
  const active = usePaneOn();
  const [result, setResult] = useState<AuthorList>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const read = (cursor?: string) => owned
    ? publication<AuthorList>({ action: "owned", cursor })
    : publication<AuthorList>({ action: "author", id: author || "", cursor });

  useEffect(() => {
    if (!active || result || error) return;
    let mounted = true;
    const initial = owned ? publication<AuthorList>({ action: "owned" })
      : publication<AuthorList>({ action: "author", id: author || "" });
    void initial.then((next) => { if (mounted) setResult(next); })
      .catch((cause) => { if (mounted) setError(publicationError(cause, "list")); });
    return () => { mounted = false; };
  }, [active, author, owned, result, error]);

  async function more() {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const next = await read(result?.nextCursor);
      setResult((old) => ({ ...next, items: [...(old?.items ?? []), ...next.items] }));
    } catch (cause) { setError(publicationError(cause, "list")); }
    finally { setBusy(false); }
  }

  function revise(item: AuthorAsset) {
    const previous: Submission = {
      id: "", state: "published", asset: item, updatedAt: "", reviews: [],
      version: { label: "", metadata: item.compatibleVersion.metadata, files: [] },
    };
    const draft = newDraft(previous, item.id);
    onNewVersion?.({ ...draft, url: item.upstreamUrl || "", label: "", cover: "" });
  }

  const authorUrl = result?.items.find((item) => item.authorUrl && validUrl(item.authorUrl))?.authorUrl;
  return <PagePad width="wide">
    <PageHead title={owned ? t("publication.myModels") : result?.name || t("s.voiceLinkAuthor")}
      actions={<>
        <Btn onClick={onBack}>{uiText("ui.common.back")}</Btn>
        {!owned && authorUrl && <Btn onClick={() => void openExternal(authorUrl)}>{t("publication.externalAuthor")}</Btn>}
      </>} />
    {error && <Warn>{error} <Btn onClick={() => setError("")}>{t("s.38108eaa1d")}</Btn></Warn>}
    {!result && !error && <p role="status">{t("s.f950213ab7")}</p>}
    {result?.items.length === 0 && <p>{t("publication.noModels")}</p>}
    {result && result.items.length > 0 && <Group>
      {result.items.map((item) => <article key={item.id} className="flex flex-wrap items-center gap-3 py-3 text-[13px]">
        {item.coverUrl && <img alt="" draggable={false} src={item.coverUrl} className="h-12 w-16 rounded-[var(--rs)] object-cover" />}
        <div className="min-w-0 flex-1 break-words">
          <strong>{item.title}</strong>
          <div className="text-[var(--help)]">{item.compatibleVersion.label}</div>
        </div>
        {item.upstreamUrl && validUrl(item.upstreamUrl) && <Btn onClick={() => void openExternal(item.upstreamUrl!)}>{t("s.voiceLinkSource")}</Btn>}
        <Btn onClick={() => onView(item.id, item.title)}>{t("s.f7acefd2d4")}</Btn>
        {owned && <Btn onClick={() => revise(item)}>{t("publication.newVersion")}</Btn>}
      </article>)}
    </Group>}
    {result?.nextCursor && <Btn busy={busy} onClick={() => void more()}>{t("publication.moreModels")}</Btn>}
  </PagePad>;
}
