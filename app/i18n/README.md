# Shell i18n locale packs

Shipped with the app (`shell-i18n/locales` in the installer). Shared by React UI and Rust host.

## Locales

| Code | File |
|------|------|
| zh-CN | `locales/zh-CN.json` (default) |
| zh-TW | `locales/zh-TW.json` |
| en-US | `locales/en-US.json` |
| ja-JP | `locales/ja-JP.json` |
| ko-KR | `locales/ko-KR.json` |
| es-ES | `locales/es-ES.json` |
| fr-FR | `locales/fr-FR.json` |
| ru-RU | `locales/ru-RU.json` |

## Release update flow

1. Translators deliver `docs/i18n/sheets/<locale>.md`
2. `python scripts/dev/prepare_i18n_release.py` (audit + merge all)
3. Frontend `LOCALES` / Rust `i18n::supported` already list the eight codes
4. `npm run tauri:build` packs `../i18n/locales` → `shell-i18n/locales`

Do **not** hand-edit locale JSON for routine translation updates — merge from MD.
