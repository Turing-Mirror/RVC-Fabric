import { describe, expect, it } from "vitest";
import { voiceAuthorList, voiceVersionLabel } from "./voiceDisplay";

describe("voiceVersionLabel", () => {
  it("formats catalog YYMMDD as vYY.MM.DD", () => {
    expect(voiceVersionLabel("260731")).toBe("v26.07.31");
  });

  it("accepts YYYYMMDD and ISO prefixes", () => {
    expect(voiceVersionLabel("20260731")).toBe("v26.07.31");
    expect(voiceVersionLabel("2026-07-31T12:00:00Z")).toBe("v26.07.31");
    expect(voiceVersionLabel("2026/7/3")).toBe("v26.07.03");
  });

  it("returns empty for garbage instead of a broken badge", () => {
    expect(voiceVersionLabel(undefined)).toBe("");
    expect(voiceVersionLabel("")).toBe("");
    expect(voiceVersionLabel("unknown")).toBe("");
    expect(voiceVersionLabel("261331")).toBe(""); // 月/日越界
  });
});

describe("voiceAuthorList", () => {
  it("expands the authors array and merges the single-author URL", () => {
    const out = voiceAuthorList({
      authors: [{ name: "A" }, { name: "B", url: "https://x/b" }, "C"],
      author: "A",
      author_url: "https://x/a",
    });
    expect(out).toEqual([
      { name: "A", url: "https://x/a" },
      { name: "B", url: "https://x/b" },
      { name: "C", url: undefined },
    ]);
  });

  it("falls back to a single author field", () => {
    expect(voiceAuthorList({ author: "某人", author_url: "https://x/s" })).toEqual([
      { name: "某人", url: "https://x/s" },
    ]);
    expect(voiceAuthorList({})).toEqual([]);
  });

  it("drops entries without names", () => {
    const out = voiceAuthorList({ authors: [{ url: "https://x/x" }, { name: "" }] });
    expect(out).toEqual([]);
  });
});
