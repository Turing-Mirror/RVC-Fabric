import { useEffect, useState, memo } from "react";
import { Btn, Block, PagePad } from "../components/ui";
import { setHot } from "../lib/engine";
import { listVoices, selectVoice, type VoiceModel } from "../lib/voices";
import { resolveCover, useCoverCache } from "../lib/cover";
import { openTool } from "../components/ToolWindow";
import emblem from "../assets/logo_ui.png";
import { t } from "../i18n/t";

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
 * 最近使用三卡封面边长：随窗口宽自适应。
 *
 * - 基准 = 默认窗宽（tauri `inner_size` 1180）下的 176 / 122
 * - 窗比默认更大 → 线性放大，**最大 +25%**（220 / 152.5）
 * - 窗比默认更小 → 沿用原来的 1020 / 720 两档收缩
 */
const DEFAULT_WIN_W = 1180;
const BASE_CUR = 176;
const BASE_SIDE = 122;
const BASE_FONT_CUR = 30;
const BASE_FONT_SIDE = 26;
const MAX_GROW = 0.25;

type RecentCardMetrics = {
  cur: number;
  side: number;
  fontCur: number;
  fontSide: number;
};

function recentCardMetrics(vw: number): RecentCardMetrics {
  // 窄窗：回到原先断点尺寸（略做连续插值，避免跳变）
  if (vw <= 720) {
    return { cur: 130, side: 92, fontCur: 22, fontSide: 19 };
  }
  if (vw <= 1020) {
    const t = (vw - 720) / (1020 - 720);
    const cur = Math.round(130 + t * (158 - 130));
    const side = Math.round(92 + t * (110 - 92));
    return {
      cur,
      side,
      fontCur: Math.round(BASE_FONT_CUR * (cur / BASE_CUR)),
      fontSide: Math.round(BASE_FONT_SIDE * (side / BASE_SIDE)),
    };
  }
  if (vw <= DEFAULT_WIN_W) {
    const t = (vw - 1020) / (DEFAULT_WIN_W - 1020);
    const cur = Math.round(158 + t * (BASE_CUR - 158));
    const side = Math.round(110 + t * (BASE_SIDE - 110));
    return {
      cur,
      side,
      fontCur: Math.round(BASE_FONT_CUR * (cur / BASE_CUR)),
      fontSide: Math.round(BASE_FONT_SIDE * (side / BASE_SIDE)),
    };
  }
  // 宽于默认窗：向「默认 × 1.25」爬，到屏幕可用宽为止
  const maxW = Math.max(
    DEFAULT_WIN_W + 1,
    typeof window !== "undefined" ? window.screen?.availWidth || 1920 : 1920,
  );
  const t = Math.min(1, (vw - DEFAULT_WIN_W) / (maxW - DEFAULT_WIN_W));
  const grow = 1 + MAX_GROW * t;
  return {
    cur: Math.round(BASE_CUR * grow),
    side: Math.round(BASE_SIDE * grow),
    fontCur: Math.round(BASE_FONT_CUR * grow),
    fontSide: Math.round(BASE_FONT_SIDE * grow),
  };
}

