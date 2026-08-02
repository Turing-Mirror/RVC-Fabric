/**
 * 对外的仓库与社媒地址，一处定义。
 *
 * 「其他」页的列表和「关注一下」的邀请浮层用的是同一份 —— 抖音号换了、
 * B 站改了主页地址，只改这里。以前只有「其他」页有，浮层要用就得抄一份，
 * 抄完两边就开始各走各的。
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

export const REPO_LINKS: LinkEntry[] = [
  {
    title: "GitHub 源码",
    short: "GitHub",
    desc: "Turing-Mirror/RVC-Fabric",
    url: "https://github.com/Turing-Mirror/RVC-Fabric",
  },
  {
    title: "CNB 发布与制品",
    short: "CNB",
    desc: "Turing-Mirror/RVC-Fabric-Releases",
    url: "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases",
  },
];

export const SOCIAL_LINKS: LinkEntry[] = [
  {
    title: "哔哩哔哩 @图灵镜",
    short: "哔哩哔哩",
    url: "https://space.bilibili.com/3546871148579062",
  },
  {
    title: "抖音 @图灵镜",
    short: "抖音",
    desc: "抖音号 TuringMirror",
    url: "https://v.douyin.com/6NxXcrKK9cc",
  },
  {
    title: "小红书 @图灵镜",
    short: "小红书",
    desc: "小红书号 TuringMirror",
    url: "https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094",
  },
];

/** 「其他」页那张列表的顺序：先仓库后社媒。 */
export const ALL_LINKS: LinkEntry[] = [...REPO_LINKS, ...SOCIAL_LINKS];

/** 邀请关注时给的四个去处：三大社媒 + GitHub。CNB 是发制品的，不放在这里。 */
export const FOLLOW_LINKS: LinkEntry[] = [
  ...SOCIAL_LINKS,
  REPO_LINKS[0],
];
