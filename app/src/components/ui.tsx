import type { ComponentProps } from "react";
import { Block as SharedBlock, Btn as SharedBtn, ListItem as SharedListItem } from "trm-ui";

export { PagePad, PageHead, Group, HelpMark, Warn, AccordionGroup, type AccordionItem } from "trm-ui";

// Preserve the product's spacing, button wrapping, and collapse timing at this boundary.
export function Block(props: ComponentProps<typeof SharedBlock>) {
  return <SharedBlock actionClassName="ml-auto" {...props} />;
}
export function Btn(props: ComponentProps<typeof SharedBtn>) {
  return <SharedBtn noWrap={false} {...props} />;
}
export function ListItem(props: ComponentProps<typeof SharedListItem>) {
  return <SharedListItem collapseMs={280} {...props} />;
}