function useRecentCardMetrics(): RecentCardMetrics {
  const [m, setM] = useState<RecentCardMetrics>(() =>
    recentCardMetrics(
      typeof window !== "undefined" ? window.innerWidth : DEFAULT_WIN_W,
    ),
  );
  useEffect(() => {
    const onResize = () => setM(recentCardMetrics(window.innerWidth));
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return m;
}

/**
 * Brand mark in the hero band. Decorative, so no alt text and no pointer
 * target. Dropped below 720px, where it would land on top of the copy instead
 * of beside it.
 */
function HeroEmblem() {
  // 新竖向 LOGO 自带色（青字 + 黑底），不要套 dark 模式的 invert，否则会串色。
  return (
    <img
      src={emblem}
      alt=""
      aria-hidden
      draggable={false}
      className="pointer-events-none select-none absolute right-[30px] top-1/2 -translate-y-1/2 h-[112px] w-auto opacity-[var(--emblem-opacity)] max-[1020px]:right-[22px] max-[1020px]:h-[96px] max-[720px]:hidden"
    />
  );
}

/**
 * Home — stage band + 3 recent cards, current voice in the centre (larger).
 *
 * Recency comes from `recent_keys` (app_config `recent_models`), which
 * `voices_select` maintains — the same ordering the Tk shell used.
 */
function HomePageImpl({ currentId, onOpenModels, onVoiceChange }: Props) {
  const [models, setModels] = useState<VoiceModel[]>([]);
  const [recentKeys, setRecentKeys] = useState<string[]>([]);
  const [selectedIdx, setSelectedIdx] = useState(-1);
  // Distinguish "no voices installed" from "could not read the catalog" —
  // showing 「还没有本地音色」 after a failed call sends the user off to import
  // something they may already have.
  const [loadError, setLoadError] = useState("");
  const [msg, setMsg] = useState("");
  const cardPx = useRecentCardMetrics();
  // 封面本地化：已装第三方音色的远程封面走本地缓存（见 lib/cover.ts）。
  const coverCache = useCoverCache(
    models.map((m) => m.cover || "").filter(Boolean),
  );

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
      setMsg(t("s.314a72cba4"));
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
      setMsg(t("home.switchFail", { error: String(e) }));
    }
  };

  if (!current) {
    return (
      <div>
        <div className="relative overflow-hidden bg-[var(--stage)] px-[30px] pt-8 pb-7 max-[1020px]:px-[22px] max-[720px]:px-4">
          <h2 className="text-[27px] font-semibold tracking-tight m-0 mb-[15px] max-[860px]:text-2xl">{t("s.9d835868b4")}</h2>
          <p className="text-[12.5px] text-[var(--ink-muted)] m-0">
            {loadError
              ? t("s.c4a98bd0e6", { v0: loadError })
              : t("s.2a26295b90")}
          </p>
          <HeroEmblem />
        </div>
        <PagePad>
          <Block title={t("s.71265fc4cb")}>
            <div className="flex justify-center">
              <Btn onClick={onOpenModels}>{t("s.3c12966a8c")}</Btn>
            </div>
          </Block>
          <ToolShortcuts />
        </PagePad>
      </div>
    );
  }

  return (
    <div>
      <div className="relative overflow-hidden bg-[var(--stage)] px-[30px] pt-8 pb-7 max-[1020px]:px-[22px] max-[1020px]:pt-7 max-[1020px]:pb-6 max-[720px]:px-4 max-[720px]:pt-[22px] max-[720px]:pb-5">
        <h2 className="text-[27px] font-semibold tracking-tight m-0 mb-[15px] max-[860px]:text-2xl">{t("s.9d835868b4")}</h2>
        <p className="text-[19px] font-semibold text-[var(--accent)] m-0 mb-1.5">
          {current.name}
        </p>
        <p className="text-[12.5px] text-[var(--ink-muted)] m-0">
          {[current.tag, current.author ? t("s.7feea73fa3", { v0: current.author }) : ""]
            .filter(Boolean)
            .join(" · ")}
          {current.tag || current.author ? " · " : ""}
          {t("s.856b4d0ba9")}
        </p>
        <HeroEmblem />
      </div>

      <PagePad>
        <Block
          title={t("s.71265fc4cb")}
          action={<Btn onClick={onOpenModels}>{t("s.35e4afb47d")}</Btn>}
        >
          {msg ? (
            <p className="text-[12.5px] text-[#b8534f] m-0 mb-3">{msg}</p>
          ) : null}
          <div className="flex gap-5 items-center justify-center flex-wrap max-[520px]:flex-col max-[720px]:gap-3">
            {ordered.map((v) => {
              const cur = v === current;
              const edge = cur ? cardPx.cur : cardPx.side;
              const fontPx = cur ? cardPx.fontCur : cardPx.fontSide;
              return (
                <button
                  key={keyOf(v)}
                  type="button"
                  onClick={() => void pick(v)}
                  className="border-0 bg-transparent p-0 text-left cursor-pointer"
                >
                  <div
                    style={{ width: edge, fontSize: fontPx }}
                    className={[
                      "rounded-[var(--r)] grid place-items-center relative overflow-hidden",
                      // 只给宽度，高度交给 aspect-square。以前选中和未选中各写
                      // 一组 w/h，三个断点下算出六种不同的长宽比 —— 同一张图在
                      // 选中前后、拉窗口前后被裁掉的部分都不一样，看着就像图在
                      // 乱缩放。比例由结构保证，就不会再飘。
                      "aspect-square",
                      "bg-[color-mix(in_srgb,var(--ink)_7%,transparent)]",
                      "text-[color-mix(in_srgb,var(--ink)_32%,transparent)]",
                      // 封面按原色显示。以前未选中的一律去色、选中才恢复，
                      // 那是拿画师的画当状态指示器用 —— 选中状态由描边和尺寸
                      // 表达就够了。
                      "transition-[width,font-size,transform,box-shadow] duration-300 ease-[var(--spring)]",
                      "active:scale-[0.985]",
                      cur
                        ? "shadow-[inset_0_0_0_1.5px_color-mix(in_srgb,var(--ink)_26%,transparent)]"
                        : "",
                    ].join(" ")}
                  >
                    {v.cover ? (
                      <img
                        src={resolveCover(v.cover, coverCache)}
                        alt=""
                        draggable={false}
                        // contain 而不是 cover：官方封面全是 1:1，在方形框里
                        // 两者结果一样、都不裁；第三方是竖图（最极端 0.395），
                        // cover 会切掉七成。宁可两边留出底色，也别把人裁没。
                        className="absolute inset-0 w-full h-full object-contain"
                      />
                    ) : (
                      <span>{(v.name || "?").slice(0, 4)}</span>
                    )}
                    {cur ? (
                      <span className="absolute top-2.5 right-2.5 text-[11px] text-[var(--accent)]">{t("s.e6aa2cbd7b")}</span>
                    ) : null}
                    {v.has_index ? (
                      <span className="absolute right-2.5 bottom-2 text-[11px] text-[var(--meta)]">{t("s.ec673c54d6")}</span>
                    ) : null}
                  </div>
                  <div className="text-[11.5px] text-[var(--meta)] mt-3">
                    {v.tag || t("s.c4301894a2")}
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
                    {v.author ? t("s.7feea73fa3", { v0: v.author }) : "\u00a0"}
                  </div>
                </button>
              );
            })}
          </div>
        </Block>
        <ToolShortcuts />
      </PagePad>
    </div>
  );
}

