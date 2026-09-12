import { expect, it } from "vitest";
import { coverSize } from "./imageSize";
it("limits both landscape and portrait slivers", () => {
  expect(coverSize(6000, 8)).toEqual([2048, 3]);
  expect(coverSize(8, 6000)).toEqual([3, 2048]);
  expect(coverSize(400, 300)).toEqual([683, 512]);
});
