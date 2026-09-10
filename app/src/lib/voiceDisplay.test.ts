import { afterEach, describe, expect, it } from "vitest";
import { setTLocale } from "../i18n/t";
import {
  displayVoiceAuthor,
  displayVoiceFieldForGroup,
  displayVoiceTag,
  voiceAuthorList,
  voiceVersionLabel,
} from "./voiceDisplay";

afterEach(() => setTLocale("zh-CN"));

describe("voiceVersionLabel", () => {
  it("formats catalog YYMMDD as vYY.MM.DD", () => {
    expect(voiceVersionLabel("260731")).toBe("v26.07.31");
  });

  it("accepts YYYYMMDD and ISO prefixes", () => {
    expect(voiceVersionLabel("20260731")).toBe("v26.07.31");
    expect(voiceVersionLabel("2026-07-31T12:00:00Z")).toBe("v26.07.31");
    expect(voiceVersionLabel("2026/7/3")).toBe("v26.07.03");
  });

  it("accepts a numeric YYMMDD from unquoted YAML", () => {
    expect(voiceVersionLabel(260731)).toBe("v26.07.31");
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

  it("drops placeholder author names so the card does not say 未知", () => {
    expect(voiceAuthorList({ author: "未知" })).toEqual([]);
    expect(voiceAuthorList({ author: "—" })).toEqual([]);
    expect(voiceAuthorList({ authors: [{ name: "unknown" }] })).toEqual([]);
  });
});

describe("displayVoiceAuthor", () => {
  it("falls back to the authors array when the single field is empty", () => {
    expect(
      displayVoiceAuthor({
        authors: [{ name: "A" }, { name: "B", url: "https://x/b" }],
      }),
    ).toBe("A和B");
  });
});

describe("displayVoiceTag", () => {
  it("localizes a generic tag from an older sidecar", () => {
    setTLocale("en-US");
    expect(displayVoiceTag({ tag: "音色" }, "en-US")).toBe("Voice");
    expect(displayVoiceTag({ tag: "自制", source: "trained" }, "en-US")).toBe(
      "Custom",
    );
  });
});

describe("displayVoiceFieldForGroup", () => {
  it("uses a localized value from any row in a mixed-source bucket", () => {
    expect(
      displayVoiceFieldForGroup(
        [
          { series: "蔚蓝档案" },
          {
            series: "蔚蓝档案",
            series_i18n: { "en-US": "Blue Archive" },
          },
        ],
        "series",
        "en-US",
      ),
    ).toBe("Blue Archive");
  });

  it("uses a localized child-group value from any row in the bucket", () => {
    expect(
      displayVoiceFieldForGroup(
        [
          { group: "游戏开发部" },
          {
            group: "游戏开发部",
            group_i18n: { "en-US": "Game Development Department" },
          },
        ],
        "group",
        "en-US",
      ),
    ).toBe("Game Development Department");
  });
});
