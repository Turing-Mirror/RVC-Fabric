import { expect, it } from "vitest";
import { namesFromMetadata, namesToMetadata } from "./communityPublication";
import { voiceOtherNames, voiceSearchText } from "./voiceDisplay";

it("keeps every translation: first name per language is primary, the rest are other names", () => {
  const entries = [
    { locale: "zh-CN", name: "阿罗娜" }, { locale: "zh-TW", name: "彩奈" },
    { locale: "zh-CN", name: "阿洛娜" }, { locale: "en-US", name: "Arona" },
  ];
  const meta = namesToMetadata(entries);
  expect(meta).toEqual({
    nameI18n: { "zh-CN": "阿罗娜", "zh-TW": "彩奈", "en-US": "Arona" },
    nameAliases: { "zh-CN": ["阿洛娜"] },
  });
  expect(namesFromMetadata(meta.nameI18n, meta.nameAliases).map((e) => e.name)).toEqual(["阿罗娜", "阿洛娜", "彩奈", "Arona"]);
  expect(namesToMetadata([])).toEqual({ nameI18n: undefined, nameAliases: undefined });
});

it("search and the detail line include other translations", () => {
  const voice = { id: "arona", name: "Arona", name_i18n: { "zh-CN": "阿罗娜", "zh-TW": "彩奈" }, name_aliases: { "zh-CN": ["阿洛娜"] }, series_aliases: ["碧蓝档案"] };
  const text = voiceSearchText(voice);
  for (const name of ["阿洛娜", "彩奈"]) expect(text).toContain(name);
  expect(voiceOtherNames(voice, "阿罗娜")).toEqual(["Arona", "阿洛娜", "彩奈"]);
});