/**
 * 首页底下那三个直达按钮。
 *
 * 这三件事以前只有一条路：「其他」页 → 往下翻到「音频工具」→ 点「打开」。
 * 分离 → 训练 → 合成是同一条「做音色」的链路，放在最近使用的正下方。
 * 下载模型仍在「其他」页，不占首页入口。
 */
function ToolShortcuts() {
  const items: Array<{ label: string; desc: string; go: () => void }> = [
    {
      label: t("s.8fd038283b"),
      desc: t("s.2d5f93d547"),
      go: () => openTool("separate"),
    },
    {
      label: t("s.ba65bd5595"),
      desc: t("s.30e91c9e4d"),
      go: () => openTool("train"),
    },
    {
      label: t("s.6f311c47fe"),
      desc: t("s.3bf3d98458"),
      go: () => openTool("tts"),
    },
  ];
  return (
    <Block title={t("s.21093d185d")}>
      <div className="flex gap-3 flex-wrap max-[520px]:flex-col">
        {items.map((it) => (
          <button
            key={it.label}
            type="button"
            onClick={it.go}
            className={[
              "flex-1 min-w-[180px] text-left border-0 cursor-pointer",
              "rounded-[var(--r)] px-4 py-3.5",
              "bg-[color-mix(in_srgb,var(--ink)_4%,transparent)]",
              "transition-[transform,background] duration-200 ease-[var(--ease)]",
              "hover:bg-[color-mix(in_srgb,var(--ink)_7%,transparent)]",
              "active:scale-[0.985]",
            ].join(" ")}
          >
            <div className="text-[13.5px] font-semibold text-[var(--ink)]">
              {it.label}
            </div>
            <div className="text-[12px] text-[var(--meta)] mt-1">{it.desc}</div>
          </button>
        ))}
      </div>
    </Block>
  );
}

/**
 * Memoised: App re-renders on every engine status tick (2.5x a second while
 * converting). Without this the whole page tree was rebuilt each time for a
 * mic-level change that only the dock cares about.
 */
export const HomePage = memo(HomePageImpl);
