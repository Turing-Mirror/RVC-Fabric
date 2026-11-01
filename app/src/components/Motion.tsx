import type { ComponentProps } from "react";
import { Swap as SharedSwap, stagger as sharedStagger } from "trm-ui";

export { FlowList, Roll, Curtain, FLOW_MS, FADE_OUT_MS as SWAP_OUT_MS } from "trm-ui";
export function Swap(props: ComponentProps<typeof SharedSwap>) {
  return <SharedSwap dir={0} variant="fade" {...props} />;
}
export function stagger(i: number) {
  return sharedStagger(i, { step: 24, max: 12 });
}
