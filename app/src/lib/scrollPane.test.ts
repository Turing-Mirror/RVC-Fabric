import { expect, it } from "vitest";
import { offsetTopInPane } from "./scrollPane";

it("sums offsetTop up to the pane and ignores transforms", () => {
  const pane = { offsetTop: 0 } as HTMLElement;
  const mid = { offsetTop: 40, offsetParent: pane } as unknown as HTMLElement;
  const el = { offsetTop: 120, offsetParent: mid } as unknown as HTMLElement;
  expect(offsetTopInPane(el, pane)).toBe(160);
});
