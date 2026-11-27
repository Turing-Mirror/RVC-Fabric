import { useEffect, useState } from "react";
import { useI18n as useUiI18n, Btn, Collapse, Field, Group, SearchBox, Select, TextInput, usePaneOn } from "trm-ui";
import { useI18n } from "../i18n";
import { NamesEditor } from "./NamesEditor";
import { categoryTerm, publication, type Category, type CategoryChoice, type CategorySelection } from "../lib/communityPublication";

const locales = ["en-US", "zh-CN", "zh-TW", "ja-JP", "ko-KR", "es-ES", "fr-FR", "ru-RU"];
const cache = new Map<string, { time: number; request: Promise<Category[]> }>();

function browse(parent = "") {
  const cached = cache.get(parent);
  if (cached && Date.now() - cached.time < 60_000) return cached.request;
  const request = publication<{ items: Category[] }>({ action: "categories", parent: parent || undefined })
    .then(({ items }) => items ?? [])
    .catch((error: unknown) => { cache.delete(parent); throw error; });
  cache.set(parent, { time: Date.now(), request });
  return request;
}

function useCategoryList(parent?: string) {
  const active = usePaneOn();
  const [result, setResult] = useState<{ parent: string; items: Category[]; failed?: boolean }>();
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!active || parent === undefined) return;
    let current = true;
    void browse(parent).then((items) => { if (current) setResult({ parent, items }); })
      .catch(() => { if (current) setResult({ parent, items: [], failed: true }); });
    return () => { current = false; };
  }, [active, parent, retry]);
  return {
    items: result?.parent === parent ? result?.items : undefined,
    failed: result?.parent === parent && result?.failed,
    reload: () => setRetry((count) => count + 1),
  };
}

const terms = (category: Category) => [category.name, ...Object.values(category.names), ...category.aliases].map(categoryTerm);

function asChoice(items: Category[] | undefined, label: string): CategoryChoice | undefined {
  const key = categoryTerm(label);
  const matches = items?.filter((row) => terms(row).includes(key));
  return matches?.length === 1 ? { id: matches[0].id } : undefined;
}

