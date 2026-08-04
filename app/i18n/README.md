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

## Add a language

1. Copy `locales/zh-CN.json` → `locales/<code>.json` and translate values  
2. Add code to `app/src/i18n/types.ts` (`LocaleCode` + `LOCALES`)  
3. Add to Rust `i18n::supported`  
4. Ship file via `tauri.conf.json` resources (`../i18n/locales` → `shell-i18n/locales`)

## Migrate more UI strings

1. Add keys to both locale JSON files  
2. Replace hard-coded Chinese with `t("…")` / `useI18n()`  
3. Re-run `python scripts/dev/build_i18n_catalog.py` — migrated lines leave the draft  

Full inventory: `docs/i18n/`.
