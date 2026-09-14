/**
 * 附加模型的展示名适配层（C8/N05、C-06）。
 *
 * 下载广场用用途名（extras.items.<pack>.label），工具下拉框却只剩
 * 英文文件名——这里把两边贯通：文件名 → 所属下载包 → 本地化用途名
 * ＋必要的变体标识。文件不改名、value 仍是原始 basename，换语言或
 * 展示名不改变实际调用目标。
 *
 * 别名（DeEcho / De-Echo 等旧拼写）只在这一处归一化：小写、去连字符
 * 与下划线后查表。识别不了的手动导入模型原样返回文件名，不伪造用途。
 */
import { t } from "../i18n/t";

/** 归一化 basename：小写、去掉 - 和 _，旧拼写别名由此合并。 */
function norm(basename: string): string {
  return basename.toLowerCase().replace(/[-_]/g, "");
}

type Info = {
  /** extras.items.<pack> 里的用途名 */
  pack: string;
  /**
   * 变体标识：sepVariant.* 的语义键（normal/aggressive/…）或原样的
   * 型号串（"HP3"、"7"）。多文件同包时必须给出，保证选项不重名。
   */
  tag?: string;
  /** 完整展示名 i18n 键（sepModels.*），设置后不再拼 pack+tag。 */
  name?: string;
};

const KNOWN: Record<string, Info> = {
  // pymss-vocal 人声提取
  "3hpvocaluvr.pth": { pack: "pymss-vocal", tag: "HP3" },
  "4hpvocaluvr.pth": { pack: "pymss-vocal", tag: "HP4" },
  // pymss-deecho 去回声（三个变体拼写都有旧别名）
  "uvrdeechonormal.pth": { pack: "pymss-deecho", tag: "normal" },
  "uvrdeechoaggressive.pth": { pack: "pymss-deecho", tag: "aggressive" },
  "uvrdeechodereverb.pth": {
    pack: "pymss-deecho",
    name: "sepModels.deechoDereverb",
  },
  // pymss-denoise 降噪
  "uvrdenoise.pth": { pack: "pymss-denoise" },
  "uvrdenoiselite.pth": { pack: "pymss-denoise", tag: "lite" },
  // pymss-dereverb 去混响
  "uvrdereverbaufr33jarredou4bandv4msfullband.pth": {
    pack: "pymss-dereverb",
  },
  // pymss-inst 伴奏提取
  "1hpuvr.pth": { pack: "pymss-inst", tag: "1" },
  "2hpuvr.pth": { pack: "pymss-inst", tag: "2" },
  // pymss-karaoke 卡拉OK
  "5hpkaraokeuvr.pth": { pack: "pymss-karaoke", tag: "5" },
  "6hpkaraokeuvr.pth": { pack: "pymss-karaoke", tag: "6" },
  // pymss-bve 背景和声
  "uvrbve4bsn441001.pth": { pack: "pymss-bve" },
  // pymss-harmonic 和声/噪声
  "harmonicnoiseseparationyxlllc.pth": { pack: "pymss-harmonic" },
  // pymss-hp2 HP2 系列（编号即文件名身份，不意译品质）
  "7hp2uvr.pth": { pack: "pymss-hp2", tag: "7" },
  "8hp2uvr.pth": { pack: "pymss-hp2", tag: "8" },
  "9hp2uvr.pth": { pack: "pymss-hp2", tag: "9" },
  // pymss-mgm MGM 融合
  "mgmmainv4.pth": { pack: "pymss-mgm", tag: "main" },
  "mgmhighendv4.pth": { pack: "pymss-mgm", tag: "highend" },
  "mgmlowendav4.pth": { pack: "pymss-mgm", tag: "lowendA" },
  "mgmlowendbv4.pth": { pack: "pymss-mgm", tag: "lowendB" },
  // pymss-sp SP 频谱系列
  "10spuvr2b320001.pth": { pack: "pymss-sp", tag: "10" },
  "11spuvr2b320002.pth": { pack: "pymss-sp", tag: "11" },
  "12spuvr3b44100.pth": { pack: "pymss-sp", tag: "12" },
  "13spuvr4b441001.pth": { pack: "pymss-sp", tag: "13" },
  "14spuvr4b441002.pth": { pack: "pymss-sp", tag: "14" },
  "15spuvrmid441001.pth": { pack: "pymss-sp", tag: "15" },
  "16spuvrmid441002.pth": { pack: "pymss-sp", tag: "16" },
  // pymss-wind 管弦伴奏
  "17hpwindinstuvr.pth": { pack: "pymss-wind" },
};

/** 变体标识：sepVariant.* 有翻译的用语义键，否则按型号串原样显示。 */
function tagText(tag: string): string {
  const v = t(`sepVariant.${tag}`);
  return v.startsWith("sepVariant.") ? tag : v;
}

/**
 * 展示名：完整名 > 包用途名＋变体 > 原始文件名。
 * 包名缺译（键原样返回）或未知模型都回退到 basename —— 不出现翻译键，
 * 也不给手动导入的模型编造用途。
 */
export function extraModelLabel(basename: string): string {
  const info = KNOWN[norm(basename)];
  if (!info) return basename;
  if (info.name) {
    const v = t(info.name);
    if (!v.startsWith("sepModels.")) return v;
  }
  const label = t(`extras.items.${info.pack}.label`);
  if (label.startsWith("extras.items.")) return basename;
  return info.tag ? `${label}（${tagText(info.tag)}）` : label;
}
