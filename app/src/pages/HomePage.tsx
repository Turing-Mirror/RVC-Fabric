import { Btn, Block, PagePad } from "../components/ui";

type Voice = {
  id: string;
  name: string;
  tag: string;
  author: string;
  hasIndex?: boolean;
};

const DEMO: Voice[] = [
  { id: "soyo", name: "Soyo", tag: "少女音", author: "望月星逸", hasIndex: true },
  { id: "anon", name: "Anon", tag: "少女音", author: "望月星逸", hasIndex: true },
  { id: "rana", name: "Rana", tag: "少女音", author: "望月星逸", hasIndex: true },
];

type Props = {
  currentId?: string;
  onOpenModels?: () => void;
  onSelect?: (id: string) => void;
};

/**
 * Home — stage band + 3 recent cards with current in C position (center, larger).
 * Demo data only until catalog is wired (stage 4).
 */
export function HomePage({
  currentId = "anon",
  onOpenModels,
  onSelect,
}: Props) {
  const current = DEMO.find((v) => v.id === currentId) ?? DEMO[1];
  // C-position layout: left · current(center) · right
  const others = DEMO.filter((v) => v.id !== current.id);
  const ordered = [others[0], current, others[1]].filter(Boolean) as Voice[];

  return (
    <div>
      <div className="bg-[var(--stage)] px-[30px] pt-8 pb-7 max-[1020px]:px-[22px] max-[1020px]:pt-7 max-[1020px]:pb-6 max-[720px]:px-4 max-[720px]:pt-[22px] max-[720px]:pb-5">
        <h2 className="text-[27px] font-semibold tracking-tight m-0 mb-[15px] max-[860px]:text-2xl">
          选择音色，开始变声
        </h2>
        <p className="text-[19px] font-semibold text-[var(--accent)] m-0 mb-1.5">
          {current.name}
        </p>
        <p className="text-[12.5px] text-[var(--ink-muted)] m-0">
          {current.tag} · {current.author} · 260723 · 切换立即生效 · 运行中会自动重载
        </p>
        {/* Right-side brand logo slot intentionally empty */}
      </div>

      <PagePad>
        <Block
          title="最近使用"
          action={<Btn onClick={onOpenModels}>全部音色</Btn>}
        >
          <div className="flex gap-5 items-center justify-center flex-wrap max-[520px]:flex-col max-[720px]:gap-3">
            {ordered.map((v) => {
              const cur = v.id === current.id;
              return (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => onSelect?.(v.id)}
                  className="border-0 bg-transparent p-0 text-left cursor-pointer"
                >
                  <div
                    className={[
                      "rounded-[var(--r)] grid place-items-center relative",
                      "bg-[color-mix(in_srgb,var(--ink)_7%,transparent)]",
                      "text-[color-mix(in_srgb,var(--ink)_32%,transparent)]",
                      "grayscale transition-[filter,transform,box-shadow] duration-300 ease-[var(--spring)]",
                      "hover:grayscale-[0.3] hover:-translate-y-1 active:translate-y-px active:scale-[0.985]",
                      cur
                        ? "w-[236px] h-[176px] text-[30px] grayscale-0 shadow-[inset_0_0_0_1.5px_color-mix(in_srgb,var(--ink)_26%,transparent)] max-[1020px]:w-[208px] max-[1020px]:h-[158px] max-[720px]:w-[170px] max-[720px]:h-[130px]"
                        : "w-[156px] h-[122px] text-[26px] max-[1020px]:w-[138px] max-[1020px]:h-[110px] max-[720px]:w-[112px] max-[720px]:h-[92px]",
                    ].join(" ")}
                  >
                    {v.name}
                    {cur ? (
                      <span className="absolute top-2.5 right-2.5 text-[11px] text-[var(--accent)]">
                        使用中
                      </span>
                    ) : null}
                    {v.hasIndex ? (
                      <span className="absolute right-2.5 bottom-2 text-[11px] text-[var(--meta)]">
                        ✓ 检索库
                      </span>
                    ) : null}
                  </div>
                  <div className="text-[11.5px] text-[var(--meta)] mt-3">{v.tag}</div>
                  <div
                    className={[
                      "font-semibold mt-0.5 leading-snug",
                      cur ? "text-[14.5px]" : "text-[13.5px]",
                    ].join(" ")}
                  >
                    {v.name}
                  </div>
                  <div className="text-xs text-[var(--meta)] mt-0.5">
                    作者 · {v.author}
                  </div>
                </button>
              );
            })}
          </div>
        </Block>
      </PagePad>
    </div>
  );
}
