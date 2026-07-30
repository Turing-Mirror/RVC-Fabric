import { useEffect, useState } from "react";
import { Btn, Block, PagePad } from "../components/ui";
import { setHot } from "../lib/engine";
import { coverSrc, listVoices, selectVoice, type VoiceModel } from "../lib/voices";

type Props = {
  currentId?: string;
  onOpenModels?: () => void;
  /** Same payload the models page reports, so the dock agrees either way. */
  onVoiceChange?: (info: {
    model: VoiceModel;
    pitch?: number;
    formant?: number;
    profileSummary?: string;
  }) => void;
};

const keyOf = (m: VoiceModel) => m.dir || m.path || m.name;

/**
 * Home — stage band + 3 recent cards, current voice in the centre (larger).
 *
 * Recency comes from `recent_keys` (app_config `recent_models`), which
 * `voices_select` maintains — the same ordering the Tk shell used.
 */
export function HomePage({ currentId, onOpenModels, onVoiceChange }: Props) {
  const [models, setModels] = useState<VoiceModel[]>([]);
  const [recentKeys, setRecentKeys] = useState<string[]>([]);
  const [selectedIdx, setSelectedIdx] = useState(-1);
  // Distinguish "no voices installed" from "could not read the catalog" —
  // showing 「还没有本地音色」 after a failed call sends the user off to import
  // something they may already have.
  const [loadError, setLoadError] = useState("");
  const [msg, setMsg] = useState("");

  const load = async () => {
    try {
      const cat = await listVoices();
      setModels(cat.models || []);
      setSelectedIdx(Number(cat.selected_idx ?? -1));
      const rk = (cat as unknown as { recent_keys?: unknown }).recent_keys;
      setRecentKeys(Array.isArray(rk) ? rk.map(String) : []);
      setLoadError("");
    } catch (e) {
      setModels([]);
      setLoadError(String(e));
    }
  };
  useEffect(() => {
    void load();
  }, [currentId]);

  const current =
    (selectedIdx >= 0 ? models[selectedIdx] : undefined) ?? models[0];

  // Most-recent first, current excluded — it always takes the centre slot.
  const rest = [...models]
    .filter((m) => m !== current)
    .sort((a, b) => {
      const ia = recentKeys.indexOf(keyOf(a));
      const ib = recentKeys.indexOf(keyOf(b));
      return (ia < 0 ? 1e9 : ia) - (ib < 0 ? 1e9 : ib);
    });
  const ordered = current
    ? ([rest[0], current, rest[1]].filter(Boolean) as VoiceModel[])
    : [];

  const pick = async (m: VoiceModel) => {
    if (m.missing) {
      setMsg("这个音色的模型文件缺失或没下载完整");
      return;
    }
    try {
      setMsg("");
      const res = await selectVoice({ path: m.path, dir: m.dir, name: m.name });
      // Picking here used to only record the selection: the voice's saved
      // pitch / formant were never pushed to a running stream and the dock kept
      // showing the previous voice's name and numbers. Same handling as the
      // models page now.
      if (res.pitch != null || res.formant != null) {
        try {
          await setHot({
            pitch: Number(res.pitch ?? 0),
            formant: Number(res.formant ?? 0),
          });
        } catch {
          /* worker may be idle */
        }
      }
      onVoiceChange?.({
        model: (res.model as VoiceModel) || m,
        pitch: res.pitch as number | undefined,
        formant: res.formant as number | undefined,
        profileSummary: res.profile_summary,
      });
      await load();
    } catch (e) {
      // Clicking a card and having nothing happen is the worst outcome.
      setMsg(`切换失败：${String(e)}`);
    }
  };

  if (!current) {
    return (
      <div>
        <div className="bg-[var(--stage)] px-[30px] pt-8 pb-7 max-[1020px]:px-[22px] max-[720px]:px-4">
          <h2 className="text-[27px] font-semibold tracking-tight m-0 mb-[15px] max-[860px]:text-2xl">
            选择音色，开始变声
          </h2>
          <p className="text-[12.5px] text-[var(--ink-muted)] m-0">
            {loadError
              ? `读取音色目录失败：${loadError}`
              : "还没有本地音色。到「模型」页导入，或从社区音色下载。"}
          </p>
        </div>
        <PagePad>
          <Block title="最近使用">
            <div className="flex justify-center">
              <Btn onClick={onOpenModels}>去「模型」页</Btn>
            </div>
          </Block>
        </PagePad>
      </div>
    );
  }

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
          {[current.tag, current.author ? `作者 · ${current.author}` : ""]
            .filter(Boolean)
            .join(" · ")}
          {current.tag || current.author ? " · " : ""}
          切换立即生效 · 运行中会自动重载
        </p>
        {/* Right-side brand logo slot intentionally empty */}
      </div>

      <PagePad>
        <Block
          title="最近使用"
          action={<Btn onClick={onOpenModels}>全部音色</Btn>}
        >
          {msg ? (
            <p className="text-[12.5px] text-[#b8534f] m-0 mb-3">{msg}</p>
          ) : null}
          <div className="flex gap-5 items-center justify-center flex-wrap max-[520px]:flex-col max-[720px]:gap-3">
            {ordered.map((v) => {
              const cur = v === current;
              return (
                <button
                  key={keyOf(v)}
                  type="button"
                  onClick={() => void pick(v)}
                  className="border-0 bg-transparent p-0 text-left cursor-pointer"
                >
                  <div
                    className={[
                      "rounded-[var(--r)] grid place-items-center relative",
                      "bg-[color-mix(in_srgb,var(--ink)_7%,transparent)]",
                      "text-[color-mix(in_srgb,var(--ink)_32%,transparent)]",
                      "grayscale transition-[filter,transform,box-shadow] duration-300 ease-[var(--spring)]",
                      "hover:grayscale-[0.3] active:scale-[0.985]",
                      cur
                        ? "w-[236px] h-[176px] text-[30px] grayscale-0 shadow-[inset_0_0_0_1.5px_color-mix(in_srgb,var(--ink)_26%,transparent)] max-[1020px]:w-[208px] max-[1020px]:h-[158px] max-[720px]:w-[170px] max-[720px]:h-[130px]"
                        : "w-[156px] h-[122px] text-[26px] max-[1020px]:w-[138px] max-[1020px]:h-[110px] max-[720px]:w-[112px] max-[720px]:h-[92px]",
                    ].join(" ")}
                  >
                    {v.cover ? (
                      <img
                        src={coverSrc(v.cover)}
                        alt=""
                        className="absolute inset-0 w-full h-full object-cover rounded-[var(--r)]"
                      />
                    ) : (
                      <span>{(v.name || "?").slice(0, 4)}</span>
                    )}
                    {cur ? (
                      <span className="absolute top-2.5 right-2.5 text-[11px] text-[var(--accent)]">
                        使用中
                      </span>
                    ) : null}
                    {v.has_index ? (
                      <span className="absolute right-2.5 bottom-2 text-[11px] text-[var(--meta)]">
                        ✓ 检索库
                      </span>
                    ) : null}
                  </div>
                  <div className="text-[11.5px] text-[var(--meta)] mt-3">
                    {v.tag || "音色"}
                  </div>
                  <div
                    className={[
                      "font-semibold mt-0.5 leading-snug",
                      cur ? "text-[14.5px]" : "text-[13.5px]",
                    ].join(" ")}
                  >
                    {v.name}
                  </div>
                  <div className="text-xs text-[var(--meta)] mt-0.5">
                    {v.author ? `作者 · ${v.author}` : "\u00a0"}
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
