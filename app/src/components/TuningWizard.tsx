import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Btn, HelpMark } from "./ui";
import { setHot } from "../lib/engine";
import { applyProfile, currentVoice } from "../lib/voices";
import { auditionVoice } from "../lib/audition";
import { t } from "../i18n/t";

/**
 * 效果调校向导：「变声结果不像目标音色？」
 *
 * 把 FAQ 那条「最常见原因是音高没调对」从文字升级成**用耳朵做选择题**：
 * 每一步先应用参数、再当场试听（voice_audition 用当前参数合成一句固定
 * 的话），用户只需要回答「哪个更接近」，不接触任何术语定义。
 *
 * 「恢复默认参数」在每一步都在：一键切回该音色的默认档案
 * （voices_profile_use 的 profile_id 为空串即默认档案），选砸了随时有退路。
 */
type Step = "intro" | "pitch" | "index" | "algo" | "done";

export function TuningWizard({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState<Step>("intro");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [modelDir, setModelDir] = useState("");
  const [pitch, setPitch] = useState(0);
  const [formant, setFormant] = useState(0);

  useEffect(() => {
    let alive = true;
    void currentVoice()
      .then((v) => {
        if (!alive) return;
        setModelDir(String((v.model as { dir?: string } | null)?.dir || ""));
        setPitch(Number(v.pitch ?? 0));
        setFormant(Number(v.formant ?? 0));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  // 应用参数到引擎（引擎没跑时静默失败——配置已写，下次开启生效）。
  const applyParams = useCallback(
    async (p: number, f: number) => {
      try {
        await setHot({ pitch: p, formant: f });
      } catch {
        /* worker 可能没跑 */
      }
      setPitch(p);
      setFormant(f);
    },
    [],
  );

  // 试听：复用 lib/audition 的通道（空路径 = 当前选中的音色，用当前参数）。
  const audition = async () => {
    if (busy) return;
    setBusy(true);
    setNote("");
    const err = await auditionVoice("");
    if (err) setNote(err);
    setBusy(false);
  };

  const resetDefaults = async () => {
    if (!modelDir) return;
    setBusy(true);
    try {
      const r = await applyProfile(modelDir, "");
      await applyParams(Number(r.pitch ?? 0), Number(r.formant ?? 0));
      setNote(t("s.twResetDone"));
    } catch (e) {
      setNote(String(e));
    } finally {
      setBusy(false);
    }
  };

  const close = () => {
    // 退出前把最终参数同步回配置档案（向导里改的是热参数；落盘由
    // 设置页的 useConfig 那条路负责，这里补一次以防向导是唯一改动方）。
    void invoke("config_set", { patch: { pitch, formant } }).catch(() => {});
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-[90] grid place-items-center p-6 bg-[color-mix(in_srgb,var(--ink)_28%,transparent)]"
      onClick={close}
    >
      <div
        className="w-full max-w-[560px] max-h-[82vh] overflow-auto rounded-[var(--r)] bg-[var(--surface)] p-5 shadow-[0_20px_60px_rgba(0,0,0,0.22)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 mb-1">
          <h3 className="m-0 text-[16px] font-semibold">{t("s.twTitle")}</h3>
          <Btn onClick={close}>{t("s.6c14bd7f6f")}</Btn>
        </div>
        <p className="m-0 mb-4 text-[12.5px] text-[var(--ink-muted)]">
          {t("s.twLead")}
        </p>

        {step === "intro" ? (
          <div className="flex flex-col gap-3">
            <p className="m-0 text-[13.5px] leading-relaxed">
              {t("s.twIntroQ")}
            </p>
            <div className="flex flex-col gap-2">
              <Btn onClick={() => setStep("pitch")}>{t("s.twIntroPitch")}</Btn>
              <Btn onClick={() => setStep("index")}>{t("s.twIntroIndex")}</Btn>
              <Btn onClick={() => setStep("algo")}>{t("s.twIntroAlgo")}</Btn>
            </div>
          </div>
        ) : null}

        {step === "pitch" ? (
          <div className="flex flex-col gap-3">
            <p className="m-0 text-[13.5px] leading-relaxed flex items-center gap-2">
              {t("s.twPitchQ")} <HelpMark title={t("s.d7f3306fcc")} />
            </p>
            <div className="flex items-center gap-2 flex-wrap">
              {[12, 0, -12].map((v) => (
                <Btn key={v} onClick={() => void applyParams(v, formant)}>
                  {v > 0 ? "+12" : v === 0 ? "0" : "-12"}
                </Btn>
              ))}
              <Btn primary disabled={busy} onClick={() => void audition()}>
                {busy ? t("s.auditionBusy") : t("s.lcMicRunAudition")}
              </Btn>
            </div>
            <p className="m-0 text-[12.5px] text-[var(--ink-muted)]">
              {t("s.twPitchAfter")}
            </p>
            <div className="flex items-center gap-2 flex-wrap mt-1">
              <Btn onClick={() => setStep("index")}>{t("s.twNext")}</Btn>
              <Btn disabled={busy} onClick={() => void resetDefaults()}>
                {t("s.twReset")}
              </Btn>
            </div>
          </div>
        ) : null}

        {step === "index" ? (
          <div className="flex flex-col gap-3">
            <p className="m-0 text-[13.5px] leading-relaxed flex items-center gap-2">
              {t("s.twIndexQ")} <HelpMark title={t("s.49e4ba4794")} />
            </p>
            <p className="m-0 text-[12.5px] text-[var(--ink-muted)]">
              {t("s.twIndexWhere")}
            </p>
            <div className="flex items-center gap-2 flex-wrap mt-1">
              <Btn onClick={() => setStep("done")}>{t("s.twNext")}</Btn>
              <Btn disabled={busy} onClick={() => void resetDefaults()}>
                {t("s.twReset")}
              </Btn>
            </div>
          </div>
        ) : null}

        {step === "algo" ? (
          <div className="flex flex-col gap-3">
            <p className="m-0 text-[13.5px] leading-relaxed flex items-center gap-2">
              {t("s.twAlgoQ")} <HelpMark title={t("s.ff175008d6")} />
            </p>
            <p className="m-0 text-[12.5px] text-[var(--ink-muted)]">
              {t("s.twAlgoWhere")}
            </p>
            <div className="flex items-center gap-2 flex-wrap mt-1">
              <Btn onClick={() => setStep("done")}>{t("s.twNext")}</Btn>
              <Btn disabled={busy} onClick={() => void resetDefaults()}>
                {t("s.twReset")}
              </Btn>
            </div>
          </div>
        ) : null}

        {step === "done" ? (
          <div className="flex flex-col gap-3">
            <p className="m-0 text-[13.5px] leading-relaxed">{t("s.twDone")}</p>
            <p className="m-0 text-[12.5px] text-[var(--ink-muted)]">
              {t("s.twDoneHint")}
            </p>
            <div className="flex items-center gap-2 flex-wrap">
              <Btn primary onClick={close}>
                {t("s.33246f6a5e")}
              </Btn>
              <Btn disabled={busy} onClick={() => void resetDefaults()}>
                {t("s.twReset")}
              </Btn>
            </div>
          </div>
        ) : null}

        {note ? (
          <p className="m-0 mt-3 text-[12.5px] text-[var(--meta)] break-all">
            {note}
          </p>
        ) : null}
      </div>
    </div>
  );
}
