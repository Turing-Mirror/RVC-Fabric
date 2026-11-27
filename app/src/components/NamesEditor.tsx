import { useState } from "react";
import { Btn, Select, TextInput } from "trm-ui";
import { useI18n } from "../i18n";
import { categoryTerm, NAME_LOCALES, type NameEntry } from "../lib/communityPublication";
export { namesFromMetadata, namesToMetadata, type NameEntry } from "../lib/communityPublication";

const MAX_PER_LOCALE = 9;


const languageName = (id: string, display: string) => new Intl.DisplayNames([display], { type: "language" }).of(id) || id;

/**
 * A list of names. Different translations of one name coexist (阿罗娜, 阿洛娜, 彩奈).
 * With languages, the first name of each language is the one shown to readers of that language.
 */
export function NamesEditor({ label, note, entries, withLanguage, disabled, onChange }: {
  label: string;
  note?: string;
  entries: NameEntry[];
  withLanguage?: boolean;
  disabled?: boolean;
  onChange: (entries: NameEntry[]) => void;
}) {
  const { t, locale } = useI18n();
  const [lang, setLang] = useState<string>(locale);
  const [text, setText] = useState("");
  const name = text.trim();
  const sameLanguage = entries.filter((entry) => !withLanguage || entry.locale === lang);
  const duplicate = sameLanguage.some((entry) => categoryTerm(entry.name) === categoryTerm(name));
  const full = withLanguage && sameLanguage.length >= MAX_PER_LOCALE;
  const add = () => {
    if (!name || duplicate || full) return;
    onChange([...entries, withLanguage ? { locale: lang, name } : { name }]);
    setText("");
  };
  const ordered = withLanguage
    ? NAME_LOCALES.flatMap((id) => entries.filter((entry) => entry.locale === id))
    : entries;
  return (
    <div className="min-w-0 space-y-2">
      <div className="text-[13px]">{label}</div>
      {note ? <p className="m-0 text-[12.5px] text-[var(--help)]">{note}</p> : null}
      {ordered.length ? (
        <ul className="m-0 list-none space-y-1 p-0">
          {ordered.map((entry) => (
            <li key={(entry.locale ?? "") + entry.name} className="flex min-w-0 items-center gap-2 text-[13px]">
              {withLanguage && entry.locale ? <span className="shrink-0 text-[var(--help)]">{languageName(entry.locale, locale)}</span> : null}
              <span className="min-w-0 break-words">{entry.name}</span>
              <Btn text disabled={disabled} onClick={() => onChange(entries.filter((item) => item !== entry))}>{t("publication.removeName")}</Btn>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        {withLanguage ? (
          <Select value={lang} disabled={disabled} ariaLabel={t("publication.language")} onChange={setLang}
            options={NAME_LOCALES.map((id) => ({ id, label: languageName(id, locale) }))} />
        ) : null}
        <TextInput value={text} maxLength={100} disabled={disabled} aria-label={label}
          onChange={setText} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); add(); } }} />
        <Btn disabled={disabled || !name || duplicate || full} onClick={add}>{t("publication.addName")}</Btn>
      </div>
    </div>
  );
}
