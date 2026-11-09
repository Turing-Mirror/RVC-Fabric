import type { ComponentProps } from "react";
import { Pager as SharedPager } from "trm-ui";

export { pageList } from "trm-ui";

export function Pager({ className = "mt-6", ...props }: ComponentProps<typeof SharedPager>) {
  return <SharedPager className={className} {...props} />;
}
