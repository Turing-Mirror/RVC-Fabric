import type { ComponentProps } from "react";
import { Block as SharedBlock, Btn as SharedBtn, ListItem as SharedListItem } from "trm-ui";

export { PagePad, PageHead, Group, HelpMark, Warn, AccordionGroup, type AccordionItem } from "trm-ui";

// Preserve the product's spacing, button wrapping, and collapse timing at this boundary.
export function Block(props: ComponentProps<typeof SharedBlock>) {
  return <SharedBlock actionClassName="ml-auto" {...props} />;
}
export function Btn(props: ComponentProps<typeof SharedBtn>) {
  // 选中且禁用的按钮是状态标识（例如"使用中"），不变淡。
  return <SharedBtn noWrap={false} dimDisabled={!props.on} {...props} />;
}
export function ListItem(props: ComponentProps<typeof SharedListItem>) {
  return <SharedListItem collapseMs={280} {...props} />;
}