function CategoryField({ label, choice, initial, list, onChange, disabled }: {
  label: string;
  choice?: CategoryChoice;
  initial?: string;
  list: ReturnType<typeof useCategoryList>;
  onChange: (choice?: CategoryChoice) => void;
  disabled?: boolean;
}) {
  const { t, locale } = useI18n();
  const { t: uiText } = useUiI18n();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [translation, setTranslation] = useState("");
  function displayName(item: Category) {
    const name = item.names[locale] || item.name;
    const collision = list.items?.some((other) => other.id !== item.id && categoryTerm(other.names[locale] || other.name) === categoryTerm(name));
    return collision && name !== item.name ? name + " (" + item.name + ")" : name;
  }
  const selected = choice && "id" in choice ? list.items?.find((item) => item.id === choice.id) : undefined;
  const proposed = choice && "name" in choice ? choice : undefined;
  const value = selected ? displayName(selected) : proposed?.name ?? initial ?? "";
  const key = categoryTerm(query);
  const existing = list.items?.filter((item) => terms(item).some((term) => term.includes(key))) ?? [];
  const exact = Boolean(key && list.items?.some((item) => terms(item).includes(key)));
  const offer = Boolean(list.items && key && query.trim().length <= 100 && !exact);

  function choose(value?: CategoryChoice) {
    onChange(value);
    setOpen(false);
    setQuery("");
    setTranslation("");
  }

  const allowTranslations = Boolean(proposed);
  return (
    <div className="min-w-0 space-y-2 sm:row-span-2 sm:grid sm:grid-rows-subgrid sm:space-y-0" onBlur={(event) => {
      if (!event.relatedTarget || !event.currentTarget.contains(event.relatedTarget)) setOpen(false);
    }}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-[13px]">{label}</div>
        {choice && <Btn text disabled={disabled} onClick={() => choose()}>{uiText("ui.common.clear")}</Btn>}
      </div>
      <div className="min-w-0 space-y-2">
        {disabled ? <TextInput aria-label={label} value={value} onChange={() => undefined} disabled /> :
          <div onFocus={() => { if (!open) setQuery(choice ? "" : value); setOpen(true); }}>
            <SearchBox full value={open ? query : value}
              ariaLabel={label} onChange={(next) => { setQuery(next); setOpen(true); }} />
          </div>}
        <Collapse open={open && !disabled}>
          {list.failed ? <div className="flex flex-wrap items-center gap-2 text-[12.5px] text-[var(--help)]">
            {t("publication.requestFailed")} <Btn text onClick={list.reload}>{t("s.38108eaa1d")}</Btn>
          </div> : list.items ? <Group>
            <div className="max-h-48 space-y-1 overflow-y-auto">
              {existing.slice(0, key ? 20 : 12).map((item) => <div key={item.id}>
                <Btn text onClick={() => choose({ id: item.id })}>{displayName(item)}</Btn>
              </div>)}
              {offer && <Btn text onClick={() => choose({ name: query.trim(), locale })}>
                {t("publication.proposeCategory", { v0: query.trim() })}
              </Btn>}
              {!existing.length && !offer && <p className="m-0 text-[12.5px] text-[var(--help)]">{t("publication.searchCategory")}</p>}
            </div>
          </Group> : <p className="m-0 text-[12.5px] text-[var(--help)]" role="status">{t("s.f950213ab7")}</p>}
        </Collapse>
        {choice && <NamesEditor label={t("publication.otherNames")} disabled={disabled}
          entries={(choice.aliases ?? []).map((name) => ({ name }))}
          onChange={(entries) => onChange({ ...choice, aliases: entries.length ? entries.map((entry) => entry.name) : undefined })} />}
        {allowTranslations && proposed && <div className="space-y-2">
          <p className="m-0 text-[12.5px] text-[var(--help)]">{t("publication.categoryUnderReview")}</p>
          <div className="grid gap-2 sm:grid-cols-2">
            <Field label={t("publication.categoryTranslation")} control={<Select full
              value={translation} ariaLabel={t("publication.categoryTranslation")} disabled={disabled}
              options={[{ id: "", label: t("publication.language") }, ...locales.filter((id) => id !== proposed.locale).map((id) =>
                ({ id, label: new Intl.DisplayNames([id], { type: "language" }).of(id) || id }))]}
              onChange={setTranslation} />} />
            {translation && <TextInput value={proposed.translations?.[translation] ?? ""} disabled={disabled} maxLength={100}
              aria-label={t("publication.categoryTranslation")} onChange={(label) => {
                const translations = { ...proposed.translations };
                if (label.trim()) translations[translation] = label;
                else delete translations[translation];
                onChange({ ...proposed, translations });
              }} />}
          </div>
        </div>}
      </div>
    </div>
  );
}

export function CommunityCategories({ value, series, group, disabled, onChange }: {
  value?: CategorySelection | null;
  series: string;
  group: string;
  disabled?: boolean;
  onChange: (value: CategorySelection | null) => void;
}) {
  const { t } = useI18n();
  const roots = useCategoryList("");
  const selectedSeries = value === undefined ? asChoice(roots.items, series) : value?.series;
  const parent = selectedSeries && ("id" in selectedSeries ? selectedSeries.id : undefined);
  const children = useCategoryList(parent);
  const selectedDepartment = value ? value.department : asChoice(children.items, group);
  const list = parent ? children : { items: [] as Category[], failed: false, reload: () => undefined };
  return <div className="grid gap-4 sm:grid-cols-2 sm:gap-y-2">
    <CategoryField label={t("publication.series")} choice={selectedSeries} initial={series} list={roots} disabled={disabled}
      onChange={(series) => onChange(series ? { series } : null)} />
    {selectedSeries && <CategoryField key={parent ?? "proposed"} label={t("publication.department")}
      choice={selectedDepartment} initial={group} list={list} disabled={disabled}
      onChange={(department) => onChange({ series: selectedSeries, department })} />}
  </div>;
}
