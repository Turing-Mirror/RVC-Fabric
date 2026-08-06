import { t } from "../i18n/t";
/**
 * 对外的仓库与社媒地址，一处定义。
 *
 * 标题/短名必须在调用时 t()：模块顶层 t() 会在 import 时锁死默认中文，
 * 切语言后「其他 → 仓库与社媒」和关注邀请仍会显示中文。
 */
export type LinkEntry = {
  /** 列表里显示的标题。 */
  title: string;
  /** 浮层按钮上的短名字，列表里放不下那么长。 */
  short: string;
  /** 账号自己的标识，除此之外不写别的。 */
  desc?: string;
  url: string;
};

export function repoLinks(): LinkEntry[] {
  return [
    {
      title: t("s.8d93847089"),
      short: "GitHub",
      desc: "Turing-Mirror/RVC-Fabric",
      url: "https://github.com/Turing-Mirror/RVC-Fabric",
    },
    {
      title: t("s.71031cc3ad"),
      short: "CNB",
      desc: "Turing-Mirror/RVC-Fabric-Releases",
      url: "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases",
    },
  ];
}

export function socialLinks(): LinkEntry[] {
  return [
    {
      title: t("s.a11c1a6602"),
      short: t("s.da1fd957dc"),
      url: "https://space.bilibili.com/3546871148579062",
    },
    {
      title: t("s.a3480a2554"),
      short: t("s.21a8e41cf6"),
      desc: t("s.881ebae122"),
      url: "https://v.douyin.com/6NxXcrKK9cc",
    },
    {
      title: t("s.efbfd16623"),
      short: t("s.e2866d0815"),
      desc: t("s.84ccf9394c"),
      url: "https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094",
    },
  ];
}

/** 「其他」页那张列表的顺序：先仓库后社媒。 */
export function allLinks(): LinkEntry[] {
  return [...repoLinks(), ...socialLinks()];
}

/** 邀请关注时给的四个去处：三大社媒 + GitHub。CNB 是发制品的，不放在这里。 */
export function followLinks(): LinkEntry[] {
  return [...socialLinks(), repoLinks()[0]];
}
