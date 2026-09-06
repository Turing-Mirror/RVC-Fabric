import { expect, it } from "vitest";
import { isBrowserKey } from "./browserKeys";
const key = (key: string, ctrlKey = false, shiftKey = false) => ({ key, ctrlKey, shiftKey, altKey: false, metaKey: false });
it("blocks browser actions while preserving editing and app shortcuts", () => {
  for (const k of ["F5", "F7", "F9", "F12"]) expect(isBrowserKey(key(k))).toBe(true);
  expect(isBrowserKey(key("r", true))).toBe(true);
  for (const k of ["c", "v", "x", "a", "z", "F9"]) expect(isBrowserKey(key(k, true))).toBe(false);
});
