import type { ComponentProps } from "react";
import { Collapse as SharedCollapse } from "trm-ui";
export { LeavingContext, useLeaving, Leave } from "trm-ui";

export function Collapse(props: ComponentProps<typeof SharedCollapse>) {
  return <SharedCollapse ms={280} {...props} />;
}
