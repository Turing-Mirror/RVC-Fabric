import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { lookup } from "./dict";

/** 代码里写死的每个文案 key，都必须在每种语言里查得到。 */
const SRC = join(__dirname, "..");
const LOCALES = join(__dirname, "../../i18n/locales");
const zh = JSON.parse(readFileSync(join(LOCALES, "zh-CN.json"), "utf8"));

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap(name => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

const PREFIXES = Object.keys(zh).map(key => key.replace(/\./g, "\\.")).join("|");
const KEY = new RegExp(`\\b(?:t|tStatic)\\(\\s*["']((?:${PREFIXES})\\.[\\w.-]+)["']`, "g");

const keys = [...new Set(sources(SRC).flatMap(file => [...readFileSync(file, "utf8").matchAll(KEY)].map(m => m[1])))];

describe("language packs", () => {
  it("finds the keys used in the code", () => {
    expect(keys.length).toBeGreaterThan(100);
  });

  for (const file of readdirSync(LOCALES).filter(name => name.endsWith(".json"))) {
    it(`resolves every key in ${file}`, () => {
      const pack = JSON.parse(readFileSync(join(LOCALES, file), "utf8"));
      expect(keys.filter(key => typeof lookup(pack, key) !== "string")).toEqual([]);
    });
  }
});
