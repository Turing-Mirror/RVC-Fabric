import { useEffect, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { RangeBar } from "./controls";
import { Btn } from "./ui";
import { t } from "../i18n/t";
import type { DspPreset } from "./DspPresetGrid";

type Specs = {
  order: string[];
  effects: Record<
    string,
    { params: Record<string, number>; ranges: Record<string, [number, number]> }
  >;
};

/** 效果器 / 参数 → 界面上叫什么。跟 tools/dsp_voice.py 的 EFFECT_SPECS 对齐。 */
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

const PARAM_LABEL: Record<string, string> = {
  semitones: "s.dspPSemitones",
  shift: "s.dspPShift",
  amount: "s.dspPAmount",
  freq: "s.dspPFreq",
  mix: "s.dspPMix",
  rate: "s.dspPRate",
  depth: "s.dspPDepth",
  voices: "s.dspPVoices",
  bits: "s.dspPBits",
  downsample: "s.dspPDownsample",
  low: "s.dspPLow",
  high: "s.dspPHigh",
  noise: "s.dspPNoise",
  time_ms: "s.dspPTimeMs",
  feedback: "s.dspPFeedback",
  size: "s.dspPSize",
};

/** 整数参数用 1 步长，其余按范围给一个够细的步长。 */
function stepFor(lo: number, hi: number, dflt: number): number {
  if (Number.isInteger(dflt) && Number.isInteger(lo) && Number.isInteger(hi)) return 1;
  const span = hi - lo;
  if (span <= 2) return 0.01;
  if (span <= 50) return 0.1;
  return 1;
}

function fmt(v: number, step: number): string {
  if (step >= 1) return String(Math.round(v));
  return v.toFixed(step >= 0.1 ? 1 : 2);
}

const ROW = "flex items-center gap-3 py-1.5";

/**
 * DSP 预设编辑器。
 *
 * 参数范围**不在这里写死** —— 由 configs/dsp_effects.json 提供，那份是从
 * 引擎侧 EFFECT_SPECS 生成的。壳自己抄一份的话，界面上能拉到的值引擎会静默
 * 钳回去，用户看到的和听到的对不上，而且从哪一侧都查不出原因。
 *
 * 排版沿用设置页那套「标签 + 推子 + 数值」的行，不引入新样式。
 */
export function DspPresetEditor({
  preset,
  onApply,
  onSaved,
}: {
  preset: DspPreset;
  /** 参数变了就实时推给引擎（热键，不重开流）。 */
  onApply: (params: DspPreset["params"]) => void;
  /** 存/删完之后让列表重新拉一次。 */
  onSaved: () => void;
}) {
  const [specs, setSpecs] = useState<Specs | null>(null);
  const [params, setParams] = useState<DspPreset["params"]>(preset.params);
  const [saveAs, setSaveAs] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setParams(preset.params);
    setSaveAs("");
    setMsg("");
  }, [preset.id, preset.params]);

  useEffect(() => {
    void invoke<Specs>("dsp_effects")
      .then(setSpecs)
      .catch(() => setSpecs({ order: [], effects: {} }));
  }, []);

  /** 只画这个预设用到的效果器 —— 十一个全铺开等于把人劝退。 */
  const shown = useMemo(() => {
    if (!specs) return [];
    return specs.order.filter((k) => k in params);
  }, [specs, params]);

  const setParam = (effect: string, key: string, v: number) => {
    const next = { ...params, [effect]: { ...params[effect], [key]: v } };
    setParams(next);
    onApply(next);
  };

  const save = async () => {
    const id = saveAs.trim().toLowerCase().replace(/[^a-z0-9_]/g, "_").slice(0, 48);
    if (!id) {
      setMsg(t("s.dspSaveNeedName"));
      return;
    }
    setBusy(true);
    try {
      await invoke("dsp_preset_save", { id, name: saveAs.trim(), params });
      setMsg(t("s.dspSaved", { v0: saveAs.trim() }));
      setSaveAs("");
      onSaved();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await invoke("dsp_preset_delete", { id: preset.id });
      setMsg("");
      onSaved();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!specs) return null;

  return (
    <div className="mt-6 pt-5 border-t border-[var(--hairline)]">
      <div className="flex items-center gap-3 mb-2">
        <h4 className="m-0 text-[14px] font-semibold">
          {t("s.dspEditTitle", { v0: preset.name })}
        </h4>
        {preset.source === "user" ? (
          <Btn className="ml-auto" disabled={busy} onClick={() => void remove()}>
            {t("s.dspDelete")}
          </Btn>
        ) : null}
      </div>
      <p className="m-0 mb-3 text-[12.5px] text-[var(--ink-muted)] leading-snug">
        {t("s.dspEditBlurb")}
      </p>

      {shown.map((effect) => {
        const spec = specs.effects[effect];
        if (!spec) return null;
        return (
          <div key={effect} className="mb-3">
            <div className="text-[12.5px] text-[var(--meta)] mb-0.5">
              {EFFECT_LABEL[effect] ? t(EFFECT_LABEL[effect]) : effect}
            </div>
            {Object.keys(spec.params).map((key) => {
              const [lo, hi] = spec.ranges[key] || [0, 1];
              const dflt = spec.params[key];
              const step = stepFor(lo, hi, dflt);
              const v = Number(params[effect]?.[key] ?? dflt);
              return (
                <div key={key} className={ROW}>
                  <span className="w-[86px] shrink-0 text-[13px]">
                    {PARAM_LABEL[key] ? t(PARAM_LABEL[key]) : key}
                  </span>
                  <div className="flex-1">
                    <RangeBar
                      value={v}
                      min={lo}
                      max={hi}
                      step={step}
                      defaultValue={dflt}
                      onChange={(nv) => setParam(effect, key, nv)}
                      ariaLabel={`${effect}.${key}`}
                    />
                  </div>
                  <span className="w-[56px] text-right text-[13px] tabular-nums">
                    {fmt(v, step)}
                  </span>
                </div>
              );
            })}
          </div>
        );
      })}

      <div className="flex items-center gap-2 mt-4">
        <input
          value={saveAs}
          onChange={(e) => setSaveAs(e.target.value)}
          placeholder={t("s.dspSaveAsPlaceholder")}
          className="min-w-[180px] px-[11px] py-[6px] rounded-[var(--rs)] text-[13px] text-[var(--ink)] bg-transparent shadow-[inset_0_0_0_1px_var(--line)] outline-none focus:shadow-[inset_0_0_0_1px_var(--accent)]"
        />
        <Btn disabled={busy || !saveAs.trim()} onClick={() => void save()}>
          {t("s.dspSaveAs")}
        </Btn>
        {msg ? (
          <span className="text-[12.5px] text-[var(--meta)] truncate">{msg}</span>
        ) : null}
      </div>
    </div>
  );
}
