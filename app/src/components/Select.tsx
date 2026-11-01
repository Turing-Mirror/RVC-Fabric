import type { ComponentProps } from "react";
import { PopupSelect } from "trm-ui";
import { useI18n } from "../i18n";

export { TOOL_BOX, type SelectOption } from "trm-ui";
export function Select(props: ComponentProps<typeof PopupSelect>) {
  const { t } = useI18n();
  return <PopupSelect placeholder={t("s.e6b7c3d266")} missingSuffix={t("s.1cab0503c2")} {...props} />;
}
