import { t } from "../i18n/t";

/** DSP 新入口旁边的「?」文案。跟设置页 `tips()` 同一用法。 */
export function dspTips() {
  return {
    kind: t("s.dspTipKind"),
    clear: t("s.dspTipClear"),
    home: t("s.dspTipHome"),
    edit: t("s.dspTipEdit"),
    add: t("s.dspTipAdd"),
    stack: t("s.dspTipStack"),
    fx: {
      pitch: t("s.dspTipFxPitch"),
      formant: t("s.dspTipFxFormant"),
      whisper: t("s.dspTipFxWhisper"),
      ring: t("s.dspTipFxRing"),
      vibrato: t("s.dspTipFxVibrato"),
      chorus: t("s.dspTipFxChorus"),
      bitcrush: t("s.dspTipFxBitcrush"),
      drive: t("s.dspTipFxDrive"),
      radio: t("s.dspTipFxRadio"),
      echo: t("s.dspTipFxEcho"),
      reverb: t("s.dspTipFxReverb"),
    } as Record<string, string>,
  };
}
