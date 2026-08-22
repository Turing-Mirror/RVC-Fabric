import { describe, expect, it } from "vitest";
import { interpolate, lookup, packOf } from "./dict";
import zh from "../../i18n/locales/zh-CN.json";

/** 语言包的取值与插值 —— i18n 的地基，坏了整屏都是 s.xxx 字面量。 */
describe("lookup", () => {
  it("resolves dotted paths", () => {
    const d = { s: { abc: "x" }, nav: { home: "首页" } };
    expect(lookup(d as never, "s.abc")).toBe("x");
    expect(lookup(d as never, "nav.home")).toBe("首页");
  });

  it("returns undefined for missing keys", () => {
    expect(lookup({} as never, "nope")).toBeUndefined();
  });

  it("finds hash keys inside the shipped zh-CN pack", () => {
    const pack = packOf("zh-CN") as unknown as Record<string, unknown>;
    expect(pack).toBe(zh as never);
  });
});

describe("interpolate", () => {
  it("fills {name} placeholders", () => {
    expect(interpolate("第 {n} / {total} 页", { n: 2, total: 9 })).toBe(
      "第 2 / 9 页",
    );
  });

  it("still understands legacy ${name} placeholders", () => {
    expect(interpolate("a ${x} b", { x: 1 })).toBe("a 1 b");
  });

  it("drops missing variables to empty string", () => {
    expect(interpolate("[{gone}]", {})).toBe("[]");
  });

  it("leaves plain text untouched without vars", () => {
    expect(interpolate("没有占位符")).toBe("没有占位符");
  });
});
