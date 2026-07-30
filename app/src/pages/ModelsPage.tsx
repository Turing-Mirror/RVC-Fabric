import { Block, Btn, Group, ListItem, PageHead, PagePad } from "../components/ui";

const DEMO = [
  { id: "anon", name: "Anon", tag: "少女音", author: "望月星逸", index: true, cur: true },
  { id: "rana", name: "Rana", tag: "少女音", author: "望月星逸", index: true, cur: false },
  { id: "soyo", name: "Soyo", tag: "少女音", author: "望月星逸", index: true, cur: false },
  { id: "kiki", name: "Kikiv2", tag: "少女音", author: "RVC", index: false, cur: false },
  { id: "teio", name: "TokaiTeio", tag: "少女音", author: "RVC", index: false, cur: false },
];

/** Models page shell — grid, index panel, profiles (demo data until catalog binds). */
export function ModelsPage() {
  return (
    <PagePad>
      <PageHead
        title="音色目录"
        sub="共 3 个 · 使用中：Anon"
        actions={
          <>
            <Btn primary>社区音色</Btn>
            <Btn>导入音色…</Btn>
            <Btn>刷新</Btn>
            <Btn>打开目录</Btn>
          </>
        }
      />

      <Block>
        <div className="flex items-center gap-3 flex-wrap mb-[18px]">
          <span className="inline-flex justify-between gap-3 items-center min-w-[230px] px-[13px] py-[7px] rounded-[var(--rs)] text-[13px] text-[var(--meta)] shadow-[inset_0_0_0_1px_var(--line)]">
            搜索音色 / 标签…
          </span>
          <span className="ml-auto flex gap-1.5">
            <Btn on>默认</Btn>
            <Btn>名称</Btn>
            <Btn>检索库</Btn>
          </span>
        </div>

        <div className="grid grid-cols-5 gap-x-4 gap-y-[22px] max-[1180px]:grid-cols-4 max-[1020px]:grid-cols-3 max-[720px]:grid-cols-2">
          {DEMO.map((v) => (
            <div key={v.id}>
              <div className="aspect-[4/3] rounded-[var(--r)] grid place-items-center relative bg-[color-mix(in_srgb,var(--ink)_7%,transparent)] text-[color-mix(in_srgb,var(--ink)_32%,transparent)] text-2xl grayscale hover:grayscale-[0.3] transition-[filter,transform] duration-300 ease-[var(--spring)] hover:-translate-y-1">
                {v.name.slice(0, 4)}
                {v.cur ? (
                  <span className="absolute top-2.5 right-2.5 text-[11px] text-[var(--accent)]">
                    使用中
                  </span>
                ) : null}
                {v.index ? (
                  <span className="absolute right-2.5 bottom-2 text-[11px] text-[var(--meta)]">
                    ✓ 检索库
                  </span>
                ) : null}
              </div>
              <div className="text-[11.5px] text-[var(--meta)] mt-2.5">{v.tag}</div>
              <div className="text-[14.5px] font-semibold mt-0.5">{v.name}</div>
              <div className="text-xs text-[var(--meta)] mt-0.5">作者 · {v.author}</div>
              <div className="mt-2.5">
                {v.cur ? (
                  <Btn on uw disabled>
                    使用中
                  </Btn>
                ) : (
                  <Btn uw>使用</Btn>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="flex items-center justify-center gap-3 mt-[26px] text-[12.5px] text-[var(--meta)]">
          <Btn>上一页</Btn>
          <span>
            第 <b className="text-[var(--ink)] font-semibold">1</b> /{" "}
            <b className="text-[var(--ink)] font-semibold">1</b> 页 · 共{" "}
            <b className="text-[var(--ink)] font-semibold">3</b> 个
          </span>
          <Btn>下一页</Btn>
        </div>
      </Block>

      <Block
        title="特征索引文件（.index）"
        note="检索库可选；无 index 也能用"
        action={<Btn>绑定 index 文件…</Btn>}
      >
        <Group>
          <ListItem title="不用检索库（仅 .pth）" right={<Btn uw>使用</Btn>} />
          <ListItem
            title="added_IVF256_Flat_nprobe_1_Anon-local_v2.index"
            desc="当前音色目录"
            right={
              <Btn on uw disabled>
                使用中
              </Btn>
            }
          />
        </Group>
      </Block>

      <Block
        title="配置档案"
        note="同一个音色可存多套参数（音高／音效／性能），点「使用」即切换；可导出分享，也能导入别人调好的档案"
      >
        <Group>
          <ListItem
            meta="原始"
            title="默认（原始参数）"
            right={<Btn uw>使用</Btn>}
          />
          <ListItem
            meta="自建"
            title="开黑日常"
            desc="音高 +15 · 共鸣 1.20 · 相似度 0.86"
            right={
              <>
                <Btn on uw disabled>
                  使用中
                </Btn>
                <Btn>删除</Btn>
              </>
            }
          />
          <ListItem
            meta="官方优化"
            title="唱歌"
            desc="音高 +12 · 共鸣 0.80 · 相似度 0.91"
            right={
              <>
                <Btn uw>使用</Btn>
                <Btn>删除</Btn>
              </>
            }
          />
          <ListItem
            right={
              <>
                <Btn>另存当前为档案</Btn>
                <Btn>导入档案…</Btn>
                <Btn>导出当前档案（可分享）…</Btn>
              </>
            }
          />
        </Group>
      </Block>
    </PagePad>
  );
}
