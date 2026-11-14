import type { ComponentProps } from "react";
import { RangeBar as SharedRangeBar, Slider as SharedSlider } from "trm-ui";
import { useI18n } from "../i18n";

export { Field, SliderValue, Toggle } from "trm-ui";
export { Select, type SelectOption } from "./Select";
export function RangeBar(props: ComponentProps<typeof SharedRangeBar>) {
  const { t } = useI18n();
  return <SharedRangeBar defaultMarkLabel={t("s.4b829fbdac")} {...props} />;
}
export function Slider(props: ComponentProps<typeof SharedSlider>) {
  const { t } = useI18n();
  return <SharedSlider defaultMarkLabel={t("s.4b829fbdac")} {...props} />;
}
