import { type ComponentProps } from "react";
import { ModalLayer, usePageActive } from "trm-ui";

export function Modal(props: ComponentProps<typeof ModalLayer>) {
  const active = usePageActive();
  return active ? <ModalLayer {...props} /> : null;
}
