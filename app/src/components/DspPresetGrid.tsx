import { useEffect, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Btn } from "./ui";
import { t } from "../i18n/t";

/** 一条预设。参数的合法范围由引擎侧 dsp_voice.EFFECT_SPECS 定义，壳不重复一份。 */
export type DspPreset = {
  id: string;
  name: string;
  desc?: string;
  params: Record<string, Record<string, number>>;
  source?: "builtin" | "user";
};

/** 效果器 id → 界面上叫什么。跟 tools/dsp_voice.py 的 EFFECT_SPECS 对齐。 */
const EFFECT_LABEL: Record<string, string> = {
  pitch: "s.dspFxPitch",
  formant: "s.dspFxFormant",
  whisper: "s.dspFxWhisper",
  ring: "s.dspFxRing",
  vibrato: "s.dspFxVibrato",
  chorus: "s.dspFxChorus",
  bitcrush: "s.dspFxBitcrush",
  drive: "s.dspFxDrive",
  radio: "s.dspFxRadio",
  echo: "s.dspFxEcho",
  reverb: "s.dspFxReverb",
};

function effectNames(p: DspPreset): string {
  return Object.keys(p.params || {})
    .map((k) => (EFFECT_LABEL[k] ? t(EFFECT_LABEL[k]) : k))
    .join(" · ");
}

/**
 * DSP 预设网格。
 *
 * 卡片排版照搬模型页的音色卡：同一个页面里两种列表长得不一样，用户会以为
 * 自己进错地方了。区别只在封面位置 —— 预设没有立绘，画的是它用到哪几个
 * 效果器，那正是用户想知道的「这个预设会把我变成什么样」。
 */
export function DspPresetGrid({
  cols,
  query,
  activeId,
  onUse,
  onStop,
  busy,
}: {
  cols: number;
  query: string;
  /** 当前生效的预设 id；空串表示 DSP 没开。 */
  activeId: string;
  onUse: (p: DspPreset) => void;
  onStop: () => void;
  busy?: boolean;
}) {
  const [list, setList] = useState<DspPreset[] | null>(null);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    let alive = true;
    void invoke<{ presets: DspPreset[] }>("dsp_presets")
      .then((r) => {
        if (alive) setList(r.presets || []);
      })
      .catch((e) => {
        if (alive) {
          setList([]);
          setMsg(String(e));
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  const view = useMemo(() => {
    const q = query.trim().toLowerCase();
    const all = list || [];
    if (!q) return all;
    return all.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.id.includes(q) ||
        (p.desc || "").toLowerCase().includes(q),
    );
  }, [list, query]);

  if (list == null) {
    return (
      <div className="text-[13.5px] text-[var(--ink-muted)] py-10 px-2">
        {t("s.dspPresetsLoading")}
      </div>
    );
  }
  if (msg) {
    return <div className="text-[12.5px] text-[var(--meta)] py-6 px-2">{msg}</div>;
  }
  if (!view.length) {
    return (
      <div className="text-[13.5px] text-[var(--ink-muted)] py-10 px-2">
        {query ? t("s.041c85897b", { v0: query }) : t("s.dspNoPresets")}
      </div>
    );
  }

  return (
    <div
      className="grid gap-x-4 gap-y-[22px]"
      style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
    >
      {view.map((p) => {
        const cur = p.id === activeId;
        return (
          <div key={p.id}>
            <div className="aspect-[4/3] rounded-[var(--r)] relative overflow-hidden bg-[color-mix(in_srgb,var(--ink)_7%,transparent)] p-3.5 flex flex-col justify-end">
              {/* 预设没有立绘，画它用到哪几个效果器 —— 那才是用户想知道的 */}
              <div className="text-[12px] text-[var(--ink-muted)] leading-relaxed line-clamp-4">
                {effectNames(p)}
              </div>
              {cur ? (
                <span className="absolute top-2.5 right-2.5 text-[11px] text-[var(--accent)] font-semibold">
                  {t("s.e6aa2cbd7b")}
                </span>
              ) : null}
              {p.source === "user" ? (
                <span className="absolute left-2.5 top-2.5 text-[11px] text-[var(--meta)]">
                  {t("s.dspPresetMine")}
                </span>
              ) : null}
            </div>
            <div className="text-[11.5px] text-[var(--meta)] mt-2.5">
              {t("s.dspPresetTag")}
            </div>
            <div className="text-[14.5px] font-semibold mt-0.5 truncate">{p.name}</div>
            <div className="text-xs text-[var(--meta)] mt-0.5 truncate">
              {p.desc || ""}
            </div>
            <div className="mt-2.5 flex items-center gap-1.5">
              {cur ? (
                <Btn uw disabled={busy} onClick={onStop}>
                  {t("s.dspPresetStop")}
                </Btn>
              ) : (
                <Btn uw disabled={busy} onClick={() => onUse(p)}>
                  {t("s.0e2d3a3c09")}
                </Btn>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
