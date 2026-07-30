import { Block, Btn, Group, PageHead, PagePad } from "../components/ui";

/** Plaza shell — feed/changelog wire-up is stage 5. Ads are NOT dismissible here. */
export function PlazaPage() {
  return (
    <PagePad>
      <PageHead
        title="广场"
        sub="图灵镜 · 更新与投放"
        actions={<Btn>刷新</Btn>}
      />

      <Block
        title="更新日志"
        note="1.2.4"
        action={<Btn>查看全部</Btn>}
      >
        <Group>
          <div className="py-3">
            <div className="text-[15px] font-semibold">
              1.2.4
              <span className="font-normal text-[var(--meta)] text-[12.5px] ml-2.5">
                2026-07-30
              </span>
            </div>
            <ul className="m-2.5 ml-0 p-0 list-none">
              {[
                "修复「其他」页生成诊断包成功后没有反馈的问题",
                "设置页的详细帮助问号统一放到标签左侧",
                "安装包改为通用包，运行时由启动器自动鉴别显卡后推荐",
              ].map((t) => (
                <li
                  key={t}
                  className="text-[13.5px] text-[var(--ink-muted)] leading-relaxed pl-[18px] relative before:content-['·'] before:absolute before:left-1.5 before:text-[var(--meta)]"
                >
                  {t}
                </li>
              ))}
            </ul>
          </div>
        </Group>
      </Block>

      <Block title="投放" note="3">
        <Group>
          <Feed
            title="MyGO!!!!! 五音色已上架"
            tags={[{ label: "图灵镜推荐" }]}
            body="千早爱音、高松灯、长崎爽世、椎名立希、要乐奈，都带检索库和推荐参数，可在「模型 → 社区音色」下载。"
          />
          <Feed
            title="想让声音更像这个角色"
            tags={[
              { label: "图灵镜推荐" },
              { label: "商业推广", ad: true },
            ]}
            body="把样本和当前配置打包发过来，我们做一次针对性调参。"
          />
          <Feed
            title="某声卡品牌直播套装"
            tags={[{ label: "商业推广", ad: true }]}
            body="USB 直播声卡，即插即用，支持独占低延迟。"
          />
        </Group>
      </Block>
    </PagePad>
  );
}

function Feed({
  title,
  tags,
  body,
}: {
  title: string;
  tags: { label: string; ad?: boolean }[];
  body: string;
}) {
  return (
    <div className="flex gap-[18px] items-start py-4 -mx-3.5 px-3.5 rounded-[var(--rs)] cursor-pointer transition-colors hover:bg-[color-mix(in_srgb,var(--ink)_4%,transparent)]">
      <div className="w-[104px] h-16 rounded-[var(--rs)] flex-none grayscale bg-[color-mix(in_srgb,var(--ink)_7%,transparent)] max-[720px]:w-[76px] max-[720px]:h-[50px]" />
      <div>
        <h4 className="m-0 mb-1.5 text-[14.5px] font-semibold flex items-center gap-2 flex-wrap">
          {title}
          {tags.map((t) => (
            <span
              key={t.label}
              className={[
                "text-[11.5px] px-2 py-0.5 rounded-[5px] whitespace-nowrap shadow-[inset_0_0_0_1px_var(--line)]",
                t.ad
                  ? "text-[var(--notify)] shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--notify)_48%,transparent)]"
                  : "text-[var(--meta)]",
              ].join(" ")}
            >
              {t.label}
            </span>
          ))}
        </h4>
        <p className="m-0 text-[12.5px] text-[var(--help)] leading-relaxed">{body}</p>
      </div>
    </div>
  );
}
