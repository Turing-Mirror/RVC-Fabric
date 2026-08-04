# Shell i18n locale packs

Shared by **React UI** and **Rust host** (tray, `message_code` status).

| Path | Role |
|------|------|
| `locales/zh-CN.json` | Default Chinese (source of truth for product copy) |
| `locales/en-US.json` | English |
| Install layout | `shell-i18n/locales/*.json` (Tauri resource; not Gradio `i18n/`) |

## Keys

- Semantic: `nav.home`, `dock.start`, `settings.tabs.device`, `tray.show`, `msg.engine.starting`, …
- Glossary: `glossary.terms[]` with stable `id`
- Engine status codes: `msg.<code>` — Python writes `message_code`, shell localizes

## Translation workflow (MD only for translators)

1. Export sheet: `python scripts/dev/export_i18n_sheet.py` → `docs/i18n/sheets/source.md`  
2. Give translator: `docs/i18n/给翻译AI.md` + `source.md`  
3. Translator returns `docs/i18n/sheets/<locale>.md` (table: key | zh-CN | translation)  
4. Merge: `python scripts/dev/merge_i18n_sheet.py --locale en-US --md docs/i18n/sheets/en-US.md`  
5. New locale: also register in `app/src/i18n/types.ts` + Rust `i18n::supported`

Translators must **not** hand-edit JSON.

## Add a language (engineering)

1. Merge MD → `locales/<code>.json` (step above)  
2. `app/src/i18n/types.ts` (`LocaleCode` + `LOCALES`)  
3. Rust `i18n::supported`  
4. Resources already pack whole `../i18n/locales` → `shell-i18n/locales`  
