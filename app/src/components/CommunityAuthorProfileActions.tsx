import { invoke } from "@tauri-apps/api/core";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useI18n as useUiI18n, Field, Modal, TextInput, useNotify } from "trm-ui";
import { useI18n } from "../i18n";
import { AUTHOR_URL_LABEL_LIMIT, authorLinkName, validUrl } from "../lib/communityPublication";
import { openExternal } from "../lib/plaza";
import { Btn, Warn } from "./ui";

type AuthorLink = { url: string | null; label?: string | null };
type AuthorProfile = AuthorLink & { configured: boolean };

export function CommunityAuthorProfileActions({ fallback, own, active }: {
  fallback?: AuthorLink;
  own?: boolean;
  active?: boolean;
}) {
  const { t } = useI18n();
  const { t: uiText } = useUiI18n();
  const { tip } = useNotify();
  const [global, setGlobal] = useState<AuthorProfile>();
  const [draft, setDraft] = useState({ url: "", label: "" });
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const reads = useRef(0);

  useEffect(() => {
    if (!own || !active) return;
    let cancelled = false;
    function read() {
      const ticket = ++reads.current;
      void invoke<AuthorProfile>("community_account_author_profile").then(value => {
        if (!cancelled && ticket === reads.current) setGlobal(value);
      }).catch(() => {});
    }
    read();
    window.addEventListener("focus", read);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", read);
    };
  }, [own, active]);

  const current = own && global && (global.configured || global.url) ? global : fallback;
  const url = current?.url;
  const showLink = url && validUrl(url);
  const form = useRef<HTMLFormElement>(null);
  const canSave = !draft.url.trim() || validUrl(draft.url);
  const title = t("publication.editAuthorProfile");

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!canSave || busy) return;
    setBusy(true);
    setFailed(false);
    try {
      const saved = await invoke<AuthorProfile>("community_account_author_profile", { update: draft });
      reads.current++;
      setGlobal(saved);
      setEditing(false);
      tip(t("publication.authorProfileSaved"));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return <>
    {showLink && <Btn text onClick={() => void openExternal(url)}>
      <span className="block max-w-52 truncate" title={url}>{authorLinkName(url, current?.label)}</span>
    </Btn>}
    {own && <Btn onClick={() => {
      setDraft({ url: current?.url ?? "", label: current?.label ?? "" });
      setFailed(false);
      setEditing(true);
    }}>{title}</Btn>}
    <Modal open={Boolean(active && own && editing)} onClose={() => { if (!busy) setEditing(false); }} width={460} label={title}>
      <form className="space-y-4 p-6" ref={form} onSubmit={event => void save(event)}>
        <h2 className="m-0 text-xl font-semibold">{title}</h2>
        <Field label={t("publication.authorLink")} control={<TextInput aria-label={t("publication.authorLink")}
          value={draft.url} onChange={url => setDraft(value => ({ ...value, url }))} maxLength={2048} disabled={busy} />} />
        <Field label={t("publication.authorLinkName")} control={<TextInput aria-label={t("publication.authorLinkName")}
          value={draft.label} onChange={label => setDraft(value => ({ ...value, label }))} maxLength={AUTHOR_URL_LABEL_LIMIT} disabled={busy} />} />
        <p className="m-0 text-[12.5px] text-[var(--help)]">{t("publication.authorProfileHint")}</p>
        {failed && <Warn>{t("publication.authorProfileSaveFailed")}</Warn>}
        <button type="submit" hidden aria-hidden="true" />
        <div className="flex justify-end gap-2">
          <Btn disabled={busy} onClick={() => setEditing(false)}>{uiText("ui.common.cancel")}</Btn>
          <Btn primary busy={busy} disabled={!canSave} onClick={() => form.current?.requestSubmit()}>{t("publication.saveAuthorProfile")}</Btn>
        </div>
      </form>
    </Modal>
  </>;
}
