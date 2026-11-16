import { Btn, Group, PageHead, PagePad } from "trm-ui";
import { useI18n } from "../i18n";
import { useSubmissionCover } from "../hooks/useSubmissionCover";
import { type Submission, validUrl } from "../lib/communityPublication";
import { openExternal } from "../lib/plaza";
import { CommunityThumb } from "./CommunityThumb";

export function CommunitySubmissionDetail({ submission, onBack, onEdit }: {
  submission: Submission;
  onBack: () => void;
  onEdit: () => void;
}) {
  const { t, locale } = useI18n();
  const cover = useSubmissionCover(submission.coverUrl ? undefined : submission.coverUploadId);
  const editable = submission.state === "rejected" || submission.state === "withdrawn";
  const { asset, version } = submission;
  const state = t({
    pending: "publication.pending",
    published: "publication.published",
    rejected: "publication.rejected",
    withdrawn: "publication.withdrawn",
  }[submission.state]);
  const source = version.files[0]?.sources[0];

  return <PagePad width="wide">
    <PageHead title={asset.title} back={onBack} actions={editable && <Btn primary onClick={onEdit}>{t("publication.edit")}</Btn>} />
    <div className="mt-4 space-y-6">
      <Group>
        <div className="flex items-start gap-4">
          <CommunityThumb title={asset.title} src={submission.coverUrl || cover} />
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap gap-3 text-[13px]"><strong>{state}</strong><span>{version.label}</span></div>
            <p className="m-0 text-[13px] text-[var(--help)]">{asset.originalAuthor}</p>
            {asset.description && <p className="m-0 whitespace-pre-wrap break-words text-[15px]">{asset.description}</p>}
            {version.files.map((file) => <div key={file.path} className="break-all text-[12.5px] text-[var(--help)]">{file.path}</div>)}
            {source && validUrl(source.canonicalUrl) && <Btn text onClick={() => void openExternal(source.canonicalUrl)}>{t("s.voiceLinkSource")}</Btn>}
          </div>
        </div>
      </Group>
      {submission.reviews.length > 0 && <section>
        <h3 className="mb-3 mt-0 text-[16px] font-semibold">{t("publication.reviewHistory")}</h3>
        <Group>
          <div className="divide-y divide-[var(--hairline)]">
            {submission.reviews.map((entry, index) => <div key={entry.createdAt ?? index} className="py-3">
              {entry.action && <strong className="text-[13px]">{t({
                publish: "publication.published", reject: "publication.rejected", withdraw: "publication.withdrawn",
              }[entry.action])}</strong>}
              {entry.createdAt && <time className="ml-2 text-[11.5px] text-[var(--help)]" dateTime={entry.createdAt}>
                {new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(entry.createdAt))}
              </time>}
              {entry.reason && <p className="mb-0 mt-1 whitespace-pre-wrap break-words text-[13px]">{entry.reason}</p>}
            </div>)}
          </div>
        </Group>
      </section>}
    </div>
  </PagePad>;
}
